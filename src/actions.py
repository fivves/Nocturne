# actions.py

from .integrations import get_current_integration, models
import random, threading, os, shutil, pathlib
from datetime import datetime, UTC
from . import widgets as Widgets
from gi.repository import Gio, Adw, Gtk, GLib, Gst
from .constants import DATA_DIR, BASE_NAVIDROME_DIR, DOWNLOADS_DIR

# -- HELPER --

def __show_page(window, page):
    # page is Adw.NavigationViewPage
    application = window.get_application()
    active_window = application.props.active_window
    if active_window.__gtype_name__ == 'NocturnePopoutWindow':
        page_dialog = None
        for dialog in active_window.get_dialogs():
            if dialog.__gtype_name__ == 'NocturnePageDialog':
                dialog.navigation_view.push(page)
                return
        Widgets.PageDialog(page).present(active_window)
    else:
        active_window.main_bottom_sheet.set_open(False)
        active_window.main_split_view.set_show_content(True)
        active_window.main_navigationview.push(page)

def __show_custom_toast(window, model_id:str, title_property:str, subtitle:str, icon_name:str=None):
    integration = get_current_integration()
    model = integration.loaded_models.get(model_id)
    custom_widget = Adw.ActionRow(
        title=model.get_property(title_property) if model else title_property,
        subtitle=subtitle
    )
    if icon_name:
        custom_widget.set_icon_name(icon_name)
    else:
        album_art = Gtk.Image(
            css_classes=['card'],
            height_request=48,
            width_request=48,
            overflow=Gtk.Overflow.HIDDEN,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        if paintable := integration.getCoverArt(model_id):
            album_art.set_from_paintable(paintable)
            album_art.set_pixel_size(48)
        else:
            album_art.set_from_icon_name("music-note-symbolic")
        custom_widget.add_prefix(album_art)
    toast = Adw.Toast(
        custom_title=custom_widget,
        timeout=2
    )
    GLib.idle_add(window.get_application().props.active_window.toast_overlay.add_toast, toast)

def __replace_queue(window, songs:list, current_id:str=None):
    integration = get_current_integration()
    queue_model = integration.loaded_models.get('currentSong').get_property('queueModel')
    GLib.idle_add(queue_model.remove_all)
    if len(songs) > 0:
        if current_id is None:
            current_id = songs[0]
        GLib.idle_add(queue_model.splice,
            0,
            0,
            [Gtk.StringObject.new(SongId) for SongId in songs]
        )
    GLib.idle_add(integration.loaded_models.get('currentSong').set_property, 'songId', current_id)
    if Gio.Settings(schema_id="com.jeffser.Nocturne").get_value('auto-play').unpack():
        threading.Thread(target=generate_auto_play_queue, args=(window, False)).start()

def __play_next(window, songs:list):
    integration = get_current_integration()
    current_song_id = integration.loaded_models.get('currentSong').get_property('songId')
    queue_model = integration.loaded_models.get('currentSong').get_property('queueModel')
    if queue_model.get_property('n-items') == 0 or not current_song_id:
        __replace_queue(window, songs)
    else:
        current_song_index = 0
        for i, so in enumerate(list(queue_model)): # so=string object
            song_id = so.get_string()
            if song_id in songs and song_id != current_song_id:
                queue_model.remove(i)
            elif song_id == current_song_id:
                current_song_index = i + 1
        songs.reverse()
        GLib.idle_add(queue_model.splice,
            current_song_index,
            0,
            [Gtk.StringObject.new(SongId) for SongId in songs if SongId != current_song_id]
        )

def __play_later(window, songs:list):
    integration = get_current_integration()
    current_song_id = integration.loaded_models.get('currentSong').get_property('songId')
    queue_model = integration.loaded_models.get('currentSong').get_property('queueModel')
    if queue_model.get_property('n-items') == 0 or not current_song_id:
        __replace_queue(window, songs)
    else:
        for i, so in enumerate(list(queue_model)): # so=string object
            song_id = so.get_string()
            if song_id in songs and song_id != current_song_id:
                queue_model.remove(i)
        GLib.idle_add(queue_model.splice,
            queue_model.get_property('n-items'),
            0,
            [Gtk.StringObject.new(SongId) for SongId in songs if SongId != current_song_id]
        )

# -- MISC --

def generate_auto_play_queue(window, replace_on_finish:bool):
    def run():
        integration = get_current_integration()
        integration.loaded_models.get('currentSong').set_property('generatingQueue', True)
        queue_model = integration.loaded_models.get('currentSong').get_property('queueModel')
        generated_queue_model = integration.loaded_models.get('currentSong').get_property('generatedQueue')
        generated_queue_model.remove_all()

        song_list = []
        if queue_model.get_property('n-items') > 0:
            artists = []
            for so in list(queue_model):
                if model := integration.loaded_models.get(so.get_string()):
                    artists.append(model.artistId)
            if len(artists) > 0:
                main_artist = max(set(artists), key=artists.count)
                song_list = integration.getSimilarSongs(main_artist)

        # Remove repeated songs, if it ends up being less than 5 then just generate a random queue
        song_list = [s for s in song_list if s not in [so.get_string() for so in list(queue_model)]]
        if len(song_list) < 5:
            song_list = integration.getRandomSongs()

        generated_queue_model.splice(
            0,
            0,
            [Gtk.StringObject.new(s) for s in song_list]
        )

        integration.loaded_models.get('currentSong').set_property('generatingQueue', False)

        if replace_on_finish:
            __replace_queue(window, [so.get_string() for so in list(generated_queue_model)])

    threading.Thread(target=run).start()

def set_equalizer_preset(window, preset_name:str):
    preset = {
        "flat": [0.0] * 6,
        "clarity": [-2.0, -4.0, 2.0, 5.0, 3.0, 1.0],
        "jazz": [4.0, 2.0, 1.0, -2.0, -5.0, -8.0],
        "rock": [5.0, 2.0, -2.0, 3.0, 2.0, 0.0],
        "classic": [2.0, -2.0, 0.0, 1.0, 2.0, 4.0],
        "acoustic": [-2.0, 3.0, 1.0, -2.0, 4.0, 2.0]
    }.get(preset_name, [0.0] * 6)

    settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
    for i, value in enumerate(preset):
        settings.set_double("eq-band-{}".format(i), value)

def replace_root_page(window, page_tag:str):
    try:
        index = [i for i, item in enumerate(list(window.main_sidebar.get_items())) if item.get_visible() and item.page_tag == page_tag][0]
        window.main_sidebar.set_selected(index)
    except Exception as e:
        pass
    window.replace_root_page(page_tag)

def visit_url(window, url:str):
    if url.startswith('file://'):
        url = Gio.File.new_for_path(url.removeprefix('file://')).get_uri()
        os.system('xdg-open {}'.format(url))
        return

    Gio.AppInfo.launch_default_for_uri(url, None)

def toggle_star(window, model_id:str):
    integration = get_current_integration()
    if model_id in integration.loaded_models:
        model = integration.loaded_models.get(model_id)
        if model.get_property('starred'):
            if integration.unstar(model.get_property('id')):
                model.set_property('starred', None)
        else:
            if integration.star(model.get_property('id')):
                model.set_property('starred', datetime.now(UTC).isoformat(timespec='microseconds').replace('+00:00', 'Z'))

def sync_jellyfin_server(window):
    integration = get_current_integration()
    if not integration or integration.__gtype_name__ != 'NocturneIntegrationJellyfin':
        toast = Adw.Toast(
            title=_("Jellyfin sync is not available"),
            timeout=2
        )
        window.toast_overlay.add_toast(toast)
        return

    action = window.get_application().lookup_action("sync_jellyfin_server")
    if action:
        action.set_enabled(False)

    def reload_visible_page():
        page = window.main_navigationview.get_visible_page()
        if not page:
            return

        reset = getattr(page, "reset", None)
        if page.__gtype_name__ in (
            'NocturneSongsAllPage',
            'NocturneAlbumsAllPage',
            'NocturneArtistsPage'
        ) and callable(reset):
            reset()

        detail_refresh = {
            'NocturneAlbumPage': integration.verifyAlbum,
            'NocturneArtistPage': integration.verifyArtist,
            'NocturnePlaylistPage': integration.verifyPlaylist
        }.get(page.__gtype_name__)
        if detail_refresh and hasattr(page, "id"):
            detail_refresh(page.id, force_update=True)

        reload = getattr(page, "reload", None)
        if callable(reload):
            threading.Thread(target=reload).start()

    def run():
        synced = False
        failed = False
        try:
            synced = integration.syncLibrary()
        except Exception:
            failed = True

        if synced:
            threading.Thread(target=window.update_playlist_section_of_sidebar).start()
            GLib.idle_add(reload_visible_page)

        if failed:
            title = _("Jellyfin sync failed")
        elif synced:
            title = _("Jellyfin sync complete")
        else:
            title = _("Jellyfin sync is already running")

        def show_toast():
            window.toast_overlay.add_toast(Adw.Toast(
                title=title,
                timeout=2
            ))

        GLib.idle_add(show_toast)
        if action:
            GLib.idle_add(action.set_enabled, True)

    threading.Thread(target=run).start()

def logout(window):
    integration = get_current_integration()
    integration.terminate_instance()
    settings = Gio.Settings(schema_id="com.jeffser.Nocturne")
    settings.set_string('integration-user', '')
    settings.set_string('selected-instance-type', '')
    threading.Thread(target=__replace_queue, args=(window,[])).start()
    GLib.idle_add(window.main_stack.set_visible_child_name, 'welcome')
    GLib.idle_add(replace_root_page, window, 'home')
    if window.get_application().player.mpris_published:
        window.get_application().player.mpris.unpublish()
    dialogs = window.get_dialogs()
    if len(dialogs) > 0:
        dialogs[0].close()
    for page in list(window.main_navigationview):
        if isinstance(page, Adw.NavigationPage):
            GLib.idle_add(page.reset)

def show_external_file_warning(window):
    dialog = Adw.AlertDialog(
        heading=_("External File"),
        body=_("This track was loaded from an external file, this means it will have less features compared to a track inside the library")
    )
    dialog.add_response('close', _('Close'))
    dialog.choose(window, None, lambda *_: None, None)

def update_navidrome_server(window):
    window.main_stack.set_visible_child_name('setup')
    if dialog := window.get_visible_dialog():
        dialog.close()

def delete_navidrome_server(window):
    def response(dialog, task):
        selected_option = dialog.choose_finish(task)
        if selected_option == "delete":
            shutil.rmtree(BASE_NAVIDROME_DIR)
        elif selected_option == "keep_data":
            os.remove(os.path.join(BASE_NAVIDROME_DIR, 'navidrome'))
        elif selected_option == "cancel":
            return
        toast = Adw.Toast(
            title=_("Navidrome server deleted successfully"),
            timeout=2
        )
        GLib.idle_add(window.toast_overlay.add_toast, toast)
        GLib.idle_add(window.main_stack.set_visible_child_name, 'welcome')

    if dialog := window.get_visible_dialog():
        dialog.close()
    dialog = Adw.AlertDialog(
        heading=_("Delete Navidrome Server"),
        body=_("Are you sure you want to delete the integrated Navidrome server?")
    )
    dialog.add_response('cancel', _('Cancel'))
    dialog.add_response("keep_data", _("Keep Data"))
    dialog.add_response("delete", _("Delete Everything"))
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.choose(window, None, response)

def open_popout_window(window, fullscreened:bool=False):
    if not window.get_application().popout_window:
        window.get_application().popout_window = Widgets.PopoutWindow(
            application=window.get_application(),
            fullscreened=fullscreened
        )
    GLib.idle_add(window.get_application().popout_window.present)

def toggle_fullscreen(window):
    integration = get_current_integration()
    if integration.loaded_models.get('currentSong').get_property('queueModel').get_property('n-items') > 0:
        if popout_window := window.get_application().popout_window:
            popout_window.present()
            if popout_window.is_fullscreen():
                popout_window.unfullscreen()
            else:
                popout_window.fullscreen()
        else:
            window.get_application().lookup_action("toggle_fullscreen").set_enabled(False)
            open_popout_window(window, True)
            GLib.timeout_add(1000, window.get_application().lookup_action("toggle_fullscreen").set_enabled, True)

# -- PLAYER --

def player_play(window):
    window.get_application().player.gst.set_state(Gst.State.PLAYING)

def player_pause(window):
    window.get_application().player.gst.set_state(Gst.State.PAUSED)

def player_toggle(window):
    player = window.get_application().player
    if not player:
        return

    success, state, pending = player.gst.get_state(0)
    if state == Gst.State.PLAYING:
        player.gst.set_state(Gst.State.PAUSED)
    else:
        player.gst.set_state(Gst.State.PLAYING)

def player_next(window):
    window.get_application().player.handle_song_change_request("next")

def player_previous(window):
    window.get_application().player.handle_song_change_request("previous")

# -- RADIO --

def play_radio(window, model_id:str):
    integration = get_current_integration()
    if model_id in [so.get_string() for so in integration.loaded_models.get('currentSong').get_property('queueModel')]:
        integration.loaded_models.get('currentSong').set_property('songId', model_id)
    else:
        threading.Thread(target=__replace_queue, args=(window,[model_id],)).start()

def update_radio(window, id:str=""):
    integration = get_current_integration()
    model = integration.loaded_models.get(id) if id else None

    def response(dialog, task, name_el, stream_el, id:str):
        if dialog.choose_finish(task) == 'save':
            name = name_el.get_text().strip() or _("No Name")
            stream = stream_el.get_text().strip()
            if not stream.startswith('http'):
                stream = 'http://' + stream
            if name and (stream or not stream_el.get_visible()):
                integration = get_current_integration()
                if id:
                    result = integration.updateInternetRadioStation(
                        id,
                        name,
                        stream
                    )
                else:
                    result = integration.createInternetRadioStation(
                        name,
                        stream
                    )
                if result:
                    toast = Adw.Toast(
                        title=_("Radio updated successfully") if id else _("Radio added successfully"),
                        timeout=2
                    )
                    window.toast_overlay.add_toast(toast)
                    if id:
                        model.set_property('title', name)
                        model.set_property('streamUrl', stream)
                    else:
                        threading.Thread(target=window.main_navigationview.get_visible_page().reload).start()
                    return
            toast = Adw.Toast(
                title=_("Error updating radio") if id else _("Error adding radio"),
                timeout=2
            )
            window.toast_overlay.add_toast(toast)

    list_box = Gtk.ListBox(
        selection_mode=Gtk.SelectionMode.NONE,
        css_classes=['boxed-list']
    )
    name_el = Adw.EntryRow(title=_("Name"))
    if model and model.get_property('isRadio'):
        name_el.set_text(model.get_property('title'))
    list_box.append(name_el)
    stream_el = Adw.EntryRow(
        title=_("Stream Url")
    )
    if model and model.get_property('isRadio'):
        stream_el.set_text(model.get_property('streamUrl'))
    list_box.append(stream_el)

    dialog = Adw.AlertDialog(
        heading=_("Update Radio Station") if id else _("Add Radio Station"),
        extra_child=list_box
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("save", _("Save"))
    dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
    dialog.choose(window, None, lambda *prms: threading.Thread(target=response, args=prms).start(), name_el, stream_el, id)

def add_radio(window):
    update_radio(window)

def delete_radio(window, model_id:str):
    integration = get_current_integration()
    model = integration.loaded_models.get(model_id)

    def response(dialog, task, id):
        if dialog.choose_finish(task) == 'delete':
            result = integration.deleteInternetRadioStation(id)
            if result:
                toast = Adw.Toast(
                    title=_("Radio deleted successfully"),
                    timeout=2
                )
                window.toast_overlay.add_toast(toast)
                del integration.loaded_models[id]
                threading.Thread(target=window.main_navigationview.get_visible_page().reload).start()
            else:
                toast = Adw.Toast(
                    title=_("Error deleting radio"),
                    timeout=2
                )
                window.toast_overlay.add_toast(toast)

    dialog = Adw.AlertDialog(
        heading=_("Delete Radio Station"),
        body=_("Are you sure you want to delete '{}'?").format(model.get_property('title'))
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("delete", _("Delete"))
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.choose(window, None, response, model_id)

# -- SONG --

def play_song(window, model_id:str):
    integration = get_current_integration()
    if model_id in [so.get_string() for so in integration.loaded_models.get('currentSong').get_property('queueModel')]:
        integration.loaded_models.get('currentSong').set_property('songId', model_id)
    else:
        threading.Thread(target=__replace_queue, args=(window,[model_id],)).start()

def play_song_from_list(window, data:dict):
    song_id = data.get('songId')
    songs = data.get('songs', [song_id])

    if song_id:
        threading.Thread(
            target=__replace_queue,
            args=(window, songs, song_id)
        ).start()

def play_song_next(window, model_id:str):
    threading.Thread(
        target=__play_next,
        args=(window, [model_id])
    ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'title', _("Playing Next"))
    ).start()

def play_song_later(window, model_id:str):
    threading.Thread(
        target=__play_later,
        args=(window, [model_id])
    ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'title', _("Playing Later"))
    ).start()

def play_songs(window, song_list:list):
    threading.Thread(
        target=__replace_queue,
        args=(window, song_list)
    ).start()

def play_songs_next(window, song_list:list):
    threading.Thread(
        target=__play_next,
        args=(window, song_list)
    ).start()
    if len(song_list)> 1:
        threading.Thread(
            target=__show_custom_toast,
            args=(window, None, _("{} Songs").format(len(song_list)), _("Playing Next"), "list-high-priority-symbolic")
        ).start()
    else:
        threading.Thread(
            target=__show_custom_toast,
            args=(window, song_list[0], "title", _("Playing Next"))
        ).start()

def play_songs_later(window, song_list:list):
    threading.Thread(
        target=__play_later,
        args=(window, song_list,)
    ).start()
    if len(song_list) > 1:
        threading.Thread(
            target=__show_custom_toast,
            args=(window, None, _("{} Songs").format(len(song_list)), _("Playing Later"), "list-low-priority-symbolic")
        ).start()
    else:
        threading.Thread(
            target=__show_custom_toast,
            args=(window, song_list[0], "title", _("Playing Later"))
        ).start()

def edit_lyrics(window, song_id:str):
    Widgets.LyricsDialog(song_id).present(window.get_application().props.active_window)

def save_lyrics(window, lyric_dict:dict):
    # lyric_dict KEYS
    # id:str
    # content:str

    integration = get_current_integration()
    model = integration.loaded_models.get(lyric_dict.get('id'))
    file_name_without_ext = '{}|{}|{}|{}'.format(
        model.get_property('title'),
        model.get_property('artist'),
        model.get_property('album') or model.get_property('title'),
        model.get_property('duration')
    )
    lyrics_dir = os.path.join(DATA_DIR, 'lyrics')
    lrc_path = os.path.join(lyrics_dir, file_name_without_ext+'.lrc')

    with open(lrc_path, 'w') as f:
        f.write(lyric_dict.get('content'))

    window.lyrics_page.song_changed(lyric_dict.get('id'))

    threading.Thread(
        target=__show_custom_toast,
        args=(window, lyric_dict.get('id'), "title", _("Lyrics Saved"))
    ).start()

def play_random_queue(window):
    integration = get_current_integration()
    threading.Thread(
        target=__replace_queue,
        args=(window, integration.getRandomSongs(),)
    ).start()

# -- ALBUM --

def show_album(window, model_id:str):
    __show_page(window, Widgets.AlbumPage(model_id))

def show_album_from_song(window, model_id:str):
    integration = get_current_integration()
    if model := integration.loaded_models.get(model_id):
        if album_id := model.get_property('albumId'):
            __show_page(window, Widgets.AlbumPage(album_id))

def play_album(window, model_id:str):
    integration = get_current_integration()
    album = integration.loaded_models.get(model_id)

    if album:
        integration.verifyAlbum(album.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__replace_queue,
            args=(window, [s.get('id') for s in album.get_property('song')])
        ).start()

def play_album_next(window, model_id:str):
    integration = get_current_integration()
    album = integration.loaded_models.get(model_id)

    if album:
        integration.verifyAlbum(album.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__play_next,
            args=(window, [s.get('id') for s in album.get_property('song')])
        ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'name', _("Playing Next"))
    ).start()

