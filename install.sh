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
PYTHON_PATH=""
INSTALL_DEPS="${INSTALL_DEPS:-ask}"
PYTHON_VENV="${PYTHON_VENV:-$PREFIX/lib/nocturne/venv}"
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
      meson)
        printf 'On Arch Linux, install it with: sudo pacman -S meson\n' >&2
        ;;
      ninja)
        printf 'On Arch Linux, install it with: sudo pacman -S ninja\n' >&2
        ;;
      blueprint-compiler)
        printf 'On Arch Linux, install it with: sudo pacman -S blueprint-compiler\n' >&2
        ;;
      glib-compile-resources|glib-compile-schemas)
        printf 'On Arch Linux, install it with: sudo pacman -S glib2\n' >&2
        ;;
    esac
    exit 1
  fi
}

resolve_python() {
  if ! PYTHON_PATH="$(command -v "$PYTHON_BIN")"; then
    printf 'Missing required command: %s\n' "$PYTHON_BIN" >&2
    exit 1
  fi

  PYTHON_BIN="$PYTHON_PATH"
}

print_required_dependency_help() {
  cat >&2 <<'EOF'

Nocturne cannot be installed because the Python and system libraries needed to
launch it are not all available to the interpreter that will run the installed
app.

Install the missing packages, then run ./install.sh again.

To let the installer try the dependency setup itself, run:
  INSTALL_DEPS=1 ./install.sh
EOF

  if is_arch_linux; then
    cat >&2 <<'EOF'

Arch Linux package starting point:
  sudo pacman -S python-gobject gtk4 libadwaita libsecret gstreamer \
    gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly \
    python-requests python-urllib3 python-pillow python-cairo

Python packages that may need pip/AUR if your distro does not package them:
  tinytag colorthief mpris-server syncedlyrics beautifulsoup4 rapidfuzz
EOF
  else
    cat >&2 <<'EOF'

Required runtime families:
  Python GObject bindings, GTK 4, libadwaita 1, libsecret, GStreamer,
  GStreamer base/good/bad/ugly plugins, requests, urllib3, Pillow, pycairo,
  tinytag, colorthief, and mpris-server.
EOF
  fi
}

should_install_dependencies() {
  case "${INSTALL_DEPS,,}" in
    1|yes|true|on)
      return 0
      ;;
    0|no|false|off)
      return 1
      ;;
  esac

  if [[ ! -t 0 ]]; then
    return 1
  fi

  local answer=""
  printf 'Install missing dependencies now? [y/N] '
  read -r answer
  [[ "${answer,,}" == "y" || "${answer,,}" == "yes" ]]
}

install_required_dependencies() {
  if ! should_install_dependencies; then
    return 1
  fi

  if is_arch_linux; then
    cat <<'EOF'
Installing Arch system dependencies with pacman...
EOF
    sudo pacman -S --needed \
      python-gobject gtk4 libadwaita libsecret gstreamer \
      gst-plugins-base gst-plugins-good gst-plugins-bad gst-plugins-ugly \
      python-requests python-urllib3 python-pillow python-cairo
  else
    cat >&2 <<'EOF'
Automatic system dependency installation is only implemented for Arch Linux.
The installer will still try to set up Python-only dependencies in a venv, but
GTK, libadwaita, libsecret, and GStreamer must come from your distro packages.
EOF
  fi

  printf 'Creating Python environment in %s...\n' "$PYTHON_VENV"
  "$PYTHON_BIN" -m venv --system-site-packages "$PYTHON_VENV"

  install_venv_python_dependencies

  PYTHON_BIN="$PYTHON_VENV/bin/python"
}

install_venv_python_dependencies() {
  printf 'Installing Nocturne Python dependencies into %s...\n' "$PYTHON_VENV"
  "$PYTHON_VENV/bin/python" -m pip install \
    requests urllib3 pillow tinytag colorthief mpris-server \
    syncedlyrics beautifulsoup4 rapidfuzz
}

