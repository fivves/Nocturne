#!/usr/bin/env bash
set -Eeuo pipefail

APP_BIN="nocturne"
APP_ID="com.jeffser.Nocturne"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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

check_pipx_syncedlyrics_environment() {
  if ! is_arch_linux || ! command -v pipx >/dev/null 2>&1; then
    return 0
  fi

  if ! pipx list --short 2>/dev/null | grep -qx 'syncedlyrics'; then
    return 0
  fi

  printf 'Checking pipx syncedlyrics environment...\n'
  if ! pipx runpip syncedlyrics check; then
    printf 'pipx syncedlyrics has broken Python dependencies. Reinstall it with: pipx reinstall syncedlyrics\n' >&2
    exit 1
  fi
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
    print("Missing or broken synced lyrics Python dependencies:", file=sys.stderr)
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
    check_pipx_syncedlyrics_environment
    return 0
  fi

  if is_arch_linux; then
    cat >&2 <<'EOF'

On Arch Linux, install the packaged dependencies first:
  sudo pacman -S python-beautifulsoup4 python-rapidfuzz python-requests

Then install syncedlyrics into the Python environment used by Nocturne.
If you use pipx, verify its environment with:
  sudo pacman -S python-pipx
  pipx install syncedlyrics
  pipx runpip syncedlyrics check

Note: pipx creates an isolated environment. A standalone pipx install is not
automatically importable by the python3 interpreter used by this Meson install.
EOF
  else
    cat >&2 <<'EOF'

Install the missing Python packages before running this installer again:
  syncedlyrics beautifulsoup4 rapidfuzz requests
EOF
  fi

  exit 1
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
