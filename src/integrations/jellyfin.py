# jellyfin.py

from gi.repository import Gtk, GLib, GObject, Gdk, Gio, GdkPixbuf
from . import secret, models, local
from .base import Base
from ..constants import DOWNLOAD_QUEUE_DIR, DOWNLOADS_DIR, DOWNLOAD_MIME_MAP
import requests, subprocess, random, threading, base64, os, json, platform

class Jellyfin(Base):
    __gtype_name__ = 'NocturneIntegrationJellyfin'

    login_page_metadata = {
        'icon-name': "network-server-symbolic",
        'title': "Jellyfin",
        'description': _("Connect to a Jellyfin server."),
        'entries': ["url", "user", "password", "trust-server"],
    }
    button_metadata = {
        'title': _("Jellyfin"),
        'subtitle': _("Use an existing Jellyfin instance")
    }
    limitations = ('no-edit-radio',)
    cache_actions = {
        'deleted-radios': []
    }

    AUTH_HEADER = 'MediaBrowser Client="Nocturne", Device="{}", DeviceId="{}", Version="1.0.0"'.format(platform.node(), str(abs(hash(platform.node()))))

    url = GObject.Property(type=str, default="http://127.0.0.1:8096")

    # Loaded by API
    accessToken = GObject.Property(type=str)
    userId = GObject.Property(type=str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._library_cache_loaded = False
        self._library_cache_refreshing = False
        self._library_cache_complete = set()
        self._library_cache_ids = {}
        self._library_cache_lock = threading.Lock()

    def _get_library_cache_file(self) -> str:
        return os.path.join(self.getIntegrationDir(), "library-cache-v3.json")

    def _model_library_type(self, model) -> str:
        if isinstance(model, models.Album):
            return "album"
        if isinstance(model, models.Artist):
            return "artist"
        if isinstance(model, models.Playlist):
            return "playlist"
        if isinstance(model, models.Song):
            if model.get_property("isExternalFile") or model.get_property("isRadio"):
                return ""
            return "song"
        return ""

    def _model_cache_type(self, model) -> str:
        model_type = self._model_library_type(model)
        if not model_type or not model.get_property("id"):
            return ""
        return model_type

    def _set_library_cache_ids(self, model_type:str, ids:list):
        seen = set()
        self._library_cache_ids[model_type] = []
        for model_id in ids:
            if model_id and model_id not in seen:
                seen.add(model_id)
                self._library_cache_ids[model_type].append(model_id)

    def _prune_library_cache(self, ids_by_type:dict):
        current_ids_by_type = {
            model_type: set(ids)
            for model_type, ids in ids_by_type.items()
        }
        for model_id, model in list(self.loaded_models.items()):
            model_type = self._model_library_type(model)
            if model_type in current_ids_by_type and model_id not in current_ids_by_type[model_type]:
                del self.loaded_models[model_id]

    def _serialize_model(self, model) -> dict:
        data = {}
        for prop in model.list_properties():
            name = prop.get_name()
            if name == "gdkPaintable":
                continue
            value = model.get_property(name)
            try:
                json.dumps(value)
                data[name] = value
            except TypeError:
                pass
        return data

    def _save_library_cache(self):
        if not self._library_cache_loaded:
            return

        payload = {
            "version": 3,
            "url": self.get_property("url").strip("/"),
            "userId": self.get_property("userId"),
            "complete": list(self._library_cache_complete),
            "ids": self._library_cache_ids,
            "models": {}
        }
        for model_id, model in list(self.loaded_models.items()):
            model_type = self._model_cache_type(model)
            if model_type:
                payload["models"][model_id] = {
                    "type": model_type,
                    "data": self._serialize_model(model)
                }

        cache_file = self._get_library_cache_file()
        tmp_file = "{}.tmp".format(cache_file)
        try:
            with self._library_cache_lock:
                with open(tmp_file, "w") as f:
                    json.dump(payload, f, ensure_ascii=False)
                os.replace(tmp_file, cache_file)
        except Exception:
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception:
                pass

    def _load_library_cache(self):
        cache_file = self._get_library_cache_file()
        try:
            with open(cache_file, "r") as f:
                payload = json.load(f)
        except Exception:
            self._library_cache_loaded = True
            return

        if payload.get("version") != 3:
            self._library_cache_loaded = True
            return
        if payload.get("url") != self.get_property("url").strip("/"):
            self._library_cache_loaded = True
            return
        if payload.get("userId") != self.get_property("userId"):
            self._library_cache_loaded = True
            return

        model_classes = {
            "album": models.Album,
            "artist": models.Artist,
            "playlist": models.Playlist,
            "song": models.Song
        }
        for model_id, cached in payload.get("models", {}).items():
            model_class = model_classes.get(cached.get("type"))
            data = cached.get("data")
            if model_class and isinstance(data, dict):
                if model_id in self.loaded_models:
                    self.loaded_models.get(model_id).update_data(**data)
                else:
                    self.loaded_models[model_id] = model_class(**data)

        self._library_cache_loaded = True
        self._library_cache_complete = set(payload.get("complete", []))
        self._library_cache_ids = {}
        ids_by_type = payload.get("ids", {})
        if isinstance(ids_by_type, dict):
            for model_type, ids in ids_by_type.items():
                if isinstance(ids, list):
                    self._set_library_cache_ids(model_type, ids)

    def _cache_model(self, model_id:str, model_type:str, data:dict):
        model_classes = {
            "album": models.Album,
            "artist": models.Artist,
            "playlist": models.Playlist,
            "song": models.Song
        }
        model_class = model_classes.get(model_type)
        if not model_id or not model_class:
            return

        if model := self.loaded_models.get(model_id):
            model.update_data(**data)
        else:
            self.loaded_models[model_id] = model_class(**data)

    def _song_data_from_item(self, song:dict) -> dict:
        return {
            "id": song.get("Id"),
            "title": song.get("Name"),
            "album": song.get("Album"),
            "albumId": song.get("AlbumId"),
            "artist": song.get("AlbumArtist"),
            "artistId": (song.get("ArtistItems") or [{}])[0].get("Id"),
            "duration": int(song.get("RunTimeTicks", 0) / 10000000),
            "artists": [{"id": art.get("Id"), "name": art.get("Name")} for art in song.get("ArtistItems", [])],
            "starred": song.get("UserData", {}).get("IsFavorite", False),
            "track": song.get("IndexNumber") or 0,
            "discNumber": song.get("ParentIndexNumber") or 0,
            "albumGain": song.get("AlbumNormalizationGain", song.get("NormalizationGain")) or 0.0,
            "trackGain": song.get("NormalizationGain") or 0.0
        }

    def _album_artist_data_from_item(self, artist:dict) -> dict:
        return {
            "id": artist.get("Id"),
            "name": artist.get("Name"),
            "albumCount": artist.get("AlbumCount") or artist.get("ChildCount") or 0,
            "starred": artist.get("UserData", {}).get("IsFavorite", False),
            "biography": artist.get("Overview", ""),
            "similarArtist": [{"id": art.get("Id"), "name": art.get("Name")} for art in artist.get("SimilarItems", [])]
        }

    def _album_artist_album_data(self, artist_id:str) -> dict:
        albums = self.make_request(
            action="Users/{userId}/Items",
            mode="GET",
            params={
                "AlbumArtistIds": artist_id,
                "IncludeItemTypes": "MusicAlbum",
                "Recursive": "true"
            }
        ).get("Items", [])

        return {
            "albumCount": len(albums),
            "album": [{"id": album.get("Id"), "name": album.get("Name")} for album in albums]
        }

    def _cached_album_artist_album_data(self, artist_id:str) -> dict:
        albums = []
        for model in list(self.loaded_models.values()):
            if not isinstance(model, models.Album):
                continue
            if model.get_property("artistId") == artist_id:
                albums.append({"id": model.get_property("id"), "name": model.get_property("name")})

        return {
            "albumCount": len(albums),
            "album": albums
        }

    def _cached_ids(self, model_type:str, query:str="", count:int=0, offset:int=0) -> list:
        if not self._library_cache_loaded:
            return []

        query = query.casefold()
        matches = []
        cached_model_ids = self._library_cache_ids.get(model_type)
        if cached_model_ids is None:
            cached_model_ids = [
                model_id for model_id, model in list(self.loaded_models.items())
                if self._model_cache_type(model) == model_type
            ]

        for model_id in cached_model_ids:
            model = self.loaded_models.get(model_id)
            if not model or self._model_cache_type(model) != model_type:
                continue
            if query:
                haystack = []
                if isinstance(model, models.Song):
                    haystack = [model.title, model.album, model.artist]
                    haystack.extend([artist.get("name") for artist in model.artists or []])
                elif isinstance(model, models.Album):
                    haystack = [model.name, model.artist]
                    haystack.extend([artist.get("name") for artist in model.artists or []])
                elif isinstance(model, models.Artist):
                    haystack = [model.name]
                if query not in " ".join([value or "" for value in haystack]).casefold():
                    continue
            matches.append(model_id)

        if count:
            return matches[offset:offset+count]
        return matches[offset:]

    def _refresh_library_cache(self) -> bool:
        if self._library_cache_refreshing:
            return False
        self._library_cache_refreshing = True
        try:
            results = self.search("", artistCount=100000, albumCount=100000, songCount=100000, prefer_cache=False)
            current_ids = {}
            complete_types = set(results.get("_complete", []))
            for model_type in ("artist", "album", "song"):
                if model_type in complete_types:
                    self._library_cache_complete.add(model_type)
                    self._set_library_cache_ids(model_type, results.get(model_type, []))
                    current_ids[model_type] = self._library_cache_ids.get(model_type, [])
            playlists = self.getPlaylists(prefer_cache=False)
            if playlists:
                self._library_cache_complete.add("playlist")
                self._set_library_cache_ids("playlist", playlists)
                current_ids["playlist"] = self._library_cache_ids.get("playlist", [])
            self._prune_library_cache(current_ids)
            self._save_library_cache()
            return True
        finally:
            self._library_cache_refreshing = False

    def syncLibrary(self) -> bool:
        if self._library_cache_refreshing:
            return False

        if not self._library_cache_loaded:
            self._load_library_cache()
        return self._refresh_library_cache()

    def get_base_header(self) -> dict:
        headers = {
            "Authorization": self.AUTH_HEADER
        }
        if token := self.get_property('accessToken'):
            headers["Authorization"] += ', Token="{}"'.format(token)
        return headers

    def get_url(self, action:str, **keys) -> str:
        action = action.format(userId=self.get_property('userId'), **keys)
        return '{}/{}'.format(self.get_property('url').strip('/'), action)

    def make_request(self, action:str, json:dict={}, params:dict={}, mode:str="GET", action_keys:dict={}) -> dict:
        params = {
            **params
        }
        headers = {
            **self.get_base_header(),
            "Accept": "application/json"
        }
        try:
            if mode == 'GET':
                response = requests.get(
                    self.get_url(action, **action_keys),
                    params=params,
                    json=json,
                    headers=headers,
                    verify=not self.get_property('trustServer')
                )
            elif mode == 'POST':
                response = requests.post(
                    self.get_url(action, **action_keys),
                    params=params,
                    json=json,
                    headers=headers,
                    verify=not self.get_property('trustServer')
                )
            elif mode == 'DELETE':
                response = requests.delete(
                    self.get_url(action, **action_keys),
                    params=params,
                    json=json,
                    headers=headers,
                    verify=not self.get_property('trustServer')
                )
            if response.status_code in (200, 201):
                return response.json()
            elif response.status_code == 204:
                return {'state': 'ok'}
        except Exception as e:
            pass
        return {}

    # ----------- #

    def start_instance(self) -> bool:
        return True

    def terminate_instance(self):
        pass

    def on_login(self):
        self._load_library_cache()

    def get_stream_url(self, song_id:str) -> str:
        model = self.loaded_models.get(song_id)
        if not model:
            model = models.Song(id=song_id)
            self.loaded_models[song_id] = model
        if model.get_property('isRadio') and model.get_property('streamUrl'):
            return model.get_property('streamUrl')
        elif model.get_property('isExternalFile'):
            return 'file://{}'.format(model.get_property('path'))
        base_url = self.get_url('Audio/{}/stream'.format(song_id))
        max_bitrate = Gio.Settings(schema_id="com.jeffser.Nocturne").get_value('max-bitrate').unpack()
        if max_bitrate == 0:
            return '{}?static=true&api_key={}'.format(
                base_url,
                self.get_property('accessToken')
            )
        else:
            return '{}?static=true&audioBitrate={}&api_key={}'.format(
                base_url,
                max_bitrate*1000,
                self.get_property('accessToken')
            )

    def initiateQuickConnect(self) -> dict:
        return self.make_request(
            action='QuickConnect/Initiate',
            mode='POST',
        )

    def checkQuickConnect(self, secret_str:str) -> bool:
        response = self.make_request(
            action='QuickConnect/Connect',
            params={'secret': secret_str}
        )
        if response.get('Authenticated'):
            secret.store_password(response.get("Secret"))
            return True
        return False

    def getCoverArt(self, model_id:str='', big:bool=False) -> Gdk.Paintable:
        if model := self.loaded_models.get(model_id):
            if isinstance(model, models.Song) and model.get_property('isRadio'):
                return None
            if isinstance(model, models.Song) and model.get_property('isExternalFile'):
                return local.Local.getCoverArt(self, model_id, big=big)
            if not big and model.get_property('gdkPaintable') is not None:
                return model.get_property('gdkPaintable')

            params = {
                'maxWidth': 720 if big else 240,
                'quality': 90
            }
            try:
                response = requests.get(
                    self.get_url('Items/{id}/Images/Primary', id=model_id),
                    headers=self.get_base_header(),
                    params=params,
                    verify=not self.get_property('trustServer'),
                    timeout=10
                )
                # Treat non-200 responses as empty content to avoid
                # propagating network-related exceptions up and into the UI thread
                response.raise_for_status()
                response_bytes = response.content
            except Exception:
                response_bytes = b''

            if response_bytes and len(response_bytes) > 0:
                try:
                    gbytes = GLib.Bytes.new(response_bytes)
                    texture = Gdk.Texture.new_from_bytes(gbytes)
                    if big:
                        return texture
                    model.set_property('gdkPaintable', texture)
                    return model.get_property('gdkPaintable')
                except Exception as e:
                    pass
        return None

    def ping(self) -> bool:
        self.set_property('accessToken', "")
        self.set_property('userId', "")
        response = self.make_request(
            action='Users/AuthenticateWithQuickConnect',
            json={
                "Secret": secret.get_plain_password()
            },
            mode='POST'
        )
        self.set_property('accessToken', response.get('AccessToken'))
        self.set_property('userId', response.get('User', {}).get('Id'))
        if self.get_property("accessToken") and self.get_property("userId"):
            self.set_property("user", response.get('User', {}).get('Name'))
        else:
            response = self.make_request(
                action='Users/AuthenticateByName',
                json={
                    'Username': self.get_property('user'),
                    'Pw': secret.get_plain_password()
                },
                mode='POST'
            )
            self.set_property('accessToken', response.get('AccessToken'))
            self.set_property('userId', response.get('User', {}).get('Id'))
        return self.get_property('accessToken') and self.get_property('userId')

    def getAlbumList(self, list_type:str="recent", size:int=10, offset:int=0) -> list:
        cached_albums = self._cached_ids("album", count=size, offset=offset)
        if list_type == "random" and cached_albums:
            all_cached_albums = self._cached_ids("album")
            return random.sample(all_cached_albums, min(size, len(all_cached_albums)))
        if list_type == "starred" and cached_albums:
            starred_albums = [
                model_id for model_id in self._cached_ids("album")
                if self.loaded_models.get(model_id).get_property("starred")
            ]
            return starred_albums[offset:offset+size]

        params = {
            "IncludeItemTypes": "MusicAlbum",
            "Recursive": "true",
            "Limit": size,
            "StartIndex": offset,
            "Fields": "ArtistItems,IsFavorite",
        }
        if list_type == "random":
            params["SortBy"] = "Random"
        elif list_type == "newest":
            params["SortBy"] = "DateCreated"
            params["SortOrder"] = "Descending"
        elif list_type == "frequent":
            params["SortBy"] = "PlayCount"
            params["SortOrder"] = "Descending"
        elif list_type == "recent":
            params["SortBy"] = "DatePlayed"
            params["SortOrder"] = "Descending"
        elif list_type == "starred":
            params["Filters"] = "IsFavorite"

        albums = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params=params
        ).get('Items', [])
        id_list = []
        for album in albums:
            artists = album.get("ArtistItems", [])
            songs = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params={
                    "ParentId": album.get("Id"),
                    "IncludeItemTypes": "Audio",
                    "Fields": "RunTimeTicks"
                }
            ).get("Items", [])

            duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

            album_model = models.Album(
                id=album.get("Id"),
                name=album.get("Name"),
                artist=artists[0].get("Name") if artists else "Unknown",
                artistId=artists[0].get("Id") if artists else "",
                songCount=len(songs),
                duration=duration,
                artists=[{"id": art.get("Id"), "name": art.get("Name")} for art in artists],
                song=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs],
                starred=album.get("UserData", {}).get("IsFavorite", False)
            )
            self.loaded_models[album.get("Id")] = album_model
            id_list.append(album.get("Id"))
        self._save_library_cache()
        return id_list

    def getArtists(self, size:int=10, list_type:str="alphabetical") -> list:
        cached_artists = self._cached_ids("artist", count=size)
        if list_type == "random" and cached_artists:
            all_cached_artists = self._cached_ids("artist")
            return random.sample(all_cached_artists, min(size, len(all_cached_artists)))
        if cached_artists:
            return cached_artists

        params = {
            "Limit": size,
            "Recursive": "true",
            "Fields": "Overview,SimilarItems,UserData",
            "SortBy": "SortName",
            "SortOrder": "Ascending"
        }
        if list_type == "random":
            params["SortBy"] = "Random"
            params.pop("SortOrder")
        response = self.make_request(
            action='Artists/AlbumArtists',
            mode='GET',
            params=params
        )
        id_list = []
        for artist in response.get('Items', []):
            artist_data = self._album_artist_data_from_item(artist)
            artist_data.update(self._album_artist_album_data(artist.get("Id")))
            artist_model = models.Artist(**artist_data)
            self.loaded_models[artist.get("Id")] = artist_model
            id_list.append(artist.get("Id"))
        self._save_library_cache()
        return id_list

    def getPlaylists(self, prefer_cache:bool=True) -> list:
        cached_playlists = self._cached_ids("playlist")
        if prefer_cache and cached_playlists and "playlist" in self._library_cache_complete:
            return cached_playlists

        params = {
            "IncludeItemTypes": "Playlist",
            "Recursive": "true",
            "Fields": "None"
        }
        response = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params=params
        )
        id_list = []
        for playlist in response.get('Items', []):
            songs = self.make_request(
                action='Playlists/{id}/Items',
                action_keys={"id": playlist.get("Id")},
                mode="GET",
                params={
                    "Fields": "RunTimeTicks",
                    "UserId": self.get_property("userId")
                }
            ).get("Items", [])

            duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

            playlist_model = models.Playlist(
                id=playlist.get("Id"),
                name=playlist.get("Name"),
                songCount=len(songs),
                duration=duration,
                entry=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs]
            )
            self.loaded_models[playlist.get("Id")] = playlist_model
            id_list.append(playlist.get("Id"))
        self._save_library_cache()
        return id_list

    def getStarredSongs(self) -> list:
        song_list = []
        songs = self.make_request(
            action="Users/{userId}/Items",
            mode="GET",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Fields": "Id",
                "Filters": "IsFavorite"
            }
        ).get("Items", [])

        return [song.get("Id") for song in songs]

    def verifyArtist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        def run():
            artist = self.make_request(
                action='Users/{userId}/Items/{id}',
                action_keys={"id": model_id},
                mode="GET"
            )
            if not artist.get("Id"):
                return

            albums = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params={
                    "AlbumArtistIds": model_id,
                    "IncludeItemTypes": "MusicAlbum",
                    "Recursive": "true",
                    "Fields": "ItemCounts"
                }
            ).get("Items", [])

            self.loaded_models.get(model_id).update_data(
                id=artist.get("Id"),
                name=artist.get("Name"),
                albumCount=len(albums),
                album=[{"id": alb.get("Id"), "name": alb.get("Name")} for alb in albums],
                starred=artist.get("UserData", {}).get("IsFavorite", False),
                biography=artist.get("Overview", ""),
                similarArtist=[{"id": art.get("Id"), "name": art.get("Name")} for art in artist.get("SimilarItems", [])]
            )
            self._save_library_cache()

        model = self.loaded_models.get(model_id)
        needs_album_count = model is not None and model.get_property("albumCount") == 0

        if model_id not in self.loaded_models or force_update or needs_album_count:
            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Artist(id=model_id)
            if use_threading:
                threading.Thread(target=run).start()
            else:
                run()

        threading.Thread(target=self.getCoverArt, args=(model_id,)).start()

    def verifyAlbum(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        def run():
            album = self.make_request(
                action='Users/{userId}/Items/{id}',
                action_keys={"id": model_id},
                mode="GET"
            )
            if not album.get("Id"):
                return

            songs = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params={
                    "ParentId": model_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": "true",
                    "Fields": "RunTimeTicks,IndexNumber,ParentIndexNumber",
                    "SortBy": "ParentIndexNumber,IndexNumber",
                    "SortOrder": "Ascending"
                }
            ).get("Items", [])

            duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

            for i, song in enumerate(songs):
                if model := self.loaded_models.get(song.get("Id")):
                    model.update_data(track=song.get("IndexNumber") or i)

            self.loaded_models.get(model_id).update_data(
                id=album.get("Id"),
                name=album.get("Name"),
                artist=album.get("AlbumArtist"),
                artistId=album.get("ArtistItems", [{}])[0].get("Id") if album.get("ArtistItems") else None,
                songCount=len(songs),
                duration=duration,
                artists=[{"id": art.get("Id"), "name": art.get("Name")} for art in album.get("ArtistItems", [])],
                song=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs],
                starred=album.get("UserData", {}).get("IsFavorite", False)
            )
            self._save_library_cache()

        if model_id not in self.loaded_models or force_update:
            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Album(id=model_id)
            if use_threading:
                threading.Thread(target=run).start()
            else:
                run()

        threading.Thread(target=self.getCoverArt, args=(model_id,)).start()

    def verifyPlaylist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        def run():
            playlist = self.make_request(
                action='Users/{userId}/Items/{id}',
                action_keys={"id": model_id},
                mode="GET"
            )
            if not playlist.get("Id"):
                return

            songs = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params={
                    "ParentId": model_id,
                    "IncludeItemTypes": "Audio",
                    "Recursive": "true",
                    "Fields": "RunTimeTicks"
                }
            ).get("Items", [])

            duration = int(sum(song.get("RunTimeTicks", 0) for song in songs) / 10000000)

            self.loaded_models.get(model_id).update_data(
                id=playlist.get("Id"),
                name=playlist.get("Name"),
                songCount=len(songs),
                duration=duration,
                entry=[{"id": song.get("Id"), "name": song.get("Name")} for song in songs]
            )
            self._save_library_cache()

        if model_id not in self.loaded_models or force_update:
            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Playlist(id=model_id)
            if use_threading:
                threading.Thread(target=run).start()
            else:
                run()

        threading.Thread(target=self.getCoverArt, args=(model_id,)).start()

    def verifySong(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        def run():
            params = {
                "Fields": "ArtistItems,AlbumId,RunTimeTicks,UserData,IndexNumber,ParentIndexNumber"
            }
            song = self.make_request(
                action='Users/{userId}/Items/{id}',
                action_keys={"id": model_id},
                mode='GET',
                params=params
            )
            if not song.get("Id"):
                return

            self.loaded_models.get(model_id).update_data(**self._song_data_from_item(song))
            self._save_library_cache()

        if model_id not in self.loaded_models or force_update:
            if model_id not in self.loaded_models:
                self.loaded_models[model_id] = models.Song(id=model_id)
            if use_threading:
                threading.Thread(target=run).start()
            else:
                run()

        threading.Thread(target=self.getCoverArt, args=(model_id,)).start()

    def star(self, model_id:str) -> bool:
        response = self.make_request(
            action='Users/{userId}/FavoriteItems/{id}',
            action_keys={"id": model_id},
            mode='POST'
        )
        is_favorite = response.get('IsFavorite', False)
        if is_favorite:
            if model := self.loaded_models.get(model_id):
                model.set_property('starred', True)
            self._save_library_cache()
        return is_favorite

    def unstar(self, model_id:str) -> bool:
        response = self.make_request(
            action='Users/{userId}/FavoriteItems/{id}',
            action_keys={"id": model_id},
            mode='DELETE'
        )
        is_unstarred = not response.get('IsFavorite', False)
        if is_unstarred:
            if model := self.loaded_models.get(model_id):
                model.set_property('starred', False)
            self._save_library_cache()
        return is_unstarred

    def getPlayQueue(self) -> tuple:
        QUEUEFILE = os.path.join(self.getIntegrationDir(), 'queue.json')

        try:
            with open(QUEUEFILE, 'r') as f:
                queue_dict = json.load(f)
            if not isinstance(queue_dict, dict):
                queue_dict = {}
        except Exception:
            queue_dict = {}

        song_list = [model_id for model_id in queue_dict.get('id', [])]
        current = queue_dict.get('current', "")
        if current not in song_list:
            if len(song_list) > 0:
                current = song_list[0]
            else:
                current = ""

        return current, song_list

    def savePlayQueue(self, id_list:list, current:str, position:int) -> bool:
        QUEUEFILE = os.path.join(self.getIntegrationDir(), 'queue.json')

        final_id_list = []
        for model_id in id_list:
            if model := self.loaded_models.get(model_id):
                if not model.isExternalFile:
                    final_id_list.append(model_id)

        if current not in final_id_list:
            if len(final_id_list) > 0:
                current = final_id_list[0]
            else:
                current = ""

        queue_dict = {
            'id': final_id_list,
            'current': current,
            'position': position
        }

        with open(QUEUEFILE, 'w') as f:
            json.dump(queue_dict, f, ensure_ascii=False)

        return True

    def getSimilarSongs(self, model_id:str, count:int=20) -> list:
        artist_songs = self.make_request(
            action='Users/{userId}/Items',
            mode="GET",
            params={
                "ArtistIds": model_id,
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Limit": 1,
            }
        ).get('Items', [])

        if len(artist_songs) == 0:
            return []

        songs = self.make_request(
            action='Items/{id}/Similar',
            action_keys={"id": artist_songs[0].get("Id")},
            mode='GET',
            params={
                "UserId": self.get_property("userId"),
                "Limit": count,
                "IncludeItemTypes": "Audio",
                "Fields": "ArtistItems,RunTimeTicks,UserData"
            }
        ).get("Items", [])

        id_list = []
        for song in songs:
            properties = self._song_data_from_item(song)
            if song.get("Id") in self.loaded_models:
                self.loaded_models.get(song.get("Id")).update_data(**properties)
            else:
                self.loaded_models[song.get("Id")] = models.Song(**properties)
            id_list.append(song.get("Id"))
        self._save_library_cache()
        return id_list

    def getRandomSongs(self, size:int=20) -> list:
        songs = self.make_request(
            action='Users/{userId}/Items',
            mode="GET",
            params={
                "IncludeItemTypes": "Audio",
                "Recursive": "true",
                "Fields": "RunTimeTicks,UserData,ArtistItems",
                "Limit": size,
                "SortBy": "Random",
                "MediaTypes": "Audio"
            }
        ).get('Items', [])

        id_list = []
        for song in songs:
            properties = self._song_data_from_item(song)
            if song.get("Id") in self.loaded_models:
                self.loaded_models.get(song.get("Id")).update_data(**properties)
            else:
                self.loaded_models[song.get("Id")] = models.Song(**properties)
            id_list.append(song.get("Id"))
        self._save_library_cache()
        return id_list

    def getLyrics(self, songId:str) -> dict:
        result = self.make_request(
            action='Audio/{id}/Lyrics',
            action_keys={'id': songId},
            mode='GET'
        )
        isSynced = bool(result.get('Lyrics', [{}])[0].get('Start'))
        if isSynced:
            lines = []
            for line in result.get('Lyrics', []):
                lines.append({
                    'content': line.get('Text'),
                    'ms': line.get('Start') / 10000
                })
            return {
                'type': 'lrc',
                'content': lines
            }
        else:
            text = '\n'.join([line.get('Text') for line in result.get('Lyrics', [])])
            if text:
                return {
                    'type': 'plain',
                    'content': text
                }
        return {'type': 'not-found'}

    def search(self, query:str, artistCount:int=0, artistOffset:int=0, albumCount:int=0, albumOffset:int=0, songCount:int=0, songOffset:int=0, prefer_cache:bool=True) -> dict:
        if prefer_cache:
            cached = {
                "artist": self._cached_ids("artist", query, artistCount, artistOffset) if artistCount else [],
                "album": self._cached_ids("album", query, albumCount, albumOffset) if albumCount else [],
                "song": self._cached_ids("song", query, songCount, songOffset) if songCount else []
            }
            artist_ready = "artist" in self._library_cache_complete or len(cached["artist"]) >= artistCount
            album_ready = "album" in self._library_cache_complete or len(cached["album"]) >= albumCount
            song_ready = "song" in self._library_cache_complete or len(cached["song"]) >= songCount
            if (
                (not artistCount or (cached["artist"] and artist_ready)) and
                (not albumCount or (cached["album"] and album_ready)) and
                (not songCount or (cached["song"] and song_ready))
            ):
                return cached

        def fetch_items(item_type:str, limit:int, offset:int, fields:str=""):
            if limit <= 0:
                return [], True
            response = self.make_request(
                action='Users/{userId}/Items',
                mode="GET",
                params={
                    "SearchTerm": query,
                    "IncludeItemTypes": item_type,
                    "Recursive": "true",
                    "Limit": limit,
                    "StartIndex": offset,
                    "Fields": fields
                }
            )
            if "Items" not in response:
                return [], False
            return response.get('Items', []), True

        def fetch_album_artists(limit:int, offset:int):
            if limit <= 0:
                return [], True
            response = self.make_request(
                action='Artists/AlbumArtists',
                mode='GET',
                params={
                    "SearchTerm": query,
                    "Recursive": "true",
                    "Limit": limit,
                    "StartIndex": offset,
                    "Fields": "Overview,SimilarItems,UserData",
                    "SortBy": "SortName",
                    "SortOrder": "Ascending"
                }
            )
            if "Items" not in response:
                return [], False
            return response.get('Items', []), True

        artists, artists_complete = fetch_album_artists(artistCount, artistOffset)
        albums, albums_complete = fetch_items("MusicAlbum", albumCount, albumOffset, "ArtistItems,IsFavorite,RunTimeTicks")
        songs, songs_complete = fetch_items("Audio", songCount, songOffset, "ArtistItems,AlbumId,RunTimeTicks,UserData,IndexNumber,ParentIndexNumber")

        for album in albums:
            artists_list = album.get("ArtistItems", [])
            self._cache_model(album.get("Id"), "album", {
                "id": album.get("Id"),
                "name": album.get("Name"),
                "artist": artists_list[0].get("Name") if artists_list else album.get("AlbumArtist") or "Unknown",
                "artistId": artists_list[0].get("Id") if artists_list else "",
                "artists": [{"id": art.get("Id"), "name": art.get("Name")} for art in artists_list],
                "starred": album.get("UserData", {}).get("IsFavorite", False)
            })

        for song in songs:
            self._cache_model(song.get("Id"), "song", self._song_data_from_item(song))

        for artist in artists:
            artist_data = self._album_artist_data_from_item(artist)
            if not artist_data.get("albumCount"):
                album_data = self._cached_album_artist_album_data(artist.get("Id"))
                if album_data.get("albumCount"):
                    artist_data.update(album_data)
                else:
                    artist_data.update(self._album_artist_album_data(artist.get("Id")))
            self._cache_model(artist.get("Id"), "artist", artist_data)

        if artists or albums or songs:
            self._save_library_cache()

        return {
            'artist': [item.get("Id") for item in artists],
            'album': [item.get("Id") for item in albums],
            'song': [item.get("Id") for item in songs],
            '_complete': [
                model_type for model_type, complete in {
                    'artist': artists_complete,
                    'album': albums_complete,
                    'song': songs_complete
                }.items()
                if complete
            ]
        }

    def getInternetRadioStations(self) -> list:
        def cache_radio(model_id:str, title:str, streamUrl:str=None):
            if not model_id or model_id in self.cache_actions.get('deleted-radios'):
                return False

            radio_model = models.Song(
                id=model_id,
                title=title,
                streamUrl=streamUrl or "",
                duration=-1,
                isRadio=True
            )
            self.loaded_models[model_id] = radio_model
            return True

        def get_channels(params:dict=None) -> list:
            params = params or {}
            response = self.make_request(
                action='LiveTv/Channels',
                mode='GET',
                params={
                    "userId": self.get_property("userId"),
                    **params
                }
            )
            return response.get('Items', []) if isinstance(response, dict) else []

        def add_channel(radio:dict) -> bool:
            radio_id = radio.get("Id")
            if not cache_radio(radio_id, radio.get("Name")):
                return False

            raw_url = None
            radio_metadata = self.make_request(
                action='Items/{id}/PlaybackInfo',
                action_keys={'id': radio_id},
                params={
                    "fields": "Path",
                    "userId": self.get_property("userId")
                }
            ).get('MediaSources', [])
            if len(radio_metadata) > 0:
                raw_url = radio_metadata[0].get('Path')
            if not raw_url:
                raw_url = self.get_stream_url(radio_id)
            self.loaded_models.get(radio_id).set_property("streamUrl", raw_url)
            return True

        channels = get_channels({"type": "Radio"})

        # Some Jellyfin M3U internet-radio stations are exposed as Live TV channels
        # without the Radio channel type, so retry without that filter before giving up.
        if not channels:
            channels = get_channels()

        id_list = []
        for radio in channels:
            radio_id = radio.get("Id")
            if radio_id in id_list:
                continue
            if add_channel(radio):
                id_list.append(radio_id)

        tuner_hosts_response = self.make_request(
            action='LiveTv/TunerHosts',
            mode='GET'
        )
        if isinstance(tuner_hosts_response, dict):
            tuner_hosts = tuner_hosts_response.get('Items', [])
        elif isinstance(tuner_hosts_response, list):
            tuner_hosts = tuner_hosts_response
        else:
            tuner_hosts = []

        if not tuner_hosts:
            live_tv_config = self.make_request(
                action='System/Configuration/livetv',
                mode='GET'
            )
            tuner_hosts = live_tv_config.get('TunerHosts', []) if isinstance(live_tv_config, dict) else []

        if not isinstance(tuner_hosts, list):
            tuner_hosts = []

        for radio in tuner_hosts:
            radio_id = radio.get("Id")
            if radio_id in id_list:
                continue
            title = radio.get("FriendlyName") or radio.get("Name") or radio.get("Url")
            stream_url = radio.get("Url") or ""
            if cache_radio(radio_id, title, stream_url):
                id_list.append(radio_id)

        return id_list

    def createInternetRadioStation(self, name:str, streamUrl:str) -> bool:
        radio = self.make_request(
            action='LiveTv/TunerHosts',
            mode='POST',
            json={
                "Url": streamUrl,
                "Type": "M3U",
                "FriendlyName": name
            }
        )
        if radio.get('Id'):
            self.loaded_models[radio.get("Id")] = models.Song(
                id=radio.get("Id"),
                title=radio.get("FriendlyName"),
                duration=-1,
                isRadio=True
            )
            return True
        return False

    def deleteInternetRadioStation(self, model_id:str) -> bool:
        response = self.make_request(
            action='LiveTv/TunerHosts',
            mode='DELETE',
            params={
                "id": model_id
            }
        )
        if response.get('state') == 'ok':
            self.cache_actions['deleted-radios'].append(model_id)
            return True
        return False

    def createPlaylist(self, name:str=None, playlistId:str=None, songId:list=[]) -> str:
        if playlistId:
            return self.updatePlaylist(
                playlistId=playlistId,
                songIdToAdd=songId
            )

        response = self.make_request(
            action='Playlists',
            mode="POST",
            params={
                "UserId": self.get_property("userId"),
                "MediaType": "Audio"
            },
            json={
                "Name": name,
                "Ids": ",".join(songId)
            }
        )
        return response.get("Id")

    def updatePlaylist(self, playlistId:str, songIdToAdd:list=[], songIndexToRemove:list=[]) -> bool:
        if songIndexToRemove:
            current_items = self.make_request(
                action='Playlists/{id}/Items',
                action_keys={"id": playlistId},
                mode="GET",
                params={
                    "UserId": self.get_property("userId")
                }
            ).get("Items", [])

            entry_ids_to_remove = []
            for index in songIndexToRemove:
                if 0 <= index < len(current_items):
                    entry_ids_to_remove.append(current_items[index].get("PlaylistItemId"))

            if entry_ids_to_remove:
                self.make_request(
                    action='Playlists/{id}/Items',
                    action_keys={"id": playlistId},
                    mode="DELETE",
                    params={
                        "EntryIds": ",".join(entry_ids_to_remove)
                    }
                )

        if songIdToAdd:
            self.make_request(
                action="Playlists/{id}/Items",
                action_keys={"id": playlistId},
                mode="POST",
                params={
                    "Ids": ",".join(songIdToAdd),
                    "UserId": self.get_property("userId")
                }
            )

        return True

    def deletePlaylist(self, model_id:str) -> bool:
        response = self.make_request(
            action='Items/{id}',
            action_keys={'id': model_id},
            mode="DELETE"
        )
        return response.get("state") == "ok"

    def setRating(self, model_id:str, rating:int=0) -> bool:
        RATINGSFILE = os.path.join(self.getIntegrationDir(), 'ratings.json')

        try:
            with open(RATINGSFILE, 'r') as f:
                rating_dict = json.load(f)
            if not isinstance(rating_dict, dict):
                rating_dict = {}
        except Exception:
            rating_dict = {}
        rating_dict[model_id] = rating

        self.loaded_models.get(model_id).set_property('userRating', rating)
        with open(RATINGSFILE, 'w') as f:
            json.dump(rating_dict, f, ensure_ascii=False)
        return True

    def getTopSongs(self, artist_id:str, count:int=10) -> list:
        songs = self.make_request(
            action='Users/{userId}/Items',
            mode='GET',
            params={
                'AlbumArtistIds': artist_id,
                'IncludeItemTypes': 'Audio',
                'SortBy': 'PlayCount',
                'SortOrder': 'Descending',
                'Limit': count,
                'Recursive': 'true'
            }
        ).get('Items', [])
        return [song.get('Id') for song in songs if song.get('Id')]

    def downloadSong(self, model_id:str, file_title:str, progress_callback:callable):
        headers = {
            **self.get_base_header(),
            "Accept": "application/json"
        }
        try:
            with requests.get(self.get_url('Items/{id}/Download', id=model_id), headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded_size = 0
                extension = DOWNLOAD_MIME_MAP.get(r.headers.get('Content-Type'), '.mp3')
                file_name = '{}{}'.format(file_title, extension)
                file_path = os.path.join(DOWNLOAD_QUEUE_DIR, file_name)
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                progress_callback(downloaded_size / total_size)
                os.replace(file_path, os.path.join(DOWNLOADS_DIR, file_name))
        except:
            pass

    def getServerInformation(self) -> dict:
        server_information = {
            'link': self.get_property('url').strip('/'),
            'username': self.get_property('user').title()
        }
        try:
            params = {
                "maxWidth": 240,
                "quality": 90
            }
            response = requests.get(
                self.get_url('Users/{userId}/Images/Primary'),
                params=params,
                verify=not self.get_property('trustServer')
            )
            response_bytes = response.content if response.status_code == 200 else b''
            if response_bytes and len(response_bytes) > 0:
                gbytes = GLib.Bytes.new(response_bytes)
                server_information['picture'] = Gdk.Texture.new_from_bytes(gbytes)
        except Exception:
            pass

        try:
            info = self.make_request(
                action="System/Info",
                mode="GET"
            )
            server_information["title"] = "{} {}".format(info.get("ServerName"), info.get("Version"))
        except Exception:
            pass

        return server_information
