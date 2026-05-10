# window.py
#
# Copyright 2026 Jeffry Samuel
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gi.repository import Gtk, Adw, GLib, Gst, Gio, GObject, Pango, Gdk

from . import actions
from .integrations import get_current_integration
from .constants import SIDEBAR_MENU
import threading

class SidebarItem(Adw.SidebarItem):
    __gtype_name__ = 'NocturneSidebarItem'
    page_tag = GObject.Property(type=str)
    playlist_id = GObject.Property(type=str) # optional

@Gtk.Template(resource_path='/com/jeffser/Nocturne/window.ui')
class NocturneWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'NocturneWindow'

    sidebar_headerbar = Gtk.Template.Child()
    loading_el = Gtk.Template.Child()
    breakpoint_el = Gtk.Template.Child()
    main_navigationview = Gtk.Template.Child()
    main_bottom_sheet = Gtk.Template.Child()
    main_split_view = Gtk.Template.Child()
    sheet_split_view = Gtk.Template.Child()
    playing_page = Gtk.Template.Child()
    queue_page = Gtk.Template.Child()
    lyrics_page = Gtk.Template.Child()
    player_sidebar_splitview = Gtk.Template.Child()
    sidebar_playing_page = Gtk.Template.Child()
    sidebar_queue_page = Gtk.Template.Child()
    sidebar_lyrics_page = Gtk.Template.Child()
    main_sidebar = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    footer = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    sync_button_el = Gtk.Template.Child()
    downloads_button_el = Gtk.Template.Child()

    @Gtk.Template.Callback()
    def close_request(self, window):
        if not self.get_hide_on_close():
            if integration := get_current_integration():
                id_list = [so.get_string() for so in integration.loaded_models.get('currentSong').get_property('queueModel')]
                current_song = integration.loaded_models.get('currentSong')
                integration.savePlayQueue(id_list, current_song.get_property('songId'), current_song.get_property('positionSeconds') * 1000)
                integration.terminate_instance()
            settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
            settings.set_int('default-width', self.get_width())
            settings.set_int('default-height', self.get_height())
            self.get_application().quit()

    @Gtk.Template.Callback()
    def on_sidebar_activated(self, sidebar, index):
        page_tag = sidebar.get_selected_item().get_property('page_tag')
        if page_tag == "playlist":
            playlist_id = sidebar.get_selected_item().get_property('playlist_id')
            self.activate_action("app.replace_root_page", GLib.Variant('s', 'playlists'))
            self.activate_action("app.show_playlist", GLib.Variant('s', playlist_id))
        else:
            self.replace_root_page(page_tag)

    def replace_root_page(self, page_tag:str):
        page = self.main_navigationview.find_page(page_tag)
        if page:
            self.main_bottom_sheet.set_open(False)
            self.main_split_view.set_show_content(True)
            threading.Thread(target=page.reload).start()
            self.main_navigationview.replace([page])

    def create_action(self, callback:callable, shortcuts:list=[], parameter_type:str="s"):
        self.get_application().create_action(
            name=callback.__name__,
            callback=lambda at, va, cb=callback, win=self: cb(win, va.unpack()) if va is not None else cb(win),
            shortcuts=shortcuts,
            parameter_type=GLib.VariantType.new(parameter_type) if parameter_type else None
        )

    def focus_accepts_text(self, widget) -> bool:
        while widget:
            if isinstance(widget, (Gtk.Entry, Gtk.SearchEntry, Gtk.TextView, Gtk.Editable)):
                return True
            widget = widget.get_parent()
        return False

    def setup_keyboard_shortcuts(self):
        key_controller = Gtk.EventControllerKey()
        key_controller.connect('key-pressed', self.on_key_pressed)
        self.add_controller(key_controller)

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval != Gdk.KEY_space:
            return Gdk.EVENT_PROPAGATE
        modifiers = (
            Gdk.ModifierType.CONTROL_MASK |
            Gdk.ModifierType.ALT_MASK |
            Gdk.ModifierType.META_MASK |
            Gdk.ModifierType.SUPER_MASK
        )
        if state & modifiers or self.focus_accepts_text(self.get_focus()):
            return Gdk.EVENT_PROPAGATE

        actions.player_toggle(self)
        return Gdk.EVENT_STOP

    def setup_sidebar(self):
        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        for section in SIDEBAR_MENU:
            section_el = Adw.SidebarSection(
                title=section.get('title')
            )
            self.main_sidebar.append(section_el)
            for item in section.get('items'):
                row = SidebarItem(
                    title=item.get('title'),
                    icon_name=item.get('icon-name'),
                    page_tag=item.get('page-tag')
                )
                if item.get('page-tag') == 'playlists':
                    settings.bind(
                        'show-playlists-in-sidebar',
                        row,
                        'visible',
                        Gio.SettingsBindFlags.INVERT_BOOLEAN
                    )
                section_el.append(row)

    def update_loading_message(self, integration):
        message = integration.get_property("loadingMessage")
        self.loading_el.set_visible(message)
        self.loading_el.set_tooltip_text(message)
        if not message:
            threading.Thread(target=self.main_navigationview.get_visible_page().reload).start()

    def update_playlist_section_of_sidebar(self):
        integration = get_current_integration()
        integration.connect('notify::loadingMessage', lambda integration, ud: self.update_loading_message(integration))
        if integration.get_property('loadingMessage'):
            self.update_loading_message(integration)

        settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        playlist_section = self.main_sidebar.get_sections()[-1]

        GLib.idle_add(playlist_section.remove_all)
        item = SidebarItem(
            title=_("All"),
            icon_name="playlist-symbolic",
            page_tag="playlists"
        )
        settings.bind(
            'show-playlists-in-sidebar',
            item,
            'visible',
            Gio.SettingsBindFlags.DEFAULT
        )
        GLib.idle_add(playlist_section.append, item)

        for playlistId in integration.getPlaylists()[:4]:
            if model := integration.loaded_models.get(playlistId):
                item = SidebarItem(
                    page_tag="playlist",
                    playlist_id=playlistId
                )
                settings.bind(
                    'show-playlists-in-sidebar',
                    item,
                    'visible',
                    Gio.SettingsBindFlags.DEFAULT
                )
                GLib.idle_add(playlist_section.append, item)
                integration.connect_to_model(playlistId, "name", lambda name, row=item: row.set_title(name))
                integration.connect_to_model(playlistId, "songCount", lambda n, row=item: row.set_subtitle(('{} Songs' if n > 1 else '{} Song').format(n)))

    def setup(self):
        # call using glib_add
        self.footer.setup()
        self.playing_page.setup()
        self.lyrics_page.setup()
        self.queue_page.setup()
        self.sidebar_playing_page.setup()
        self.sidebar_lyrics_page.setup()
        self.sidebar_queue_page.setup()
        self.downloads_button_el.setup()
        integration = get_current_integration()
        sync_available = integration.__gtype_name__ == 'NocturneIntegrationJellyfin'
        self.sync_button_el.set_visible(sync_available)
        if action := self.get_application().lookup_action("sync_jellyfin_server"):
            action.set_enabled(sync_available)
        integration.connect_to_model('currentSong', 'songId', self.song_changed)

    def song_changed(self, songId:str):
        playing = bool(songId)
        if application := self.get_root().get_application():
            if playing:
                application.inhibit_suspend()
            else:
                application.uninhibit_suspend()
                if popout_window := application.popout_window:
                    popout_window.close()
        self.big_breakpoint_toggled()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.create_action(actions.generate_auto_play_queue, parameter_type="b")
        self.create_action(actions.set_equalizer_preset)
        self.create_action(actions.replace_root_page)
        self.create_action(actions.visit_url)
        self.create_action(actions.toggle_star)
        self.create_action(actions.sync_jellyfin_server, parameter_type=None)
        self.create_action(actions.logout, parameter_type=None)
        self.create_action(actions.show_external_file_warning, parameter_type=None)
        self.create_action(actions.update_navidrome_server, parameter_type=None)
        self.create_action(actions.delete_navidrome_server, parameter_type=None)
        self.create_action(actions.open_popout_window, shortcuts=['<ctrl>P'], parameter_type=None)
        self.create_action(actions.toggle_fullscreen, shortcuts=['F11'], parameter_type=None)

        self.create_action(actions.player_play, parameter_type=None)
        self.create_action(actions.player_pause, parameter_type=None)
        self.create_action(actions.player_toggle, parameter_type=None)
        self.setup_keyboard_shortcuts()
        self.create_action(actions.player_next, parameter_type=None)
        self.create_action(actions.player_previous, parameter_type=None)

        self.create_action(actions.play_radio)
        self.create_action(actions.add_radio, parameter_type=None)
        self.create_action(actions.update_radio)
        self.create_action(actions.delete_radio)

        self.create_action(actions.play_song)
        self.create_action(actions.play_song_from_list, parameter_type="a{sv}") # dict with string keys and any values
        self.create_action(actions.play_song_next)
        self.create_action(actions.play_song_later)
        self.create_action(actions.play_songs, parameter_type="as")
        self.create_action(actions.play_songs_next, parameter_type="as")
        self.create_action(actions.play_songs_later, parameter_type="as")
        self.create_action(actions.edit_lyrics)
        self.create_action(actions.save_lyrics, parameter_type="a{sv}")
        self.create_action(actions.play_random_queue, parameter_type=None)

        self.create_action(actions.show_album)
        self.create_action(actions.show_album_from_song)
        self.create_action(actions.play_album)
        self.create_action(actions.play_album_next)
        self.create_action(actions.play_album_later)
        self.create_action(actions.play_album_shuffle)

        self.create_action(actions.show_playlist)
        self.create_action(actions.play_playlist)
        self.create_action(actions.play_playlist_next)
        self.create_action(actions.play_playlist_later)
        self.create_action(actions.play_playlist_shuffle)
        self.create_action(actions.update_playlist)
        self.create_action(actions.create_playlist, parameter_type=None)
        self.create_action(actions.remove_songs_from_playlist, parameter_type="a{sv}")
        self.create_action(actions.prompt_add_songs_to_playlist, parameter_type="as")
        self.create_action(actions.add_songs_to_playlist, parameter_type="a{sv}")
        self.create_action(actions.prompt_add_song_to_playlist)
        self.create_action(actions.prompt_add_album_to_playlist)
        self.create_action(actions.delete_playlist)

        self.create_action(actions.show_artist)
        self.create_action(actions.show_artist_from_song)
        self.create_action(actions.show_artist_from_album)
        self.create_action(actions.play_shuffle_artist)
        self.create_action(actions.play_radio_artist)

        self.create_action(actions.download_song)
        self.create_action(actions.download_songs, parameter_type="as")
        self.create_action(actions.download_album)
        self.create_action(actions.download_playlist)
        self.create_action(actions.delete_download)
        self.create_action(actions.delete_downloads, parameter_type="as")

        self.settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
        self.set_property('default-width', self.settings.get_value('default-width').unpack())
        self.set_property('default-height', self.settings.get_value('default-height').unpack())
        self.set_property('hide-on-close', self.settings.get_value('hide-on-close').unpack())
        self.settings.bind(
            "hide-on-close",
            self,
            "hide-on-close",
            Gio.SettingsBindFlags.DEFAULT
        )

        list(list(self.sidebar_headerbar)[0])[0].get_center_widget().get_child().set_ellipsize(Pango.EllipsizeMode.NONE)

        css_settings = {
            'use-dynamic-accent': 'dynamic-accent',
            'player-blur-bg': 'player-translucent'
        }
        for key, class_name in css_settings.items():
            self.settings.connect('changed::{}'.format(key), self.css_toggled, class_name)
            self.css_toggled(self.settings, key, class_name)

        self.settings.connect('changed::global-dynamic-bg-mode', self.dynamic_bg_mode_changed, 'global-')
        self.dynamic_bg_mode_changed(self.settings, 'global-dynamic-bg-mode', 'global-')
        self.settings.connect('changed::player-dynamic-bg-mode', self.dynamic_bg_mode_changed, '')
        self.dynamic_bg_mode_changed(self.settings, 'player-dynamic-bg-mode', '')
        self.settings.connect('changed::use-sidebar-player', lambda *_: self.big_breakpoint_toggled())
        GLib.idle_add(self.setup_sidebar)

    def css_toggled(self, settings, key, css_class):
        if settings.get_value(key).unpack():
            self.add_css_class(css_class)
        else:
            self.remove_css_class(css_class)

    def dynamic_bg_mode_changed(self, settings, key, prefix):
        value = settings.get_value(key).unpack()
        self.remove_css_class('{}dynamic-bg-gradient'.format(prefix))
        self.remove_css_class('{}dynamic-bg-blur'.format(prefix))
        if value:
            self.add_css_class('{}dynamic-bg-{}'.format(prefix, value))

    @Gtk.Template.Callback()
    def on_drop(self, drop_target, file, x, y):
        self.get_application().do_open([file])

    @Gtk.Template.Callback()
    def big_breakpoint_toggled(self, bp=None):
        if integration := get_current_integration():
            song_playing = bool(integration.loaded_models.get('currentSong').get_property('songId'))
        else:
            song_playing = False

        is_small = self.get_width() <= 840
        if is_small:
            GLib.idle_add(self.player_sidebar_splitview.set_show_sidebar, False)
            GLib.idle_add(self.main_bottom_sheet.set_reveal_bottom_bar, song_playing)
            GLib.idle_add(self.main_bottom_sheet.set_can_open, song_playing)
        else:
            show_sidebar = self.settings.get_value('use-sidebar-player').unpack()
            GLib.idle_add(self.player_sidebar_splitview.set_show_sidebar, show_sidebar and song_playing)
            GLib.idle_add(self.main_bottom_sheet.set_reveal_bottom_bar, not show_sidebar and song_playing)
            GLib.idle_add(self.main_bottom_sheet.set_can_open, not show_sidebar and song_playing)
            if show_sidebar:
                GLib.idle_add(self.main_bottom_sheet.set_open, False)
        if not song_playing:
            GLib.idle_add(self.main_bottom_sheet.set_open, False)
