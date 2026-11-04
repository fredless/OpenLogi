#!/usr/bin/env bash
# Prepare a Claude Code cloud session (Ubuntu 24.04, x86_64) to build, test,
# and lint OpenLogi the way `.github/workflows/ci.yml` does on Linux.
#
# Paste the body into the environment's Setup script (cloud environment menu →
# Edit → Setup script). It is idempotent: a second run only re-checks.
# It cannot read the environment's secrets, and needs none.
#
# Versions: typos and ast-grep are pinned to what ci.yml pins; cargo-deny and
# prek follow their latest release, as CI's install-action and devenv do.
set -euo pipefail

TYPOS_VERSION=1.49.0   # ci.yml: crate-ci/typos@… # v1.49.0
AST_GREP_VERSION=0.45.1 # ci.yml: ast-grep/action with version 0.45.1

log() { printf '\n==> %s\n' "$*"; }

as_root() {
	if [ "$(id -u)" -eq 0 ]; then "$@"; else sudo "$@"; fi
}

# ── System libraries (the exact list from ci.yml's Linux jobs) + shell lint ──
APT_PACKAGES=(
	libudev-dev gcc g++ clang libfontconfig-dev libwayland-dev
	libxkbcommon-x11-dev libx11-xcb-dev libssl-dev libzstd-dev pkg-config
	shellcheck shfmt
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
rustup target add wasm32-unknown-unknown --toolchain stable

# ── CI tools as prebuilt binaries (cargo-binstall falls back to compiling) ──
if ! command -v cargo-binstall >/dev/null 2>&1; then
	log "cargo-binstall: installing"
	cargo install --locked cargo-binstall
fi

have_version() { # have_version <binary> <version>
	command -v "$1" >/dev/null 2>&1 && "$1" --version 2>/dev/null | grep -qF "$2"
}

if ! have_version typos "$TYPOS_VERSION"; then
	log "typos $TYPOS_VERSION"
	cargo binstall --no-confirm --force "typos-cli@$TYPOS_VERSION"
fi
# The crate is ast-grep; its binary is `ast-grep` (it also ships `sg`, which
# collides with shadow-utils' /usr/bin/sg — always call `ast-grep`).
if ! have_version ast-grep "$AST_GREP_VERSION"; then
	log "ast-grep $AST_GREP_VERSION"
	cargo binstall --no-confirm --force "ast-grep@$AST_GREP_VERSION"
fi
for tool in cargo-deny prek; do
	if ! command -v "$tool" >/dev/null 2>&1; then
		log "$tool"
		cargo binstall --no-confirm "$tool"
	fi
done

# ── Warm the dependency cache when run from a checkout ──────────────────────
if [ -f Cargo.lock ] && grep -q 'name = "openlogi"' Cargo.lock; then
	log "cargo fetch"
	cargo fetch --locked
fi

log "done: $(rustc --version); typos $(typos --version | cut -d' ' -f2); ast-grep $(ast-grep --version | cut -d' ' -f2)"
