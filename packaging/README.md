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

Just double-click it - no working-directory setup needed. It finds the real
repo root itself by walking up from its own on-disk location
(`sys.executable`, not `os.getcwd()`) looking for `ingest/list_characters.py`,
so it works whether it's sitting in `dist/` or copied to the repo root
directly (real bug hit and fixed 2026-08-24: the original `os.getcwd()`-based
version crashed with `ModuleNotFoundError: No module named 'list_characters'`
on the very first real double-click, since Windows' double-click cwd didn't
line up with either location - see `gui/api.py`'s `_find_repo_root()`).

It does still need to be *somewhere inside* (or in `dist/` directly under) a
real Gearing-Tool checkout - it reads `data/characters/<name-realm>/` and
imports `ingest/list_characters.py`/`ingest/build_character.py` as real
source files rather than bundling them into the exe. Moving just the `.exe`
file out to somewhere with no repo around it won't work; that's a real,
deliberate v1 scope decision (a personal single-repo tool), not an oversight.

## Known real gotcha already resolved here, not guessed

`slpp` (used by `ingest/build_character.py` to parse Lua SavedVariables) is
several import-levels below `gui/app.py`'s own imports, reached only via a
dynamic `sys.path.insert()` + bare `import` - PyInstaller's static analysis
can't see through that and silently omits it. Confirmed by a real failed
launch during development (`ModuleNotFoundError: No module named 'slpp'`)
before `hiddenimports=["slpp"]` was added to the spec file. If a future
change adds another dependency reached the same indirect way, expect the
same failure mode and the same fix.

## Verification done so far

- Console build (`console=True` variant) launched clean, no traceback.
- First windowed build launched clean in automated testing (process + window
  title only) but crashed on the user's real first double-click - the
  `os.getcwd()` bug above. Fixed, rebuilt.
- Rebuilt exe verified launching clean from a working directory with no
  relation to the repo at all (`C:\Users\Matthias`, not inside the repo
  tree), confirming the fix isn't coincidental.
- **Still not done by a human**: actually clicking through the character
  list / report links in the real rendered window. Automated checks confirm
  it starts and has the right title, not that it looks/behaves right.