def play_album_later(window, model_id:str):
    integration = get_current_integration()
    album = integration.loaded_models.get(model_id)

    if album:
        integration.verifyAlbum(album.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__play_later,
            args=(window, [s.get('id') for s in album.get_property('song')])
        ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'name', _("Playing Later"))
    ).start()

def play_album_shuffle(window, model_id:str):
    integration = get_current_integration()
    album = integration.loaded_models.get(model_id)

    if album:
        integration.verifyAlbum(album.get_property('id'), force_update=True, use_threading=False)
        song_list = [s.get('id') for s in album.get_property('song')]
        random.shuffle(song_list)
        threading.Thread(
            target=__replace_queue,
            args=(window, song_list)
        ).start()

# -- PLAYLIST --

def show_playlist(window, model_id:str):
    __show_page(window, Widgets.PlaylistPage(model_id))

def play_playlist(window, model_id:str):
    integration = get_current_integration()
    playlist = integration.loaded_models.get(model_id)

    if playlist:
        integration.verifyPlaylist(playlist.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__replace_queue,
            args=(window, [s.get('id') for s in playlist.get_property('entry')],)
        ).start()

def play_playlist_next(window, model_id:str):
    integration = get_current_integration()
    playlist = integration.loaded_models.get(model_id)

    if playlist:
        integration.verifyPlaylist(playlist.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__play_next,
            args=(window, [s.get('id') for s in playlist.get_property('entry')],)
        ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'name', _("Playing Next"))
    ).start()

