"""Python surface exposed to the pywebview window's JS via `js_api` - see
gui/app.py. Was read-only (v1: picker + report viewer only) until the Run
Report feature (see the approved plan,
C:\\Users\\Matthias\\.claude\\plans\\staged-purring-lynx.md) - now also runs a
real sweep + renders a local HTML report on demand.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

# When frozen (PyInstaller --onefile), __file__ resolves inside the temp
# extraction dir (sys._MEIPASS), not next to the real data/ or ingest/
# directories - and ingest/*.py are real on-disk source files this deliberately
# does NOT ask PyInstaller to bundle (its static import analysis doesn't
# reliably catch the dynamic sys.path.insert()+bare-import pattern below).
#
# REAL BUG, hit live 2026-08-24 (not a hypothetical): using os.getcwd() to
# find the repo root crashed with "No module named 'list_characters'" the
# first time the exe was actually double-clicked, because it was sitting in
# dist/ (where the build puts it) rather than the repo root, and Windows'
# double-click cwd didn't line up with either. The real fix (walk up from
# sys.executable's own on-disk location, not cwd) now lives once in
# core/repo_root.py instead of duplicated in every core/ingest/cli module
# (2026-08-26, prompted by the user asking whether the tool was actually
# ready for a bundled installer - it wasn't, every one of those had the
# exact same latent bug).
#
# REAL BUG #2, hit live 2026-08-26 building that same fix: gui/api.py
# itself IS bundled/compiled into the frozen exe (PyInstaller's static
# analyzer traces `from api import Api` in gui/app.py just fine, unlike the
# dynamic sys.path.insert()+bare-import pattern used for core/ingest below),
# so THIS file's own __file__ genuinely does resolve inside the temp
# extraction dir when frozen. A first fix attempt used sys.executable's own
# directory directly as "core"'s parent - still wrong, confirmed by a real
# launch of the packaged exe still crashing the same way: the real exe
# lives in dist/, one level BELOW the real repo root (core/ is a sibling of
# dist/'s PARENT, not of dist/ itself) - exactly the same one-level-too-shallow
# mistake the ORIGINAL _find_repo_root() (before today's consolidation) was
# written to avoid by walking up multiple levels, not just one. This one
# bootstrap step can't yet delegate to repo_root.py (that's the very thing
# being located), so it keeps its own small copy of that same walk-up
# search - every other real REPO_ROOT usage in this file and everywhere
# else in the codebase still goes through repo_root.py alone.
def _find_core_dir(start: str) -> str:
    d = start
    for _ in range(6):
        if os.path.isfile(os.path.join(d, "ingest", "list_characters.py")):
            return os.path.join(d, "core")
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    raise RuntimeError(
        f"Could not find the Gearing-Tool repo root by walking up from {start!r} - "
        f"looked for ingest/list_characters.py. Make sure this exe is somewhere inside "
        f"(or in dist/ inside) a real Gearing-Tool checkout."
    )


if getattr(sys, "frozen", False):
    _core_dir = _find_core_dir(os.path.dirname(os.path.abspath(sys.executable)))
else:
    _core_dir = _find_core_dir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _core_dir)
import repo_root  # noqa: E402

REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
sys.path.insert(0, os.path.join(REPO_ROOT, "ingest"))
import list_characters  # noqa: E402
import build_character  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "core"))
import run_full_sweep_mv  # noqa: E402
import build_ledger_data  # noqa: E402
import character_profiles  # noqa: E402
import render_report  # noqa: E402
import local_config  # noqa: E402

# Moved to core/character_profiles.py 2026-08-25 (a real bug: cli/gear.py's
# own sweep command had no equivalent guard and was silently defaulting
# non-Hunter characters to Hunter's whole profile - see that module's
# docstring). Kept as a local alias so nothing else in this file needs to
# change.
SUPPORTED_CHARACTERS = character_profiles.SUPPORTED_CHARACTERS

# Phase 1 real, not a gap anymore (2026-08-25): every profile's own
# reference_bis/phase1.json now exists (rebuilt from wowsims' own real p1
# gear_sets files for the 4 wowsims-preset-based profiles; Hunter's own
# hand-curated Wowhead reference still needs a real Phase 1 entry - see
# QUESTIONS.md). time_horizon.py's own bis_until_phase loop already ranged
# over 1..FINAL_PHASE unconditionally from the start (its own docstring:
# "a future phase1 file would be too [picked up for free], with no code
# change needed") - this was genuinely only ever a missing-data gap, not a
# code gap, confirmed by that loop needing zero changes here.
PHASES = ["phase1", "phase2", "phase3", "phase4", "phase5"]

# GearingToolCompanion isn't published on CurseForge yet (per the user,
# 2026-08-30) - this repo's own mirrored copy (see CLAUDE.md's "Addon sync"
# section) IS the real, current addon source, so installing FROM here is
# installing the real thing, not a stand-in.
ADDON_SRC_DIR = os.path.join(REPO_ROOT, "addons", "GearingToolCompanion")


def _addon_file_hashes(dir_path: str) -> dict[str, str] | None:
    """None if the directory doesn't exist at all (never-installed case,
    distinct from "installed but different files"). sha256 per file, not a
    single combined hash, so a future partial-install/corruption case could
    still be diagnosed file-by-file if it ever comes up - not needed today,
    but cheap to keep."""
    if not os.path.isdir(dir_path):
        return None
    hashes = {}
    for fname in sorted(os.listdir(dir_path)):
        fpath = os.path.join(dir_path, fname)
        if os.path.isfile(fpath):
            with open(fpath, "rb") as f:
                hashes[fname] = hashlib.sha256(f.read()).hexdigest()
    return hashes

# One global job slot, not per-character concurrency - the real sim-call
# concurrency ceiling (valuation.SIMSERVER_POOL_SIZE=2) means two
# simultaneous sweeps would just contend for the same workers with no
# throughput benefit, and sim_cache.json's whole-file read-modify-write is a
# real corruption risk under concurrent writes. Lock-protected module-level
# dict rather than per-request state since pywebview calls each js_api
# method on its own thread.
_status_lock = threading.Lock()
_run_status: dict = {
    "active": False, "error": None, "done": False, "stage": None, "detail": None,
    "name_realm": None, "phase": None, "report_url": None, "eta_seconds": None,
    "eta_measured_at": None, "stage_index": None, "stage_total": None,
}


def _set_status(**kwargs) -> None:
    with _status_lock:
        _run_status.update(kwargs)


def _get_status() -> dict:
    """Real bug the user caught live, 2026-08-25 (a screen recording made
    this obvious - see NOTES.md): run_with_progress() only calls progress_cb
    when done crosses a new 5%-of-total boundary, so for a large stage
    (hundreds of items) the stored eta_seconds can sit frozen, unchanged,
    for many real seconds at a time. The frontend used to just display
    whatever was last stored - each 1.5s poll "corrected" toward that same
    stale number, actively fighting its own local countdown ticker instead
    of filling the gap between real updates, which is exactly what looked
    "stuck"/jumpy in the recording. Fixed at the source instead of patching
    the frontend further: age-adjust the stored estimate by how much real
    wall-clock time has passed since it was actually measured
    (eta_measured_at, stamped in _run_report_job's progress_cb), so every
    poll - not just the ones that land on a real backend tick - returns a
    genuinely live, decaying number."""
    with _status_lock:
        status = dict(_run_status)
    eta = status.get("eta_seconds")
    measured_at = status.get("eta_measured_at")
    if eta is not None and measured_at is not None:
        status["eta_seconds"] = max(0.0, eta - (time.time() - measured_at))
    return status


def _run_report_job(name_realm: str, phase: str, duration: int) -> None:
    """Runs on a background daemon thread (see Api.run_report) - never
    raises into the thread's default excepthook, every real failure mode
    (including SystemExit, which doesn't subclass Exception - build_character
    .build() raises it when no WSE export exists) is caught and surfaced
    through _run_status instead of hanging the GUI's polling forever."""
    try:
        char_dir = os.path.join(USER_DATA_DIR, "characters", name_realm)
        profile = json.load(open(os.path.join(SUPPORTED_CHARACTERS[name_realm], "profile.json"), encoding="utf-8"))
        if profile.get("synthetic_character"):
            # Real gap found and fixed (Stage 6.3, Shaman): a synthetic test
            # character (see ingest/build_synthetic_character.py) has no real
            # WowSimsExporter export to sync from at all - the normal
            # unconditional build_character.build() call below raises
            # SystemExit for it every time. Reuse the already-built
            # character.json on disk instead of re-syncing.
            _set_status(stage="Loading synthetic test character", detail=None, error=None, eta_seconds=None, eta_measured_at=None,
                        stage_index=None, stage_total=None)
            char_data = json.load(open(os.path.join(char_dir, "character.json"), encoding="utf-8"))
        else:
            _set_status(stage="Syncing character data", detail=None, error=None, eta_seconds=None, eta_measured_at=None,
                        stage_index=None, stage_total=None)
            char_data = build_character.build(name_realm)
            os.makedirs(char_dir, exist_ok=True)
            with open(os.path.join(char_dir, "character.json"), "w", encoding="utf-8") as f:
                json.dump(char_data, f, indent=2)

        def progress_cb(evt: dict) -> None:
            detail = f"{evt['done']}/{evt['total']} ({evt['pct']}%)" if evt.get("done") is not None else None
            eta = evt.get("eta_seconds")
            _set_status(stage=evt["stage"], detail=detail, eta_seconds=eta,
                        eta_measured_at=time.time() if eta is not None else None,
                        stage_index=evt.get("stage_index"), stage_total=evt.get("stage_total"))

        # Real bug avoided here, not just a defaults-are-fine shortcut: without
        # this, EVERY character's report would silently run through Hunter's
        # own profile (run_full_sweep_mv.main()'s default profile_dir) -
        # caught before it ever shipped, since SUPPORTED_CHARACTERS is now a
        # real per-character profile_dir map, not just a flat set.
        run_full_sweep_mv.main(name_realm, phase, profile_dir=SUPPORTED_CHARACTERS[name_realm],
                                progress_cb=progress_cb, duration=duration)

        _set_status(stage="Building report", detail=None, eta_seconds=None, eta_measured_at=None, stage_index=None, stage_total=None)
        ledger_data = build_ledger_data.build(name_realm, phase, profile_dir=SUPPORTED_CHARACTERS[name_realm])
        html = render_report.render(ledger_data, char_data, phase)

        out_path = local_config.report_output_path(name_realm, phase)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        report_url = Path(out_path).as_uri()

        # Same shape cli/gear.py's cmd_report_register already writes, so
        # the existing get_reports()/renderReports()/open_url() JS needs no
        # changes to display or open a Run-Report-generated entry.
        reports_path = os.path.join(char_dir, "reports.json")
        reports = {}
        if os.path.exists(reports_path):
            with open(reports_path, encoding="utf-8") as f:
                reports = json.load(f)
        reports[phase] = {"artifact_url": report_url, "generated_at": datetime.now(timezone.utc).isoformat()}
        with open(reports_path, "w", encoding="utf-8") as f:
            json.dump(reports, f, indent=2)

        _set_status(active=False, done=True, stage="Done", detail=None, eta_seconds=None, eta_measured_at=None,
                    stage_index=None, stage_total=None, report_url=report_url)
    except SystemExit as e:
        _set_status(active=False, done=True, stage=None, detail=None, eta_seconds=None, eta_measured_at=None,
                    stage_index=None, stage_total=None, error=str(e))
    except Exception as e:
        traceback.print_exc()
        _set_status(active=False, done=True, stage=None, detail=None, eta_seconds=None, eta_measured_at=None,
                    stage_index=None, stage_total=None, error=f"{type(e).__name__}: {e}")


class Api:
    def list_characters(self) -> list[dict]:
        chars = list_characters.list_all_characters()
        if local_config.debug_mode():
            chars = chars + list_characters.list_synthetic_characters()
        for c in chars:
            c["has_profile"] = c["name_realm"] in SUPPORTED_CHARACTERS
        return chars

    def get_debug_mode(self) -> bool:
        return local_config.debug_mode()

    def set_debug_mode(self, enabled: bool) -> bool:
        local_config.set_debug_mode(bool(enabled))
        return local_config.debug_mode()

    def get_reports(self, name_realm: str) -> dict:
        path = os.path.join(USER_DATA_DIR, "characters", name_realm, "reports.json")
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def get_supported_phases(self) -> list[str]:
        return PHASES

    def run_report(self, name_realm: str, phase: str, duration: int = 180) -> dict:
        if name_realm not in SUPPORTED_CHARACTERS:
            return {"started": False, "error": f"{name_realm} has no sim profile yet."}
        if phase not in PHASES:
            return {"started": False, "error": f"Unsupported phase {phase!r}."}
        if _get_status()["active"]:
            return {"started": False, "error": "A report is already running - wait for it to finish."}
        # Real fight-length setting (per the user, 2026-08-25 - real
        # encounters vary a lot in length, and item rankings can genuinely
        # depend on it, their own real Teeth of Gruul example). 180s is the
        # long-standing default (matches settings_builder.py's own
        # _ENCOUNTER) - bounds are generous but real (a 0 or negative
        # duration isn't a real fight; an absurdly long one is still valid,
        # just not worth guarding against a specific upper number here).
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            return {"started": False, "error": "Fight duration must be a whole number of seconds."}
        if duration <= 0:
            return {"started": False, "error": "Fight duration must be a positive number of seconds."}

        _set_status(active=True, done=False, error=None, stage="Starting", detail=None, eta_seconds=None, eta_measured_at=None,
                    stage_index=None, stage_total=None, name_realm=name_realm, phase=phase, report_url=None)
        threading.Thread(target=_run_report_job, args=(name_realm, phase, duration), daemon=True).start()
        return {"started": True}

    def get_run_status(self) -> dict:
        return _get_status()

    def get_report_output_dir(self) -> dict:
        """Real resolved absolute path either way, same shape as
        get_wow_root() - was returning None for "use the default" and
        letting the frontend paper over that with a vague, non-resolved
        template string ("USER_DATA_DIR/characters/<character>/reports/"), unlike
        the WoW-folder row's own always-a-real-path display. Real problem
        this masked (found while answering the user's own "is this ready
        for the bundled installer" question, 2026-08-26): that default is
        REPO_ROOT-relative, and REPO_ROOT is computed differently (and,
        for every module except this file, INCORRECTLY under a frozen
        PyInstaller build - see REPO_ROOT's own comment above) depending on
        where it's computed - showing the real resolved path here at least
        makes it possible to notice when it points somewhere wrong."""
        configured = local_config.report_output_root()
        if configured:
            return {"path": configured, "is_configured": True}
        return {"path": os.path.join(USER_DATA_DIR, "characters", "<character>", "reports"), "is_configured": False}

    def pick_report_folder(self) -> str | None:
        import webview
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        local_config.set_report_output_root(result[0])
        return result[0]

    def reset_report_output_dir(self) -> None:
        local_config.set_report_output_root(None)

    def get_wow_root(self) -> dict:
        """Returns both the effective path (whatever wow_root() resolves to
        right now) and whether it came from an explicit user override, so
        the settings UI can show "auto-detected" vs a user's own choice
        rather than always looking the same."""
        configured = local_config.load().get("wow_root")
        return {"path": local_config.wow_root(), "is_configured": bool(configured)}

    def pick_wow_root_folder(self) -> str | None:
        import webview
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        local_config.set_wow_root(result[0])
        return result[0]

    def reset_wow_root(self) -> None:
        local_config.set_wow_root(None)

    def get_addon_status(self) -> dict:
        """GearingToolCompanion isn't on CurseForge yet (per the user,
        2026-08-30) - installing it today means manually copying two files
        into the right WoW folder, easy to get wrong or forget after an
        update. Real, content-hash-based comparison (the .toc has no
        `## Version:` field to compare instead - never invent one) so
        "up to date" actually means "these exact bytes", not just "a folder
        with this name exists". install_path is always returned (even when
        not installed yet) so the UI can show where it WOULD go."""
        install_path = os.path.join(local_config.wow_root(), "Interface", "AddOns", "GearingToolCompanion")
        shipped = _addon_file_hashes(ADDON_SRC_DIR)
        installed = _addon_file_hashes(install_path)
        return {
            "install_path": install_path,
            "installed": installed is not None,
            "up_to_date": installed is not None and installed == shipped,
        }

    def install_companion_addon(self) -> dict:
        install_path = os.path.join(local_config.wow_root(), "Interface", "AddOns", "GearingToolCompanion")
        try:
            os.makedirs(install_path, exist_ok=True)
            for fname in os.listdir(ADDON_SRC_DIR):
                shutil.copy2(os.path.join(ADDON_SRC_DIR, fname), os.path.join(install_path, fname))
        except OSError as e:
            return {"success": False, "error": str(e), "install_path": install_path}
        return {"success": True, "error": None, "install_path": install_path}

    def get_sim_credits(self) -> dict:
        """Real links pulled straight from sim/tbc-new/README.md, not
        invented - that file's own license section explicitly asks anyone
        using the project to keep "a user visible link back to the
        original project" (real quote), so this exists to satisfy that,
        not just as a nice-to-have. version_label prefers a real tag
        (e.g. "v0.0.119"); commit_sha is always the real full SHA
        underneath it, shown too since a label can legitimately be a
        fallback short-SHA instead of a tag."""
        return {
            "version_label": repo_root.sim_version_label(),
            "commit_sha": repo_root.sim_commit_sha(),
            "github_url": "https://github.com/wowsims/tbc-new",
            "patreon_url": "https://www.patreon.com/wowsims",
            "discord_url": "https://discord.gg/jJMPr9JWwx",
        }
