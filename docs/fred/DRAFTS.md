# Drafts for upstream (NOT posted)

Every block here needs Fred's explicit go-ahead on the exact text before it is
posted anywhere. Repo style: short, casual, problem-focused, English, no AI
attribution.

---

## A. Comment on #1875 (Windows test offer, editor gaps)

> Hi! I'm on Windows 11 with an MX Creative Keypad, an MX Master 4 and an MX
> Keys Mini over Bolt, and I'd be glad to test this on Windows. It changes
> Windows behaviour too (it hides Type Text, Run AppleScript and Sleep there),
> so a Windows pass seems worth having alongside the `platform: linux` label.
>
> Two gaps I noticed while comparing the editors on current master:
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

## D. Discussion (Ideas): a shape for driving device outputs from scripts

Category: Ideas. Title: `Driving device outputs from scripts: one api verb per capability?`

> I'd like scripts to drive device *outputs*: a status image on an MX Creative
> Keypad key, a Litra on when a call starts, a keyboard backlight flash, a haptic
> tap when a build finishes. Before building anything I'd like to check the
> intended shape.
>
> From reading the code and #2060 / #1821 / #1657, the pattern seems to be one
> typed IPC method per capability, exposed as an `openlogi api <capability>`
> subcommand: same JSON envelope, device IDs from `api devices`, no new socket
> or listener. #2060's `api haptic` already follows it.
>
> Concretely:
> 1. `api light` / `api backlight` / `api lighting` over the existing
>    `set_light` / `set_backlight` / `set_lighting` calls. (Side note:
>    `openlogi light` currently opens the HID device directly instead of going
>    through the agent.)
> 2. For the keypad, a transient per-key face override (image or text) with a
>    clear/TTL, layered over the binding faces, plus
>    `api keypad-face --device <id> --key <n> --image <file> | --clear`.
>
> Questions:
> - Is "a typed `api` verb per output capability" the direction you want, or
>   would you rather this wait for the peripheral/capability work in #1657?
> - Should external overrides have shared lease semantics (owner, TTL, restore)
>   across devices, or be decided per capability?
>
> I can implement and test on Windows 11 (keypad, MX Master 4, MX Keys Mini).
