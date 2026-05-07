# constants.py

import os, subprocess, json, shutil
from tinytag import TinyTag

IN_FLATPAK = bool(os.getenv("FLATPAK_ID"))
IN_SNAP = bool(os.getenv("FLATPAK_ID"))

def get_xdg_home(env: str, default: str) -> str:
    base = os.getenv(env) or os.path.expanduser(default)
    if IN_FLATPAK:
        return base
    path = os.path.join(base, "com.jeffser.Nocturne")
    if not os.path.exists(path):
        os.makedirs(path)
    return path

DATA_DIR = get_xdg_home("XDG_DATA_HOME", "~/.local/share")
CONFIG_DIR = get_xdg_home("XDG_CONFIG_HOME", "~/.config")
CACHE_DIR = get_xdg_home("XDG_CACHE_HOME", "~/.cache")

# Wrapped in a try/catch for non-Linux platforms where these commands don't exist
try:
    DEFAULT_MUSIC_DIR = subprocess.check_output(["xdg-user-dir", "MUSIC"], text=True).strip() or os.path.expanduser("~/Music")
except Exception:
    DEFAULT_MUSIC_DIR = os.path.expanduser("~/Music")

INTEGRATIONS_DIR = os.path.join(DATA_DIR, "integrations")
os.makedirs(INTEGRATIONS_DIR, exist_ok=True)
# DEPRECATED DONT USE THESE VARIABLES
OLD_JELLYFIN_DATA_DIR = os.path.join(DATA_DIR, "jellyfin")
if os.path.isdir(OLD_JELLYFIN_DATA_DIR) and not os.path.isdir(os.path.join(INTEGRATIONS_DIR, 'NocturneIntegrationJellyfin')):
    os.rename(OLD_JELLYFIN_DATA_DIR, os.path.join(INTEGRATIONS_DIR, 'NocturneIntegrationJellyfin'))

OLD_LOCAL_DATA_DIR = os.path.join(DATA_DIR, "local")
if os.path.isdir(OLD_LOCAL_DATA_DIR) and not os.path.isdir(os.path.join(INTEGRATIONS_DIR, 'NocturneIntegrationLocal')):
    os.rename(OLD_LOCAL_DATA_DIR, os.path.join(INTEGRATIONS_DIR, 'NocturneIntegrationLocal'))
# ----------

MPRIS_COVER_PATH = os.path.join(CACHE_DIR, 'cover')
os.makedirs(MPRIS_COVER_PATH, exist_ok=True)
DOWNLOAD_QUEUE_DIR = os.path.join(DATA_DIR, 'downloading')
if os.path.isdir(DOWNLOAD_QUEUE_DIR):
    shutil.rmtree(DOWNLOAD_QUEUE_DIR)
os.makedirs(DOWNLOAD_QUEUE_DIR, exist_ok=True)
DOWNLOADS_DIR = os.path.join(DATA_DIR, 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)
DOWNLOAD_MIME_MAP = {
    "audio/mpeg": ".mp3",
    "audio/flac": ".flac",
    "audio/x-flac": ".flac",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a"
}

# Fallback only used if the system does not have a keyring
FALLBACK_PASSWORD_PATH = os.path.join(CONFIG_DIR, 'pass.txt')

BASE_NAVIDROME_DIR = os.path.join(DATA_DIR, "navidrome")
os.makedirs(BASE_NAVIDROME_DIR, exist_ok=True)
NAVIDROME_ENV = {
    "ND_DATAFOLDER": BASE_NAVIDROME_DIR,
    "ND_PORT": "4534",
    "ND_LOGLEVEL": "ERROR",
    "ND_ENABLEINSIGHTSCOLLECTOR": "false"
}

def get_navidrome_path() -> str | None:
    NAVIDROME_PATH = os.path.join(BASE_NAVIDROME_DIR, 'navidrome')
    if os.path.isfile(NAVIDROME_PATH):
        return NAVIDROME_PATH

def get_navidrome_env() -> dict:
    return {
        **os.environ.copy(),
        **NAVIDROME_ENV
    }

def check_if_navidrome_ready() -> bool:
    # checks if admin has already been created
    navidrome_path = get_navidrome_path()
    if navidrome_path:
        try:
            output = subprocess.check_output([navidrome_path, "user", "list", "-f", "json", "-n", "--loglevel", "error"], stderr=subprocess.STDOUT, env=get_navidrome_env()).strip()
            output_json = json.loads(output)
            return len(output_json) > 0
        except Exception as e:
            pass
    return False

NOCTURNE_VERSION = ""
def get_nocturne_version() -> str:
    global NOCTURNE_VERSION
    return NOCTURNE_VERSION
def set_version(version_str:str):
    global NOCTURNE_VERSION
    NOCTURNE_VERSION = version_str

