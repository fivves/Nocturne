#!/usr/bin/env bash
set -Eeuo pipefail

APP_BIN="nocturne"
APP_ID="com.jeffser.Nocturne"
PROJECT_NAME="nocturne"
SECRET_SCHEMA="com.jeffser.Nocturne.Password"

APPLY=0
UNINSTALL_FLATPAK=0
SKIP_SYSTEM=0
SUDO="${SUDO:-sudo}"

prefixes=()

usage() {
  cat <<EOF
Usage: $0 [--yes] [--flatpak] [--prefix PATH] [--skip-system]

Completely removes Nocturne install files and user state.

By default this is a dry run. Pass --yes to actually remove files.

Options:
  --yes          Actually remove everything found.
  --flatpak      Also uninstall the Flatpak app and delete its data if present.
  --prefix PATH  Remove Nocturne from this install prefix. Can be repeated.
                 Defaults to: \$HOME/.local, /usr/local, /usr, /root/.local
  --skip-system  Only remove user-owned files and settings.
  -h, --help     Show this help.

Environment:
  SUDO=doas      Use a different privilege command for system-owned files.
EOF
}

add_default_prefixes() {
  prefixes+=("$HOME/.local")
  prefixes+=("/usr/local")
  prefixes+=("/usr")
  prefixes+=("/root/.local")
}

quote_args() {
  printf ' %q' "$@"
}

run_cmd() {
  if [[ "$APPLY" -eq 1 ]]; then
    "$@"
  else
    printf 'Would run:'
    quote_args "$@"
    printf '\n'
  fi
}

run_root_cmd() {
  if [[ "$(id -u)" -eq 0 ]]; then
    run_cmd "$@"
    return
  fi

  run_cmd "$SUDO" "$@"
}

