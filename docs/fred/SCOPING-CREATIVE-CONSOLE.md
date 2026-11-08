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

### Update 2026-11-05: macOS-named window actions on Windows

Not Power User items, but the same problem and the same fix. The Navigation
actions are macOS concepts that Windows maps to "their nearest Windows
shortcut" (`openlogi-inject/src/inject/windows.rs:262-276`, master
`4ea5b600`):

| Action (macOS name) | What Windows does | Problem |
|---|---|---|
| Mission Control | Win+Tab (Task View) | macOS name for a Windows feature |
| App Exposé | Win+Tab (the same line of code) | Exact duplicate of Mission Control; Windows has no per-app window spread |
| Launchpad | Win key (Start menu) | macOS name |
| Previous / Next Desktop | Win+Ctrl+← / → | Fine; Windows calls them desktops too |
| Show Desktop | Win+D | Fine |
| Lock Screen | synthetic Win+L | Name fine; Windows ignores a synthetic Win+L. #1447 / #1846 switch to `LockWorkStation()` |
| Sleep | skipped | #1447 adds `SetSuspendState`; #1875 hides it meanwhile |

**Defaults are affected too.** A new mouse gets Mission Control on the gesture
button and on gesture-up, and App Exposé on gesture-click
(`openlogi-core/src/binding/defaults.rs:77,113,117`). On Windows, two different
default gestures therefore do exactly the same thing.

**Upstream:** nothing Windows-specific found. The precedents:

- **#1875:** `is_available_on(Host)` (hide) and `translation_key_on(Host)`
  (rename per OS). Its naming table only has Linux rows: GNOME's Super key is
  "Activities Overview", Launchpad is "Show Applications", and desktops are
  "workspaces". For Linux it also changes the gesture-click default from App
  Exposé to the Actions Ring.
- **#1446** (merged) and **#1853** (open): the GNOME versions of these window
  actions.
- **#1437** (open): relabels Browser Back/Forward to "History Back/Forward"
  in every locale. It keeps the locale keys and the stored action names, so
  configs are unaffected. This is the precedent for renaming safely.

**Suggested Windows rows for #1875's tables.** No new mechanism, a few locale
strings, and no config or wire change:

- `translation_key_on(Windows)`: Mission Control → "Task View", Launchpad →
  "Start Menu".
- `is_available_on(Windows)`: hide App Exposé, since it duplicates Task View.
  Existing bindings keep working and show "(not available here)", as #1875
  already does for Type Text.
- **Ask the maintainer** for a distinct Windows gesture-click default, such as
  the Actions Ring (as #1875 does for Linux) or Show Desktop. Defaults are a
  product call.

**Placement.** Raise it in the #1875 comment (draft A, point 3). If the author
or maintainer wants #1875 to stay Linux-focused, it becomes a small follow-up PR
on top of it: table rows, locale strings, a test. That's a good first code
contribution, because every row can be verified on Windows by pressing the
button.

### Update 2026-11-08: what changed upstream since Nov 5

Checked against upstream master `aec0dee9` (48 commits after `4ea5b600`) and the
threads on 2026-11-08.

**Still true on master:**
- The keyboard/keypad Power User list is unchanged; it moved to
  `features/keyboard/function_row.rs:1695` (G-key work, #1239/#1240).
- On Windows, Type text and AppleScript are still stubs, Sleep is still
  skipped, Lock is still a synthetic Win+L, and Mission Control and App Exposé
  both send Win+Tab (`inject/windows.rs:269-311`).
- The Ring editor still gates only AppleScript (`action_ring/editor.rs:112`).

**#2422 now overlaps #1875 and our Windows rows.** marcinhosh, opened Nov 6,
`needs: decision`, no maintainer comment.
- It relabels per OS, including the Windows names from our suggestion:
  Mission Control → "Task View" and Launchpad → "Start Menu" on Windows;
  Activities Overview, Show Applications and Workspace on Linux.
- It does this with `cfg!` branches in `ui/action.rs::localized_action_label`,
  not #1875's `translation_key_on(Host)` table. It filters App Exposé with
  another `cfg!` in `binding_editor.rs::action_rows_with` (Linux outside KDE
  only), so App Exposé is still offered on Windows.
- **Collision:** #1875 and #2422 add the same four locale keys
  (`activities_overview`, `show_applications`, `previous_workspace`,
  `next_workspace`). Whichever merges second conflicts.
- It changes `default_gesture_binding` on every OS: Up/Click → Mission
  Control, Down → Launchpad, Left/Right → Previous/Next Desktop (previously Up
  Mission Control, Down Show Desktop, Left/Right tabs, Click App Exposé).
- Greptile 4/5, with a P1: the new Down default breaks on KDE.
- Our position (draft A point 3, draft E): one home for per-OS names and
  availability (#1875's table), Windows rows there, App Exposé hidden on
  Windows, and ask whether the default change was meant beyond Linux.

**Lock / Sleep on Windows consolidated into #1447.**
- AprilNEA closed #1846 on Nov 5 "to keep a single PR".
- #1447 got `needs: decision` on Nov 6, and a force-push dismissed
  davidbudnick's approval.
- #1727 is the tracking issue; #2412 (Lock from the Actions Ring) was closed
  as its duplicate: "on Windows the Lock Screen action is sent as a synthetic
  Win+L, which Windows ignores".
- A Windows 11 test report from Fred on #1447 (Lock and Sleep) is now the most
  useful single contribution here. It's on the fork as `pr/1447`.

**Keypad image fix #2322:** still open, no activity since Nov 3. AprilNEA's
#2473 (Nov 8) restructures the same `PendingQueue` code (one lifecycle state
per correlation key), so expect #2322 to need a rebase or rework on top of it.

**Other:**
- #2386: AprilNEA confirmed Previous/Next Desktop on Windows sends Win+Ctrl+←/→
  "as designed"; the reporter's problem was a separate wheel issue.
- #2416 / #2418 (merged): synthesized shortcuts no longer release a modifier
  the user holds, including Windows held chords.
- #1875, #1605, #2240 (Dialpad) and discussion #420: no maintainer movement.

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
