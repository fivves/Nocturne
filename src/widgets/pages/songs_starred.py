# songs_starred.py

from gi.repository import Gtk, Adw, GLib, GObject, Gio
from ...integrations import get_current_integration
from ..search import clear_search_entry
from ..song import SongSmallRow, SongRow
import threading, re

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/songs_starred.ui')
class SongsStarredPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneSongsStarredPage'

    list_el = Gtk.Template.Child()
    wrapbox_el = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()

    def reload(self):
        GLib.idle_add(self.main_stack.set_visible_child_name, 'loading')
        integration = get_current_integration()
        songs = integration.getStarredSongs()
        GLib.idle_add(self.reset)
        for id in songs:
            GLib.idle_add(self.list_el.list_el.append, SongRow(id))
            GLib.idle_add(self.wrapbox_el.append, SongSmallRow(id))
        GLib.idle_add(self.update_visibility)

    def reset(self):
        self.list_el.list_el.remove_all()
        for el in list(self.wrapbox_el):
            self.wrapbox_el.remove(el)

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        query = search_entry.get_text()
        for child in list(self.list_el.list_el) + list(self.wrapbox_el):
            child.set_visible(child.get_name() != 'GtkListBoxRow' and re.search(query, child.get_name(), re.IGNORECASE))
        GLib.idle_add(self.update_visibility)

    @Gtk.Template.Callback()
    def on_stop_search(self, search_entry):
        clear_search_entry(search_entry)

    def update_visibility(self):
        for row in list(self.list_el.list_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
        
