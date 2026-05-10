import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk


def clear_search_entry(search_entry: Gtk.SearchEntry):
    search_entry.set_text("")
