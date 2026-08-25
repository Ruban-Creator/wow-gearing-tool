"""Python surface exposed to the pywebview window's JS via `js_api` - see
gui/app.py. Was read-only (v1: picker + report viewer only) until the Run
Report feature (see the approved plan,
C:\\Users\\Matthias\\.claude\\plans\\staged-purring-lynx.md) - now also runs a
real sweep + renders a local HTML report on demand.
"""
from __future__ import annotations

import json
import os
import sys
import threading
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
# double-click cwd didn't line up with either. Fixed by walking up from the
# exe's own real on-disk location (sys.executable, not cwd - correct
# regardless of what launched it or what the working directory happens to
# be) looking for a directory that actually has ingest/list_characters.py -
# works whether the exe stays in dist/ (repo root is one level up) or gets
# copied to the repo root directly, with no "Start in" folder configuration
# required from the user at all.
def _find_repo_root(start: str) -> str:
    d = start
    for _ in range(6):  # a handful of parent levels is plenty; never walk to the disk root
        if os.path.isfile(os.path.join(d, "ingest", "list_characters.py")):
            return d
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
    REPO_ROOT = _find_repo_root(os.path.dirname(os.path.abspath(sys.executable)))
else:
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "ingest"))
import list_characters  # noqa: E402
import build_character  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "core"))
import run_full_sweep_mv  # noqa: E402
import build_ledger_data  # noqa: E402
import render_report  # noqa: E402
import local_config  # noqa: E402

# Real character -> profile_dir map, not just a flat set - Stage 6.1 (Arms
# Warrior) is the second one, real and proven (real sim run, real report
# rendered, see QUESTIONS.md). Computing this from identity.class/spec is
# still unreliable in general (a GTCompanion-sourced identity block has no
# spec field at all - see list_characters.py), so this stays a literal
# mapping rather than derived logic - add a line here once a new profile is
# proven, same as this one was.
SUPPORTED_CHARACTERS = {
    "Lerynia-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter"),
    "Rubán-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "arms_warrior"),
    "Béarforceone-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "balance_druid"),
    # Synthetic test character (Stage 6.3) - no real Shaman export exists yet,
    # see profile.json's synthetic_character_note. Real, proven pipeline run
    # (full sweep, real report), just not a real personal character.
    "Test-Elemental-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "elemental_shaman"),
}

# reference_bis/phase1.json doesn't exist yet (a real data-curation gap, not
# a code gap - see the plan's Context section) - deliberately not offered
# until that data exists, rather than let a user pick it and hit a
# FileNotFoundError deep in the pipeline.
PHASES = ["phase2", "phase3", "phase4", "phase5"]

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
    "name_realm": None, "phase": None, "report_url": None,
}


def _set_status(**kwargs) -> None:
    with _status_lock:
        _run_status.update(kwargs)


def _get_status() -> dict:
    with _status_lock:
        return dict(_run_status)


def _run_report_job(name_realm: str, phase: str) -> None:
    """Runs on a background daemon thread (see Api.run_report) - never
    raises into the thread's default excepthook, every real failure mode
    (including SystemExit, which doesn't subclass Exception - build_character
    .build() raises it when no WSE export exists) is caught and surfaced
    through _run_status instead of hanging the GUI's polling forever."""
    try:
        char_dir = os.path.join(REPO_ROOT, "data", "characters", name_realm)
        profile = json.load(open(os.path.join(SUPPORTED_CHARACTERS[name_realm], "profile.json"), encoding="utf-8"))
        if profile.get("synthetic_character"):
            # Real gap found and fixed (Stage 6.3, Shaman): a synthetic test
            # character (see ingest/build_synthetic_character.py) has no real
            # WowSimsExporter export to sync from at all - the normal
            # unconditional build_character.build() call below raises
            # SystemExit for it every time. Reuse the already-built
            # character.json on disk instead of re-syncing.
            _set_status(stage="Loading synthetic test character", detail=None, error=None)
            char_data = json.load(open(os.path.join(char_dir, "character.json"), encoding="utf-8"))
        else:
            _set_status(stage="Syncing character data", detail=None, error=None)
            char_data = build_character.build(name_realm)
            os.makedirs(char_dir, exist_ok=True)
            with open(os.path.join(char_dir, "character.json"), "w", encoding="utf-8") as f:
                json.dump(char_data, f, indent=2)

        def progress_cb(evt: dict) -> None:
            detail = f"{evt['done']}/{evt['total']} ({evt['pct']}%)" if evt.get("done") is not None else None
            _set_status(stage=evt["stage"], detail=detail)

        # Real bug avoided here, not just a defaults-are-fine shortcut: without
        # this, EVERY character's report would silently run through Hunter's
        # own profile (run_full_sweep_mv.main()'s default profile_dir) -
        # caught before it ever shipped, since SUPPORTED_CHARACTERS is now a
        # real per-character profile_dir map, not just a flat set.
        run_full_sweep_mv.main(name_realm, phase, profile_dir=SUPPORTED_CHARACTERS[name_realm],
                                progress_cb=progress_cb)

        _set_status(stage="Building report", detail=None)
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

        _set_status(active=False, done=True, stage="Done", detail=None, report_url=report_url)
    except SystemExit as e:
        _set_status(active=False, done=True, stage=None, detail=None, error=str(e))
    except Exception as e:
        traceback.print_exc()
        _set_status(active=False, done=True, stage=None, detail=None, error=f"{type(e).__name__}: {e}")


class Api:
    def list_characters(self) -> list[dict]:
        chars = list_characters.list_all_characters()
        for c in chars:
            c["has_profile"] = c["name_realm"] in SUPPORTED_CHARACTERS
        return chars

    def get_reports(self, name_realm: str) -> dict:
        path = os.path.join(REPO_ROOT, "data", "characters", name_realm, "reports.json")
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def open_url(self, url: str) -> None:
        webbrowser.open(url)

    def get_supported_phases(self) -> list[str]:
        return PHASES

    def run_report(self, name_realm: str, phase: str) -> dict:
        if name_realm not in SUPPORTED_CHARACTERS:
            return {"started": False, "error": f"{name_realm} has no sim profile yet."}
        if phase not in PHASES:
            return {"started": False, "error": f"Unsupported phase {phase!r}."}
        if _get_status()["active"]:
            return {"started": False, "error": "A report is already running - wait for it to finish."}

        _set_status(active=True, done=False, error=None, stage="Starting", detail=None,
                    name_realm=name_realm, phase=phase, report_url=None)
        threading.Thread(target=_run_report_job, args=(name_realm, phase), daemon=True).start()
        return {"started": True}

    def get_run_status(self) -> dict:
        return _get_status()

    def get_report_output_dir(self) -> str | None:
        return local_config.report_output_root()

    def pick_report_folder(self) -> str | None:
        import webview
        result = webview.windows[0].create_file_dialog(webview.FOLDER_DIALOG)
        if not result:
            return None
        local_config.set_report_output_root(result[0])
        return result[0]

    def reset_report_output_dir(self) -> None:
        local_config.set_report_output_root(None)
