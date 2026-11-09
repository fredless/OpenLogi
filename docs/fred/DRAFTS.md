# Drafts for upstream (NOT posted)

Every block here needs Fred's explicit go-ahead on the exact text before it is
posted anywhere. Repo style: short, casual, problem-focused, English, no AI
attribution.

---

## A. Comment on #1875 (optional, short; Fred commented on #2422 instead)

Context (2026-11-09): #1875 is 349 commits behind master and conflicts in 5
files (`binding_editor.rs`, `function_row.rs`, `services/i18n/tests.rs`,
`inject/linux.rs`, overlay `ring.rs`). No maintainer review since Oct 17.

> Still interested in this one? It now conflicts with master, and #2422 adds
> overlapping labels and App Exposé filtering (commented there). Happy to test
> on Windows if it gets rebased. Gap I noticed: Workflow step picker still
> offers Type Text/AppleScript steps on Windows.

---

## B. Heads-up to AlexanderYW (where: a comment on #1873, or wherever he prefers)

> Hey Alexander, thanks for the keypad work — it's running on Windows now
> after #2283/#2322. I'm planning to look at Windows parity for the Power
> User actions (Type Text via SendInput) and help test #1875, nothing
> keypad-specific. If you're working on keypad features next, what's on your
> list? Happy to test them on Windows so we don't overlap.

---

## C. Feature issue (only if the maintainers want a separate issue for candidate 2)

Title: `[Feature]: Windows: implement TypeText (SendInput KEYEVENTF_UNICODE)`

> `Action::TypeText` only logs `TypeText injection is not implemented on
> Windows yet` (`crates/openlogi-inject/src/inject/windows.rs`), so Type Text
> bindings and Workflow Type Text steps do nothing on Windows, while the
> Actions Ring editor and the keyboard/keypad panels offer them.
>
> Proposal: send each UTF-16 code unit as a `KEYEVENTF_UNICODE` key down/up
> pair through `SendInput` (surrogate pairs as two units), going through
> the shared `with_held_modifiers` helper the macOS path uses. Then mark `TypeText` available on Windows
> in #1875's table.
>
> I can implement and test on Windows 11 (Notepad, browser, emoji and
> non-Latin text).

---

## D. Discussion (Ideas): device outputs from scripts

Category: Ideas. Title: `Device outputs from scripts (keypad, haptics, lights)`

> Would like scripts to use devices for signals: keypad key shows build status
> or mute state, MX Master 4 taps when a job finishes, Litra on when a call
> starts. Today `openlogi api` only changes settings; it can't buzz, light or
> draw.
>
> #2060's `api haptic` looks like the pattern: one `api` command per output,
> through the agent, nothing new running. Script changes should be temporary
> (clear on timeout, layout comes back) and visible in the GUI.
>
> Open questions: should scripts send events that config maps to effects
> ("build failed" → tap + red key), or effects directly? And is this in scope
> for OpenLogi? Happy to prototype/test on Windows.

---

## E. Comment on #2422 (POSTED by Fred, 2026-11-08, his wording)

> thanks for dropping Windows function names in here too! Trying line this up
> with #1875, which adds a per-host table in openlogi-core. These two both add
> the same four OS keys and both filter App Exposé, so conflict. Could the
> labels and filtering here become rows in the #1875 table instead of cfg!
> branches in localized_action_label and action_rows_with? pickers, overlay and
> dispatcher could then all read one place.

Not raised yet (candidates for a follow-up): App Exposé still offered on
Windows (duplicates Task View); the gesture-default change applies on every OS,
not just GNOME.