run_prefix_cmd() {
  local prefix=$1
  shift

  if [[ "$prefix" == "$HOME" || "$prefix" == "$HOME"/* || -w "$prefix" ]]; then
    run_cmd "$@"
  else
    run_root_cmd "$@"
  fi
}

remove_paths() {
  local -a user_paths=()
  local -a root_paths=()
  local path

  for path in "$@"; do
    [[ -e "$path" || -L "$path" ]] || continue

    if [[ "$path" == "$HOME" || "$path" == "$HOME"/* || -w "$(dirname "$path")" ]]; then
      user_paths+=("$path")
    else
      root_paths+=("$path")
    fi
  done

  if [[ ${#user_paths[@]} -gt 0 ]]; then
    run_cmd rm -rf -- "${user_paths[@]}"
  fi

  if [[ ${#root_paths[@]} -gt 0 ]]; then
    run_root_cmd rm -rf -- "${root_paths[@]}"
  fi
}

remove_matching_files() {
  local glob=$1
  local -a matches=()

  shopt -s nullglob
  matches=($glob)
  shopt -u nullglob

  if [[ ${#matches[@]} -gt 0 ]]; then
    remove_paths "${matches[@]}"
  fi
}

prefix_install_paths() {
  local prefix=$1
  printf '%s\n' \
    "$prefix/bin/$APP_BIN" \
    "$prefix/share/$PROJECT_NAME" \
    "$prefix/share/applications/$APP_ID.desktop" \
    "$prefix/share/metainfo/$APP_ID.metainfo.xml" \
    "$prefix/share/glib-2.0/schemas/$APP_ID.gschema.xml" \
    "$prefix/share/dbus-1/services/$APP_ID.service" \
    "$prefix/share/icons/hicolor/scalable/apps/$APP_ID.svg" \
    "$prefix/share/icons/hicolor/symbolic/apps/$APP_ID-symbolic.svg"
}

refresh_prefix_caches() {
  local prefix=$1

  if command -v glib-compile-schemas >/dev/null 2>&1 && [[ -d "$prefix/share/glib-2.0/schemas" ]]; then
    run_prefix_cmd "$prefix" glib-compile-schemas "$prefix/share/glib-2.0/schemas"
  fi

  if command -v gtk4-update-icon-cache >/dev/null 2>&1 && [[ -d "$prefix/share/icons/hicolor" ]]; then
    run_prefix_cmd "$prefix" gtk4-update-icon-cache -q -t -f "$prefix/share/icons/hicolor"
  elif command -v gtk-update-icon-cache >/dev/null 2>&1 && [[ -d "$prefix/share/icons/hicolor" ]]; then
    run_prefix_cmd "$prefix" gtk-update-icon-cache -q -t -f "$prefix/share/icons/hicolor"
  fi

  if command -v update-desktop-database >/dev/null 2>&1 && [[ -d "$prefix/share/applications" ]]; then
    run_prefix_cmd "$prefix" update-desktop-database "$prefix/share/applications"
  fi
}

remove_installs() {
  local prefix
  local -a paths=()

  if [[ "$SKIP_SYSTEM" -eq 1 ]]; then
    prefixes=("$HOME/.local")
  fi

  for prefix in "${prefixes[@]}"; do
    if [[ "$prefix" != /* ]]; then
      printf 'Skipping non-absolute prefix: %s\n' "$prefix" >&2
      continue
    fi

    mapfile -t paths < <(prefix_install_paths "$prefix")
    remove_paths "${paths[@]}"
    remove_matching_files "$prefix/share/locale/*/LC_MESSAGES/nocturne.mo"
    refresh_prefix_caches "$prefix"
  done
}

remove_user_state() {
  local data_home="${XDG_DATA_HOME:-$HOME/.local/share}"
  local config_home="${XDG_CONFIG_HOME:-$HOME/.config}"
  local cache_home="${XDG_CACHE_HOME:-$HOME/.cache}"
  local state_home="${XDG_STATE_HOME:-$HOME/.local/state}"

  remove_paths \
    "$data_home/$APP_ID" \
    "$config_home/$APP_ID" \
    "$cache_home/$APP_ID" \
    "$state_home/$APP_ID" \
    "$HOME/.var/app/$APP_ID" \
    "$HOME/.local/lib/nocturne"
}

reset_settings() {
  if command -v gsettings >/dev/null 2>&1 && gsettings list-schemas | grep -qx "$APP_ID"; then
    run_cmd gsettings reset-recursively "$APP_ID"
  fi

  if command -v dconf >/dev/null 2>&1; then
    run_cmd dconf reset -f /com/jeffser/Nocturne/
  fi
}

remove_secret() {
  local secret_type

  if command -v secret-tool >/dev/null 2>&1; then
    for secret_type in password listenbrainz; do
      if [[ "$APPLY" -eq 1 ]]; then
        secret-tool clear xdg:schema "$SECRET_SCHEMA" type "$secret_type" >/dev/null 2>&1 || true
      else
        printf 'Would run:'
        quote_args secret-tool clear xdg:schema "$SECRET_SCHEMA" type "$secret_type"
        printf '\n'
      fi
    done
  fi
}

remove_flatpak() {
  if [[ "$UNINSTALL_FLATPAK" -ne 1 ]]; then
    return
  fi

  if ! command -v flatpak >/dev/null 2>&1; then
    printf 'Flatpak requested, but flatpak is not installed.\n' >&2
    return
  fi

  if flatpak info "$APP_ID" >/dev/null 2>&1; then
    run_cmd flatpak uninstall --delete-data -y "$APP_ID"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes|--apply)
      APPLY=1
      shift
      ;;
    --flatpak)
      UNINSTALL_FLATPAK=1
      shift
      ;;
    --prefix)
      if [[ $# -lt 2 ]]; then
        printf 'Missing value for --prefix\n' >&2
        exit 2
      fi
      prefixes+=("$2")
      shift 2
      ;;
    --skip-system)
      SKIP_SYSTEM=1
      shift
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

if [[ ${#prefixes[@]} -eq 0 ]]; then
  add_default_prefixes
fi

if [[ "$APPLY" -ne 1 ]]; then
  cat <<EOF
Dry run. No files will be removed.
Run with --yes to wipe Nocturne:
  $0 --yes

EOF
fi

remove_flatpak
remove_installs
remove_user_state
reset_settings
remove_secret

if [[ "$APPLY" -eq 1 ]]; then
  printf 'Nocturne uninstall complete.\n'
else
  printf 'Dry run complete.\n'
fi
