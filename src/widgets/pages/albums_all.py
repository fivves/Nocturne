# albums_all.py

from gi.repository import Gtk, Adw, GLib, GObject, Gio
from ...integrations import get_current_integration, models
from ..album import AlbumRow, AlbumButton
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/albums_all.ui')
class AlbumsAllPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneAlbumsAllPage'

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

    def append_results(self, album_ids:list, token:int):
        if token != self.search_token:
            return

        for album_id in album_ids:
            if album_id in self.list_rows:
                self.list_rows[album_id].set_visible(True)
            else:
                row = AlbumRow(album_id)
                self.list_rows[album_id] = row
                self.list_el.append(row)

            if album_id in self.grid_rows:
                self.grid_rows[album_id].set_visible(True)
            else:
                button = AlbumButton(album_id)
                self.grid_rows[album_id] = button
                self.wrapbox_el.append(button)

        self.end_stack.set_visible_child_name('end' if len(album_ids) < 30 else 'loading')
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
            albumCount=30,
            albumOffset=self.offset
        )
        GLib.idle_add(self.append_results, search_results.get('album'), token)

    @Gtk.Template.Callback()
    def on_search(self, search_entry):
        self.offset = 0
        self.search_token += 1
        self.query = search_entry.get_text()
        self.searching = False
        for widget in list(self.list_rows.values()) + list(self.grid_rows.values()):
            widget.set_visible(False)
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