def get_display_time(seconds:float, show_ms:bool=False) -> str:
    total_seconds = max(0, seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if show_ms:
        seconds_str = f"{seconds:05.2f}"
    else:
        seconds_str = f"{seconds:02.0f}"

    if hours > 0:
        # Format H:MM:SS.ms
        return f"{hours:01.0f}:{minutes:02.0f}:{seconds_str}"
    else:
        # Format MM:SS.ms
        return f"{minutes:02.0f}:{seconds_str}"

def get_song_info_from_file(file_path:str, star_dict:dict={}, is_external_file:bool=False) -> dict | None:
    tag = TinyTag.get(file_path)
    if not tag:
        return None
    album_artist = (tag.albumartist or tag.artist or "").split(';')[0].strip()
    artists = [art.strip() for art in (tag.artist or album_artist or _("Unknown Artist")).split(';') if art.strip()]
    album_artist = album_artist or artists[0]
    song = {
        'path': file_path,
        'coverArt': file_path,
        'duration': tag.duration or 0,
        'title': tag.title or os.path.basename(file_path),
        'album': tag.album or "",
        'artist': album_artist,
        'artists': [{
            'id': "ARTIST:{}".format(art.strip()),
            'name': art.strip(),
            'starred': star_dict.get("ARTIST:{}".format(art.strip()))
        } for art in artists],
        'track': tag.track or 0,
        'isExternalFile': is_external_file,
        'discNumber': tag.disc or 0,
        'albumGain': tag.extra.get('replaygain_album_gain') or tag.extra.get('REPLAYGAIN_ALBUM_GAIN') or 1,
        'trackGain': tag.extra.get('replaygain_track_gain') or tag.extra.get('REPLAYGAIN_TRACK_GAIN') or 1
    }

    if not is_external_file:
        song["artistId"] = "ARTIST:{}".format(album_artist) if album_artist else ""
        song["albumId"] = "ALBUM:{}".format(song.get("album")) if song.get('album') else ""

    return song

TRANSLATORS = [
    "Jeffry Samuel (Spanish) https://jeffser.com",
    "Martin Prokoph (German) https://github.com/Motschen",
    "Aleksandr Shamaraev (Russian) https://github.com/AlexanderShad",
    "Muhammed Emin Akalan (Turkish) https://github.com/muhammedeminakalan",
    "Yuan Chiu (Traditional Chinese) https://yuaner.tw",
    "Saul Gman (Simplified Chinese) https://github.com/Ja4e"
]

PLAYBACK_MODES = {
    'consecutive': {
        'icon-name': 'media-playlist-consecutive-symbolic',
        'display-name': _("Consecutive")
    },
    'repeat-all': {
        'icon-name': 'media-playlist-repeat-symbolic',
        'display-name': _("Repeat All")
    },
    'repeat-one': {
        'icon-name': 'media-playlist-repeat-song-symbolic',
        'display-name': _("Repeat One")
    }
}

BITRATE_OPTIONS = {
    _("Low ({})"): 64,
    _("Medium ({})"): 128,
    _("High ({})"): 192,
    _("Ultra ({})"): 320,
    _("Original File"): 0
}

SIDEBAR_MENU = [
    { # Section
        'items': [
            { # Item
                'title': _("Home"),
                'icon-name': "user-home-symbolic",
                'page-tag': 'home'
            },
            { # Item
                'title': _("Artists"),
                'icon-name': "music-artist-symbolic",
                'page-tag': 'artists'
            },
            { # Item
                'title': _("Playlists"),
                'icon-name': "playlist-symbolic",
                'page-tag': "playlists"
            }
        ]
    },
    { # Section
        'title': _("Albums"),
        'items': [
            { # Item
                'title': _("All"),
                'icon-name': "music-queue-symbolic",
                'page-tag': 'albums-all'
            },
            { # Item
                'title': _("Random"),
                'icon-name': "playlist-shuffle-symbolic",
                'page-tag': 'albums-random'
            },
            { # Item
                'title': _("Favorites"),
                'icon-name': "heart-filled-symbolic",
                'page-tag': 'albums-starred'
            },
            { # Item
                'title': _("Recently Added"),
                'icon-name': "list-add-symbolic",
                'page-tag': 'albums-newest'
            },
            { # Item
                'title': _("Recently Played"),
                'icon-name': "media-playback-start-symbolic",
                'page-tag': 'albums-recent'
            },
            { # Item
                'title': _("Most Played"),
                'icon-name': "media-playlist-repeat-symbolic",
                'page-tag': 'albums-frequent'
            }
        ]
    },
    { # Section
        'title': _("Songs"),
        'items': [
            { # Item
                'title': _("All"),
                'icon-name': "music-note-symbolic",
                'page-tag': 'songs-all'
            },
            { # Item
                'title': _("Favorites"),
                'icon-name': "heart-filled-symbolic",
                'page-tag': 'songs-starred'
            },
            { # Item
                'title': _("Radios"),
                'icon-name': "sound-wave-symbolic",
                'page-tag': 'radios'
            }
        ]
    },
    { # Section
        'title': _("Playlists"),
        'items': []
    }
]

CONTEXT_ALBUM = {
    "play": {
        "name": _("Play"),
        "icon-name": "media-playback-start-symbolic",
        "action-name": "app.play_album"
    },
    "shuffle": {
        "name": _("Shuffle"),
        "icon-name": "playlist-shuffle-symbolic",
        "action-name": "app.play_album_shuffle"
    },
    "play-next": {
        "name": _("Play Next"),
        "icon-name": "list-high-priority-symbolic",
        "action-name": "app.play_album_next"
    },
    "play-later": {
        "name": _("Play Later"),
        "icon-name": "list-low-priority-symbolic",
        "action-name": "app.play_album_later"
    },
    "add-to-playlist": {
        "name": _("Add To Playlist"),
        "icon-name": "playlist-symbolic",
        "action-name": "app.prompt_add_album_to_playlist"
    },
    "download": {
        "name": _("Download"),
        "icon-name": "folder-download-symbolic",
        "action-name": "app.download_album"
    },
    "show-artist": {
        "name": _("Show Artist"),
        "icon-name": "music-artist-symbolic",
        "action-name": "app.show_artist_from_album"
    }
}

CONTEXT_ARTIST = {
    "shuffle": {
        "name": _("Shuffle"),
        "icon-name": "playlist-shuffle-symbolic",
        "action-name": "app.play_shuffle_artist"
    },
    "radio": {
        "name": _("Radio"),
        "icon-name": "sound-symbolic",
        "action-name": "app.play_radio_artist"
    }
}

CONTEXT_PLAYLIST = {
    "play": {
        "name": _("Play"),
        "icon-name": "media-playback-start-symbolic",
        "action-name": "app.play_playlist"
    },
    "shuffle": {
        "name": _("Shuffle"),
        "icon-name": "media-playlist-shuffle-symbolic",
        "action-name": "app.play_playlist_shuffle"
    },
    "play-next": {
        "name": _("Play Next"),
        "icon-name": "list-high-priority-symbolic",
        "action-name": "app.play_playlist_next"
    },
    "play-later": {
        "name": _("Play Later"),
        "icon-name": "list-low-priority-symbolic",
        "action-name": "app.play_playlist_later"
    },
    "download": {
        "name": _("Download"),
        "icon-name": "folder-download-symbolic",
        "action-name": "app.download_playlist"
    },
    "edit": {
        "name": _("Edit"),
        "icon-name": "document-edit-symbolic",
        "action-name": "app.update_playlist"
    },
    "delete": {
        "name": _("Delete"),
        "css": ["error"],
        "icon-name": "user-trash-symbolic",
        "action-name": "app.delete_playlist"
    }
}

CONTEXT_SONG = {
    "select": {
        "name": _("Select"),
        "icon-name": "object-select-symbolic"
    },
    "play-next": {
        "name": _("Play Next"),
        "icon-name": "list-high-priority-symbolic",
        "action-name": "app.play_song_next"
    },
    "play-later": {
        "name": _("Play Later"),
        "icon-name": "list-low-priority-symbolic",
        "action-name": "app.play_song_later"
    },
    "edit-radio": {
        "name": _("Edit"),
        "icon-name": "document-edit-symbolic",
        "action-name": "app.update_radio"
    },
    "edit-lyrics": {
        "name": _("Edit Lyrics"),
        "icon-name": "text-justify-center-symbolic",
        "action-name": "app.edit_lyrics"
    },
    "add-to-playlist": {
        "name": _("Add To Playlist"),
        "icon-name": "playlist-symbolic",
        "action-name": "app.prompt_add_song_to_playlist"
    },
    "download": {
        "name": _("Download"),
        "icon-name": "folder-download-symbolic",
        "action-name": "app.download_song"
    },
    "show-album": {
        "name": _("Show Album"),
        "icon-name": "music-queue-symbolic",
        "action-name": "app.show_album_from_song"
    },
    "show-artist": {
        "name": _("Show Artist"),
        "icon-name": "music-artist-symbolic",
        "action-name": "app.show_artist_from_song"
    },
    "delete-radio": {
        "name": _("Delete"),
        "css": ["error"],
        "icon-name": "user-trash-symbolic",
        "action-name": "app.delete_radio"
    },
    "remove": {
        "name": _("Remove"),
        "css": ["error"],
        "icon-name": "user-trash-symbolic"
    },
    "delete-download": {
        "name": _("Delete Download"),
        "css": ["error"],
        "icon-name": "user-trash-symbolic",
        "action-name": "app.delete_download"
    }
}

CONTEXT_MANAGED_NAVIDROME_SERVER = {
    "visit": {
        "name": _("Visit Webpage"),
        "icon-name": "globe-symbolic",
        "action-name": "app.visit_url",
        "action-target": "http://127.0.0.1:4534"
    },
    "update": {
        "name": _("Update Server"),
        "icon-name": "update-symbolic",
        "action-name": "app.update_navidrome_server"
    },
    "delete": {
        "name": _("Delete Server"),
        "css": ["error"],
        "icon-name": "user-trash-symbolic",
        "action-name": "app.delete_navidrome_server"
    }
}
