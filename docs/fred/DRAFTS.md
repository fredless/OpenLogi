# Drafts for upstream (NOT posted)

Every block here needs Fred's explicit go-ahead on the exact text before it is
posted anywhere. Repo style: short, casual, problem-focused, English, no AI
attribution.

---

## A. Comment on [#1875](https://github.com/AprilNEA/OpenLogi/pull/1875) (POSTED by Fred, 2026-11-09, his wording)

Context: [#1875](https://github.com/AprilNEA/OpenLogi/pull/1875) was 349 commits behind master and conflicted in 5 files
(`binding_editor.rs`, `function_row.rs`, `services/i18n/tests.rs`,
`inject/linux.rs`, overlay `ring.rs`); no maintainer review since Oct 17.

> Still interested in this one? It now conflicts with master, and #2422 adds
> overlapping labels and App Exposé filtering (commented there). Happy to test
> on Windows if it gets rebased. But also, a gap I noticed: workflow step picker
> still offers Type Texmat/AppleScript steps on Windows.

---

## B. Heads-up to AlexanderYW (where: a comment on [#1873](https://github.com/AprilNEA/OpenLogi/pull/1873), or wherever he prefers)

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

## D. Discussion (Ideas): one API for external triggering

Category: Ideas. Title: `One API for external triggers: api JSON as the contract, transports as adapters`

> Would like one consistent way to trigger devices from outside (MX Master 4
> haptic, keypad key status, Litra, backlight), not a new surface per feature.
> Today `openlogi api` covers settings only; haptics are being added
> separately (#2060), events too (#1821).
>
> Proposal: the `api` JSON envelope (`schema_version`, `ok`, `data`/`error`)
> is the single public contract. Transports are thin adapters around one
> dispatcher.
>
> 1. **One request type.** Derive `Deserialize` on the existing `ApiCommand`
>    (`cmd/api.rs`) so argv and JSON produce the same typed request, and the
>    one `match` that dispatches it stays the only dispatcher. No
>    `execute(String, JSON)`; unknown commands are rejected.
>    ```json
>    {"id":7,"command":"haptic","device":"<id from api devices>","args":{"waveform":"damp_collision"}}
>    {"id":7,"schema_version":1,"ok":true,"data":{"queued":true}}
>    ```
> 2. **Transports, in order:**
>    - CLI (today, unchanged behaviour)
>    - `openlogi api --stdin`: NDJSON requests in, replies out, one agent
>      connection. Covers high-rate use (keypad animation, counters) with no
>      listener.
>    - later, opt-in `openlogi api serve --listen <unix socket | named pipe |
>      127.0.0.1:port>`: its own process, an ordinary `ClientKind::Cli`-style
>      agent client. The agent gains no listener; anything network-facing
>      needs a token (and is off by default).
> 3. **Outputs** are typed agent IPC methods, one per capability, appended
>    to the wire as usual: haptic (#2060), light / backlight / lighting (IPC
>    exists: `set_light`, `set_backlight`, `set_lighting`), keypad key face
>    (new). Effects from scripts are temporary: a TTL or explicit clear, then
>    the configured state comes back, and the GUI shows what's overridden.
> 4. **Events** use the same envelope as a stream: `api watch` on stdout/stdin
>    or the socket, over the existing `observe` long-poll (generalises #1821).
> 5. **Addressing:** device IDs from `api devices`, plus a selector by kind or
>    capability (#2451: `--device keyboard`).
>
> Phasing:
> 1. Refactor to request type + dispatcher, no behaviour change.
> 2. `--stdin`.
> 3. Output commands.
> 4. `watch`.
> 5. `serve`.
>
> Each step is shippable. Direction ok, or would you rather this wait for
> #1657's capability model? Happy to prototype on Windows.

---

## E. Comment on [#2422](https://github.com/AprilNEA/OpenLogi/pull/2422) (POSTED by Fred, 2026-11-08, his wording)

> thanks for dropping Windows function names in here too! Trying line this up
> with #1875, which adds a per-host table in openlogi-core. These two both add
> the same four OS keys and both filter App Exposé, so conflict. Could the
> labels and filtering here become rows in the #1875 table instead of cfg!
> branches in localized_action_label and action_rows_with? pickers, overlay and
> dispatcher could then all read one place.

Not raised yet (candidates for a follow-up): App Exposé still offered on
Windows (duplicates Task View); the gesture-default change applies on every OS,
not just GNOME.
