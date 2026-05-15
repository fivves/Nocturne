# base.py

from gi.repository import Gtk, GLib, GObject, Gdk
from . import models, secret
from ..constants import get_nocturne_version, DEFAULT_MUSIC_DIR, INTEGRATIONS_DIR
import requests, io, urllib3, time, os, json
from PIL import Image
from datetime import datetime
from urllib.parse import urlparse

# Just so that the logs don't get cluttered with warnings if trust-server = True
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DO NOT USE DIRECTLY
class Base(GObject.Object):
    __gtype_name__ = 'NocturneIntegrationBase'

    # For how to fill these checkout navidrome.py and local.py
    login_page_metadata = {}
    button_metadata = {}
    limitations = ()

    # Always have a currentSong inside loaded_models
    loaded_models = {'currentSong': models.CurrentSong()}

    url = GObject.Property(type=str)
    trustServer = GObject.Property(type=bool, default=False)
    user = GObject.Property(type=str)
    libraryDir = GObject.Property(type=str, default=DEFAULT_MUSIC_DIR)

    # Show spinner in sidebar with message as tooltip text if set
    loadingMessage = GObject.Property(type=str)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.loaded_models = {'currentSong': models.CurrentSong()}

    def open_json(self, filename:str, is_list:bool=False) -> dict | list:
        # loads a JSON file from the current integration
        try:
            with open(os.path.join(self.getIntegrationDir(), filename), 'r') as f:
                result = json.load(f)
                if is_list:
                    if not isinstance(result, list):
                        return []
                else:
                    if not isinstance(result, dict):
                        return {}
                return result
        except Exception:
            return [] if is_list else {}

    def check_if_ready(self, row) -> bool:
        # gets called to see if it is ready to show login page
        return True

    def connect_to_model(self, model_id:str, parameter:str, callback:callable) -> str:
        # do not modify this function, it works as is in any instance
        connection_id = ""
        if model_id in self.loaded_models:
            connection_id = self.loaded_models.get(model_id).connect(
                'notify::{}'.format(parameter),
                lambda *_, parameter=parameter, model_id=model_id: GLib.idle_add(callback, self.loaded_models.get(model_id).get_property(parameter))
            )
            GLib.idle_add(callback, self.loaded_models.get(model_id).get_property(parameter))
        return connection_id

    def start_instance(self) -> bool:
        # always called in different thread, because it might take a couple of seconds to get started
        print('WARNING', 'start_instance', 'not implemented')
        return False

    def terminate_instance(self):
        # called when the instance is no longer used
        print('WARNING', 'terminate_instance', 'not implemented')

    def on_login(self):
        # gets called in different thread when the login is successful
        print('WARNING', 'on_login', 'not implemented')

    def get_stream_url(self, song_id:str) -> str:
        # should return a valid url for a gst stream
        print('WARNING', 'get_stream_url', 'not implemented')
        return ""

    def getIntegrationDir(self) -> str:
        # do not modify this function
        directory = os.path.join(INTEGRATIONS_DIR, self.__gtype_name__)
        os.makedirs(directory, exist_ok=True)
        return directory

    def getCoverArt(self, model_id:str='', big:bool=False) -> Gdk.Paintable:
        # should set gdkPaintable to Model
        # should return Gdk.Paintable (texture)
        # Important: if big is set to True then DO NOT save the picture to the model, just return it
        # Resolutios: 240 normally, 720 if big is set to True
        print('WARNING', 'getCoverArt', 'not implemented')
        return None

    def ping(self) -> bool:
        # return True if logged in and connection is successful
        print('WARNING', 'ping', 'not implemented')
        return False

    def getAlbumList(self, list_type:str="recent", size:int=10, offset:int=0) -> list:
        # add non existing elements to self.loaded_models, returns lists of IDs, nothing more
        # list_type = random, newest, frequent, recent, starred
        print('WARNING', 'getAlbumList', 'not implemented')
        return []

    def getArtists(self, size:int=10, list_type:str="alphabetical") -> list:
        # add non existing elements to self.loaded_models, returns lists of IDs, nothing more
        # list_type = alphabetical, random
        print('WARNING', 'getArtists', 'not implemented')
        return []

    def getPlaylists(self) -> list:
        # add non existing elements to self.loaded_models, returns lists of IDs, nothing more
        print('WARNING', 'getPlaylists', 'not implemented')
        return []

    def getStarredSongs(self) -> list:
        # returns a list of IDs of songs
        print('WARNING', 'getStarredSongs', 'not implemented')
        return []

    def verifyArtist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        # verifies that element is fully loaded with all it's metadata, should also call for getCoverArt
        print('WARNING', 'verifyArtist', 'not implemented')

    def verifyAlbum(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        # verifies that element is fully loaded with all it's metadata, should also call for getCoverArt
        print('WARNING', 'verifyAlbum', 'not implemented')

    def verifyPlaylist(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        # verifies that element is fully loaded with all it's metadata, should also call for getCoverArt
        print('WARNING', 'verifyPlaylist', 'not implemented')

    def verifySong(self, model_id:str, force_update:bool=False, use_threading:bool=True):
        # verifies that element is fully loaded with all it's metadata, should also call for getCoverArt
        print('WARNING', 'verifySong', 'not implemented')

    def star(self, model_id:str) -> bool:
        # stars an element, should return True if change is done
        print('WARNING', 'star', 'not implemented')
        return False

    def unstar(self, model_id:str) -> bool:
        # unstars an element, should return True if change is done
        print('WARNING', 'unstar', 'not implemented')
        return False

    def getPlayQueue(self) -> tuple:
        # returns the song ID to be played and a list of IDs
        print('WARNING', 'getPlayQueue', 'not implemented')
        return "", []

    def savePlayQueue(self, id_list:list, current:str, position:int) -> bool:
        # save the play queue for retrieving later, called on close, return True if ok
        print('WARNING', 'savePlayQueue', 'not implemented')
        return False

    def getSimilarSongs(self, model_id:str, count:int=20) -> list:
        # returns list of IDs of similar songs to id, if it can not be implemented just return the result of getRandomSongs
        print('WARNING', 'getSimilarSongs', 'not implemented')
        return []

    def getRandomSongs(self, size:int=20) -> list:
        # returns a list of song IDs
        print('WARNING', 'getRandomSongs', 'not implemented')
        return []

    def getLyrics(self, songId:str) -> dict:
        # returns same dicts as lyrics -> helpers -> get_lyrics
        return {'type': 'not-found'}

    def search(self, query:str, artistCount:int=0, artistOffset:int=0, albumCount:int=0, albumOffset:int=0, songCount:int=0, songOffset:int=0) -> dict:
        # returns a dict with results trucated with the count and offset, the dict has keys for album, artist and song, the values are lists of IDs
        # for an example view local.py
        print('WARNING', 'search', 'not implemented')
        return {'artist': {}, 'album': {}, 'song': {}}

    def getInternetRadioStations(self) -> list:
        # returns a list of Song IDs with the property isRadio=True
        # make sure the id also exists in self.loaded_models, no need to be verified
        print('WARNING', 'getInternetRadioStations', 'not implemented')
        return []

    def createInternetRadioStation(self, name:str, streamUrl:str) -> bool:
        # returns True if created successfully
        print('WARNING', 'createInternetRadioStation', 'not implemented')
        return False

    def updateInternetRadioStation(self, model_id:str, name:str, streamUrl:str) -> bool:
        # returns True if updated successfully
        print('WARNING', 'updateInternetRadioStation', 'not implemented')
        return False

    def deleteInternetRadioStation(self, model_id:str) -> bool:
        # returns True if deleted successfully
        print('WARNING', 'deleteInternetRadioStation', 'not implemented')
        return False

    def createPlaylist(self, name:str=None, playlistId:str=None, songId:list=[]) -> str:
        # returns id if created successfully
        print('WARNING', 'createPlaylist', 'not implemented')
        return ""

    def updatePlaylist(self, playlistId:str, songIdToAdd:list=[], songIndexToRemove:list=[]) -> bool:
        # returns True if updated successfully
        print('WARNING', 'updatePlaylist', 'not implemented')
        return False

    def deletePlaylist(self, model_id:str) -> bool:
        # returns True if deleted successfully
        print('WARNING', 'deletePlaylist', 'not implemented')
        return False

    def setRating(self, model_id:str, rating:int=0) -> bool:
        # returns True if rated successfully
        print('WARNING', 'setRating', 'not implemented')
        return False

    def getTopSongs(self, artist_id:str, count:int=10) -> list:
        # returns list of ids
        print('WARNING', 'getTopSongs', 'not implemented')
        return []

    def downloadSong(self, model_id:str, file_title:str, progress_callback:callable):
        # from constants.py
        # file_title does NOT include extension (.mp3, .flac, etc)
        # download into DOWNLOAD_QUEUE_DIR
        # on finish move file to DOWNLOADS_DIR
        # see navidrome.py for example
        print('WARNING', 'downloadSong', 'not implemented')

    def scrobble(self, model_id:str, submission:bool=True):
        # the id is for a Song, this is how views are stored
        # called when a song is played
        # if you need to inherit this, also call super().scrobble(id) so that listenbrainz can also get the scrobble
        playback_scrobble = self.open_json('playback.json')
        date_formated = datetime.now().strftime("%m-%Y")
        if date_formated not in playback_scrobble:
            playback_scrobble[date_formated] = {}
        if model_id in playback_scrobble.get(date_formated):
            playback_scrobble[date_formated][model_id] += 1
        else:
            playback_scrobble[date_formated][model_id] = 1
        with open(os.path.join(self.getIntegrationDir(), 'playback.json'), 'w') as f:
            json.dump(playback_scrobble, f, ensure_ascii=False)

        if model := self.loaded_models.get(model_id):
            if token := secret.get_plain_password("listenbrainz"):
                listen_payload = {
                    "track_metadata": {
                        "artist_name": model.get_property("artist"),
                        "track_name": model.get_property("title"),
                        "release_name": model.get_property("album"),
                        "additional_info": {
                            "submission_client": "com.jeffser.Nocturne",
                            "submission_client_version": get_nocturne_version(),
                            "media_player": "Nocturne"
                        }
                    }
                }
                
                if submission:
                    listen_payload["listened_at"] = int(time.time() - (self.loaded_models.get('currentSong').get_property('positionSeconds') or 0))

                payload = {
                    "listen_type": "single" if submission else "playing_now",
                    "payload": [listen_payload]
                }
                headers = {
                    "Authorization": f"Token {token}",
                    "Content-Type": "application/json"
                }
                try:
                    response = requests.post("https://api.listenbrainz.org/1/submit-listens", json=payload, headers=headers)
                except:
                    pass
    
    def getServerInformation(self) -> dict:
        # should return these keys:
        # picture : gdk.Paintable
        # username : str
        # title : str
        # link : str
        print('WARNING', 'getServerInformation', 'not implemented')
        return {}
