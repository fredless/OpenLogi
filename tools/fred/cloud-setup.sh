#!/usr/bin/env bash
# Prepare a Claude Code cloud session (Ubuntu 24.04, x86_64) to build, test,
# and lint OpenLogi the way `.github/workflows/ci.yml` does on Linux.
#
# Paste the body into the environment's Setup script (cloud environment menu →
# Edit → Setup script). It is idempotent: a second run only re-checks.
# It cannot read the environment's secrets, and needs none.
#
# Versions: typos and ast-grep match what ci.yml pins; cargo-deny and prek are
# pinned to the releases current on 2026-11-04 (CI and devenv use latest).
set -euo pipefail

TYPOS_VERSION=1.49.0      # ci.yml: crate-ci/typos@… # v1.49.0
AST_GREP_VERSION=0.45.1   # ci.yml: ast-grep/action with version 0.45.1
CARGO_DENY_VERSION=0.20.2 # CI installs latest; bump by hand
PREK_VERSION=0.5.10       # devenv ships latest; bump by hand

log() { printf '\n==> %s\n' "$*"; }

as_root() {
  if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# ── System libraries (the exact list from ci.yml's Linux jobs) + shell lint ──
APT_PACKAGES=(
  libudev-dev gcc g++ clang libfontconfig-dev libwayland-dev
  libxkbcommon-x11-dev libx11-xcb-dev libssl-dev libzstd-dev pkg-config
  shellcheck shfmt unzip curl
  # The C cross compiler `ring` needs for `cargo xtask ci clippy-windows`.
  gcc-mingw-w64-x86-64
)
missing=()
for pkg in "${APT_PACKAGES[@]}"; do
  dpkg -s "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
done
if [ "${#missing[@]}" -gt 0 ]; then
  log "apt: installing ${missing[*]}"
  as_root env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
else
  log "apt: all packages present"
fi

# ── Rust toolchain ──────────────────────────────────────────────────────────
# rust-toolchain.toml pins `stable`; the workspace's rust-version tracks current
# stable, so an image with an older stable cannot build it until updated.
export PATH="$HOME/.cargo/bin:$PATH"
if ! command -v rustup >/dev/null 2>&1; then
  log "rustup: installing"
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
fi
log "rustup: updating stable"
rustup update stable --no-self-update
rustup component add rustfmt clippy --toolchain stable
# wasm: the portable-crates CI job. windows-gnu: the clippy (windows) proxy,
# the only local lint of `cfg(windows)` code.
rustup target add wasm32-unknown-unknown x86_64-pc-windows-gnu --toolchain stable

# ── CI tools as pinned prebuilt binaries ─────────────────────────────────────
# Downloaded straight from each project's GitHub release. (cargo-binstall would
# need api.github.com, which the session proxy refuses, and then compiles every
# tool from source for ~15 minutes.) `cargo install` is only the fallback.
BIN_DIR="$HOME/.cargo/bin"
GH=https://github.com

have_version() { # have_version <binary> <version>
  command -v "$1" >/dev/null 2>&1 && "$1" --version 2>/dev/null | grep -qF "$2"
}

# fetch_tool <binary> <version> <release-asset-url> <cargo-install-args…>
fetch_tool() {
  local bin=$1 version=$2 url=$3
  shift 3
  have_version "$bin" "$version" && return 0
  log "$bin $version"
  local tmp
  tmp=$(mktemp -d)
  if curl -fsSL --retry 3 -o "$tmp/asset" "$url"; then
    case "$url" in
      *.zip) unzip -q -o "$tmp/asset" -d "$tmp/x" ;;
      *) mkdir -p "$tmp/x" && tar -xzf "$tmp/asset" -C "$tmp/x" ;;
    esac
    install -m 0755 "$(find "$tmp/x" -type f -name "$bin" | head -n1)" "$BIN_DIR/$bin"
  else
    log "$bin: download failed, compiling with cargo install"
    cargo install --locked "$@"
  fi
  rm -rf "$tmp"
  have_version "$bin" "$version"
}

fetch_tool typos "$TYPOS_VERSION" \
  "$GH/crate-ci/typos/releases/download/v$TYPOS_VERSION/typos-v$TYPOS_VERSION-x86_64-unknown-linux-musl.tar.gz" \
  "typos-cli@$TYPOS_VERSION"
# Its binary is `ast-grep`; the `sg` alias collides with shadow-utils'
# /usr/bin/sg, so always call `ast-grep`.
fetch_tool ast-grep "$AST_GREP_VERSION" \
  "$GH/ast-grep/ast-grep/releases/download/$AST_GREP_VERSION/app-x86_64-unknown-linux-gnu.zip" \
  "ast-grep@$AST_GREP_VERSION"
fetch_tool cargo-deny "$CARGO_DENY_VERSION" \
  "$GH/EmbarkStudios/cargo-deny/releases/download/$CARGO_DENY_VERSION/cargo-deny-$CARGO_DENY_VERSION-x86_64-unknown-linux-musl.tar.gz" \
  "cargo-deny@$CARGO_DENY_VERSION"
fetch_tool prek "$PREK_VERSION" \
  "$GH/j178/prek/releases/download/v$PREK_VERSION/prek-x86_64-unknown-linux-musl.tar.gz" \
  "prek@$PREK_VERSION"

# ── Warm the dependency cache when run from a checkout ──────────────────────
if [ -f Cargo.lock ] && grep -q 'name = "openlogi"' Cargo.lock; then
  log "cargo fetch"
  cargo fetch --locked
fi

log "done: $(rustc --version); typos $(typos --version | cut -d' ' -f2); ast-grep $(ast-grep --version | cut -d' ' -f2)"
