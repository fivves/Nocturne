<p align="center"><img src="https://jeffser.com/images/nocturne/logo.svg">
<h1 align="center">Nocturne</h1>

<p align="center">Nocturne is a Navidrome / Jellyfin client that brings all your music together in one place, Nocturne not only connects to existing instances but it's capable of installing and managing it's own Navidrome instance</p>

<p align="center"><a href='https://flathub.org/apps/com.jeffser.Nocturne'><img width='190' alt='Download on Flathub' src='https://flathub.org/api/badge?locale=en'/></a></p>

---

> [!IMPORTANT]
> Please be aware that [GNOME Code of Conduct](https://conduct.gnome.org) applies to Nocturne before interacting with this repository.

> [!WARNING]
> AI TOOLS ARE FULLY WELCOME ON THIS FORK, IN CONTRAST THE POLICY OF THE OFFICIAL BUILD! If you disagree with the use of AI-agent assisted tools, do NOT use this fork. 

## Features

- Exploration by songs, artists, albums, radios and playlists
- Playlist management
- Compatibility with Jellyfin, OpenSubsonic and local files
- Audio equalizer and audio visualizer
- Mpris integration
- Integrated Navidrome instance management
- Automatic lyrics fetching
- Downloads and offline mode
- Cool interface

## Changes In This Fork

Compared with upstream Nocturne 1.0.1 (`Jeffser/Nocturne` at `64a83ff`), this fork currently includes:

### Jellyfin

- Added a persistent Jellyfin library cache for songs, albums, artists, and playlists, scoped to the current server URL and user.
- Loads cached Jellyfin library data at login so library pages and searches can populate before fresh network results finish.
- Refreshes the Jellyfin cache in the background after login.
- Added a Jellyfin-only sidebar sync button to manually refresh the server library cache and reload the visible library page.
- Updated Jellyfin search to cache returned models and reuse cached results when the relevant library section is complete.
- Changed Jellyfin artist lookups to use album artists, including artist album counts, artist albums, biographies, related artists, and top-song queries.
- Saves Jellyfin cache updates after album, artist, playlist, song, random-song, similar-song, favorite, and unfavorite operations.
- Stores more Jellyfin song metadata locally, including track number, disc number, album ReplayGain, and track ReplayGain.

### Local Files

- Reworked local-library scanning to use a bounded worker pool instead of starting one thread per song.
- Added local song, album, artist, and search-text indexes for faster list loading and search.
- Reused those indexes for random albums, newest albums, favorite albums, artist lists, random songs, and local search.
- Added duplicate cover-art load protection so the same cover is not parsed by multiple background workers at once.
- Made local metadata parsing safer when tracks have missing artist tags, using album artist or an unknown-artist fallback.
- Preserved semicolon-separated artist support while avoiding crashes on empty artist metadata.

### Large Library UI

- Reworked songs, albums, and artists search pages to keep ID-to-widget dictionaries instead of scanning GTK children for every result.
- Added search tokens so stale worker results are ignored when the search text changes quickly.
- Moved result appending and page visibility updates onto the GTK main loop.
- Added widget reuse to paginated album pages so repeated album results are shown again instead of duplicated.
- Moved artist page top-song widget creation and dynamic background CSS application onto the GTK main loop.

### Carousel

- Replaced the carousel internals with a horizontal scrolled layout that fills available width.
- Added previous and next overlay buttons with smooth page scrolling.
- Added pagination state updates so carousel buttons appear only when content overflows.
- Added horizontal scroll and Shift + wheel support for carousel navigation.

### Playback And Controls

- Added a global Space shortcut for play/pause.
- Added Play/Pause to the shortcuts dialog.
- Added spectrum visualizer throttling so spectrum parsing workers do not accumulate faster than they finish.

### Build, Install, And Maintenance

- Added `install.sh` for local installs: dependency checks, fresh Meson build, running-app shutdown, install to `~/.local`, icon-cache refresh, and relaunch.
- Added Arch-oriented synced-lyrics dependency checks and guidance to the installer.
- Added a Meson `update_icon_cache` option so scripted installs can control when icon cache updates happen.
- Added `AGENTS.md` with a compact project map, build commands, architecture notes, and performance guidance for future agent-assisted work.

## Screenies

HomePage | Song Queue | Lyrics | Song List | Album Page
:------------------:|:-----------------:|:----------------:|:---------------------------:|:--------------------:
![screenie1](https://jeffser.com/images/nocturne/screenie1.png) | ![screenie2](https://jeffser.com/images/nocturne/screenie2.png) | ![screenie3](https://jeffser.com/images/nocturne/screenie3.png) | ![screenie4](https://jeffser.com/images/nocturne/screenie4.png) | ![screenie5](https://jeffser.com/images/nocturne/screenie5.png)

## Dependencies
The following dependencies are requirements of the project.
- `python3 >= 3.13`
- `gtk4`
- `libadwaita-1 >= 1.9`
- `glib-2.0 >= 2.84.0`
- `libsecret`
- `gstreamer`
- `blueprint-compiler >= 0.18.0`
- Python packages: `requests`, `urllib3`, `Pillow`, `pycairo`, `tinytag`, `colorthief`, `mpris-server`

## Install
### Linux (Flatpak)
Most Linux distributions come with Flatpak preinstalled, make sure your device has [the Flathub repo enabled](https://flathub.org/en/setup).
```sh
flatpak install flathub com.jeffser.Nocturne
```

### Arch Linux (AUR)
Nocturne is packaged unofficially in the AUR, to install it first make sure you have an AUR helper such as [yay](https://github.com/jguer/yay).
```sh
yay -S nocturne
```

### Local Installer
```sh
./install.sh
```
The local installer checks the launch-time dependency stack before building. On
Arch Linux it can also install missing dependencies:
```sh
INSTALL_DEPS=1 ./install.sh
```
Arch repo packages are installed with pacman. Python packages that are not in
the official repos, including `tinytag` and `syncedlyrics`, are installed into
Nocturne's local venv.

## Build
### Linux (Flatpak)
Dependencies are automatically managed and built depending on host environment.
```sh
flatpak-builder build com.jeffser.Nocturne.yml --force-clean --install-deps-from=flathub
flatpak-builder --run build com.jeffser.Nocturne.yml nocturne
```

### macOS
#### 1. Install Dependencies with [Homebrew](https://brew.sh/)
```sh
brew install python@3.14 meson ninja pkgconf \
  glib gtk4 libadwaita pygobject3 gstreamer \
  gobject-introspection libsecret \
  desktop-file-utils
```

#### 2. Install Project & Packages
```sh
# 1. Install blueprint-compiler
git clone https://github.com/GNOME/blueprint-compiler
cd blueprint-compiler
meson build --prefix=/usr/local
sudo ninja install -C build
cd ..

# 2. Clone the project
git clone https://github.com/Jeffser/Nocturne/
cd Nocturne

# 3. Install python packages
python3 -m venv ./venv
source ./venv/bin/activate
pip install requests colorthief favicon mutagen mpris-server
```

#### 3. Build Project
```sh
meson setup build --prefix=$HOME/.local
ninja -C build
ninja install -C build
```

#### 4. Run Development Build
```sh
nocturne
```

## Special Thanks
### Translators

Language                | Contributors
:-----------------------|:-----------
Spanish                 | [Jeffry Samuel](https://github.com/jeffser)
German                  | [Martin Prokoph](https://github.com/Motschen)
Russian                 | [Aleksandr Shamaraev](https://github.com/AlexanderShad)
Simplified Chinese      | [Saul Gman](https://github.com/Ja4e)
Turkish                 | [Muhammed Emin Akalan](https://github.com/muhammedeminakalan)
Traditional Chinese     | [Yuan Chiu](https://yuaner.tw)
