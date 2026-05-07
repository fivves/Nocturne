# albums.py

from gi.repository import Gtk, Adw, GLib
from ...integrations import get_current_integration
from ..album import AlbumButton
import threading

@Gtk.Template(resource_path='/com/jeffser/Nocturne/pages/albums.ui')
class AlbumsPage(Adw.NavigationPage):
    __gtype_name__ = 'NocturneAlbumsPage'

    list_el = Gtk.Template.Child()
    main_stack = Gtk.Template.Child()
    end_stack = Gtk.Template.Child()
    scrolledwindow = Gtk.Template.Child()
    def __init__(self):
        super().__init__()
        self.offset = 0
        self.loading = False
        self.album_buttons = {}
        self.scrolledwindow.get_vadjustment().connect('notify::upper', lambda va, ud: GLib.timeout_add(1000, self.check_scrollbar, va))

    def check_scrollbar(self, adjustment):
        if adjustment.get_upper() <= adjustment.get_page_size():
            threading.Thread(target=self.load_albums).start()

    def reload(self):
        GLib.idle_add(self.main_stack.set_visible_child_name, 'loading')
        self.offset = 0
        self.loading = False
        GLib.idle_add(self.reset)
        GLib.idle_add(self.end_stack.set_visible_child_name, 'loading')
        threading.Thread(target=self.load_albums).start()

    def reset(self):
        self.list_el.remove_all()
        self.album_buttons = {}

    def append_albums(self, albums:list):
        for album_id in albums:
            if album_id in self.album_buttons:
                self.album_buttons[album_id].set_visible(True)
            else:
                button = AlbumButton(album_id)
                self.album_buttons[album_id] = button
                self.list_el.list_el.append(button)

        self.end_stack.set_visible_child_name('end' if len(albums) < 20 else 'loading')
        self.offset += 20
        self.loading = False
        self.update_visibility()

    def load_albums(self):
        if self.loading:
            return

        self.loading = True
        integration = get_current_integration()
        
        albums = integration.getAlbumList(
            list_type=self.get_tag().split('-')[1],
            size=20,
            offset=self.offset
        )

        GLib.idle_add(self.append_albums, albums)

    @Gtk.Template.Callback()
    def scroll_edge_reached(self, scrolledwindow, pos):
        if pos == Gtk.PositionType.BOTTOM and self.end_stack.get_visible_child_name() == 'loading':
            threading.Thread(target=self.load_albums).start()

    def update_visibility(self):
        for row in list(self.list_el.list_el):
            if row.get_visible():
                self.main_stack.set_visible_child_name('content')
                return
        self.main_stack.set_visible_child_name('no-content')
