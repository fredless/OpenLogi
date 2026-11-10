# External device control: what exists, what's in flight, what's missing

Personal research notes (`fred/notes`), 2026-11-05. Code refs are pinned to
upstream master **`4ea5b600`**. Upstream threads were read the same day (bodies
via the search API; comments via the public web pages). Nothing here has been
proposed upstream.

**The question:** can an outside program — a script, a Claude Code hook, a
Stream Deck button, a CI notifier — tell OpenLogi to *do something to a
device*: flash a light, buzz a mouse, change a backlight, put an image on a
keypad key? And if a mechanism is needed, what shape fits OpenLogi's principles
(lightweight, OS-portable, the agent owns all device I/O)?

**Short answer:** the shape already exists and upstream is converging on it —
**one typed IPC method per capability, surfaced as an `openlogi api <capability>`
subcommand**. It covers *settings* today (DPI, SmartShift, …). It covers
*outputs* nowhere yet, but haptics are in flight ([#2060](https://github.com/AprilNEA/OpenLogi/pull/2060)) and lights/backlight
need only surface. The MX Creative Keypad is the one output that needs a
genuinely new capability.

---

## 1. Device outputs and use cases

| Output | Protocol | Devices | Example external uses | Reachable from outside today? |
|---|---|---|---|---|
| **Haptic pulse** | HID++ `0x19b0` play waveform | MX Master 4 | "build done" tap; distinct pattern for a VIP message, CI failure, meeting starting; Claude Code finished | **No** on master. Only Actions Ring hover/activate (`crates/openlogi-agent/src/server.rs:578,646`, single-flight `RingHapticPlayer` :670). Only 2 of the ~15 firmware waveforms are named (`crates/openlogi-hidpp/src/feature/haptic_feedback.rs:56`). **[#2060](https://github.com/AprilNEA/OpenLogi/pull/2060) adds `openlogi api haptic`.** |
| **Litra power / brightness / colour temp** | `0x1990` Illumination (+ raw `0x11 ff 04`) | Litra Glow, Beam | on-air light when a call starts; warmer light after sunset; blink as a doorbell | IPC `set_light` (`crates/openlogi-ipc/src/ipc.rs:995`). CLI `openlogi light …` **opens the HID device itself, bypassing the agent** (`crates/openlogi-cli/src/cmd/light.rs:221`). Auto-on with camera (macOS). |
| **Keyboard backlight** | `0x1982` Backlight2 | MX Keys / MX Mechanical class | dim at night; flash as a status lamp | IPC `set_backlight` (`ipc.rs:1088`); `openlogi backlight` **via the agent** (`cmd/backlight.rs:151`). Not in `api`. |
| **Keyboard RGB** | `0x8070/0x8071/0x8081/0x8080` | G915 and other G-series | colour as status (red = CI failing); effects (open [#2023](https://github.com/AprilNEA/OpenLogi/pull/2023)) | IPC `set_lighting` (`ipc.rs:952`); `diag lighting` (direct). Not in `api`. |
| **Keypad LCD tiles** | vendor report `0x14` JPEG, acked on `0x13` | MX Creative Keypad (3×3, 118 px) | status tiles (CI, mic mute, timer); a script-pushed image or text per key; a countdown animation; switch page on an event | **No.** Faces are only `Blank` or an action `Icon` (`crates/openlogi-agent-core/src/watchers/key_display/render.rs:20`). The low-level write accepts *any* key-sized JPEG ≤ 64 KB (`crates/openlogi-device/src/write/key_display.rs:91-98`), acked within `ACK_TIMEOUT` 2 s (:53). |
| Keypad brightness | `0x8040` | MX Creative Keypad | dim at night / when away | Decoder only, unused; the probe example warns that level 0 may reset the device. |
| DPI LED | `0x1300` | some mice | indicator | Indirect (precision-mode action). |
| DPI, SmartShift, report rate, Fn lock, OS layout, Easy-Switch rename | various | mice, keyboards | per-game DPI from a launcher | **Yes, `openlogi api`.** |
| Change host (Easy-Switch) | `0x1814` | multi-host MX | KVM-style "switch everything to the laptop" | IPC `switch_host`; `diag host-switch`. Not in `api`; [#2068](https://github.com/AprilNEA/OpenLogi/pull/2068) open. |
| Sidetone, press force, pointer speed, disabled keys | `0x8300`, `0x19c0`, `0x2205`, `0x4521/2` | headsets, MX Master 4, … | — | IPC `set_*` only. |
| UVC camera controls | UVC | Logitech webcams | re-apply exposure/focus when Teams starts ([#1676](https://github.com/AprilNEA/OpenLogi/issues/1676)) | `openlogi camera set` — direct, not via the agent. |
| Decoders with no surface | `0x8310` EQ, `0x4600` Crown, `0x8090` mode, `0x1983` Backlight3 | — | — | none |

Input-only devices (the Dialpad's dials, gesture buttons) aren't outputs; they're
already handled as bindable inputs where supported.

---

## 2. Every way in today (all local, same-user; nothing network-facing)

| Path | What it can do | Notes |
|---|---|---|
| **`openlogi api …`** | status, devices, dpi, smartshift, fn-lock, os-layout, report-rate, easy-switch | **The only stable public interface.** One JSON object per run with `schema_version` 1, independent of the IPC version; stable error codes; devices addressed by an opaque ID from `api devices`; `--save` persists and reloads. Connects via `connect_as(ClientKind::Cli)` (`crates/openlogi-cli/src/agent.rs:47`); 2 s handshake, 5 s per call. "There is no profile-switch API yet" (`docs/USAGE.md:180`). |
| Other CLI commands | `backlight` (via agent); `light`, `camera`, `diag …` (direct HID/UVC) | The direct ones are the documented diagnostic exception and can fight the agent. |
| Agent IPC (tarpc/bincode) | `set_light`, `set_lighting`, `set_backlight`, `switch_host`, `set_*` | **Internal, not public:** strict version equality each release, Rust-only encoding. No authentication ([#1341](https://github.com/AprilNEA/OpenLogi/issues/1341)); the Windows pipe is machine-wide on master (`crates/openlogi-ipc/src/transport.rs:43-49`), which [#2299](https://github.com/AprilNEA/OpenLogi/pull/2299) fixes. No "run action", "notify", haptic or image call; executable actions deliberately never cross the wire (`ipc.rs:790`). |
| IPC event streams | `observe` (whole snapshot, long-poll ≤ 20 s), `observe_backlight`, `observe_notices`, `observe_lock_keys` (`ipc.rs:1043,1122-1132`) | Not exposed by any CLI command. [#1821](https://github.com/AprilNEA/OpenLogi/pull/1821) adds the first `api watch-…`. |
| `openlogi://` deeplinks | show, settings, about, update check, quit | GUI navigation only; not registered on Windows. |
| `config.toml` | anything configurable | No file watcher; applied only when the GUI opens or after `api … --save`. Not a signalling channel. |
| Flow | handoff between paired computers | Trusted peers only; other request kinds are rejected. |
| HTTP / WebSocket / D-Bus server / MQTT | — | **None exist.** D-Bus is client-only (MPRIS, GNOME). |

The reverse direction already works: a button can **run** a script
(`RunShellCommand`, `Workflow`, `OpenApplication` with a URL).

---

## 3. Who else is thinking about this upstream

Most relevant first.

- **[#2060](https://github.com/AprilNEA/OpenLogi/pull/2060) — "event haptics for the MX Master 4"** (Tintin0, open, `needs:
  decision`, labelled by AprilNEA on Nov 1 with no comment yet). Besides per-event
  haptics, it adds `Agent::play_haptic` (IPC v46) and **`openlogi api haptic`**:
  ```sh
  openlogi api haptic                                   # one subtle tap
  openlogi api haptic --waveform damp_collision --repeat 2
  ```
  Its USAGE adds a Claude Code hook example (`Stop` → `openlogi api haptic
  --repeat 2`). A commenter (seralso) called the external trigger "the part I'm
  most interested in"; the author replied that exposing more firmware waveforms
  "and maybe simple sequences" for `api haptic` is a follow-up. **This is your
  haptics use case, already built in the right shape.** Now on your fork as
  `pr/2060`.
- **[#712](https://github.com/AprilNEA/OpenLogi/pull/712) — "expose device haptics to third-party apps"** (Aug, open, stalled). The
  same idea, but via a **separate `haptic.sock` JSON listener inside the agent**.
  No maintainer review in 2½ months; Greptile flagged a cross-device arm/play
  race. A commenter found the MX Master 4 reports 15 waveforms. The useful lesson
  from it is the queueing: route through a single-flight worker and let a newer
  request replace an unplayed one ("a stale buzz is worse than no buzz"), because
  haptic plays share the HID++ channel with input capture. `pr/712`.
- **[#1821](https://github.com/AprilNEA/OpenLogi/pull/1821) — "publish opt-in keyboard host-switch observations"** (draft):
  `openlogi api watch-host-switch --device <id>`, the first **event stream out**
  through `api`, opt-in and default-off. `pr/1821`.
- **[#1657](https://github.com/AprilNEA/OpenLogi/pull/1657) — AprilNEA's own draft "peripheral drivers, Wasm plugins"** (Oct,
  `feat/peripheral-extensions`). Not an external API, but it states the
  maintainer's design principles for exactly this kind of growth:
  - "There is no unrestricted `execute(String, JSON)`."
  - A new cross-device behaviour "should become a typed capability rather than
    an expanding opaque command surface."
  - "Do not add a global bus."
  - Adds an `openlogi peripheral …` CLI. `pr/1657`.
- **Discussion [#420](https://github.com/AprilNEA/OpenLogi/discussions/420) — "Actions Ring & Haptic Feedback".** AprilNEA (Nov 1):
  "The separate local haptic-daemon compatibility idea is not tracked yet. This
  thread stays open for a scope decision." Your Nov 4 question there is
  unanswered.
- **`docs/DECISIONS.md:729`, "a crossing edge gets a wire, not an event layer":**
  any new process boundary gets a versioned, append-only `openlogi-ipc` method;
  an in-process event bus or transport-agnostic event layer is deliberately not
  built.
- Related: [#987](https://github.com/AprilNEA/OpenLogi/pull/987) (close-button haptic), [#1676](https://github.com/AprilNEA/OpenLogi/issues/1676) (UVC apply from CLI), [#1341](https://github.com/AprilNEA/OpenLogi/issues/1341) / [#2299](https://github.com/AprilNEA/OpenLogi/pull/2299)
  (IPC auth; Windows pipe per-user, by AprilNEA), [#2068](https://github.com/AprilNEA/OpenLogi/pull/2068) (software Easy-Switch),
  [#1375](https://github.com/AprilNEA/OpenLogi/issues/1375) (deep link to a device), [#2023](https://github.com/AprilNEA/OpenLogi/pull/2023) (RGB effects), [#1275](https://github.com/AprilNEA/OpenLogi/pull/1275) (Litra + camera on
  Windows).

Searches for webhook, MQTT, HTTP server, Home Assistant, Stream Deck, Hammerspoon
and custom keypad images found **no** request or work on a network listener or
keypad image API.

---

## 4. Synthesis — the mechanism mostly exists as a pattern

Upstream code, the doctrine docs and the in-flight PRs all point the same way:

> **one typed IPC method per output capability → one `openlogi api <capability>`
> subcommand**, addressed by the device ID from `api devices`, JSON in/out,
> `--save` only where persisting makes sense.

Why it fits OpenLogi's principles:

- **Lightweight:** no new daemon, port, socket, HTTP server, plugin host or
  bus. Nothing runs when nobody calls it.
- **Portable:** `openlogi api` and the IPC already work on macOS, Linux and
  Windows; any language (Python, JS, PowerShell, shell, AutoHotkey, a Stream Deck
  "run command") can call a CLI and parse JSON.
- **Safe enough:** same-user only, the trust model the IPC already has (with
  [#2299](https://github.com/AprilNEA/OpenLogi/pull/2299) closing the Windows gap). A network-facing surface would need its own
  pairing/trust story like Flow's — a much bigger decision.
- **Generic without being opaque:** generality comes from **capability
  discovery** (`api devices` already lists measured capabilities) plus a small,
  typed verb per capability — not from a universal `send(device, json)`, which
  the maintainer has explicitly ruled out.

What's missing, smallest first:

1. **Surface only, IPC already exists:** `api light`, `api backlight`,
   `api lighting`. Also: `openlogi light` should go through the agent like
   `openlogi backlight` does.
2. **Haptics:** [#2060](https://github.com/AprilNEA/OpenLogi/pull/2060) (`api haptic`) — test and support it rather than duplicate
   it. Follow-ups it already mentions: more waveforms, simple sequences.
3. **Keypad — the one genuinely new capability** (your first target):
   - A **transient face override** per key — image, text or icon — layered over
     the binding-derived faces in the key-display watcher
     (`watchers/key_display.rs`), with an explicit `KeyFace` variant for it.
   - **Lease semantics:** an override has an owner and a lifetime (until cleared,
     a TTL, or the next page change), so an external signal never silently
     rewrites the user's configured layout and a dead script can't leave a key
     stuck.
   - An IPC method and `openlogi api keypad-face --device <id> --key <n>
     (--image <file> | --text <s> | --clear) [--ttl <s>]`. The agent would size
     and encode the image, since the device needs an exact-size JPEG.
   - **Animation** is bounded by the per-tile ack round trip (≤ 2 s timeout;
     about 1 ms per image measured on Windows in [#2322](https://github.com/AprilNEA/OpenLogi/pull/2322)), and launching one CLI
     process per frame is wasteful. If animation matters, an `api` **stdin
     streaming mode** (NDJSON in, one long-lived process) keeps it cheap without
     a new socket.
   - Keypad brightness (`0x8040`) could join later, minding the level-0 hazard.
4. **Events out:** one generic `api watch` (NDJSON over the existing `observe`
   long-poll) versus narrow per-feature watches like [#1821](https://github.com/AprilNEA/OpenLogi/pull/1821).
5. **Shared semantics any of these must settle** — worth agreeing once, not per
   device:
   - **override vs saved setting:** who wins, for how long, what restores it;
   - **ownership/lease:** one owner and one transition authority per output (the
     repo's own rule), so external writes don't fight the GUI or config;
   - **rate limiting / single-flight:** the [#712](https://github.com/AprilNEA/OpenLogi/pull/712) lesson; a flood of requests must
     not starve input capture or time out unrelated writes;
   - **discovery:** capabilities in `api devices` decide which verbs apply.

### 4a. Prior art: how Logi Options+ plugins do it

Researched 2026-11-05 from Logitech's Actions SDK docs (the same SDK as
Loupedeck's).

- **The device has one owner.** The *Logi Plugin Service*, a separate background
  process, owns the hardware. Plugins (C#, or Node.js in beta) never write to the
  keypad. This is the same split as OpenLogi's agent.
- **Key images are pulled, not pushed.** A plugin overrides
  `GetCommandImage(actionParameter, imageSize)` and returns a PNG or SVG. Classic
  button images are 80×80 PNG. A `BitmapBuilder` composes a background image plus
  drawn text, which is how counters and status text are made. When its state
  changes, the plugin calls `ActionImageChanged()` for one action, or
  `ActionImageChanged(null)` for every visible button. The service then calls
  `GetCommandImage` again and pushes the result.
- **There is no built-in animation.** The SDK docs have no API for animation,
  frame rates, timelines or animated GIFs. Counters, countdowns and "animated"
  plugins run their own timer and call `ActionImageChanged` each tick: every
  frame is a redraw.
  - The only frame-rate API found is in a third-party community SDK,
    *LoupixDeck.PluginSdk*, whose host has a central scheduler with `TargetFps`
    and `RenderAnimatedFrame`. That is not Logitech's.
  - Loupedeck's support page "Animation & Effects" is about Adobe After Effects
    shortcuts and is irrelevant.
- **Haptics go through named events, not direct waveform calls.**
  - A plugin declares events in YAML (`name`, `displayName`, e.g.
    `periodic15min`, `buttonPress`) and raises them with
    `PluginEvents.RaiseEvent(name)`.
  - `events/extra/eventMapping.yaml` maps each event to a waveform, with a
    `DEFAULT` and optional per-device overrides (`MX Master 4:
    sharp_collision`). The plugin must declare the `HasHapticMapping`
    capability.
  - The design guidelines say: subtle waveforms for frequent events, intense
    ones for important notifications, and don't fire too often.

**What this means for OpenLogi:**

- **Keypad.** The minimal design matches theirs: a way for a caller to set a
  key's face (image or text), after which the existing key-display watcher
  repaints only what changed. No animation engine is needed. Animation is "set it
  again, often", with its ceiling set by the per-tile write-and-ack round trip.
  That ceiling, plus process launch cost, is the argument for an `api` stdin
  streaming mode if animation matters.
- **Haptics.** [#2060](https://github.com/AprilNEA/OpenLogi/pull/2060)'s `openlogi api haptic --waveform …` makes the *caller* pick
  the waveform. Logitech's event indirection lets callers send a meaning
  (`ci-failed`) while the *user's config* decides how it feels per device. This
  is worth raising with the maintainer. It also generalises beyond haptics: one
  named event could buzz the mouse *and* light a keypad key *and* flash the
  backlight, configured once in `config.toml`. It would be a single
  `openlogi api event <name>` verb rather than a verb per output, though it
  needs care to stay "typed" in the [#1657](https://github.com/AprilNEA/OpenLogi/pull/1657) sense: events would be declared in
  config, not free-form.

Sources:
- [Logi Actions SDK docs](https://logitech.github.io/actions-sdk-docs/)
- [Full documentation export (llms-full.txt)](https://logitech.github.io/actions-sdk-docs/llms-full.txt)
- [Haptics overview](https://logitech.github.io/actions-sdk-docs/csharp/haptics/haptics-overview/)
- [LoupixDeck.PluginSdk changelog](https://github.com/RadiatorTwo/LoupixDeck.PluginSdk/wiki/Changelog)
- [Loupedeck support: Animation & Effects](https://support.loupedeck.com/animation-effects.html)

### 4b. Update 2026-11-08: upstream changes since Nov 5

Upstream master `aec0dee9`.

- **`openlogi api` is unchanged:** still the same eight subcommands, so no
  outputs, events or profiles.
- **IPC protocol is now v46.** [#1239](https://github.com/AprilNEA/OpenLogi/pull/1239) (G-keys) took it. [#2060](https://github.com/AprilNEA/OpenLogi/pull/2060) (`api haptic`,
  `Agent::play_haptic`) also claimed v46, so it needs renumbering before it can
  land. There's still no maintainer comment on [#2060](https://github.com/AprilNEA/OpenLogi/pull/2060). Greptile's Nov 4 review
  adds that some event-haptic choices never play on Windows or Linux.
- **[#2451](https://github.com/AprilNEA/OpenLogi/issues/2451) (new request, `needs: decision`):** target a device *class* instead
  of an ID, e.g. `openlogi api fn-lock --device keyboard --set on`, for
  meeting-room logins. It's directly relevant to the "generic mechanism"
  discussion. Discovery by capability or kind is the generic part, and a
  class selector is the CLI-side expression of it. The reporter also
  mentions "set light on for all keyboards" and webcam settings.
- **[#2430](https://github.com/AprilNEA/OpenLogi/issues/2430) (new request):** haptic taps on Haptic Sense panel gestures (MX
  Master 4). It overlaps [#2060](https://github.com/AprilNEA/OpenLogi/pull/2060)'s event haptics. It proposes a global toggle or
  a per-binding `haptic = "<waveform>"`, which is an alternative to the named
  event mapping noted in 4a.
- **[#2426](https://github.com/AprilNEA/OpenLogi/pull/2426) (merged):** `openlogi diag hidpp` calls any HID++ 2.0 feature with
  raw parameters. It's a direct-hardware diagnostic, not an external control
  path, but handy for probing outputs before building anything: the keypad's
  `0x8040` brightness, more `0x19b0` waveforms, the Dialpad's `0x4610`.
- **Unchanged:** [#712](https://github.com/AprilNEA/OpenLogi/pull/712), [#1821](https://github.com/AprilNEA/OpenLogi/pull/1821), [#1657](https://github.com/AprilNEA/OpenLogi/pull/1657), discussion [#420](https://github.com/AprilNEA/OpenLogi/discussions/420) (Fred's haptic-daemon
  question is still unanswered), [#1341](https://github.com/AprilNEA/OpenLogi/issues/1341) / [#2299](https://github.com/AprilNEA/OpenLogi/pull/2299).

## 5. Open questions (for Fred, then the maintainer)

Posted for maintainer input on 2026-11-10 as [Discussion #2505](https://github.com/AprilNEA/OpenLogi/discussions/2505) ("One API schema for external triggers and events"): existing `api` envelope as the single contract, one dispatcher, transports as adapters (CLI, `--stdin`, later an opt-in listener), phased, aligned with [#1657](https://github.com/AprilNEA/OpenLogi/pull/1657).

1. Which of your use cases need **transient** effects (alert buzz, flash, status
   tile) versus **setting changes** (light on for the meeting)? The answer decides
   whether "lease/override" semantics are needed beyond the keypad.
2. Is per-call CLI latency acceptable for your keypad ideas, or do you want
   animation (which argues for a streaming mode)?
3. Would the maintainer accept `api keypad-face` before the keypad override exists
   in the GUI, or should the override first exist as a user-visible concept?
4. Per-output verbs (`api haptic`, `api keypad-face`, …) or named events mapped in
   config (`api event ci-failed`, like Logitech's haptic event mapping), or both?
   The second matches "send a meaning, let the user decide the feel" and spans
   devices; the first is simpler and already started ([#2060](https://github.com/AprilNEA/OpenLogi/pull/2060)).
5. Should "typed `api` verb per output capability, with shared lease semantics" be
   proposed as a GitHub Discussion before anyone codes it? A draft is in
   `DRAFTS.md` (section D). Nothing has been posted.
