# local.py

from gi.repository import Gtk, GLib, GObject, Gdk, Gio, GdkPixbuf
from . import secret, models
from .base import Base
from datetime import datetime, timezone
import requests, random, threading, io, pathlib, re, json, os, time, uuid, pwd, getpass, time, shutil
from PIL import Image
from tinytag import TinyTag
from ..constants import DOWNLOADS_DIR, get_song_info_from_file
from concurrent.futures import ThreadPoolExecutor, as_completed

class Local(Base):
    __gtype_name__ = 'NocturneIntegrationLocal'

    login_page_metadata = {
        'icon-name': "folder-open-symbolic",
        'title': _("Local Files"),
        'description': _("Let Nocturne load your local files directly, for big libraries it is recommended to use a dedicated server."),
        'entries': ['library-dir'],
        'login-label': _("Continue")
    }
    button_metadata = {
        'title': _("Local Files"),
        'subtitle': _("Limited functionality")
    }
    limitations = ('no-max-bitrate',)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._model_lock = threading.Lock()
        self._cover_art_loading = set()
        self._cover_art_lock = threading.Lock()
        self._song_ids = []
        self._album_ids = []
        self._artist_ids = []
        self._search_text = {}

    def _rebuild_indexes(self):
        song_ids = []
        album_ids = []
        artist_ids = []
        search_text = {}

        for model_id, model in self.loaded_models.items():
            if model_id.startswith('SONG:'):
                song_ids.append(model_id)
                search_text[model_id] = ' '.join([
                    model.get_property('title') or '',
                    model.get_property('album') or '',
                    model.get_property('artist') or ''
                ]).casefold()
            elif model_id.startswith('ALBUM:'):
                album_ids.append(model_id)
                search_text[model_id] = ' '.join([
                    model.get_property('name') or '',
                    model.get_property('artist') or ''
                ]).casefold()
            elif model_id.startswith('ARTIST:'):
                artist_ids.append(model_id)
                search_text[model_id] = (model.get_property('name') or '').casefold()

        self._song_ids = song_ids
        self._album_ids = album_ids
        self._artist_ids = artist_ids
        self._search_text = search_text

    def _load_song_metadata(self, song_id:str, star_dict:dict):
        song_model = self.loaded_models.get(song_id)
        if not song_model:
            return

        song = get_song_info_from_file(song_model.get_property("path"), star_dict=star_dict)
        if not song:
            return

        song["id"] = song_id
        song["starred"] = song.get("id") in star_dict

        album_id = song.get('albumId') or 'ALBUM:NO_ALBUM:{}'.format(song.get('artists')[0].get('id'))
        artist_id = song.get('artistId')

        with self._model_lock:
            song_model.update_data(**song)

            if album_id:
                if album_id in self.loaded_models:
                    album_song_list = self.loaded_models.get(album_id).song
                    if {'id': song_id} not in album_song_list:
                        album_song_list.append({'id': song_id})
                else:
                    self.loaded_models[album_id] = models.Album(
                        id=album_id,
                        coverArt=song.get('path'),
                        name=song.get('album') or _("No Album"),
                        artist=song.get('artist'),
                        artistId=song.get('artistId'),
                        song=[{'id': song_id}],
                        starred=album_id in star_dict
                    )

            if artist_id:
                if artist_id not in self.loaded_models:
                    self.loaded_models[artist_id] = models.Artist(
                        id=artist_id,
                        coverArt=song.get('path'),
                        name=song.get('artist'),
                        album=[],
                        albumCount=0,
                        starred=artist_id in star_dict
                    )

                album_list = self.loaded_models.get(artist_id).album
                if album_id and not any(album.get('id') == album_id for album in album_list):
                    album_list.append({'id': album_id})
                    self.loaded_models.get(artist_id).albumCount += 1

    def on_login(self):
        # Goes through the whole directory retrieving all the metadata
        path_obj = pathlib.Path(self.get_property('libraryDir'))

        def load_songs():
            # load songs, albums, artists
            self.set_property('loadingMessage', _("Loading Songs"))
            star_dict = self.open_json('stars.json')
            song_ids = []
            for file_path in path_obj.rglob("*"):
                if file_path.suffix.lower() in ('.mp3', '.flac', '.m4a', '.ogg', '.wav'):
                    song_id = 'SONG:{}'.format(file_path)
                    self.loaded_models[song_id] = models.Song(id=song_id, path=file_path, coverArt=file_path)
                    song_ids.append(song_id)

            worker_count = min(8, max(2, (os.cpu_count() or 2)))
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                futures = [executor.submit(self._load_song_metadata, song_id, star_dict) for song_id in song_ids]
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception:
                        pass

            self._rebuild_indexes()
            self.set_property('loadingMessage', "")
        threading.Thread(target=load_songs).start()

        # Load radios
        radio_dict = self.open_json('radios.json')

        for radio_id, radio in radio_dict.items():
            self.loaded_models[radio_id] = models.Song(
                id=radio_id,
                title=radio.get('name'),
                streamUrl=radio.get('streamUrl'),
                duration=-1,
                isRadio=True
            )

        self.load_playlists()

    def load_playlists(self):
        # Load playlists
        playlist_dict = self.open_json('playlists.json')

        for playlist_id, playlist in playlist_dict.items():
            if playlist_id not in self.loaded_models:
                path_str = ""
                if len(playlist.get('songId', [])) > 0:
                    if model := self.loaded_models.get(playlist.get('songId')[0]):
                        path_str = model.get_property('path')

                self.loaded_models[playlist_id] = models.Playlist(
                    id=playlist_id,
                    name=playlist.get('name'),
                    songCount=len(playlist.get('songId', [])),
                    entry=[{'id': model_id} for model_id in playlist.get('songId', [])],
                    coverArt = path_str
                )

    # ----------- #

    def get_stream_url(self, song_id:str) -> str:
        model = self.loaded_models.get(song_id)
        if model.get_property('isRadio'):
            return model.get_property('streamUrl')
        return 'file://{}'.format(model.get_property('path'))

    def getCoverArt(self, model_id:str='', big:bool=False) -> Gdk.Paintable:
        if model := self.loaded_models.get(model_id):
            if isinstance(model, models.Song) and model.get_property('isRadio'):
                return None
            if not big and not isinstance(model, models.Playlist) and model.get_property('gdkPaintable'):
                return model.get_property('gdkPaintable')

            coverArtPath = model.get_property('coverArt')
            if not coverArtPath:
                return None

            tag = TinyTag.get(coverArtPath, image=True)
            if tag is None:
                return None

            image_data = tag.get_image()
            if not image_data:
                return None

            try:
                img = Image.open(io.BytesIO(image_data))
                width = 720 if big else 240
                w_percent = (width / float(img.size[0]))
                height = int((float(img.size[1]) * float(w_percent)))
                resized_img = img.resize((width, height), Image.LANCZOS)
                buffer = io.BytesIO()
                resized_img.save(buffer, format="JPEG", quality=85)
                raw_data = buffer.getvalue()
                gbytes = GLib.Bytes.new(raw_data)
                texture = Gdk.Texture.new_from_bytes(gbytes)
                model.set_property('gdkPaintable', texture)
                return model.get_property('gdkPaintable')
            except Exception as e:
                pass
        return None

    def _load_cover_art_async(self, model_id:str):
        with self._cover_art_lock:
            if model_id in self._cover_art_loading:
                return
            self._cover_art_loading.add(model_id)

        def run():
            try:
                self.getCoverArt(model_id)
            finally:
                with self._cover_art_lock:
                    self._cover_art_loading.discard(model_id)

        threading.Thread(target=run).start()

    def ping(self) -> bool:
        # Always true, it checks it at login
        return True

    def getAlbumList(self, list_type:str="recent", size:int=10, offset:int=0) -> list:
        album_list = []
        if list_type == "random":
            album_list = list(self._album_ids or [model_id for model_id in list(self.loaded_models) if model_id.startswith('ALBUM:')])
            random.shuffle(album_list)
        elif list_type == "newest":
            albums = {} # id : creation_time
            album_ids = self._album_ids or [model_id for model_id in list(self.loaded_models) if model_id.startswith('ALBUM:')]
            for model in [self.loaded_models.get(model_id) for model_id in album_ids]:
                albums[model.get_property('id')] = pathlib.Path(model.get_property('coverArt')).stat().st_ctime
            album_list = sorted(albums, key=lambda x: albums.get(x), reverse=True)
        elif list_type in ("frequent", "recent"):
            try:
                with open(os.path.join(self.getIntegrationDir(), 'scrobble.json'), 'r') as f:
                    scrobble_dict = json.load(f)
                if not isinstance(scrobble_dict, dict):
                    return []
            except Exception:
                return []

            album_views = {}
            for data in scrobble_dict.values():
                if data.get('album') in album_views:
                    album_views[data.get('album')]['plays'] += data.get('plays')
                    album_views[data.get('album')]['last_play'] = max(data.get('last_play'), album_views.get(data.get('album')).get('last_play'))
                else:
                    album_views[data.get('album')] = {
                        'plays': data.get('plays'),
                        'last_play': data.get('last_play')
                    }

            if list_type == "frequent":
                album_list = sorted(album_views, key=lambda x: album_views.get(x).get('plays'), reverse=True)
            elif list_type == "recent":
                album_list = sorted(album_views, key=lambda x: album_views.get(x).get('last_play'), reverse=True)
        elif list_type == "starred":
            album_ids = self._album_ids or [model_id for model_id in list(self.loaded_models) if model_id.startswith('ALBUM:')]
            album_list = [model_id for model_id in album_ids if self.loaded_models.get(model_id).starred]
        else:
            album_list = self._album_ids or [model_id for model_id in list(self.loaded_models) if model_id.startswith('ALBUM:')]
        return [model_id for model_id in album_list if model_id in self.loaded_models][offset:size+offset]

    def getArtists(self, size:int=10) -> list:
        artist_ids = self._artist_ids or [model_id for model_id in list(self.loaded_models) if model_id.startswith('ARTIST:')]
        return artist_ids[:size]

    def getPlaylists(self) -> list:
        self.load_playlists()
        return [model_id for model_id in list(self.loaded_models) if model_id.startswith('PLAYLIST:')]

    def getStarredSongs(self) -> list:
        star_dict = self.open_json('stars.json')
        return [song_id for song_id in star_dict if song_id.startswith("SONG:") and song_id in self.loaded_models]

    def verifyArtist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        self._load_cover_art_async(model_id)

    def verifyAlbum(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        self._load_cover_art_async(model_id)

    def verifyPlaylist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        self._load_cover_art_async(model_id)

    def verifySong(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        def run():
            self._load_song_metadata(model_id, self.open_json('stars.json'))
            self._rebuild_indexes()

        if force_update or not self.loaded_models.get(model_id).get_property('title'):
            if use_threading:
                threading.Thread(target=run).start()
            else:
                run()

        self._load_cover_art_async(model_id)

    def star(self, model_id:str) -> bool:
        star_dict = self.open_json('stars.json')

        current_time = datetime.now(timezone.utc).isoformat(timespec='microseconds').replace("+00:00", "Z")
        star_dict[model_id] = current_time

        with open(os.path.join(self.getIntegrationDir(), 'stars.json'), 'w') as f:
            json.dump(star_dict, f, ensure_ascii=False)

        return True

    def unstar(self, model_id:str) -> bool:
        star_dict = self.open_json('stars.json')

        if model_id in star_dict:
            del star_dict[model_id]

        with open(os.path.join(self.getIntegrationDir(), 'stars.json'), 'w') as f:
            json.dump(star_dict, f, ensure_ascii=False)

        return True

    def getPlayQueue(self) -> tuple:
        queue_dict = self.open_json('queue.json')

        song_list = [model_id for model_id in queue_dict.get('id', []) if model_id in self.loaded_models]
        current = queue_dict.get('current', "")
        if current not in song_list:
            if len(song_list) > 0:
                current = song_list[0]
            else:
                current = ""

        return current, song_list

    def savePlayQueue(self, id_list:list, current:str, position:int) -> bool:
        final_id_list = []
        for model_id in id_list:
            if model := self.loaded_models.get(model_id):
                if not model.get_property('isExternalFile'):
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

        with open(os.path.join(self.getIntegrationDir(), 'queue.json'), 'w') as f:
            json.dump(queue_dict, f, ensure_ascii=False)

        return True

    def getSimilarSongs(self, model_id:str, count:int=20) -> list:
        # out of the scope of Local
        return self.getRandomSongs(count)

    def getRandomSongs(self, size:int=20) -> list:
        songs = self._song_ids or [song_id for song_id in list(self.loaded_models) if song_id.startswith('SONG:')]
        return random.sample(songs, k=min(size, len(songs)))

    def getLyrics(self, songId:str) -> dict:
        if model := self.loaded_models.get(songId):
            tag = TinyTag.get(model.get_property('path'))
            if lyrics_str := tag.extra.get('lyrics'):
                if lyrics_str.startswith('['):
                    return {'type': 'lrc-unprepared', 'content': lyrics_str}
                else:
                    return {'type': 'plain', 'content': lyrics_str}
        return {'type': 'not-found'}

    def search(self, query:str, artistCount:int=0, artistOffset:int=0, albumCount:int=0, albumOffset:int=0, songCount:int=0, songOffset:int=0) -> dict:
        needle = query.casefold()

        def filter_ids(model_ids, offset, count):
            matches = [model_id for model_id in model_ids if needle in self._search_text.get(model_id, '')]
            return matches[offset:count+offset]

        return {
            'artist': filter_ids(self._artist_ids, artistOffset, artistCount),
            'album': filter_ids(self._album_ids, albumOffset, albumCount),
            'song': filter_ids(self._song_ids, songOffset, songCount)
        }

    def getInternetRadioStations(self) -> list:
        return [model_id for model_id in list(self.loaded_models) if model_id.startswith('RADIO:')]

    def createInternetRadioStation(self, name:str, streamUrl:str) -> bool:
        radio_dict = self.open_json('radios.json')

        radio_id = str(uuid.uuid4())
        radio_dict[radio_id] = {
            'name': name,
            'streamUrl': streamUrl
        }

        self.loaded_models[radio_id] = models.Song(
            id=radio_id,
            title=name,
            streamUrl=streamUrl,
            duration=-1,
            isRadio=True
        )

        with open(os.path.join(self.getIntegrationDir(), 'radios.json'), 'w') as f:
            json.dump(radio_dict, f, ensure_ascii=False)

        return True

    def updateInternetRadioStation(self, model_id:str, name:str, streamUrl:str) -> bool:
        radio_dict = self.open_json('radios.json')

        radio_dict[model_id] = {
            'name': name,
            'streamUrl': streamUrl
        }
        if model := self.loaded_models.get(model_id):
            model.set_property('title', name)
            model.set_property('streamUrl', streamUrl)

        with open(os.path.join(self.getIntegrationDir(), 'radios.json'), 'w') as f:
            json.dump(radio_dict, f, ensure_ascii=False)

        return True

    def deleteInternetRadioStation(self, model_id:str) -> bool:
        radio_dict = self.open_json('radios.json')

        if model_id in radio_dict:
            del radio_dict[model_id]

        with open(os.path.join(self.getIntegrationDir(), 'radios.json'), 'w') as f:
            json.dump(radio_dict, f, ensure_ascii=False)

        return True

    def createPlaylist(self, name:str=None, playlistId:str=None, songId:list=[]) -> str:
        playlist_dict = self.open_json('playlists.json')

        playlistId = playlistId or 'PLAYLIST:{}'.format(str(uuid.uuid4()))

        playlist_dict[playlistId] = {
            'name': name,
            'songId': songId
        }

        path_str = ""
        if len(songId) > 0:
            if model := self.loaded_models.get(songId[0]):
                path_str = model.get_property('path')

        self.loaded_models[playlistId] = models.Playlist(
            id=playlistId,
            name=name,
            songCount=len(songId),
            entry=[{'id': model_id} for model_id in songId],
            coverArt = path_str
        )

        with open(os.path.join(self.getIntegrationDir(), 'playlists.json'), 'w') as f:
            json.dump(playlist_dict, f, ensure_ascii=False)

        return playlistId

    def updatePlaylist(self, playlistId:str, songIdToAdd:list=[], songIndexToRemove:list=[]) -> bool:
        playlist_dict = self.open_json('playlists.json')

        if playlistId in playlist_dict:
            songs = playlist_dict.get(playlistId).get('songId')
            for index in songIndexToRemove:
                songs.pop(int(index))
            songs.extend(songIdToAdd)
            playlist_dict[playlistId]['songId'] = songs

            if model := self.loaded_models.get(playlistId):
                songId = playlist_dict.get(playlistId).get('songId')
                model.set_property('songCount', len(songId))
                model.set_property('entry', [{'id': model_id} for model_id in songId])
                path_str = ""
                if len(songId) > 0:
                    if model := self.loaded_models.get(songId[0]):
                        path_str = model.get_property('path')
                model.set_property('coverArt', path_str)

        with open(os.path.join(self.getIntegrationDir(), 'playlists.json'), 'w') as f:
            json.dump(playlist_dict, f, ensure_ascii=False)

        return True

    def deletePlaylist(self, model_id:str) -> bool:
        playlist_dict = self.open_json('playlists.json')
        if model_id in playlist_dict:
            del playlist_dict[model_id]
        with open(os.path.join(self.getIntegrationDir(), 'playlists.json'), 'w') as f:
            json.dump(playlist_dict, f, ensure_ascii=False)

        return True

    def getTopSongs(self, artist_id:str, count:int=10) -> list:
        artist_scrobbles = {}
        for song_id, data in self.open_json('scrobble.json').items():
            found_artist = data.get('artist')
            if not found_artist:
                if model := self.loaded_models.get(song_id):
                    found_artist = model.get_property('artistId')

            if found_artist == artist_id:
                artist_scrobbles[song_id] = data.get('plays', 1)
        return sorted(artist_scrobbles, key=artist_scrobbles.get, reverse=True)[:count]

    def downloadSong(self, model_id:str, file_title:str, progress_callback:callable):
        if model := self.loaded_models.get(model_id):
            source_path = model.get_property('path')
            extension = pathlib.Path(source_path).suffix
            shutil.copy2(source_path, os.path.join(DOWNLOADS_DIR, '{}{}'.format(file_title, extension)))
            progress_callback(1)

    def scrobble(self, model_id:str, submission:bool=True):
        if not model_id:
            return
        if model := self.loaded_models.get(model_id):
            if model.get_property('isExternalFile') or model.get_property('isRadio'):
                return
            
            if submission:
                scrobble_dict = self.open_json('scrobble.json')

                if model_id in scrobble_dict:
                    scrobble_dict[model_id]['plays'] += 1
                    scrobble_dict[model_id]['last_play'] = int(time.time())
                    scrobble_dict[model_id]['album'] = model.get_property('albumId')
                    scrobble_dict[model_id]['artist'] = model.get_property('artistId')
                else:
                    scrobble_dict[model_id] = {
                        'plays': 1,
                        'last_play': int(time.time()),
                        'album': model.get_property('albumId'),
                        'artist': model.get_property('artistId')
                    }

                with open(os.path.join(self.getIntegrationDir(), 'scrobble.json'), 'w') as f:
                    json.dump(scrobble_dict, f, ensure_ascii=False)
        super().scrobble(model_id, submission=submission)

    def setRating(self, model_id:str, rating:int=0) -> bool:
        ratings = self.open_json('ratings.json')
        ratings[model_id] = rating
        self.loaded_models.get(model_id).set_property('userRating', rating)
        with open(os.path.join(self.getIntegrationDir(), 'ratings.json'), 'w') as f:
            json.dump(ratings, f, ensure_ascii=False)
        return True

    def getServerInformation(self) -> dict:
        server_information = {
            'link': 'file://{}'.format(self.get_property('libraryDir')),
            'title': _("Local Files")
        }
        try:
            gecos_temp = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')
            if len(gecos_temp) > 0:
                server_information["username"] = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')[0].title()
        except Exception:
            pass

        return server_information

class Offline(Local):
    __gtype_name__ = 'NocturneIntegrationOffline'

    login_page_metadata = {}
    button_metadata = {
        'title': _("Offline Mode"),
        'subtitle': _("Access your downloads")
    }
    limitations = ('no-downloads', 'no-max-bitrate')

    libraryDir = GObject.Property(type=str, default=DOWNLOADS_DIR)

    def getServerInformation(self) -> dict:
        server_information = {
            'title': _("Offline Mode")
        }
        try:
            gecos_temp = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')
            if len(gecos_temp) > 0:
                server_information["username"] = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')[0].title()
        except Exception:
            pass

        return server_information
