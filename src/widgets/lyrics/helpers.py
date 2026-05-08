# helpers.py

from ...constants import DATA_DIR
from ...integrations import get_current_integration
import os

def online_get(track_name:str, artist_name:str, lrc_path):
    try:
        import syncedlyrics

        return syncedlyrics.search(
            "[{}] [{}]".format(track_name, artist_name),
            enhanced=True,
            synced_only=True,
            save_path=lrc_path
        )
    except Exception:
        return None

def prepare_lrc(lrc_str:str) -> list:
    lrc_lines = []
    for line in lrc_str.split('\n'):
        if line.startswith('['):
            timestamp, content = line[1:].split(']')[:2]
            minutes_str, rest = timestamp.split(':')[:2]
            diveded_second = rest.split('.')
            if len(diveded_second) == 1:
                seconds_str = diveded_second[0]
                ms_str = "0"
            else:
                seconds_str, ms_str = diveded_second[:2]
            minutes = int(minutes_str)
            seconds = int(seconds_str)
            ms = int(ms_str)
            if len(ms_str) == 2:
                ms *= 10
            timing = (minutes * 60000) + (seconds * 1000) + ms
            lrc_lines.append({'ms': timing, 'content': content.strip()})
    return lrc_lines

def list_to_lrc_str(lrc_list:list) -> str:
    lrc_lines = []
    for item in lrc_list:
        ms = int(item.get('ms', 0))
        minutes = ms // 60000
        seconds = (ms % 60000) // 1000
        centiseconds = (ms % 1000) // 10

        timestamp = f"[{minutes:02d}:{seconds:02d}.{centiseconds:02d}]"
        lrc_lines.append(f"{timestamp} {item.get('content').strip()}")
    return '\n'.join(lrc_lines)

def get_lyrics(song_id:str, online_download:bool) -> dict:
    # returns these keys:
    # type (instrumental, lrc, plain, not-found, not-found-locally, radio)
    # content (none (instrumental/not-found/not-found-locally/radio), list (lrc), str (plain))

    integration = get_current_integration()
    if not integration:
        return {'type': 'not-found', 'content': None}

    model = integration.loaded_models.get(song_id)

    if not model:
        return {'type': 'not-found', 'content': None}

    if model.get_property('isRadio'):
        return {'type': 'radio', 'content': None}

    lyrics_dir = os.path.join(DATA_DIR, 'lyrics')
    os.makedirs(lyrics_dir, exist_ok=True)

    file_name_without_ext = '{}|{}|{}|{}'.format(
        model.get_property('title'),
        model.get_property('artist'),
        model.get_property('album') or model.get_property('title'),
        model.get_property('duration')
    )
    file_name_without_ext = file_name_without_ext.replace('/', '-')
    lrc_path = os.path.join(lyrics_dir, file_name_without_ext+'.lrc')
    plain_lyrics_path = os.path.join(lyrics_dir, file_name_without_ext+'.txt')

    if os.path.isfile(lrc_path):
        with open(lrc_path, 'r') as f:
            return {'type': 'lrc', 'content': prepare_lrc(f.read())}

    if os.path.isfile(plain_lyrics_path):
        with open(plain_lyrics_path, 'r') as f:
            content = f.read()
            if content == '[instrumental]':
                return {'type': 'instrumental', 'content': None}
            else:
                return {'type': 'plain', 'content': content}

    if not online_download:
        result = integration.getLyrics(song_id)
        if result.get('type') != 'not-found':
            if result.get('type') == 'lrc':
                with open(lrc_path, 'w+') as f:
                    f.write(list_to_lrc_str(result.get('content')))
            elif result.get('type') == 'lrc-unprepared':
                with open(lrc_path, 'w+') as f:
                    f.write(result.get('content'))
                result = {
                    'type': 'lrc',
                    'content': prepare_lrc(result.get('content'))
                }
            elif result.get('type') == 'plain':
                with open(plain_lyrics_path, 'w+') as f:
                    f.write(result.get('content'))
            return result

    if not online_download:
        return {'type': 'not-found-locally', 'content': None}

    lyrics = online_get(
        track_name=model.get_property('title'),
        artist_name=model.get_property('artist'),
        lrc_path=lrc_path
    )

    if not lyrics:
        return {'type': 'not-found', 'content': None}

    return {'type': 'lrc', 'content': prepare_lrc(lyrics)}
