# Building and checking OpenLogi in a cloud session

Personal notes (`fred/notes`). Results from 2026-11-04 on master `6466cd2`,
Ubuntu 24.04 x86_64, 4 vCPU / 15 GB, rustc 1.99.1.

## One-time setup

Paste `tools/fred/cloud-setup.sh` into the environment's **Setup script**
(cloud environment menu in the session title bar → Edit). It installs the
CI system libraries, MinGW (for the Windows lint), updates Rust stable, adds the
`wasm32-unknown-unknown` and `x86_64-pc-windows-gnu` targets, downloads pinned
typos / ast-grep / cargo-deny / prek, and warms the cargo cache. A first run in
a fresh container is a few minutes; a repeat run is ~5 s.

The image's default Rust (1.97) is too old: the workspace needs 1.99
(`rust-version` in `Cargo.toml`), so `rustup update stable` is not optional.

## What runs here, and the results

| Check | Command | Result | Time (warm-ish) |
|---|---|---|---|
| type-check everything | `cargo check --workspace --all-targets` | pass, 0 warnings | 6 min cold |
| Linux CI tests | `cargo test --workspace --exclude openlogi-desktop` | 3668 passed, 5 ignored — **1 environment failure**, see below | 6.5 min cold |
| desktop (GPUI) tests | `cargo test -p openlogi-desktop` | 783 passed (Linux CI doesn't run these; macOS CI does) | 3.5 min |
| Windows lint proxy | `cargo xtask ci clippy-windows` | pass | 1.3 min |
| full local CI | `cargo xtask ci` | 10 pass, 1 fail (`tests (linux)`, same IPv6 test), 4 skip | 11 min |

`cargo xtask ci` per job: rustfmt, typos, ast-grep, publish closure, shell,
clippy, MSRV (rustc 1.99), rustdoc, cargo-deny, wasm, and (after setup)
clippy (windows) proxy pass. **Skipped, by design** (another OS): tests (macos),
tests (windows), clippy (macos). Skipped is not passed.

### The one failure is the container, not the code

`openlogi-flow`'s `an_ipv6_wildcard_endpoint_takes_ipv4_and_ipv6_peers` fails
with `Io(Os { code: 97, … "Address family not supported by protocol" })`: this
container has no IPv6 at all (`/proc/net/if_inet6` is absent; a Python
`AF_INET6` socket fails the same way). GitHub's runners have IPv6, so it passes
in CI. To run everything else locally:

```sh
cargo test --workspace --exclude openlogi-desktop --no-fail-fast -- \
  --skip an_ipv6_wildcard_endpoint_takes_ipv4_and_ipv6_peers
```

`--no-fail-fast` matters: without it cargo stops at the first failing test
binary, which here hid 30 of the 43 suites.

## What this environment cannot tell you

- Anything `cfg(windows)` *at runtime*: `tests (windows)` and the real
  `clippy (windows)` job only run on Windows (your machine, or CI). The proxy
  above lints a subset of crates (`openlogi-core, -hidpp, -hid, -hook, -inject,
  -camera, -agent, -agent-core`) for the windows-gnu target.
- Anything macOS (`tests (macos)`, `clippy (macos)`, the desktop i18n
  end-to-end tests) — that's the MacBook later.
- Hardware. No HID devices exist here.

## Notes on the session's network

- `github.com` release downloads and `git` reads of public repos work.
- `api.github.com` (REST and GraphQL) returns 403 for repos not attached to the
  session — that's the session's per-repo GitHub gate, not the network level.
  `gh api search/…` works. Public issue/PR *web pages* can be read with a
  fetch, which is how the upstream comment threads were read.
