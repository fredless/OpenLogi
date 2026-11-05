# Scoping: Creative Console, the Power User menu, and external hooks

Personal notes (`fred/notes`), an **exploration aid, not a work queue**. Code
facts are pinned to master `6466cd2` (2026-11-04); upstream thread facts were
read on 2026-11-04. Nothing here has been proposed upstream.

**Guiding principle:** OpenLogi's draw over Options+ is being compact and
efficient. Each candidate below carries a *surface* note — does it add UI,
actions, config, processes or ports, or remove/unify them? Prefer the latter.

---

## 1. Where the Creative Console stands

### MX Creative Keypad (`046d:c354`, wired)

| Feature | In code | Verified on hardware |
|---|---|---|
| LCD key faces (action icon or blank, JPEG via resvg) | all OSes, no `cfg` gates in keypad modules | macOS (#1873); Windows after #2283 (you) |
| Grid keys (vendor report `0x13`, observed not diverted) | all OSes | macOS; Windows after #2283 (you) |
| Paging buttons (CIDs `0x01a1/0x01a2`, diverted) + up to 15 pages | all OSes | macOS; Windows (you) |
| Per-app profiles on the Keys tab | foreground watcher exists on all three OSes | **not runtime-tested** per #1873's own Testing section |
| Image/HID++ race fix | #2322, open | Windows: you, at `4c3182f` and on `a5b507e`+`2c58c7b`. macOS: unknown whether the race happens there |
| Brightness (`0x8040`) | decoder only (`openlogi-hidpp/src/feature/brightness_control.rs`); unused | the probe example warns level 0 may reset the device |
| Linux | same non-Windows transport as macOS; works only if `0x13`/`0x14` ride the same hidraw node | **unverified** |

The **only** per-OS difference is the transport (`openlogi-hid`): macOS/Linux use
one `0xFF43/0x1A02` node; Windows stitches three collections (architecture
notes §4).

### MX Creative Dialpad (Bolt, wpid `bc00`)

Nothing in code yet: no registry identity, `0x4610` absent from the feature
registry, Crown `0x4600` decoded but unused, and `DeviceRoute::keypad()`
rejects Bolt routes. From #2240 (AprilNEA, Nov 1–3):

- The `headset` label is "an OpenLogi bug": the Bolt register kind nibble is
  `0x0d` (`openlogi-hidpp/src/receiver/bolt/event.rs:332`). A Dialpad identity
  entry fixes it and unlocks the Keys tab.
- Controls: four divertable `0x1b04` CIDs `0x0053 0x0056 0x0059 0x005a`. Dials
  via `0x4610` at index 13: function 3 with `[dial, 0x01]`; notifications carry
  param 0 = dial (0 roller, 1 large dial), param 1 = signed steps (from the
  node-logitech-mx-creative-console library; unverified against a spec).
- Your fixture `mx-creative-dialpad-001` "will land with the identity change";
  AprilNEA says nothing else is needed from you for now and will post a test
  build. **So the Dialpad is owned by the maintainer right now — your role is
  tester.** How dial rotation becomes bindable is "under evaluation".
- #2285 (multi-device fixture blocker) is already fixed by open #2286.

---

## 2. The Power User menu on Windows (your primary interest)

### What each item does per OS

| Item | macOS | Windows | Linux |
|---|---|---|---|
| Open app / folder / URL | ✓ | ✓ (`opener` crate, `openlogi-inject/src/inject.rs:351`) | ✓ |
| Type text | ✓ | ✗ warn-only stub (`inject/windows.rs:274`) | ✗ stub (`linux.rs:493`; open PR #1605 implements it) |
| Run AppleScript | ✓ | ✗ warn-only (`windows.rs:282`) | ✗ |
| Run shell command | `/bin/sh -c` | `cmd /C`, no console window (`windows.rs:286`) | `/bin/sh -c` |
| Workflow | ✓ | partial — its Type text / AppleScript steps silently do nothing | partial |

(Also outside the Power User menu: `Sleep` is a debug-logged no-op on Windows,
`windows.rs:257`.)

### What each editor offers (three hand-written lists today)

| Editor | Offers | Shown but dead on Windows |
|---|---|---|
| Mouse button editor (`openlogi-desktop/src/features/mouse/view.rs:236-252`) | Open app, Run command | — |
| Actions Ring slot editor (`features/action_ring/editor.rs:101-128`) | Open app, Type text, Run AppleScript (hidden off macOS by `cfg!`, :112), Run command | **Type text** |
| Keyboard / keypad panel (`features/keyboard/function_row.rs:1270-1293`; the keypad uses this panel) | all five, no gating | **Type text, AppleScript**, Workflow partially |
| Workflow step picker (`features/keyboard/editors.rs:332-348`) | all five step kinds | Type text, AppleScript steps |

So your observation is right: the Actions Ring *does* show a Power User item
that can't work on Windows (Type text), and the keypad panel shows two.

### Someone already started the fix: PR #1875

**#1875 "feat(gui,linux): offer only the actions this host can perform"**
(AalmanSadath, open since 2026-10-17):

- Adds `Action::is_available_on(Host)` in a new `openlogi-core/src/binding/host.rs`
  — one table read by the pickers *and* the Linux dispatcher, so they can't
  drift. Windows row: hides `TypeText`, `RunAppleScript`, `Sleep`.
- The mouse picker, Actions Ring editor and keyboard Power User section omit
  unavailable actions; an existing binding to one keeps working-as-before and
  is labelled "(not available here)". No wire or schema change.
- Gaps by its own design: `Workflow` stays available even though its
  `TypeText` steps are skipped; the **Workflow step picker** isn't filtered.
- Status: Greptile 5/5, no findings; review requested from AprilNEA and
  davidbudnick, **no maintainer comment yet**. Base is 267 commits behind
  master (predates the keypad's #1873, though the keypad reuses the keyboard
  panel it touches). Labelled `platform: linux` although it changes Windows
  behaviour too.

This is the minimal-surface fix in the repo's own idiom (single source of truth),
already written. Re-implementing it would be duplicate work.

### Update 2026-11-05: why the editors differ, and the core fix

Re-checked on upstream master `4ea5b600`. Line numbers moved since `6466cd2`:
the keyboard panel's list is now at `function_row.rs:1490`.

**The difference is not platform logic.** The MX Master's editor has no Power
User section on macOS either. Each editor grew its own list at a different
time:

| Editor | Power User items | Platform gating | Origin |
|---|---|---|---|
| Keyboard / keypad panel | all five, hard-coded (`features/keyboard/function_row.rs:1490`) | none | #344 (Aug 9), the F-row remapper, written before Windows mattered. The keypad inherited it because #1873 reuses the keyboard panel. |
| Actions Ring slot editor | Open app, Type text, AppleScript, Run command (`features/action_ring/editor.rs:101-128`) | AppleScript hidden off macOS via `cfg!` (:112); Type text not | #1445 (Oct 17). Greptile flagged AppleScript, so only that one got gated. |
| Mouse picker | Open app and Run command only, as shared single-field editors (`features/binding_editor.rs`: `application_editor`, `command_editor`) | none needed; both work everywhere | #2103 and #2124 (AprilNEA, Oct 28), added one at a time on request |
| Workflow step picker | all five step kinds (`features/keyboard/editors.rs:332-348`) | none | — |

**Root cause.** `Action::catalog()` deliberately excludes the power-user actions
(`openlogi-core/src/binding/action.rs:164,174`). So every editor re-adds them by
hand, with its own list and its own platform rule (or none). Two decisions have
no single owner:

- *which custom actions are offered*;
- *which actions this OS can perform*.

That's the "second copy" situation the repo's single-source-of-truth rule
targets.

**Upstream state of the per-OS gaps (2026-11-05):**

| Item | Status |
|---|---|
| #1875 availability table | Open, no maintainer review; Greptile clean; labelled `platform: linux` although it changes Windows |
| #1605 Linux Type text | Open, `needs: decision` (AprilNEA, Nov 4); Greptile 0/5 (blocks button handling, drops letters, layout issues) |
| #1447 Windows Lock (`LockWorkStation`) + Sleep (`SetSuspendState`) | Approved by davidbudnick, waiting on AprilNEA; Lock hardware-confirmed by a #1727 reporter; fixes #1266 |
| #1846 Windows Lock only | Same author, overlaps #1447; davidbudnick's approval dismissed by a force-push |
| #1529 (merged) | AprilNEA moved script/workflow running into `inject.rs` over four per-OS hooks; that's why every OS has the same stub set |
| #1361 / #2337 / #2301 (merged) | Windows Run command: no console flash, quotes kept, failures logged |
| Windows Type text | **Unclaimed** |
| AppleScript counterpart | Not proposed; Run command can already launch PowerShell |

**Suggested core fix.** Small, no new surface, nothing keypad-specific:

1. **One availability owner.** Land #1875, and extend it to Workflow steps (a
   `WorkflowStep::is_available_on` beside it) so the step picker filters too.
2. **One offer owner, one shared section.**
   - A single list of power-user kinds (e.g. on `PowerUserKind`, which already
     lives in `features/keyboard/editors.rs:41`).
   - One shared Power User section, rendered by the mouse, keyboard/keypad and
     Ring editors and filtered by (1). Each editor keeps only its layout
     differences.
   - Whether the mouse *should* gain Type text and Workflow is a product
     question for the maintainer. Consistency argues yes, filtered per OS.
3. **A guard**, per the repo's rule: an ast-grep rule beside the owner that
   fails on new `cfg!(target_os …)` action gating in desktop editors and on
   hand-built power-user lists outside the owner.
4. **Shrink what's hidden.** Each OS gap closed (Windows Type text; #1447's
   Lock/Sleep) becomes a one-line change to the availability table, not an edit
   per editor.

