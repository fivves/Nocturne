# AGENTS.md

This file gives coding agents a compact map of Nocturne so future work can start with the app shape instead of re-reading the whole tree.

## Project Shape

- Nocturne is a Python GTK 4 / Libadwaita music app.
- UI files are written in Blueprint under `src/ui/**/*.blp` and compiled into GTK UI resources by Meson.
- Runtime code lives under `src/`.
- App entry point: `src/main.py`.
- Main window and app action registration: `src/window.py`.
- Application actions: `src/actions.py`.
- Playback engine and MPRIS integration: `src/widgets/playing/player.py`.
- Integration backends: `src/integrations/`.
- GObject data models: `src/integrations/models.py`.

## Build And Checks

- Syntax check Python files with `python3 -m py_compile <files>`.
- Compile Blueprint directly with `blueprint-compiler compile --output /tmp/out.ui src/ui/file.blp`.
- Full local build: `meson compile -C build`.
- The uninstalled launcher is `./nocturne-uninstalled`.

## Architecture Notes

- `NocturneApplication` in `src/main.py` owns the main window and `Player`.
- `NocturneWindow` registers most actions by passing functions from `src/actions.py` through `create_action`.
- The active music backend is global in `src/integrations/__init__.py` via `get_current_integration()`.
- Each integration has a `loaded_models` dict keyed by model id. It must include `currentSong`, a `CurrentSong` model with queue state.
- Widgets usually subscribe to model changes through `integration.connect_to_model(...)`.
- Many actions and page loaders are intentionally threaded, then marshal UI updates with `GLib.idle_add`.

## Performance Notes

- Large local libraries are sensitive to unbounded thread creation. Keep file scans and metadata reads behind a bounded worker pool.
- Avoid eager cover-art loading for every song during initial library scans. Load visible cover art on demand.
- Avoid creating GTK widgets off the main thread. Do data fetching in workers, then create/append widgets in `GLib.idle_add` callbacks.
- Avoid per-result scans through existing GTK children. Large pages should keep id-to-widget dictionaries or sets.
- Search pages should ignore stale worker results when users type quickly.
- The spectrum visualizer can emit frequent messages. Do not allow parsing workers to accumulate.
- Be careful with class-level mutable state on GObject classes. Per-integration model storage should be instance-level.

## Common Files

- `src/widgets/pages/songs_all.py`, `albums_all.py`, `artists.py`: searchable paginated library pages.
- `src/widgets/pages/albums.py`: album list variants such as random/newest/recent/frequent.
- `src/widgets/song/row.py` and `small_row.py`: list/grid song widgets.
- `src/widgets/album/row.py`, `button.py`: list/grid album widgets.
- `src/widgets/artist/row.py`, `button.py`: list/grid artist widgets.
- `src/widgets/playing/footer.py` and `control_page.py`: playback controls and current-song UI.

## Editing Guidance

- Keep GTK UI mutations on the main loop with `GLib.idle_add`.
- Use existing action names and model properties rather than introducing parallel state.
- Use Blueprint for UI layout changes, not generated `.ui` files.
- For local backend work, prefer cached/indexed lists over repeatedly walking all of `loaded_models`.
