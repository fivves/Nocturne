# playlists.py

from gi.repository import Gtk, Adw, GLib, GObject, Gio
from ...integrations import get_current_integration, models
from ..playlist import PlaylistRow, PlaylistButton
from ..search import clear_search_entry
import re

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/playlists.ui')
class PlaylistsPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturnePlaylistsPage'

    toggle_group_el = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    list_el = Gtk.Template.Child()
    wrapbox_el = Gtk.Template.Child()

    def __init__(self):
        super().__init__()
        Gio.Settings(schema_id="com.jeffser.Nocturne").bind(
            "default-view-mode",
            self.toggle_group_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )

    def reload(self):
        # call in different thread
        GLib.idle_add(self.main_stack.set_visible_child_name, 'loading')
        integration = get_current_integration()
        playlists = integration.getPlaylists()
        GLib.idle_add(self.reset)
        for id in playlists:
            GLib.idle_add(self.list_el.append, PlaylistRow(id))
            GLib.idle_add(self.wrapbox_el.append, PlaylistButton(id))
        GLib.idle_add(self.update_visibility)

    def reset(self):
        self.list_el.remove_all()
        for el in list(self.wrapbox_el):
            self.wrapbox_el.remove(el)

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        query = search_entry.get_text()
        for child in list(self.list_el) + list(self.wrapbox_el):
            child.set_visible(child.get_name() != 'GtkListBoxRow' and re.search(query, child.get_name(), re.IGNORECASE))
        GLib.idle_add(self.update_visibility)

    @Gtk.Template.Callback()
    def on_stop_search(self, search_entry):
        clear_search_entry(search_entry)

    def update_visibility(self):
        for row in list(self.list_el) + list(self.wrapbox_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
