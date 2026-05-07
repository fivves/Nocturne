# artist.py

from gi.repository import Gtk, Adw, GLib, GObject, Gio
from ...integrations import get_current_integration, models
from ..artist import ArtistRow, ArtistButton
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/artists.ui')
class ArtistsPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneArtistsPage'

    toggle_group_el = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    list_el = Gtk.Template.Child()
    wrapbox_el = Gtk.Template.Child()
    end_stack = Gtk.Template.Child()
    scrolledwindow = Gtk.Template.Child()
    def __init__(self):
        super().__init__()
        self.offset = 0
        self.searching = False
        self.search_token = 0
        self.query = ""
        self.list_rows = {}
        self.grid_rows = {}
        Gio.Settings(schema_id="com.jeffser.Nocturne").bind(
            "default-view-mode",
            self.toggle_group_el,
            "active-name",
            Gio.SettingsBindFlags.DEFAULT
        )
        self.scrolledwindow.get_vadjustment().connect('notify::upper', lambda va, ud: GLib.timeout_add(1000, self.check_scrollbar, va))

    def check_scrollbar(self, adjustment):
        if adjustment.get_upper() <= adjustment.get_page_size():
            threading.Thread(target=self.search).start()

    def reload(self):
        if len(list(self.list_el)) + len(list(self.wrapbox_el)) == 0:
            GLib.idle_add(self.on_search, self.search_entry)

    def reset(self):
        self.list_el.remove_all()
        for el in list(self.wrapbox_el):
            self.wrapbox_el.remove(el)
        self.list_rows = {}
        self.grid_rows = {}

    def append_results(self, artist_ids:list, token:int):
        if token != self.search_token:
            return

        for artist_id in artist_ids:
            if artist_id in self.list_rows:
                self.list_rows[artist_id].set_visible(True)
            else:
                row = ArtistRow(artist_id)
                self.list_rows[artist_id] = row
                self.list_el.append(row)

            if artist_id in self.grid_rows:
                self.grid_rows[artist_id].set_visible(True)
            else:
                button = ArtistButton(artist_id)
                self.grid_rows[artist_id] = button
                self.wrapbox_el.append(button)

        self.end_stack.set_visible_child_name('end' if len(artist_ids) < 30 else 'loading')
        self.offset += 30
        self.searching = False
        self.update_visibility()

    def search(self, token=None):
        if self.searching:
            return
        self.searching = True
        token = self.search_token if token is None else token
        integration = get_current_integration()
        search_results = integration.search(
            query=self.query,
            artistCount=30,
            artistOffset=self.offset
        )
        GLib.idle_add(self.append_results, search_results.get('artist'), token)

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        self.offset = 0
        self.search_token += 1
        self.query = search_entry.get_text()
        self.searching = False
        for row in list(self.list_rows.values()) + list(self.grid_rows.values()):
            row.set_visible(False)
        threading.Thread(target=self.search, args=(self.search_token,)).start()
            
    @Gtk.Template.Callback()
    def scroll_edge_reached(self, scrolledwindow, pos):
        if pos == Gtk.PositionType.BOTTOM and self.end_stack.get_visible_child_name() == 'loading':
            threading.Thread(target=self.search).start()

    def update_visibility(self):
        for row in list(self.list_el) + list(self.wrapbox_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