**Sequencing:**

1. Comment on #1875 (draft A): offer a Windows test, point out the keypad and
   Workflow gaps, and offer to rebase.
2. Implement Windows Type text.
3. Propose the shared Power User section (2–3 above) as a follow-up to #1875,
   not a competing PR.
4. Optionally, post a Windows 11 test report on #1447 for Lock and Sleep.

---

## 3. External hooks and API — is `openlogi api` enough?

What exists (details: architecture notes §10):

- **In:** `openlogi api` (stable JSON, `schema_version` 1): status, devices,
  DPI, SmartShift, Fn-lock, OS layout, report rate, Easy-Switch. Hand-edited
  `config.toml` (reload only on GUI open or `api … --save`). `openlogi://`
  deeplinks (GUI navigation only; not registered on Windows). The agent IPC
  socket is private by design.
- **Out:** Run shell command, Open app/URL, Type text, Workflow, AppleScript;
  per-app profiles.

What's missing, as facts: no events for scripts (device connected, battery,
key pressed), no profile or keypad-page switching (USAGE.md: "There is no
profile-switch API yet"), no "trigger action X" call, no config-reload command.
Related open issue: #1341 (authenticate IPC clients; the Windows named pipe is
already creator/admin-restricted by its default DACL).

**Questions to explore before proposing anything** (minimal-surface lens):

