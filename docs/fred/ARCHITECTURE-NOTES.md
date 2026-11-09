# OpenLogi architecture notes (Fred's map)

Personal notes on the `fred/notes` branch, not upstream docs. Every `path:line`
reference is pinned to **master `6466cd2`** (2026-11-04, just after v0.9.0).
Line numbers drift; if one is off by a few lines, search for the named item.
`crates/` is omitted from paths below where obvious (`openlogi-hid/src/…` means
`crates/openlogi-hid/src/…`).

Where a Rust idiom actually matters to understanding the code, there's a short
"Rust note". Everything else assumes you read code fluently.

---

## 1. The crate map, and the one rule that explains it

The single most useful sentence about this codebase: **only the agent process
touches hardware.** The GUI (`openlogi-desktop`) and the Actions Ring overlay
(`openlogi-overlay`) are pure IPC clients. The CLI is the one diagnostic
exception — `openlogi list` prefers the agent's snapshot and falls back to
direct enumeration; `openlogi diag …` opens devices directly.

The layering, bottom to top:

| Layer | Crate | What it knows |
|---|---|---|
| protocol | `openlogi-hidpp` (lib name `hidpp`) | HID++ 1.0/2.0 messages, the feature registry, the request/response channel. No OS, no async runtime of its own (it builds for wasm). |
| device logic | `openlogi-device` | Enumeration, probing, writes, capture sessions — expressed against an abstract `HidBackend` trait, so it also knows no OS. Also wasm-clean. |
| host wiring | `openlogi-hid` | The real `HidBackend`: `async-hid` transports per OS, macOS Input Monitoring, the on-disk probe cache. |
| shared types | `openlogi-core` | Config (TOML), device model, action catalog. Pure — no I/O unless a feature flag adds it. |
| orchestration | `openlogi-agent-core` | Watchers, the orchestrator, action dispatch. |
| the server | `openlogi-agent` | The binary: lifecycle, IPC server, tray, autostart. |
| IPC contract | `openlogi-ipc` | The tarpc service + socket transport, shared by agent and every client. |
| OS input | `openlogi-hook` / `openlogi-inject` | Capture (CGEventTap / evdev / `WH_MOUSE_LL`) and synthesis (CGEvent / uinput / `SendInput`). |
| clients | `openlogi-desktop`, `openlogi-overlay`, `openlogi-cli` | UI and CLI. |

Why the split between `openlogi-device` and `openlogi-hid` matters to you: almost
all device behaviour can be tested on Linux with fake backends (replay tests,
fixtures), and only the thin `openlogi-hid/src/transport/windows.rs` layer is
truly Windows-only.

> **Rust note — `cfg` gating.** `#[cfg(target_os = "windows")]` removes code at
> compile time on other OSes, so code inside it is *never compiled* on Linux CI.
> That's why the repo insists "macOS/Linux-green proves nothing for Windows
> code" (`.agents/rules/cross-platform.md`). `cfg!(target_os = "macos")` (with
> `!`) is different: a compile-time boolean used in ordinary `if`s; both branches
> still type-check everywhere.

---

## 2. Processes and IPC

### Who starts whom

- **Agent** entry: `openlogi-agent/src/main.rs:52`. It takes a single-instance
  lock (`agent.lock`) at `main.rs:66`; if another agent holds it,
  `takeover::try_replace_stale()` (`main.rs:76`) asks the holder its protocol
  version and replaces it only if provably older.
- The agent's life is a **typestate** chain in `openlogi-agent/src/lifecycle.rs`:
  `run` (:62) → `Booted` → `gate` (macOS waits for a GUI to declare itself;
  elsewhere it passes straight through) → `Wanted::arm` (:216) → `Armed::run`
  (:306). `startup::bootstrap` (`startup.rs:51`) builds the orchestrator and
  starts the IPC server *before* arming, so clients can connect early.
- **Overlay** is launched by the agent when arming (`overlay::spawn()`,
  called from `lifecycle.rs:230`, defined `overlay.rs:25`).
- **GUI** connects as a client; if the agent is unreachable, it spawns one
  (`openlogi-desktop/src/services/ipc/launch.rs:31`). The GUI has its own lock,
  which is why a second GUI exits silently on Windows.