check_required_launch_dependencies() {
  printf 'Checking required launch dependencies with %s...\n' "$PYTHON_BIN"

  if "$PYTHON_BIN" - <<'PY'
import importlib
import sys

missing = []

def check_python(module, package):
    try:
        importlib.import_module(module)
    except Exception as exc:
        missing.append((package, f"import {module!r}", exc))

def check_gi(namespace, version, package):
    try:
        import gi
        gi.require_version(namespace, version)
        importlib.import_module(f"gi.repository.{namespace}")
    except Exception as exc:
        missing.append((package, f"GI {namespace} {version}", exc))

if sys.version_info < (3, 13):
    print(
        "Python 3.13 or newer is required; "
        f"{sys.executable} is {sys.version.split()[0]}",
        file=sys.stderr,
    )
    sys.exit(1)

for namespace, version, package in (
    ("Gtk", "4.0", "GTK 4 / Python GObject bindings"),
    ("Adw", "1", "libadwaita 1 typelibs"),
    ("Secret", "1", "libsecret typelibs"),
    ("Gst", "1.0", "GStreamer typelibs"),
):
    check_gi(namespace, version, package)

for module, package in (
    ("requests", "requests"),
    ("urllib3", "urllib3"),
    ("PIL", "Pillow"),
    ("tinytag", "tinytag"),
    ("cairo", "pycairo"),
    ("colorthief", "colorthief"),
    ("mpris_server", "mpris-server"),
    ("mpris_server.server", "mpris-server runtime dependencies"),
):
    check_python(module, package)

if not any(package == "GStreamer typelibs" for package, _, _ in missing):
    try:
        from gi.repository import Gst

        Gst.init(None)
        for element in ("playbin", "equalizer-nbands", "rgvolume", "rglimiter", "spectrum"):
            if Gst.ElementFactory.find(element) is None:
                missing.append((
                    "GStreamer plugins",
                    f"GStreamer element {element!r}",
                    RuntimeError("element factory not found"),
                ))
    except Exception as exc:
        missing.append(("GStreamer runtime", "Gst.init()", exc))

if missing:
    print("Missing required launch dependencies:", file=sys.stderr)
    for package, check, exc in missing:
        print(
            f"  - {package}: {check} failed: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
    sys.exit(1)
PY
  then
    return 0
  fi

  return 1
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
  local allow_install="${1:-1}"

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

  if [[ "$allow_install" == "1" ]] && should_install_dependencies; then
    if [[ "$PYTHON_BIN" != "$PYTHON_VENV/bin/python" ]]; then
      printf 'Creating Python environment in %s...\n' "$PYTHON_VENV"
      "$PYTHON_BIN" -m venv --system-site-packages "$PYTHON_VENV"
      PYTHON_BIN="$PYTHON_VENV/bin/python"
    fi

    install_venv_python_dependencies
    check_synced_lyrics_python_dependencies 0
    return
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

remove_icon_cache_if_possible() {
  local cache_path="$1"

  if [[ ! -e "$cache_path" ]]; then
    return 0
  fi

  printf 'Removing stale icon cache %s...\n' "$cache_path"
  if ! rm -f "$cache_path"; then
    printf 'Warning: could not remove stale icon cache %s; continuing.\n' "$cache_path" >&2
  fi
}

prepare_install_dirs() {
  local icon_dir="$PREFIX/share/icons/hicolor"

  remove_icon_cache_if_possible "$icon_dir/.icon-theme.cache"
}

refresh_icon_cache() {
  local icon_dir="$PREFIX/share/icons/hicolor"

  if [[ ! -d "$icon_dir" ]] || ! command -v gtk4-update-icon-cache >/dev/null 2>&1; then
    return 0
  fi

  remove_icon_cache_if_possible "$icon_dir/.icon-theme.cache"

  if ! gtk4-update-icon-cache -q -t -f -i "$icon_dir"; then
    printf 'Warning: could not refresh icon cache for %s; install completed anyway.\n' "$icon_dir" >&2
  fi
}

require_command "$MESON"
require_command "$NINJA"
resolve_python
require_command "blueprint-compiler"
require_command "glib-compile-resources"
require_command "glib-compile-schemas"

guard_default_prefix_sudo
if ! check_required_launch_dependencies; then
  if install_required_dependencies; then
    check_required_launch_dependencies || {
      print_required_dependency_help
      exit 1
    }
  else
    print_required_dependency_help
    exit 1
  fi
fi
check_synced_lyrics_python_dependencies

printf 'Configuring fresh build in %s...\n' "$NEW_BUILD"
PATH="$(dirname "$PYTHON_BIN"):$PATH" "$MESON" setup "$NEW_BUILD" "$ROOT_DIR" --prefix="$PREFIX" "${MESON_SETUP_ARGS[@]}"

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
