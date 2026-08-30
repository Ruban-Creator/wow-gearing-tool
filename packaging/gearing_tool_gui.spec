# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Gearing Tool GUI (picker + report viewer, v1).

Build from the repo root:
    python -m PyInstaller packaging/gearing_tool_gui.spec

Output: dist/gearing-tool-gui.exe. Run it with the repo root as its working
directory (e.g. a shortcut with "Start in: <repo root>") - it reads
data/characters/<name-realm>/ and your real WoW SavedVariables files, not
anything bundled into the exe itself. See gui/api.py's REPO_ROOT/sys.frozen
handling and gui/app.py's ASSETS_DIR for exactly why.

`slpp` is a required hidden-import: it's a real runtime dependency (used by
ingest/build_character.py to parse Lua SavedVariables), but it's several
import-levels below gui/app.py's own imports, reached only via a dynamic
sys.path.insert() + bare `import` in gui/api.py (see that file's comment) -
PyInstaller's static import analysis can't see through that, so it silently
omits slpp without this. Confirmed by a real failed launch during
development (ModuleNotFoundError: No module named 'slpp') before this was
added - not a guessed-at gotcha.
"""
import os

# SPECPATH is a real PyInstaller-injected builtin (the directory containing
# this spec file) - confirmed against PyInstaller 6.22.2's own source
# (building/build_main.py) rather than guessed, so this resolves correctly
# regardless of where the repo is checked out.
REPO_ROOT = os.path.dirname(SPECPATH)
ASSETS_SRC = os.path.join(REPO_ROOT, "gui", "assets")
# Build Output (5th bucket, 2026-08-29 folder-structure rework) - the final
# packaged exe lands in build/dist/ and PyInstaller's own intermediate work
# dir in build/_pyinstaller_work/, both under build/ alongside build/bin/'s
# Go binaries, instead of a top-level dist/ + a top-level build/ that
# collides in name with this project's own "Build Output" bucket.
# NOTE: DISTPATH/WORKPATH are NOT settable from inside a spec file -
# PyInstaller already resolves and creates them from --distpath/--workpath
# (or its own hardcoded defaults) BEFORE this spec is ever exec'd
# (confirmed against PyInstaller 6.22.2's own build_main.py - CONF['distpath']/
# CONF['workpath'] are fixed at line ~1146-1151, this spec's code doesn't
# run until line ~1213). Assigning DISTPATH/WORKPATH here would silently be
# a no-op, not a real override - the actual redirect has to be the
# --distpath/--workpath flags on the build command itself. See
# packaging/README.md's Build section for the real command.

a = Analysis(
    [os.path.join(REPO_ROOT, "gui", "app.py")],
    pathex=[],
    binaries=[],
    datas=[(ASSETS_SRC, "gui/assets")],
    hiddenimports=["slpp"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="gearing-tool-gui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