- **Windows extras:** autostart is the `HKCU\…\Run\OpenLogiAgent` value
  (`openlogi-agent/src/autostart/windows.rs`); sleep/wake comes from
  `RegisterSuspendResumeNotification` (`openlogi-agent/src/resume_windows.rs:36`),
  which suspends/resumes all device I/O through the `DeviceIoGate` (§6); the
  tray runs on its own Win32 thread (`tray_windows.rs`).

> **Rust note — typestate.** `fn arm(self) -> Armed` *consumes* the old stage
> (`self` by value), so after arming, the `Wanted` value no longer exists and
> can't be armed twice. The compiler enforces the lifecycle order; there's no
> runtime "state" enum to get wrong. You'll see this pattern repeatedly.

### The IPC contract

- The service is one Rust trait, `#[tarpc::service] trait Agent`
  (`openlogi-ipc/src/ipc.rs:925`). tarpc turns it into a client stub and a server
  trait; messages are bincode over an `interprocess` local socket — a Unix socket
  on macOS/Linux, a **named pipe on Windows** (`openlogi-ipc/src/transport.rs:34`).
- **Versioning:** `PROTOCOL_VERSION = 45` (`ipc.rs:184`). Clients never compare
  numbers themselves: they call `client::connect_as(kind)` (`client.rs:134`),
  which does connect → version check → `declare_client` within a 2 s
  `HANDSHAKE_TIMEOUT` (:69) and returns `ConnectError::Skew` on mismatch. That's
  the repo's "single source of truth" rule in action.
- **The wire is append-only**: methods and enum variants are encoded by
  position, so new ones go at the end, and the version moves once per release
  (`crates/openlogi-ipc/AGENTS.md`).
- **How the GUI stays fresh:** not polling. `observe(since)` (`ipc.rs:1043`) is a
  long-poll: the agent answers as soon as its generation counter moves
  (`openlogi-agent-core/src/observable.rs:129`), or after `OBSERVE_HOLD` = 20 s
  (`ipc.rs:606`) with no change. Each answer is a whole `AgentSnapshot`
  (`ipc.rs:288`), never a delta.
- **Config changes** flow GUI → file → agent: the GUI saves `config.toml`, then
  calls `reload_saved_config` (`ipc.rs:1120`), and the agent rebuilds.

---

## 3. The device seam

- `HidBackend` (`openlogi-device/src/backend.rs:172`) is the trait the whole
  device layer is written against: `enumerate`, `enumerate_hidpp`, `open_hidpp`
  (returns an `Arc<HidppChannel>`), `open_raw_writer` (Litra lights), `watch`.
- The only real implementation is `NativeBackend`
  (`openlogi-hid/src/transport/native.rs:81`), a process-wide singleton that
  caches OS handles from the last enumeration.
- **Which HID interfaces count as HID++** is a table, `HIDPP_LONG_COLLECTIONS`
  (`openlogi-hid/src/transport.rs:239`), checked by `is_hidpp_candidate` (:356).
  The keypad's entry is `0xFF43/0x1A02`. Each opened channel leases a HID++
  software ID 1–15 per device node (`try_lease_sw_id`, :429), so several
  processes (agent + `openlogi diag`) can't confuse each other's replies.
- `open_hidpp_channel_inner` (`transport.rs:504`) forks per OS: Windows builds a
  `WindowsHidppChannel`; macOS/Linux use one `AsyncHidChannel` per device.

> **Rust note — `Arc<dyn Trait>`.** `Arc` is a thread-safe reference-counted
> pointer (like a shared object reference in JS); `dyn Trait` means "some type
> implementing this trait, chosen at runtime". `HidppChannel` holds an
> `Arc<dyn RawHidChannel>` (`openlogi-hidpp/src/channel/raw.rs:42`), so the
> protocol code works identically over the Windows composite channel, the
> macOS/Linux channel, and test fakes.

---

## 4. The Windows transport (`openlogi-hid/src/transport/windows.rs`)

