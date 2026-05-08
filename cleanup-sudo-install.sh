#!/usr/bin/env bash
set -Eeuo pipefail

APP_BIN="nocturne"
APP_ID="com.jeffser.Nocturne"
PROJECT_NAME="nocturne"

PREFIX="/root/.local"
APPLY=0

usage() {
  cat <<EOF
Usage: $0 [--apply] [--prefix PATH]

Removes files left behind by an accidental root-local install, usually from:
  sudo ./install.sh

Defaults to a dry run against:
  /root/.local

Options:
  --apply        Actually remove the listed files.
  --prefix PATH  Clean a different install prefix.
  -h, --help     Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply)
      APPLY=1
      shift
      ;;
    --prefix)
      if [[ $# -lt 2 ]]; then
        printf 'Missing value for --prefix\n' >&2
        exit 2
      fi
      PREFIX="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown argument: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ "$PREFIX" != /* ]]; then
  printf 'Prefix must be an absolute path: %s\n' "$PREFIX" >&2
  exit 2
fi

if [[ "$PREFIX" == "/" || "$PREFIX" == "/usr" || "$PREFIX" == "/usr/local" ]]; then
  cat >&2 <<EOF
Refusing to clean broad system prefix: $PREFIX

This script is intended for accidental root-local installs. If you need a system
uninstall, use the original Meson build metadata or remove files manually.
EOF
  exit 2
fi

paths=(
  "$PREFIX/bin/$APP_BIN"
  "$PREFIX/share/$PROJECT_NAME"
  "$PREFIX/share/applications/$APP_ID.desktop"
  "$PREFIX/share/metainfo/$APP_ID.metainfo.xml"
  "$PREFIX/share/glib-2.0/schemas/$APP_ID.gschema.xml"
  "$PREFIX/share/dbus-1/services/$APP_ID.service"
  "$PREFIX/share/icons/hicolor/scalable/apps/$APP_ID.svg"
  "$PREFIX/share/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"
)

shopt -s nullglob
locale_files=("$PREFIX"/share/locale/*/LC_MESSAGES/nocturne.mo)
shopt -u nullglob
paths+=("${locale_files[@]}")

existing=()
for path in "${paths[@]}"; do
  if [[ -e "$path" ]]; then
    existing+=("$path")
  fi
done

if [[ ${#existing[@]} -eq 0 ]]; then
  printf 'No Nocturne install files found under %s\n' "$PREFIX"
  exit 0
fi

if [[ "$APPLY" -ne 1 ]]; then
  printf 'Dry run. These files would be removed from %s:\n' "$PREFIX"
  printf '  %s\n' "${existing[@]}"
  printf '\nRun with --apply to remove them:\n'
  printf '  sudo %s --apply\n' "$0"
  exit 0
fi

printf 'Removing Nocturne install files from %s...\n' "$PREFIX"
rm -rf -- "${existing[@]}"

if command -v glib-compile-schemas >/dev/null 2>&1 && [[ -d "$PREFIX/share/glib-2.0/schemas" ]]; then
  glib-compile-schemas "$PREFIX/share/glib-2.0/schemas" >/dev/null 2>&1 || true
fi

if command -v gtk4-update-icon-cache >/dev/null 2>&1 && [[ -d "$PREFIX/share/icons/hicolor" ]]; then
  gtk4-update-icon-cache -q -t -f -i "$PREFIX/share/icons/hicolor" >/dev/null 2>&1 || true
fi

if command -v update-desktop-database >/dev/null 2>&1 && [[ -d "$PREFIX/share/applications" ]]; then
  update-desktop-database "$PREFIX/share/applications" >/dev/null 2>&1 || true
fi

printf 'Done. Cleaned accidental install prefix: %s\n' "$PREFIX"
