# Drafts for upstream (NOT posted)

Every block here needs Fred's explicit go-ahead on the exact text before it is
posted anywhere. Repo style: short, casual, problem-focused, English, no AI
attribution.

---

## A. Comment on #1875 (Windows test offer, editor gaps, overlap with #2422)

> Hi! I'm on Windows 11 with an MX Creative Keypad, an MX Master 4 and an MX
> Keys Mini over Bolt, and I'd be glad to test this on Windows. It changes
> Windows behaviour too (it hides Type Text, Run AppleScript and Sleep there),
> so a Windows pass seems worth having alongside the `platform: linux` label.
>
> Three gaps I noticed while comparing the editors on current master:
>
> 1. The Workflow step picker (`features/keyboard/editors.rs`) still offers
>    Type Text and AppleScript steps, which are skipped on Windows. Would a
>    `WorkflowStep::is_available_on` next to `Action::is_available_on` fit?
> 2. The editors still build their own Power User lists: the keyboard/keypad
>    panel lists all five (`function_row.rs`), the Ring editor gates only
>    AppleScript with `cfg!`, and the mouse picker offers Open app and Run
>    command. A shared Power User section filtered by your table could be a
>    small follow-up after this lands, so every editor offers the same set per
>    OS.
> 3. Heads-up on overlap: #2422 (opened Nov 6) also relabels Mission Control,
>    Launchpad and the desktop actions per OS, adds the same four locale keys
>    (`activities_overview`, `show_applications`, `previous_workspace`,
>    `next_workspace`), and filters App Exposé, but with `cfg!` branches in
>    `localized_action_label` instead of a table like your
>    `translation_key_on`. Whichever lands second will conflict. #2422 also
>    adds Windows names ("Task View", "Start Menu"), which would fit as
>    `Host::Windows` rows here. And App Exposé could be hidden on Windows too,
>    since it sends the same Win+Tab as Mission Control. Maybe worth agreeing
>    with @marcinhosh on one home for this?
>
> I'd also like to implement Windows `TypeText` (`SendInput` with
> `KEYEVENTF_UNICODE`), which would flip that cell of the Windows row. Is it
> better to land that after this PR?
>
> If the branch needs a rebase onto current master, I'm happy to help.

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

## D. Discussion (Ideas): letting your devices tell you things

Category: Ideas. Title: `Letting scripts use your devices to tell you things (keypad, haptics, lights)`

> A few moments I'd love OpenLogi to handle:
>
> - **A long build finishes while I'm in another window.** My MX Master 4
>   gives a short double tap. If it failed, the CI key on my Creative Keypad
>   turns red with an ✗.
> - **I join a call.** My Litra comes on, and the keypad's mic key shows
>   whether I'm muted, updating as I toggle it.
> - **I'm presenting.** One keypad key counts down the minutes I have left.
> - **I log in to a shared meeting-room PC.** Fn-lock is on for whatever
>   keyboard is plugged in (#2451 asks for this one).
>
> What these have in common: something outside OpenLogi knows an event
> happened, and the device I'm already touching is the nicest place to notice
> it. Today a script can change settings through `openlogi api`, but it can't
> buzz, light up or draw anything.
>
> How I'd hope it feels to use:
>
> - **I decide how things feel, not the script.** A script says what happened
>   ("build failed"), and my OpenLogi settings say what that looks or feels
>   like on each device: a tap on the mouse, a red key, both, or nothing.
>   Logitech's own plugin SDK does haptics this way: plugins raise named
>   events and a mapping picks the waveform per device.
> - **Nothing gets stuck.** Anything a script puts on a key or light is
>   temporary. It clears on its own after a while, or when the script says
>   so, and my configured layout comes back. A crashed script can't leave a
>   key red forever.
> - **I can see what's going on.** If a script is currently using a key, the
>   OpenLogi window shows it, so I'm never confused about why a key looks
>   different.
> - **Same on every computer.** The same script line works on macOS, Windows
>   and Linux, from a shell, PowerShell, a Stream Deck button or a Claude Code
>   hook.
> - **Nothing new running.** No extra background service, port or plugin
>   host; when no script calls it, it costs nothing.
>
> Under the hood I think this fits what's already there: one more
> `openlogi api` command per kind of output (#2060's `api haptic` is the first),
> going through the agent like everything else. I haven't built anything yet.
>
> Questions before anyone does:
>
> 1. Should scripts send *events* that my settings map to effects ("build
>    failed"), or ask for *effects* directly ("double tap", "make key 3 red")?
>    Or effects first, with events added later?
> 2. When a script takes over a keypad key, how long should it last by
>    default, and what should the OpenLogi window show for it?
> 3. Does this belong in OpenLogi at all, or is it better left to other tools
>    as long as OpenLogi exposes the basics?
>
> I'm on Windows 11 with an MX Creative Keypad, MX Master 4 and MX Keys Mini,
> and happy to prototype and test whichever direction you prefer.

---

## E. Comment on #2422 (overlap with #1875, Windows rows)

> Nice to see Windows names here too ("Task View", "Start Menu"). I tried to
> line this up with #1875, which is still open and adds a per-host table in
> `openlogi-core` (`Action::translation_key_on(Host)` and
> `Action::is_available_on(Host)`). The two PRs add the same four locale keys
> and both filter App Exposé, so whichever lands second will conflict. Could
> the labels and filtering here become rows in that table instead of `cfg!`
> branches in `localized_action_label` and `action_rows_with`? Then the
> pickers, the overlay and the Linux dispatcher all read one place.
>
> Two Windows notes, from Windows 11:
> - App Exposé is still offered on Windows, but it sends the same Win+Tab as
>   Mission Control (`inject/windows.rs`), so it's a duplicate there. Hiding it
>   on Windows, as this PR does on GNOME, would make sense.
> - The new gesture defaults apply on every OS, not just GNOME: Down moves
>   from Show Desktop to Launchpad (the Start menu on Windows), and Left/Right
>   from previous/next tab to previous/next desktop. Click moves from App
>   Exposé to Mission Control, which on Windows changes nothing (both were
>   already Win+Tab) but is a visible change on macOS. Was that intended
>   beyond Linux?
>
> Happy to test the Windows side once there's a direction.