1. What do you actually want a script to do? E.g. "switch keypad page when
   Lightroom opens" is already covered by per-app profiles; "flash a key when
   a build finishes" needs a way *in*.
2. If a way in is needed, is one more `openlogi api` subcommand enough
   (`api keypad-page --device … --page 2`, `api reload`)? It reuses the existing
   stable contract and process model — no daemon port, HTTP server or plugin
   system, which is where Options+ went.
3. For events, would an `api watch` streaming NDJSON over the agent's existing
   `observe` long-poll be worth its surface, or is polling `api devices` from a
   script good enough?
4. For PowerShell on Windows: `Run shell command` already reaches it
   (`powershell -NoProfile -ExecutionPolicy Bypass -File C:\path\x.ps1`). Is a
   docs line plus an OS-appropriate placeholder hint (today `echo hello`)
   enough, versus a new `RunPowerShell` action (an appended `Action` variant =
   wire + schema surface, AprilNEA's call)?

---

## 4. Candidates (ranked; none started)

Size: S < 1 day, M a few days, L a week+. Reviewer from `.github/CODEOWNERS`.

| # | Candidate | Size / risk | Crates (reviewer) | Surface | You can test |
|---|---|---|---|---|---|
| 1 | **Test and review #1875 on Windows** (and macOS once the MBP is in): Power User items hidden as expected, "(not available here)" on a pre-existing Type text binding, keypad panel included. Point out the Workflow step picker gap. Offer to help rebase if the author's gone quiet. | S / low | desktop, core (AprilNEA for core) | removes | Windows now, macOS later |
| 2 | **Windows Type text** via `SendInput` + `KEYEVENTF_UNICODE` (UTF-16, surrogate pairs, key-down/up per unit; through the shared held-chord helper `with_held_modifiers`, `openlogi-inject/src/inject.rs:519`, as macOS does). Then flip the `TypeText` cell in #1875's Windows row. Fixes Workflow Type-text steps too. Nobody has claimed it (#1605 is Linux-only; #436 has no Unicode path). | S–M / low-med | `openlogi-inject/src/inject/windows.rs` (davidbudnick, AprilNEA) | none added; makes an existing item work | Windows: bind a key, type into Notepad incl. emoji/non-Latin |
| 3 | **Windows `Sleep`** (`SetSuspendState` or equivalent) — tiny, same table row. | S / low (it sleeps your PC when tested) | inject | none | Windows |
| 4 | **PowerShell guidance**: docs + per-OS placeholder for Run command. | S / low | desktop, docs | none | trivially |
| 5 | **API questions** from §3 — a short Discussion (Ideas) draft, only if you decide you want a way in. | — | cli, ipc (AprilNEA) | adds, so needs the maintainer's yes | — |
| 6 | **Dialpad**: keep testing AprilNEA's builds (identity entry, `0x4610`). | — | — | — | Windows |
| later | Keypad brightness (`0x8040`, level-0 hazard); long-press/double-press/toggle (overlaps #2090, `needs: decision`, 300 ms single-click delay trade-off); richer LCD faces (text/custom images) | M–L | core, agent-core | adds | — |

**Coordination before writing code:**

- #1875's author (AalmanSadath) and the maintainers: candidates 1–3 all touch
  their table. A short comment on #1875 offering a Windows test + asking whether
  Windows `TypeText` should land before or after it avoids a conflict.
- AlexanderYW said more keypad PRs are coming; none of 1–4 is keypad-specific,
  but a heads-up keeps you out of each other's way (draft in `DRAFTS.md`).

All upstream text is drafted in `docs/fred/DRAFTS.md` for your approval — nothing
gets posted without your explicit go-ahead on the exact wording.
