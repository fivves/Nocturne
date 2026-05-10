# home.py

from gi.repository import Gtk, Adw, GLib, Gst, Gio
from ...integrations import get_current_integration
from ..album import AlbumButton
from ..artist import ArtistButton
from ..playlist import PlaylistButton
from ..song import SongSmallRow
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/home.ui')
class HomePage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneHomePage'

    main_stack = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    song_wrapbox = Gtk.Template.Child()
    album_carousel = Gtk.Template.Child()
    artist_carousel = Gtk.Template.Child()
    playlist_carousel = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        self.search_token = 0
        self.query = ""

    def reload(self):
        # call in different thread
        integration = get_current_integration()
        query = self.query
        if query:
            self.search_token += 1
            self.search(query, self.search_token)
            return

        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        max_songs = settings.get_value('n-songs-home').unpack()
        max_albums = settings.get_value('n-albums-home').unpack()
        max_artists = settings.get_value('n-artists-home').unpack()
        max_playlists = settings.get_value('n-playlists-home').unpack()

        # -- Songs --
        self.song_wrapbox.set_header(
            label=_("Songs"),
            icon_name="music-note-symbolic",
            page_tag="songs-all"
        )
        self.song_wrapbox.list_el.set_margin_start(10)
        self.song_wrapbox.list_el.set_margin_end(10)
        self.song_wrapbox.list_el.set_justify(Adw.JustifyMode.FILL)
        self.song_wrapbox.list_el.set_justify_last_line(True)
        self.song_wrapbox.list_el.set_child_spacing(5)
        self.song_wrapbox.list_el.set_line_spacing(5)
        songs = integration.getRandomSongs(size=max_songs) if max_songs > 0 else []
        threading.Thread(
            target=self.song_wrapbox.set_widgets,
            args=([SongSmallRow(id) for id in songs],)
        ).start()

        # -- Albums --
        self.album_carousel.set_header(
            label=_("Albums"),
            icon_name="music-queue-symbolic",
            page_tag="albums-all"
        )
        albums = integration.getAlbumList(size=max_albums) if max_albums > 0 else []
        threading.Thread(
            target=self.album_carousel.set_widgets,
            args=([AlbumButton(id) for id in albums],)
        ).start()

        # -- Artists --
        self.artist_carousel.set_header(
            label=_("Artists"),
            icon_name="music-artist-symbolic",
            page_tag="artists"
        )
        artists = integration.getArtists(size=max_artists) if max_artists > 0 else []
        threading.Thread(
            target=self.artist_carousel.set_widgets,
            args=([ArtistButton(id) for id in artists],)
        ).start()

        # -- Playlists --
        self.playlist_carousel.set_header(
            label=_("Playlists"),
            icon_name="playlist-symbolic",
            page_tag="playlists"
        )
        playlists = integration.getPlaylists()[:max_playlists]
        threading.Thread(
            target=self.playlist_carousel.set_widgets,
            args=([PlaylistButton(id) for id in playlists],)
        ).start()

        n_elements = sum([len(s) for s in (songs, albums, artists, playlists)])
        self.main_stack.set_visible_child_name('content' if n_elements > 0 else 'no-content')

    def search_playlists(self, query:str, count:int=10) -> list:
        integration = get_current_integration()
        needle = query.casefold()
        matches = []
        for playlist_id in integration.getPlaylists():
            model = integration.loaded_models.get(playlist_id)
            name = model.get_property('name') if model else ''
            if needle in name.casefold():
                matches.append(playlist_id)
            if len(matches) >= count:
                break
        return matches

    def search(self, query:str, token:int):
        integration = get_current_integration()
        search_results = integration.search(
            query=query,
            songCount=10,
            albumCount=10,
            artistCount=10
        )
        playlists = self.search_playlists(query)
        GLib.idle_add(
            self.update_search_results,
            search_results.get('song', []),
            search_results.get('album', []),
            search_results.get('artist', []),
            playlists,
            token
        )

    def update_search_results(self, songs:list, albums:list, artists:list, playlists:list, token:int):
        if token != self.search_token:
            return GLib.SOURCE_REMOVE

        self.song_wrapbox.set_header(
            label=_("Songs"),
            icon_name="music-note-symbolic",
            page_tag="songs-all"
        )
        self.song_wrapbox.list_el.set_margin_start(10)
        self.song_wrapbox.list_el.set_margin_end(10)
        self.song_wrapbox.list_el.set_justify(Adw.JustifyMode.FILL)
        self.song_wrapbox.list_el.set_justify_last_line(True)
        self.song_wrapbox.list_el.set_child_spacing(5)
        self.song_wrapbox.list_el.set_line_spacing(5)
        self.song_wrapbox.set_widgets([SongSmallRow(id) for id in songs])

        self.album_carousel.set_header(
            label=_("Albums"),
            icon_name="music-queue-symbolic",
            page_tag="albums-all"
        )
        self.album_carousel.set_widgets([AlbumButton(id) for id in albums])

        self.artist_carousel.set_header(
            label=_("Artists"),
            icon_name="music-artist-symbolic",
            page_tag="artists"
        )
        self.artist_carousel.set_widgets([ArtistButton(id) for id in artists])

        self.playlist_carousel.set_header(
            label=_("Playlists"),
            icon_name="playlist-symbolic",
            page_tag="playlists"
        )
        self.playlist_carousel.set_widgets([PlaylistButton(id) for id in playlists])

        n_elements = sum([len(s) for s in (songs, albums, artists, playlists)])
        self.main_stack.set_visible_child_name('content' if n_elements > 0 else 'no-content')
        return GLib.SOURCE_REMOVE

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        self.search_token += 1
        token = self.search_token
        query = search_entry.get_text()
        self.query = query
        threading.Thread(target=self.search if query else self.reload, args=(query, token) if query else ()).start()

    def reset(self):
        self.search_token += 1
        threading.Thread(target=self.song_wrapbox.set_widgets, args=([],)).start()
        threading.Thread(target=self.album_carousel.set_widgets, args=([],)).start()
        threading.Thread(target=self.artist_carousel.set_widgets, args=([],)).start()
        threading.Thread(target=self.playlist_carousel.set_widgets, args=([],)).start()
