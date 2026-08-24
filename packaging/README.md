# Packaging the GUI

Builds `dist/gearing-tool-gui.exe` - a single-file, double-clickable app
(picker + report viewer, v1 - see `CLAUDE.md`'s multi-character GUI section
and the approved plan referenced there).

## Build

```
pip install -r requirements.txt -r requirements-gui.txt
pip install pyinstaller
python -m PyInstaller packaging/gearing_tool_gui.spec
```

Output: `dist/gearing-tool-gui.exe` (~13 MB).

`pyinstaller` is a build-time-only tool - not listed in `requirements-gui.txt`,
since the GUI itself doesn't import it at runtime.

## Running the built exe

**Must be launched with the repo root as its working directory** - it reads
`data/characters/<name-realm>/` from a real on-disk checkout, and imports
`ingest/list_characters.py`/`ingest/build_character.py` as real source files
rather than bundling them (see `gui/api.py`'s `REPO_ROOT`/`sys.frozen`
handling for why). Either:

- Run it from a terminal already `cd`'d into the repo root, or
- Drop the exe directly in the repo root and double-click it there, or
- Make a shortcut with **Start in:** set to the repo root.

Running it from anywhere else will fail to find your character data - this
is a deliberate v1 scope decision (a personal single-repo tool doesn't need
to run from an arbitrary location), not an oversight. See the plan for the
more portable alternative (a first-run config pointing at the repo root) if
this ever actually becomes a problem.

## Known real gotcha already resolved here, not guessed

`slpp` (used by `ingest/build_character.py` to parse Lua SavedVariables) is
several import-levels below `gui/app.py`'s own imports, reached only via a
dynamic `sys.path.insert()` + bare `import` - PyInstaller's static analysis
can't see through that and silently omits it. Confirmed by a real failed
launch during development (`ModuleNotFoundError: No module named 'slpp'`)
before `hiddenimports=["slpp"]` was added to the spec file. If a future
change adds another dependency reached the same indirect way, expect the
same failure mode and the same fix.

## Verification done so far (2026-08-24, no user present to click through it)

- Console build (`console=True` variant) launched clean, no traceback.
- Final windowed build (`dist/gearing-tool-gui.exe`, this spec's actual
  output) launched clean three times in a row across rebuilds - confirmed via
  its real OS-level window title ("Gearing Tool", checked with PowerShell's
  `Get-Process`), not just "the process didn't immediately exit."
- **Not yet done**: an actual human double-click + look at the window. Please
  do that for real once you're back - I can confirm the process starts and
  the window exists, but not that it looks/behaves right without eyes on it.
