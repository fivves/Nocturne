#!/usr/bin/env bash
set -Eeuo pipefail

APP_BIN="nocturne"
APP_ID="com.jeffser.Nocturne"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX_WAS_SET="${PREFIX+x}"
PREFIX="${PREFIX:-$HOME/.local}"
BUILD_DIR="${BUILD_DIR:-$ROOT_DIR/build}"
MESON="${MESON:-meson}"
NINJA="${NINJA:-ninja}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MESON_SETUP_ARGS=(
  -Dupdate_icon_cache=false
)

STAMP="$(date +%Y%m%d%H%M%S)"
NEW_BUILD="${BUILD_DIR}.new.${STAMP}.$$"
OLD_BUILD="${BUILD_DIR}.old.${STAMP}.$$"

cleanup_failed_build() {
  if [[ -d "$NEW_BUILD" ]]; then
    rm -rf "$NEW_BUILD"
  fi
}
trap cleanup_failed_build ERR INT TERM

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    printf 'Missing required command: %s\n' "$1" >&2
    case "$1" in
      blueprint-compiler)
        printf 'On Arch Linux, install it with: sudo pacman -S blueprint-compiler\n' >&2
        ;;
    esac
    exit 1
  fi
}

is_arch_linux() {
  local os_id=""
  local os_id_like=""

  if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    os_id="${ID:-}"
    os_id_like="${ID_LIKE:-}"
  fi

  [[ "$os_id" == "arch" || " $os_id_like " == *" arch "* ]]
}

check_synced_lyrics_python_dependencies() {
  printf 'Checking synced lyrics Python dependencies with %s...\n' "$PYTHON_BIN"

  if "$PYTHON_BIN" - <<'PY'
import importlib
import inspect
import sys

deps = (
    ("syncedlyrics", "syncedlyrics", "syncedlyrics"),
    ("bs4", "beautifulsoup4", "python-beautifulsoup4"),
    ("rapidfuzz", "rapidfuzz", "python-rapidfuzz"),
    ("requests", "requests", "python-requests"),
)

missing = []
for module, package, arch_package in deps:
    try:
        importlib.import_module(module)
    except Exception as exc:
        missing.append((module, package, arch_package, exc))

if missing:
    print("Optional online synced lyrics support is unavailable:", file=sys.stderr)
    for module, package, arch_package, exc in missing:
        print(
            f"  - import {module!r} failed for {package} "
            f"(Arch: {arch_package}): {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    sys.exit(1)

import syncedlyrics

signature = inspect.signature(syncedlyrics.search)
required_parameters = {"enhanced", "save_path", "synced_only"}
missing_parameters = required_parameters.difference(signature.parameters)
if missing_parameters:
    print(
        "The installed syncedlyrics package is too old or incompatible; "
        f"missing search() parameters: {', '.join(sorted(missing_parameters))}",
        file=sys.stderr,
    )
    sys.exit(1)
PY
  then
    return 0
  fi

  if is_arch_linux; then
    cat >&2 <<'EOF'

Nocturne will still install and run. Jellyfin, Navidrome, local, and manually
saved lyrics still work; only online synced-lyrics downloads are disabled.

To enable online synced lyrics on Arch Linux, install the packaged dependencies:
  sudo pacman -S python-beautifulsoup4 python-rapidfuzz python-requests

Then install syncedlyrics into the Python interpreter used by Nocturne. For
example, install into a project venv and build Nocturne with that interpreter:
  python3 -m venv .venv
  .venv/bin/python -m pip install syncedlyrics
  PYTHON_BIN="$PWD/.venv/bin/python" ./install.sh

Note: pipx creates an isolated command environment. A standalone pipx install is
not importable by the Python interpreter that runs Nocturne.
EOF
  else
    cat >&2 <<'EOF'

Nocturne will still install and run. To enable online synced lyrics, install
these packages into the Python interpreter used by Nocturne:
  syncedlyrics beautifulsoup4 rapidfuzz requests
EOF
  fi
}

guard_default_prefix_sudo() {
  if [[ "${EUID:-$(id -u)}" -eq 0 && -n "${SUDO_USER:-}" && -z "$PREFIX_WAS_SET" ]]; then
    cat >&2 <<'EOF'
This installer defaults to PREFIX=$HOME/.local and should not be run with sudo.
Run it as your normal user:
  ./install.sh

To clean files from a previous accidental sudo install:
  sudo ./cleanup-sudo-install.sh --apply

For a system install, pass an explicit system prefix through sudo, for example:
  sudo env PREFIX=/usr/local ./install.sh
EOF
    exit 1
  fi
}

stop_running_nocturne() {
  printf 'Stopping running %s instances...\n' "$APP_BIN"

  if command -v gapplication >/dev/null 2>&1; then
    gapplication quit "$APP_ID" >/dev/null 2>&1 || true
    sleep 1
  fi

  pkill -x "$APP_BIN" >/dev/null 2>&1 || true
  pkill -f "$PREFIX/bin/$APP_BIN" >/dev/null 2>&1 || true
  pkill -f "$ROOT_DIR/nocturne-uninstalled" >/dev/null 2>&1 || true
}

prepare_install_dirs() {
  local icon_dir="$PREFIX/share/icons/hicolor"

  if [[ -e "$icon_dir/.icon-theme.cache" ]]; then
    printf 'Removing stale icon cache %s...\n' "$icon_dir/.icon-theme.cache"
    rm -f "$icon_dir/.icon-theme.cache"
  fi
}

refresh_icon_cache() {
  local icon_dir="$PREFIX/share/icons/hicolor"

  if [[ ! -d "$icon_dir" ]] || ! command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    return 0
  fi

  if [[ -e "$icon_dir/.icon-theme.cache" ]]; then
    printf 'Removing stale icon cache %s...\n' "$icon_dir/.icon-theme.cache"
    rm -f "$icon_dir/.icon-theme.cache"
  fi

  if ! gtk4-update-icon-cache -q -t -f -i "$icon_dir"; then
    printf 'Warning: could not refresh icon cache for %s; install completed anyway.\n' "$icon_dir" >&2
  fi
}

require_command "$MESON"
require_command "$NINJA"
require_command "$PYTHON_BIN"
require_command "blueprint-compiler"
require_command "glib-compile-resources"
require_command "glib-compile-schemas"

guard_default_prefix_sudo
check_synced_lyrics_python_dependencies

printf 'Configuring fresh build in %s...\n' "$NEW_BUILD"
"$MESON" setup "$NEW_BUILD" "$ROOT_DIR" --prefix="$PREFIX" "${MESON_SETUP_ARGS[@]}"

printf 'Compiling %s...\n' "$APP_BIN"
"$MESON" compile -C "$NEW_BUILD"

stop_running_nocturne

prepare_install_dirs

printf 'Installing to %s...\n' "$PREFIX"
"$MESON" install -C "$NEW_BUILD"

refresh_icon_cache

printf 'Launching %s...\n' "$APP_BIN"
"$PREFIX/bin/$APP_BIN" >/dev/null 2>&1 &
disown

if [[ -d "$BUILD_DIR" ]]; then
  mv "$BUILD_DIR" "$OLD_BUILD"
fi

mv "$NEW_BUILD" "$BUILD_DIR"
trap - ERR INT TERM

if [[ -d "$OLD_BUILD" ]]; then
  printf 'Removing old build directory %s...\n' "$OLD_BUILD"
  rm -rf "$OLD_BUILD"
fi

printf 'Done. Installed binary: %s/bin/%s\n' "$PREFIX" "$APP_BIN"