The core Windows fact: **Windows splits one USB HID device into one handle per
top-level collection, and each handle accepts only the reports its collection
declares.** Write the wrong report to the wrong handle → `ERROR_INVALID_FUNCTION`.
That was [#2281](https://github.com/AprilNEA/OpenLogi/issues/2281).

Your keypad (`046d:c354`) as Windows sees it:

| Windows | Usage | Reports | Role |
|---|---|---|---|
| COL01 | `0xFF43/0x1A02` | HID++ (0x11, 20 bytes) | HID++ requests/replies |
| COL02 | `0xFF43/0x1A08` | 0x13, 32 bytes in/out | grid-key presses, image acks |
| COL03 | `0xFF43/0x1A10` | 0x14, 4095 bytes out | LCD images |
| COL04 | `0x0001/0x0080` | system control | (OS-owned) |
| COL05 | `0x000C/0x0001` | consumer control | (OS-owned) |

How `WindowsHidppChannel` (`windows.rs:304`, opened by `open` at :324) stitches
COL01–03 back into one logical channel:

1. **Find the siblings.** `interface_siblings` (:437) re-enumerates and groups
   collections whose paths match after `normalize_collection_path` (:519) strips
   the `&ColNN` part and the trailing instance segment — so two identical
   keypads are never cross-paired.
2. **Short collection** (`short_collection`, :453): the `FF00/0001` 7-byte HID++
   collection if the device has one. The keypad doesn't.
3. **Vendor collections** (`open_vendor_collections`, :479). Which report a
   vendor collection carries is derived from its usage: on page `FF43`, the low
   byte of the usage is a bitmask where bit *n* means report `0x10+n`
   (`vendor_report_id`, :98) — `0x1A08` → `0x13`, `0x1A10` → `0x14`. Report
   lengths come from `HidP_GetCaps` (`windows_hid.rs:86`).
4. **Writes are routed by report ID**: `endpoint_for_report_id` (:49) — `0x10`
   to the short collection, a vendor report ID to its vendor collection,
   everything else to the long HID++ collection. `writer_for` (:395) returns
   "unsupported" if that collection is missing or has no output report.
5. **Reads are a race**: `read_report` (:561) races all readers with
   `read_first` (:128) and takes whichever produces a report first. Losing reads
   are dropped — safe only because async-hid's overlapped I/O buffer survives
   the drop, which is why readers are opened once and never reopened per read.
6. **Write fallback**: `ReportWriter::write_report` (:178) tries async-hid; on a
   non-disconnect error it falls back to `NativeHidWriter`
   (`windows_hid.rs:25`), which tries `WriteFile`, then `HidD_SetOutputReport`,
   then `HidD_SetFeature` (`try_write_methods`, `windows_hid.rs:112`).

> **Rust note — async drop-cancellation.** In Rust, dropping a future cancels it
> at its last `.await`. That's how "race N reads, keep the winner" works without
> explicit cancel calls — and why the comment about the overlapped buffer
> surviving the drop is load-bearing. The same property is behind [#2322](https://github.com/AprilNEA/OpenLogi/pull/2322)'s second
> commit (§5).

`windows.rs` is compiled under `cfg(any(windows, test))` (`transport.rs:202`), so
its pure helpers (routing, path normalisation) have unit tests that run on
Linux; the actual Win32 calls only compile on Windows.

---

## 5. The HID++ channel (`openlogi-hidpp/src/channel.rs`)

`HidppChannel` (:266) wraps the raw channel and owns a dedicated read thread
(spawned at :389) running `read_loop` (:805).

**Sending a request** — `send` (:505) → `send_with` (:551):

1. The request's *correlation key* is `(device index, feature index,
   function|swid)` (`channel/pending.rs:30`). Replies don't carry request IDs, so
   this triple is the only way to match a reply.
2. `PendingRequest::register_when_key_free` (`pending.rs:241`) **parks** the
   request while another request with the same key is in flight, or while an
   abandoned request's reply might still arrive (the stale grace,
   `STALE_REPLY_GRACE` = 1 s, `channel.rs:104`). Otherwise a late reply to
   request A could be mistaken for request B's answer.
3. The report is written; the caller races the reply against
   `SEND_RESPONSE_TIMEOUT` = **5 s** (`channel.rs:82`). That 5 s is exactly the
   gap you saw in [#2281](https://github.com/AprilNEA/OpenLogi/issues/2281) between the lost `getFeature` and `Channel(Timeout)`.
4. If the caller gives up (timeout or drop), the request is *abandoned*
   (`abandon`, `pending.rs:131`) and its key stays reserved for the grace period.

**Receiving** — `read_loop` (:805), per report: raw listeners first (:772 —
this is how the keypad's non-HID++ `0x13` reports are observed); then, if it
parses as HID++, match the oldest pending request whose predicate accepts it,
or log it as stale; then message listeners (notifications, diverted buttons).
Non-HID++ reports log as `report not HID++ — dropped` with up to 16 payload
bytes; HID++ ones as `raw report received … payload=[…]` (:911).

**Raw writes** (`write_raw_report`, :704, up to 4095 bytes, :77) bypass all of
the above: no key, no reply matching. Keypad images use them.

### The [#2322](https://github.com/AprilNEA/OpenLogi/pull/2322) delta (not on master yet; local ref `pr-2322`)

`git diff master...pr-2322` — 6 files. The problem: the keypad firmware drops a
HID++ request that is in flight when an image report arrives. The fix adds a
third reason for a request to park:

- `pending.rs` gains `Wait::Paused` (pr-2322 `pending.rs:97`) beside `InFlight`
  and `Stale`; `try_register` refuses every key while a pause holds or awaits
  the channel (:122).
- `HidppChannel::pause_requests()` (pr-2322 `channel.rs:709`) returns a
  `RequestPause` guard (pr-2322 `pending.rs:365`). Taking it waits until the
  requests already in flight are answered or abandoned; while held, new
  requests park ("request pause waiting for requests in flight" / "parked" in
  the trace); dropping it wakes them.
- `write_key_image_on` takes the pause before the first packet (bounded by
  `PAUSE_TIMEOUT`) and holds it until the image ack, inside a
  `tokio::spawn`ed task (pr-2322 `key_display.rs:125,144`). The second commit
  (`2c58c7b`) exists because of drop-cancellation: if the agent's 5 s write
  timeout dropped the caller's future between "packets sent" and "ack
  received", the pause would be released early; the spawned task owns the
  pause, so it can't be.

> **Rust note — RAII guards.** `RequestPause` does its work in `Drop`: when the
> value goes out of scope (normally, by early return, by panic, or by the
> owning future being cancelled), the pause is released. Like a Python context
> manager whose `__exit__` can't be skipped.

---

## 6. Inventory and probing

- `Enumerator` (`openlogi-device/src/inventory.rs:69`) is the long-lived
  enumerator; `enumerate` (:192) is the one-shot version the CLI uses (retries
  until the result settles).
- `probe_one` (`inventory/probe.rs:343`) detects what's on a node and routes:
  `probe_bolt_receiver` (`probe/bolt.rs:36`), the Unifying probe, or
  `probe_direct` (`probe/direct.rs:41`, device index `0xff` — the keypad).
- `probe_features` (`inventory/features.rs:373`) reads the feature table; the
  set of feature IDs becomes `Capabilities` (`derive_capabilities`, :351). **Tabs
  in the GUI are driven by measured capabilities, not device kind.**
- **Device kind** has four incompatible vocabularies (HID++ `0x0005` DeviceType,
  the Bolt pairing register, the asset index, OpenLogi's `DeviceKind`) — see
  `crates/openlogi-device/AGENTS.md`. The keypad reports no DeviceType, so
  `direct_identity_kind` (`inventory/mappings.rs:109`) claims it as `Numpad` from
  its USB ID. The Dialpad's "headset" label comes from the Bolt register kind
  nibble `0x0d` (`openlogi-hidpp/src/receiver/bolt/event.rs:332`), confirmed by
  AprilNEA in [#2240](https://github.com/AprilNEA/OpenLogi/issues/2240); a Dialpad identity entry is the planned fix.
- The **probe cache** (`openlogi-hid/src/probe_cache.rs:15`) persists probe
  results to `probe-cache.json`, so a warm start may *not* re-read the feature
  table — relevant when you hunt for `feature` trace lines in a log.
- `DeviceIoGate` (`openlogi-device/src/device_io.rs:34`) is checked before every
  open and write; it's how suspend/resume pauses all hardware I/O.

---

## 7. The agent core

- **Orchestrator** (`openlogi-agent-core/src/orchestrator.rs:564`) is the
  single owner of "what should every device be doing". `refresh_inventory`
  (:1377) runs on inventory changes: publish the snapshot, rebuild devices,
  re-arm capture routes, reapply settings. `publish_device_runtime` (:1108)
  republishes per-device runtime specs (capture plans, keyboard specs, keypad
  key-display specs, lights) on watch channels that the watchers read.
- **Watchers** (`openlogi-agent-core/src/watchers/`) are long-running tasks,
  each owning one concern:

  | Watcher | Owns |
  |---|---|
  | `inventory.rs` | HID reconciliation thread; emits inventory events |
  | `gesture.rs` | one mouse capture session per capture plan |
  | `keyboard.rs` | one key-capture session per keyboard spec (the keypad's keys) |
  | `key_display.rs` | painting the keypad LCD |
  | `host_switch.rs` | Easy-Switch links |
  | `light.rs` | Litra lights |
  | `pairing.rs` | on-demand pairing |
  | `pointer.rs`, `foreground_app.rs` | window under pointer; frontmost app (per-app profiles) |
  | `camera.rs` | camera in use |
  | `accessibility.rs`, `input_monitoring.rs`, `secure_input.rs` | macOS permission polls |

  HID++ watchers start at arming (`openlogi-agent/src/startup.rs:202`), state
  watchers at :280.
- **Capture sessions** (`openlogi-device/src/session/capture.rs`): one
  long-lived session per device on the inventory's own channel. The
  device-specific half is the `ArmedCapture` trait (:133); the shared loop is
  `run_capture` (:213) — publish the channel, add listeners, re-divert controls
  if another app (Options+) took them back, undivert everything on stop.
  "Diverting" a control means telling the device (feature `0x1b04`) to report
  the press to software instead of acting natively.
- **Actions** are dispatched by the agent-core runtime; agent-level requests
  (Actions Ring, keypad paging) are split off in `agent_request`
  (`openlogi-agent-core/src/runtime.rs:182`), and OS-level actions go to
  `openlogi_inject::execute` (`openlogi-inject/src/inject.rs:350`), which handles
  `OpenApplication` itself and forwards everything else to the per-OS module
  (`inject/{macos,linux,windows}.rs`).

> **Rust note — `thiserror`.** Libraries return typed error enums derived with
> `thiserror` (e.g. `ChannelError::Timeout`), binaries may use `anyhow`. When a
> log says `error=Channel(Timeout)`, that's the `Debug` form of nested enums:
> a `Channel` variant wrapping a `ChannelError::Timeout`.

---

## 8. The keypad, end to end

### A key press → an action

1. The keypad sends vendor report `13 ff 02 00 …` (framing:
   `openlogi-device/src/keypad_vendor.rs`). On Windows it arrives on COL02
   (`0x1A08`).
2. The keyboard session's raw-report handler (`session/keyboard.rs:447`) decodes
   grid keys and `emit_grid_edges` (:301) emits `ButtonDown`/`ButtonUp` for
   `ButtonId::grid(key)`. Grid keys are *observed*, never diverted; the two
   paging buttons are ordinary `0x1b04` controls (CIDs `0x01a1`/`0x01a2`) and
   are diverted.
3. `dispatch_input` (`openlogi-agent-core/src/watchers/keyboard.rs:176`) looks
   the key up in the current page's bindings (with the per-app profile overlay).
4. The action runs; a page action becomes `ActionRequest::TurnKeypadPage`,
   handled at `openlogi-agent/src/lifecycle.rs:347` → `Orchestrator::turn_keypad_page`
   (`orchestrator.rs:1050`) → `publish_device_runtime`, so both the bindings and
   the LCD faces switch.

### A config change → new LCD images

1. GUI saves `config.toml` (pages live in `DeviceConfig.keypad_pages`,
   `openlogi-core/src/config/device.rs:390`; slots named `"gridMiddle"`,
   `"page2:gridMiddle"`; `bindings_on_page`, `openlogi-core/src/bindings.rs:100`),
   then calls `reload_saved_config`.
2. The orchestrator rebuilds and `key_display_specs_for` (`orchestrator.rs:1139`)
   publishes what each key should show; `key_face` (:2432) maps a binding to an
   icon or blank.
3. The key-display watcher wakes; `Painted::plan` (`watchers/key_display.rs:143`)
   diffs wanted vs painted (with per-panel backoff); `paint_all` (:317) paints
   the changed keys.
4. `render_tile` (`watchers/key_display/render.rs:59`) draws the action's SVG icon
   white-on-black with resvg and encodes a JPEG at quality 90.
5. `write_key_image_on` (`openlogi-device/src/write/key_display.rs:98`) splits it
   into 4095-byte `0x14` packets (`image_packets`, :184), writes each through
   `write_whole_raw_report` (`openlogi-device/src/write.rs:196`) — on Windows
   routed to COL03 (`0x1A10`) — then waits up to `ACK_TIMEOUT` = 2 s (:53) for
   the `13 ff 02 2b …` ack (`image_ack`, :151) on COL02. A face is recorded as
   painted only after the ack.
6. Reconnect or wake bumps a panel generation, forcing a full repaint.

Geometry (118 px keys, 3×3, pitch 158) lives in the registry:
`openlogi-device-registry/src/keypad.rs:136`; `DeviceRoute::keypad()`
(`openlogi-core/src/hid/route.rs:175`) is the single "is this the keypad?"
check (guarded by an ast-grep rule) — and it only matches direct routes, so
nothing keypad-specific applies to a Bolt device like the Dialpad.

---

## 9. Logging cheat-sheet

`OPENLOGI_LOG` takes `tracing` filter directives (default `info`,
`openlogi-core/src/env.rs:16-19`). The agent logs to stderr **and** a
daily-rotated `agent.<date>.log` (7 kept) in the state dir
(`openlogi-agent/src/logging.rs`). Paths are XDG-style on every OS by design
(`openlogi-core/src/paths.rs:1-20`), so on Windows that's
`%USERPROFILE%\.local\state\openlogi\` and config is
`%USERPROFILE%\.config\openlogi\config.toml` — not `%APPDATA%`.

| Target | Section | You'll see |
|---|---|---|
| `hidpp::channel` | §5 | `hidpp request dev= feat= func=`, `raw report received … payload=[…]`, `report not HID++ — dropped` (trace) |
| `hidpp::channel::pending` | §5 | `hidpp response` / `hidpp no response error=Timeout`; with [#2322](https://github.com/AprilNEA/OpenLogi/pull/2322), pause/park lines |
| `hidpp::device` | §6 | `enumerating feature table`, `feature index= slot= id=0x…` |
| `openlogi_hid::transport[::windows]` | §3–4 | opens, collection pairing, disconnects |
| `openlogi_device::inventory[::probe::*]` | §6 | probe results, `DeviceType read failed` (harmless on the keypad) |
| `openlogi_device::session::{capture,keyboard,gesture}` | §7–8 | arm/re-arm, divert, grid edges |
| `openlogi_device::write::key_display` | §8 | image writes and acks |
| `openlogi_agent_core::orchestrator` | §7 | inventory refresh, rebuilds |
| `openlogi_agent_core::watchers::*` | §7 | per-watcher (e.g. `key image write failed — retrying`) |

Your proven combination:
`openlogi_hid=debug,openlogi_device=debug,openlogi_agent_core=debug,hidpp=trace,info`.
Sanitize with `tools/fred/sanitize_log.py` before sharing.

---

## 10. External surfaces — what scripts can do *to* and *with* OpenLogi

**Inbound (your scripts → OpenLogi)**

- **`openlogi api …`** is the public automation interface
  (`openlogi-cli/src/cmd/api.rs:37`; full contract in `docs/USAGE.md:82-250`).
  One JSON object on stdout with a `schema_version` (1) that is independent of
  the IPC version; stable error codes; exit 0/1. Commands: `status`, `devices`,
  `dpi`, `smartshift`, `fn-lock`, `os-layout`, `report-rate`, `easy-switch`;
  writes are immediate, `--save` also persists and reloads. It is a client of the
  running agent and never opens hardware itself. Each call is a process launch +
  IPC handshake — fine for scripts and launchers, not a high-rate channel.
- **The agent IPC socket** is deliberately *not* public: Rust-specific bincode,
  rejected on any version skew, renumbered every release.
- **`config.toml` by hand**: strict schema (typos fail the load, by design). The
  agent reloads only when the GUI opens or after `api … --save`; there is no file
  watcher and no `openlogi reload` command (`docs/CONFIGURATION.md:13-32`).
- **`openlogi://` deeplinks** (`openlogi-core/src/brand.rs:268-290`): GUI
  navigation only (show, settings, about, check-for-updates, quit), and the
  scheme isn't registered on Windows (`openlogi-agent/src/tray_windows.rs:8-10`).

**Outbound (a button/key → your scripts)**

- `RunShellCommand` (Windows: `cmd /C` with `CREATE_NO_WINDOW`,
  `openlogi-inject/src/inject/windows.rs:286`), `OpenApplication` (paths, folders,
  URLs, via the `opener` crate — `inject.rs:351`), `TypeText`, `Workflow` (a timed
  sequence of steps), `RunAppleScript` (macOS only). Per-app profiles switch
  bindings by foreground app on all three OSes.

**Gaps (facts, not proposals)**: no event/subscribe interface for scripts
(although the agent's internal `observe` long-poll exists), no profile-switch
API (USAGE.md says so), no keypad-page or "trigger this action" API. On Windows,
`TypeText` and `RunAppleScript` are warn-only stubs — see the scoping doc.
