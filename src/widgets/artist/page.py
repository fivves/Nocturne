# page.py

from gi.repository import Gtk, Adw, Gdk, GLib, Pango
from ...integrations import get_current_integration
from ...constants import CONTEXT_ARTIST
from ..containers import get_context_buttons_list
from ..song import SongSmallRow
from ..album import AlbumButton
from .button import ArtistButton
import threading, uuid, io
from colorthief import ColorThief

@Gtk.Template(resource_path='/com/jeffser/Nocturne/artist/page.ui')
class ArtistPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneArtistPage'

    clamp_el = Gtk.Template.Child()
    avatar_el = Gtk.Template.Child()
    name_el = Gtk.Template.Child()
    biography_el = Gtk.Template.Child()
    star_el = Gtk.Template.Child()
    top_songs_wrapbox = Gtk.Template.Child()
    album_wrapbox = Gtk.Template.Child()
    artist_carousel = Gtk.Template.Child()
    rating_container = Gtk.Template.Child()
    context_wrap_el = Gtk.Template.Child()

    def __init__(self, id:str):
        self.id = id
        integration = get_current_integration()
        integration.verifyArtist(self.id, True)
        super().__init__(
            tag=str(uuid.uuid4()),
        )

        self.star_el.set_action_target_value(GLib.Variant.new_string(self.id))
        context_buttons = get_context_buttons_list(CONTEXT_ARTIST, self.id)
        for btn in context_buttons:
            self.context_wrap_el.append(btn)

        integration.connect_to_model(self.id, 'name', self.update_name)
        integration.connect_to_model(self.id, 'biography', self.update_biography)
        integration.connect_to_model(self.id, 'starred', self.update_starred)
        integration.connect_to_model(self.id, 'album', self.update_album_list)
        integration.connect_to_model(self.id, 'similarArtist', self.update_artist_list)
        integration.connect_to_model(self.id, 'gdkPaintable', self.update_cover)
        integration.connect_to_model(self.id, 'userRating', self.update_rating)

        self.top_songs_wrapbox.set_header(
            label=_("Top Songs"),
            icon_name="music-note-symbolic"
        )

        self.album_wrapbox.set_header(
            label=_("Albums"),
            icon_name="music-queue-symbolic"
        )

        self.artist_carousel.set_header(
            label=_("Related Artists"),
            icon_name="music-artist-symbolic"
        )

        self.top_songs_wrapbox.list_el.set_justify(Adw.JustifyMode.FILL)
        self.top_songs_wrapbox.list_el.set_justify_last_line(True)
        self.top_songs_wrapbox.list_el.set_child_spacing(5)
        self.top_songs_wrapbox.list_el.set_line_spacing(5)
        threading.Thread(target=self.update_top_songs).start()

    def set_top_songs(self, top_songs:list):
        self.top_songs_wrapbox.set_visible(len(top_songs) > 5)
        if len(top_songs) > 5:
            song_widgets = [SongSmallRow(song_id, show_album_name=True) for song_id in top_songs]
            self.top_songs_wrapbox.set_widgets(song_widgets)

    def update_top_songs(self):
        # call in different thread
        integration = get_current_integration()
        top_songs = integration.getTopSongs(self.id)
        GLib.idle_add(self.set_top_songs, top_songs)

    def update_rating(self, rating:int):
        for i, el in enumerate(list(self.rating_container)):
            el.set_icon_name("starred-symbolic" if rating >= i+1 else "non-starred-symbolic")

    def update_cover(self, paintable:Gdk.Paintable=None):
        if paintable:
            self.avatar_el.set_custom_image(paintable)
            self.update_background(paintable.save_to_png_bytes().get_data())
        elif isinstance(self.avatar_el.get_custom_image(), Adw.SpinnerPaintable):
            self.avatar_el.set_custom_image(None)

    def update_background(self, raw_bytes:bytes):
        def apply_css(color):
            css = f"""
            clamp {{
                transition: background .2s;
                background: linear-gradient(180deg, color-mix(in srgb, rgb({','.join([str(c) for c in color])}) 50%, transparent), transparent 30%);
                background-size: 100% 1000px;
                background-repeat: no-repeat;
            }}
            """
            provider = Gtk.CssProvider()
            provider.load_from_data(css.encode())
            self.clamp_el.get_style_context().add_provider(
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        def run():
            img_io = io.BytesIO(raw_bytes)
            color = ColorThief(img_io).get_color(quality=10)
            GLib.idle_add(apply_css, color)
        if raw_bytes:
            threading.Thread(target=run).start()

    def update_name(self, name:str):
        self.avatar_el.set_tooltip_text(name)
        self.name_el.set_label(name)
        self.name_el.set_visible(name)
        self.set_title(name or _('Author'))
        self.set_name(name)

    def update_biography(self, biography:str):
        self.biography_el.set_label(biography.strip())
        self.biography_el.get_parent().set_visible(biography.strip())

    def update_starred(self, starred:bool):
        if starred:
            self.star_el.add_css_class('accent')
            self.star_el.remove_css_class('dim-label')
            self.star_el.set_icon_name('heart-filled-symbolic')
            self.star_el.set_tooltip_text(_('Favorite'))
        else:
            self.star_el.remove_css_class('accent')
            self.star_el.add_css_class('dim-label')
            self.star_el.set_icon_name('heart-outline-thick-symbolic')
            self.star_el.set_tooltip_text(_('Not Favorite'))

    def update_album_list(self, album_list:list):
        if album_list:
            albums = [a.get('id') for a in album_list if isinstance(a, dict)]
            album_buttons = []
            for album in albums:
                button = AlbumButton(album)
                button.artist_el.set_visible(False)
                button.set_halign(Gtk.Align.CENTER)
                button.name_el.remove_css_class('title-3')
                album_buttons.append(button)
            self.album_wrapbox.set_widgets(album_buttons)

    def update_artist_list(self, artist_list:list):
        artists = [a.get('id') for a in artist_list]
        GLib.idle_add(self.artist_carousel.set_widgets, [ArtistButton(id) for id in artists])

    # -- Callbacks --

    @Gtk.Template.Callback()
    def on_biography_clicked(self, button):
        if button.get_child().get_ellipsize() == Pango.EllipsizeMode.NONE:
            button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
        else:
            button.get_child().set_ellipsize(Pango.EllipsizeMode.NONE)

    @Gtk.Template.Callback()
    def change_rating(self, button):
        integration = get_current_integration()
        try:
            rating = int(button.get_name())
            if rating == integration.loaded_models.get(self.id).get_property('userRating'):
                rating = 0
        except:
            return
        integration.setRating(self.id, rating)
