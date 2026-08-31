# Packaging the GUI

Builds `build/dist/RGT.exe` - Ruban's Gearing Tool, a single-file,
double-clickable app (picker + report viewer, v1 - see `CLAUDE.md`'s multi-character GUI
section and the approved plan referenced there).

## Build

```
pip install -r requirements.txt -r requirements-gui.txt
pip install pyinstaller
python -m PyInstaller packaging/gearing_tool_gui.spec --distpath build/dist --workpath build/_pyinstaller_work
```

Output: `build/dist/RGT.exe` (~13 MB). The `--distpath`/
`--workpath` flags are real, required arguments here, not optional style -
PyInstaller's spec files can't set these themselves (its own `DISTPATH`/
`WORKPATH` spec globals are read-only convenience references, resolved
*before* the spec runs - see the spec file's own comment); omitting the
flags puts a stray top-level `dist/`/`build/<specname>/` back, colliding in
name with this project's own `build/` (Build Output) bucket.

`pyinstaller` is a build-time-only tool - not listed in `requirements-gui.txt`,
since the GUI itself doesn't import it at runtime.

## Running the built exe

Just double-click it - no working-directory setup needed. It finds the real
repo root itself by walking up from its own on-disk location
(`sys.executable`, not `os.getcwd()`) looking for `ingest/list_characters.py`,
so it works whether it's sitting in `build/dist/` or copied to the repo root
directly (real bug hit and fixed 2026-08-24: the original `os.getcwd()`-based
version crashed with `ModuleNotFoundError: No module named 'list_characters'`
on the very first real double-click, since Windows' double-click cwd didn't
line up with either location - see `gui/api.py`'s `_find_repo_root()`).

It does still need to be *somewhere inside* (or in `build/dist/` directly
under) a real Gearing-Tool checkout - it imports `ingest/list_characters.py`/
`ingest/build_character.py`/`core/*.py` as real source files rather than
bundling them into the exe, and needs `build/bin/wowsimcli.exe`/`bridge.exe`/
`simserver.exe` (the Go build output, see the repo root's own `build/README.md`
if one exists, or `CLAUDE.md`'s Local Setup section) as real siblings too.
Moving just the `.exe` file out to somewhere with no repo around it won't
work; that's a real, deliberate v1 scope decision, not an oversight - a
proper installer (the actual goal, per `CLAUDE.md`'s own framing since this
project is headed toward public release) is expected to lay out the full
checkout for the user, not just drop a bare exe.

Production Data (character caches, reports, `local_config.json`) is NOT
repo-relative, though - since the 2026-08-29 folder-structure rework it
lives under `%LOCALAPPDATA%\GearingTool\` regardless of where the exe or
its repo checkout sit, auto-created on first run. See `core/repo_root.py`'s
`USER_DATA_DIR`.

## Known real gotcha already resolved here, not guessed

`slpp` (used by `ingest/build_character.py` to parse Lua SavedVariables) is
several import-levels below `gui/app.py`'s own imports, reached only via a
dynamic `sys.path.insert()` + bare `import` - PyInstaller's static analysis
can't see through that and silently omits it. Confirmed by a real failed
launch during development (`ModuleNotFoundError: No module named 'slpp'`)
before `hiddenimports=["slpp"]` was added to the spec file. If a future
change adds another dependency reached the same indirect way, expect the
same failure mode and the same fix.

## Building the installer (Inno Setup)

`packaging/installer.iss` builds the real, shareable installer -
`packaging/output/RGT-Setup.exe`. Requires the exe (above) and all three `build/bin/`
binaries (`CLAUDE.md`'s Local Setup section) already built first.

```
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

Inno Setup installs via `winget install --id JRSoftware.InnoSetup` and lands under
`%LOCALAPPDATA%\Programs\Inno Setup 6\` - NOT `Program Files`, despite that being Inno Setup's own
usual convention; check there first before assuming it's missing.

**Payload is a real, checked subset of the repo, not the whole thing** - `installer.iss`'s own
top comment has the full reasoning, but in short: `sim/tbc-new`'s real working tree is 237MB, but
grepping every Python module for actual file reads found the running app only ever touches
`assets/database/db.json` and `sim/**/*.go` from that whole submodule (confirmed, not assumed -
`db.bin` is embedded into the Go binaries at build time via `go:embed`, never read from disk at
runtime; `ui/`/`proto/`/`cmd/`/`docs/`/`tools/` are only touched by dev-only profile-building
scripts a real end-user install never runs). Real installer payload: ~8.5MB from the submodule,
not 237MB. If a future profile-building session needs something from `ui/`/`proto/` at genuine
*runtime* (not just to build a new profile), that's a real installer scope change, not something
to silently work around - check before assuming today's exclusion list is stale.

`#define AppVersion Trim(FileRead(SourcePath + "..\build\bin\sim_version_label.txt"))` reads the
baked sim version at COMPILE time so the installer's own displayed version always matches the sim
build it actually contains - never hand-maintained separately.

**Real, unresolved finding**: `/VERYSILENT /SUPPRESSMSGBOXES` did NOT suppress the License
Agreement page on install, nor the confirmation prompt on uninstall - both popped up requiring
real manual interaction, reproduced twice (install and uninstall, both live-verified by the user
clicking through). Not yet root-caused. Don't assume a scripted/unattended install or uninstall
actually runs silently until this is understood - verify interactively, or expect a human/agent to
be watching for a dialog.

## Verification done so far

- Console build (`console=True` variant) launched clean, no traceback.
- First windowed build launched clean in automated testing (process + window
  title only) but crashed on the user's real first double-click - the
  `os.getcwd()` bug above. Fixed, rebuilt.
- Rebuilt exe verified launching clean from a working directory with no
  relation to the repo at all (`C:\Users\<user>`, not inside the repo
  tree), confirming the fix isn't coincidental.
- **Run Report feature (2026-08-24)**: `gui/api.py` now reaches into `core/`
  for the first time (`run_full_sweep_mv`, `build_ledger_data`,
  `render_report`, `local_config`) via the same dynamic
  `sys.path.insert()` + bare-`import` pattern already used for `ingest/`.
  Confirmed before rebuilding that every module reachable from that new
  import chain (`core/*.py`, `adapters/tbc/*.py`) is pure-stdlib - no new
  third-party dependency needed adding to `hiddenimports` or
  `requirements-gui.txt`. Rebuilt exe launched clean (process survived past
  the point where a frozen-path import bug would have crashed it - the same
  failure mode as the `os.getcwd()` bug above, since these new imports
  happen eagerly at `Api()` construction, not lazily inside a method) and
  rendered the real "Gearing Tool" window (confirmed via
  `Get-Process | Select MainWindowTitle`, same technique as before).
- **Still not done by a human**: actually clicking through the character
  list / report links / new Run Report and Settings dialogs in the real
  rendered window. Automated checks confirm it starts, has the right
  title, and survives past its own import chain - not that it
  looks/behaves right. The Run Report/Settings UI itself was click-tested
  against the real `gui/assets/` files running under a plain browser with
  pywebview's API mocked out (see the plan's Stage 6 note) - that covers
  the JS/HTML/CSS logic, not the packaged exe's own native window chrome.
- **Installer, 2026-08-30**: real end-to-end test, not just a compile check
  - installed to a real, separate test location
  (`%TEMP%\GearingToolInstallTest`, nothing to do with the dev repo) via the
  compiled `RGT-Setup.exe`, confirmed every expected file landed
  (both `build/bin/*.exe` and `build/dist/RGT.exe`, the trimmed
  `sim/tbc-new/` subset, `profiles/tbc/`, `addons/`), then launched the
  installed exe directly - real "Gearing Tool" window title confirmed, alive
  for 15+ seconds with no crash, running entirely from the fresh install
  location with no dev-repo relationship at all. Uninstaller
  (`unins000.exe`) also real-tested. Same "still not done by a human" gap
  as above still applies to the installed copy specifically - starting
  clean isn't the same as every feature working end to end.

## Packaging the Companion addon for CurseForge

`python packaging/build_addon_zip.py` builds `packaging/output/GearingToolCompanion-v<version>.zip`
straight from `addons/GearingToolCompanion/` - the zip's own top-level entry is a
`GearingToolCompanion/` folder (required: both CurseForge and a manual `Interface/AddOns/` drop
need the addon's own folder name at the zip root, not the `.lua`/`.toc` loose). The version in the
filename is read directly from the `.toc`'s own `## Version:` field, so it can never drift out of
sync with what the addon reports in-game - bump that field first, then re-run the script.

Only `GearingToolCompanion.lua`/`.toc`/`icon.tga` go inside the zip - `README.md`/`CHANGELOG.md`
(same directory) are NOT included; CurseForge reads those directly from the linked GitHub repo for
the project page description and changelog tab, so shipping copies inside the zip too would be
redundant, not required.

An automated packager exists at the repo root (`.pkgmeta`, real and ready) but is NOT wired up yet
- real, current CurseForge docs confirmed (2026-08-31,
https://support.curseforge.com/en/support/solutions/articles/9000197281) it works via a repo
webhook (GitHub "Webhooks & Services", `curseforge.com/api/projects/{id}/package?token={token}`)
that fires on **every commit to the whole repository**, not just addon-related ones - this repo is
a monorepo (the addon is one small subdirectory alongside the Python tool, the vendored sim
submodule, etc.), so enabling it means every unrelated Python/profile-data commit also pings
CurseForge's packager. `.pkgmeta`'s own `move-folders` (moves `addons/GearingToolCompanion` to the
zip root as `GearingToolCompanion`) handles the non-root-addon problem fine - the real remaining
cost is the ignore list needing manual upkeep every time this repo gains a new top-level
file/directory, plus the every-commit noise. Worth revisiting once the addon's own update cadence
settles down; manual upload via `build_addon_zip.py`'s own zip output is the real, working path for
now - see `packaging/curseforge_publishing_guide.html` for the full step-by-step, sourced from
CurseForge's own real, current submission docs (not guessed).
