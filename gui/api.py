"""Python surface exposed to the pywebview window's JS via `js_api` - see
gui/app.py. Read-only: v1 is a picker + report viewer, never triggers a sim
run (see the approved plan, C:\\Users\\Matthias\\.claude\\plans\\staged-purring-lynx.md).
"""
from __future__ import annotations

import json
import os
import sys
import webbrowser

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

# v1 simplification, not silently assumed: only Lerynia's Survival Hunter
# profile actually works with the sim pipeline today. Computing this from
# identity.class/spec is unreliable in general (a GTCompanion-sourced
# identity block has no spec field at all - see list_characters.py), so
# this stays a literal set until Stage 6 (multi-class support) exists and
# has_profile can become real class/spec-driven logic instead.
SUPPORTED_CHARACTERS = {"Lerynia-Thunderstrike"}

PHASES = ["phase2", "phase3", "phase4", "phase5"]


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