def play_playlist_later(window, model_id:str):
    integration = get_current_integration()
    playlist = integration.loaded_models.get(model_id)

    if playlist:
        integration.verifyPlaylist(playlist.get_property('id'), force_update=True, use_threading=False)
        threading.Thread(
            target=__play_later,
            args=(window, [s.get('id') for s in playlist.get_property('entry')])
        ).start()
    threading.Thread(
        target=__show_custom_toast,
        args=(window, model_id, 'name', _("Playing Later"))
    ).start()

def play_playlist_shuffle(window, model_id:str):
    integration = get_current_integration()
    playlist = integration.loaded_models.get(model_id)

    if playlist:
        integration.verifyPlaylist(playlist.get_property('id'), force_update=True, use_threading=False)
        song_list = [s.get('id') for s in playlist.get_property('entry')]
        random.shuffle(song_list)
        threading.Thread(
            target=__replace_queue,
            args=(window, song_list)
        ).start()

def update_playlist(window, model_id:str=None):
    integration = get_current_integration()
    model = integration.loaded_models.get(model_id) if model_id else None

    def response(dialog, task, name_el, id:str):
        if dialog.choose_finish(task) == 'create':
            name = name_el.get_text()
            if name:
                result = integration.createPlaylist(
                    name,
                    playlistId=id
                )
                if result:
                    if not id:
                        threading.Thread(target=window.update_playlist_section_of_sidebar).start()
                    toast = Adw.Toast(
                        title=_("Playlist updated successfully") if id else _("Playlist created successfully"),
                        timeout=2
                    )
                    window.toast_overlay.add_toast(toast)
                    if id:
                        model.set_property('name', name)
                    else:
                        threading.Thread(target=window.main_navigationview.get_visible_page().reload).start()
                    return
            toast = Adw.Toast(
                title=_("Error updating playlist") if id else _("Error creating playlist"),
                timeout=2
            )
            window.toast_overlay.add_toast(toast)

    list_box = Gtk.ListBox(
        selection_mode=Gtk.SelectionMode.NONE,
        css_classes=['boxed-list']
    )
    name_el = Adw.EntryRow(title=_("Name"))
    if model:
        name_el.set_text(model.get_property('name'))
    list_box.append(name_el)
    dialog = Adw.AlertDialog(
        heading=_("Update Playlist") if model_id else _("Create Playlist"),
        extra_child=list_box
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("create", _("Update") if model_id else _("Create"))
    dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
    dialog.choose(window, None, response, name_el, model_id)

def create_playlist(window):
    update_playlist(window)

def remove_songs_from_playlist(window, data:dict):
    playlist_id = data.get('playlist', "")
    song_list = data.get('indexes', [])

    integration = get_current_integration()
    result = integration.updatePlaylist(
        playlist_id,
        songIndexToRemove=song_list
    )
    if result:
        if len(song_list) > 1:
            threading.Thread(
                target=__show_custom_toast,
                args=(window, playlist_id, "name", _("{} Songs Removed").format(len(song_list)))
            ).start()
        else:
            threading.Thread(
                target=__show_custom_toast,
                args=(window, playlist_id, "name", _("Song Removed"))
            ).start()

def prompt_add_songs_to_playlist(window, song_list:list):
    dialog = Widgets.playlist.PlaylistDialog(song_list)
    dialog.present(window.get_application().props.active_window)

def prompt_add_song_to_playlist(window, model_id:str):
    dialog = Widgets.playlist.PlaylistDialog([model_id])
    dialog.present(window.get_application().props.active_window)

def prompt_add_album_to_playlist(window, model_id:str):
    integration = get_current_integration()
    integration.verifyAlbum(model_id, force_update=True, use_threading=False)
    model = integration.loaded_models.get(model_id)
    dialog = Widgets.playlist.PlaylistDialog([s.get('id') for s in model.get_property('song')])
    dialog.present(window.get_application().props.active_window)

def add_songs_to_playlist(window, data):
    integration = get_current_integration()
    dialogs = window.get_dialogs()
    if len(dialogs) > 0:
        dialogs[0].close()

    if data.get('new_playlist'):
        response = integration.createPlaylist(
            name=data.get('new_playlist'),
            songId=data.get('songs')
        )
        if response:
            integration.verifyPlaylist(response, force_update=True, use_threading=False)
            if len(data.get("songs")) > 1:
                message = _("{} Songs Added").format(len(data.get("songs")))
            else:
                message = _("1 Song Added")
            threading.Thread(
                target=__show_custom_toast,
                args=(window, response, "name", message)
            ).start()
            threading.Thread(target=window.update_playlist_section_of_sidebar).start()

    elif data.get('playlist'):
        integration.verifyPlaylist(data.get('playlist'), force_update=True, use_threading=False)
        model = integration.loaded_models.get(data.get('playlist'))
        existing_songs = [e.get('id') for e in model.get_property('entry')]
        songs = [s for s in data.get('songs') if s not in existing_songs]
        response = integration.updatePlaylist(
            playlistId=data.get('playlist'),
            songIdToAdd=songs
        )

        message = []
        if len(songs) > 0:
            if len(songs) == 1:
                message.append(_("1 Song Added"))
            else:
                message.append(_("{} Songs Added").format(len(songs)))

        skipped_songs = len(data.get('songs')) - len(songs)
        if skipped_songs > 0:
            if skipped_songs == 1:
                message.append(_("1 Song Skipped"))
            else:
                message.append(_("{} Songs Skipped").format(skipped_songs))

        threading.Thread(
            target=__show_custom_toast,
            args=(window, data.get('playlist'), "name", ' | '.join(message))
        ).start()

def delete_playlist(window, model_id:str):
    integration = get_current_integration()
    model = integration.loaded_models.get(model_id)

    def show_toast(model):
        __show_custom_toast(window, model.get_property('id'), "name", _("Playlist Deleted"))
        del integration.loaded_models[model.id]
        window.main_navigationview.get_visible_page().reload()

    def response(dialog, task, model):
        if dialog.choose_finish(task) == "delete":
            result = integration.deletePlaylist(model.get_property('id'))
            if result:
                threading.Thread(target=show_toast, args=(model,)).start()
                threading.Thread(target=window.update_playlist_section_of_sidebar).start()

    dialog = Adw.AlertDialog(
        heading=_("Delete Playlist"),
        body=_("Are you sure you want to delete '{}'?").format(model.get_property('name'))
    )
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("delete", _("Delete"))
    dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
    dialog.choose(window, None, response, model)

# -- ARTIST --

def show_artist(window, model_id:str):
    __show_page(window, Widgets.ArtistPage(model_id))

def show_artist_from_song(window, model_id:str):
    integration = get_current_integration()
    if model := integration.loaded_models.get(model_id):
        if artist_id := model.get_property('artistId'):
            __show_page(window, Widgets.ArtistPage(artist_id))

def show_artist_from_album(window, model_id:str):
    integration = get_current_integration()
    if model := integration.loaded_models.get(model_id):
        if artist_id := model.get_property('artistId'):
            __show_page(window, Widgets.ArtistPage(artist_id))

def play_shuffle_artist(window, model_id:str):
    integration = get_current_integration()
    def run():
        integration.verifyArtist(model_id, force_update=True, use_threading=False)
        model = integration.loaded_models.get(model_id)
        if model:
            songs = []
            for album in model.get_property('album'):
                integration.verifyAlbum(album.get('id'), force_update=True, use_threading=False)
                album_model = integration.loaded_models.get(album.get('id'))
                if album_model:
                    songs.extend([s.get('id') for s in album_model.get_property('song')])
            if len(songs) > 0:
                play_songs(window, random.sample(songs, min(20, len(songs))))
    threading.Thread(target=run).start()

def play_radio_artist(window, model_id:str):
    integration = get_current_integration()
    def run():
        songs = integration.getSimilarSongs(model_id)
        if len(songs) > 0:
            play_songs(window, songs)
        else:
            toast = Adw.Toast(
                title=_("No songs found")
            )
            GLib.idle_add(window.toast_overlay.add_toast, toast)
    threading.Thread(target=run).start()

# -- DOWNLOADS --

def __request_song_download(model_id:str) -> bool:
    # returns true if download is started (not finished)
    # should be called in different thread (cause of verifySong)
    integration = get_current_integration()
    integration.verifySong(model_id, use_threading=False)
    if song_model := integration.loaded_models.get(model_id):
        download_queue = integration.loaded_models.get('currentSong').get_property('downloadQueueModel')
        download_model = models.SongDownload(songId=model_id)

        artist_name = song_model.get_property('artist').split(';')[0]
        if artists := song_model.get_property('artists'):
            artist_name = artists[0].get('name')
        file_title = '{} - {} - {}'.format(song_model.get_property('title'), song_model.get_property('album'), artist_name)
        if any(pathlib.Path(DOWNLOADS_DIR).glob('{}.*'.format(file_title))):
            return False
        found, position = download_queue.find_with_equal_func(
            download_model,
            lambda item_a, item_b, ud: item_a.get_property('songId') == item_b.get_property('songId'),
            0
        )
        if found:
            return False
        download_queue.insert(0, download_model)
        callback = lambda frac, md=download_model: md.set_property('progress', frac)
        threading.Thread(target=integration.downloadSong, args=(model_id, file_title, callback)).start()
        return True
    return False

def download_song(window, model_id:str):
    def run(songId):
        is_downloading = __request_song_download(songId)
        if is_downloading:
            __show_custom_toast(
                window,
                songId,
                'title',
                _("Download Started")
            )
        else:
            __show_custom_toast(
                window,
                songId,
                'title',
                _("Already Downloaded")
            )
    threading.Thread(target=run, args=(model_id,)).start()

def download_songs(window, model_list:str):
    if len(model_list) == 1:
        download_song(window, model_list[0])
        return

    def run(songIds):
        integration = get_current_integration()
        successful_starts = 0
        for songId in songIds:
            successful_starts += 1 if __request_song_download(songId) else 0

        if len(songIds) == successful_starts:
            __show_custom_toast(
                window,
                None,
                _("{} Songs").format(len(songIds)),
                _("Download Started")
            )
        elif successful_starts > 0:
            skipped_songs = len(song_ids) - successful_starts
            skip_message = _("{} Songs Skipped").format(skipped_songs) if skipped_songs > 1 else _("1 Song Skipped")
            message = _("{} Songs ({})").format(successful_starts, skip_message) if successful_starts > 1 else _("1 Song ({})").format(skip_message)

            __show_custom_toast(
                window,
                None,
                message,
                _("Already Downloaded")
            )
        else:
            __show_custom_toast(
                window,
                None,
                _("Download Skipped"),
                _("Already Downloaded")
            )
    threading.Thread(target=run, args=(model_list,)).start()

def download_album(window, model_id:str):
    def run(albumId):
        integration = get_current_integration()
        integration.verifyAlbum(albumId, force_update=True, use_threading=False)
        if model := integration.loaded_models.get(albumId):
            song_ids = [song.get('id') for song in model.get_property('song')]
            successful_starts = 0
            for songId in song_ids:
                successful_starts += 1 if __request_song_download(songId) else 0

            if len(song_ids) == successful_starts:
                __show_custom_toast(
                    window,
                    albumId,
                    'name',
                    _("Download Started")
                )
            elif successful_starts > 0:
                skipped_songs = len(song_ids) - successful_starts
                message = _("Download Started ({} Songs Skipped)").format(skipped_songs) if skipped_songs > 1 else _("Download Started (1 Song Skipped)")
                __show_custom_toast(
                    window,
                    albumId,
                    'name',
                    message
                )
            else:
                __show_custom_toast(
                    window,
                    albumId,
                    'name',
                    _("Already Downloaded")
                )

    threading.Thread(target=run, args=(model_id,)).start()

def download_playlist(window, model_id:str):
    def run(playlistId):
        integration = get_current_integration()
        integration.verifyPlaylist(playlistId, force_update=True, use_threading=False)
        if model := integration.loaded_models.get(playlistId):
            song_ids = [song.get('id') for song in model.get_property('entry')]
            successful_starts = 0
            for songId in song_ids:
                successful_starts += 1 if __request_song_download(songId) else 0

            if len(song_ids) == successful_starts:
                __show_custom_toast(
                    window,
                    playlistId,
                    'name',
                    _("Download Started")
                )
            elif successful_starts > 0:
                skipped_songs = len(song_ids) - successful_starts
                message = _("Download Started ({} Songs Skipped)").format(skipped_songs) if skipped_songs > 1 else _("Download Started (1 Song Skipped)")
                __show_custom_toast(
                    window,
                    playlistId,
                    'name',
                    message
                )
            else:
                __show_custom_toast(
                    window,
                    playlistId,
                    'name',
                    _("Already Downloaded")
                )

    threading.Thread(target=run, args=(model_id,)).start()

def __request_download_delete(model_id:str) -> bool:
    # returns true if download is deleted
    # should call del loaded_models[id] after toast is shown
    integration = get_current_integration()
    if model := integration.loaded_models.get(model_id):
        try:
            model.set_property('deleted', True)
            os.remove(model.get_property('path'))
            return True
        except:
            return False
    return False

def delete_download(window, model_id:str):
    def run():
        integration = get_current_integration()
        deleted = __request_download_delete(model_id)
        if deleted:
            __show_custom_toast(
                window,
                model_id,
                'title',
                _("Deleted")
            )
            del integration.loaded_models[model_id]
    threading.Thread(target=run).start()

def delete_downloads(window, model_list:list):
    def run():
        integration = get_current_integration()
        successful_deletes = 0
        for songId in model_list:
            deleted = __request_download_delete(songId)
            successful_deletes += 1 if deleted else 0
            if deleted:
                del integration.loaded_models[songId]

        __show_custom_toast(
            window,
            None,
            _("{} Songs").format(successful_deletes),
            _("Deleted")
        )
    threading.Thread(target=run).start()
