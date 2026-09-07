"""Python surface exposed to the pywebview window's JS via `js_api` - see
gui/app.py. Was read-only (v1: picker + report viewer only) until the Run
Report feature (see the approved plan,
C:\\Users\\<user>\\.claude\\plans\\staged-purring-lynx.md) - now also runs a
real sweep + renders a local HTML report on demand.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
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
import run_upgrade_sweep  # noqa: E402
import build_ledger_data  # noqa: E402
import character_profiles  # noqa: E402
import render_report  # noqa: E402
import local_config  # noqa: E402
import sweep_all_loot  # noqa: E402
import source_scope  # noqa: E402
import item_db as idb  # noqa: E402
import report_storage  # noqa: E402
import version  # noqa: E402
import oom_check  # noqa: E402

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

# Also published on CurseForge as of 2026-08-31
# (https://www.curseforge.com/wow/addons/gt-companion - see index.html's
# "View on CurseForge" links) - this direct-install path still exists
# alongside it, since this repo's own mirrored copy (see CLAUDE.md's "Addon
# sync" section) IS the real, current addon source either way, and a
# one-click install from inside the GUI is still lower-friction for anyone
# who doesn't already use the CurseForge app.
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


_TOC_VERSION_RE = re.compile(r"^##\s*Version:\s*(.+)$", re.MULTILINE)


def _addon_version(dir_path: str) -> str | None:
    """Real `## Version:` field from GearingToolCompanion.toc, added
    2026-08-30 alongside the icon/branding pass (previously absent -
    get_addon_status()'s hash comparison exists precisely because this
    didn't used to be available). None if the .toc is missing/has no such
    line - never invent a version. This is a DISPLAY value only; the hash
    comparison below stays the real "up to date" source of truth, since a
    real edit with a forgotten version bump would otherwise report clean
    when it isn't."""
    toc_path = os.path.join(dir_path, "GearingToolCompanion.toc")
    if not os.path.isfile(toc_path):
        return None
    with open(toc_path, encoding="utf-8") as f:
        m = _TOC_VERSION_RE.search(f.read())
    return m.group(1).strip() if m else None


# Where the scheduled sim-update agent (designed 2026-08-30, not built yet -
# see CLAUDE.md's "Sim update procedure") is expected to publish a new
# GitHub Release, tagged to match the sim's own version, whenever it
# rebuilds. This repo's own real remote - not invented. No release exists
# yet, so every real check today legitimately reports "none published" -
# that's the correct, honest state until the agent actually runs, not a bug.
GITHUB_REPO = "Ruban-Creator/wow-gearing-tool"

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse_version(label: str) -> tuple[int, int, int] | None:
    """None for anything that isn't a clean vX.Y.Z tag - e.g. a raw short
    SHA (sim_version_label()'s own fallback when git can't resolve a real
    tag). Never guess a comparison for that case; callers must treat it as
    "can't tell, but show the human the raw label anyway"."""
    m = _VERSION_RE.fullmatch(label.strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups())


def _version_is_newer(candidate: str, current: str) -> bool | None:
    """None if either side isn't a clean vX.Y.Z - real ambiguity, not a
    false negative. True/False only when both parse."""
    c, cur = _parse_version(candidate), _parse_version(current)
    if c is None or cur is None:
        return None
    return c > cur


# One global job slot, not per-character concurrency - the real sim-call
# concurrency ceiling (valuation.SIMSERVER_POOL_SIZE=2) means two
# simultaneous sweeps would just contend for the same workers with no
# throughput benefit. (sim_cache's own journal format, since 2026-08-31,
# is safe under concurrent appends anyway - this constraint is purely
# about sim-worker contention now, not cache-file corruption risk.)
# Lock-protected module-level dict rather than per-request state since
# pywebview calls each js_api method on its own thread.
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
        # Backlog #13 - real, required for every output path below (report
        # HTML, tiered_report/ledger_data filenames, reports.json's own
        # nested key) so a character reassigned to a different sim profile
        # doesn't silently overwrite her prior spec's report.
        profile_dir_name = os.path.basename(os.path.normpath(SUPPORTED_CHARACTERS[name_realm]))
        # Real bug found and fixed 2026-08-31: this used to check the
        # PROFILE's own `synthetic_character` flag (profile.json), not
        # whether THIS CHARACTER is actually one of the built-in synthetic
        # test fixtures - a real character assigned to a profile that still
        # carries that flag from before any real player used that spec
        # (elemental_shaman, e.g.) skipped syncing her own real data and hit
        # a FileNotFoundError for her own character.json, which is never
        # pre-built for a real character the way it is for the fixtures.
        # See character_profiles.is_synthetic_character()'s own docstring.
        if character_profiles.is_synthetic_character(name_realm):
            # Real gap found and fixed (Stage 6.3, Shaman): a synthetic test
            # character (see ingest/build_synthetic_character.py) has no real
            # WowSimsExporter export to sync from at all - the normal
            # unconditional build_character.build() call below raises
            # SystemExit for it every time. Reuse the already-built
            # character.json on disk instead of re-syncing.
            _set_status(stage="Loading synthetic test character", detail=None, error=None, eta_seconds=None, eta_measured_at=None,
                        stage_index=None, stage_total=None)
            char_data = repo_root.load_json(os.path.join(char_dir, "character.json"))
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
        # own profile (run_upgrade_sweep.main()'s default profile_dir) -
        # caught before it ever shipped, since SUPPORTED_CHARACTERS is now a
        # real per-character profile_dir map, not just a flat set.
        run_upgrade_sweep.main(name_realm, phase, profile_dir=SUPPORTED_CHARACTERS[name_realm],
                                progress_cb=progress_cb, duration=duration)

        _set_status(stage="Building report", detail=None, eta_seconds=None, eta_measured_at=None, stage_index=None, stage_total=None)
        # build_with_diff() (2026-09-04) persists ledger_data_<profile>_<phase>.json
        # for real now (used to only live embedded in the HTML - see that
        # function's own docstring for the real gap this closes) and embeds a
        # real "what changed since your last sweep" comparison against the
        # rotated-aside previous file - report_template.html renders it when
        # present, silently absent on a character's first-ever sweep.
        ledger_data = build_ledger_data.build_with_diff(name_realm, phase, profile_dir=SUPPORTED_CHARACTERS[name_realm])
        html = render_report.render(ledger_data, char_data, phase)

        out_path = local_config.report_output_path(name_realm, profile_dir_name, phase)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        report_url = Path(out_path).as_uri()

        # Same shape cli/gear.py's cmd_report_register already writes (both
        # go through report_storage.py now, backlog #13), so the existing
        # get_reports()/renderReports()/open_url() JS needs no changes to
        # display or open a Run-Report-generated entry.
        reports = report_storage.load_reports(name_realm)
        reports.setdefault(profile_dir_name, {})[phase] = {
            "artifact_url": report_url, "generated_at": datetime.now(timezone.utc).isoformat()}
        report_storage.save_reports(name_realm, reports)

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
        # Per the user (2026-08-31): ingest/list_characters.py's own real
        # decision the same day keeps every character discoverable
        # regardless of level (a leveling alt genuinely being played
        # shouldn't be invisible), but that shouldn't mean the default GUI
        # view gets cluttered with them - hidden unless explicitly toggled
        # on, and a known level is required to hide (unknown/uncaptured
        # level always stays visible, never hidden by a guess).
        if not local_config.show_low_level_characters():
            chars = [c for c in chars if not c["identity"].get("level") or c["identity"]["level"] >= 70]
        for c in chars:
            c["has_profile"] = c["name_realm"] in SUPPORTED_CHARACTERS
            # Real dir_name (e.g. "elemental_shaman"), not the full profile_dir
            # path - lets the GUI's "Change profile" flow pre-select her
            # CURRENT assignment instead of always starting from scratch
            # (real gap found and fixed 2026-08-31 - a respec, e.g. Elemental
            # -> Enhancement, had no way back into the assign UI at all once
            # she already had a profile).
            c["profile_dir_name"] = (os.path.basename(SUPPORTED_CHARACTERS[c["name_realm"]])
                                      if c["has_profile"] else None)
        return chars

    def get_available_profiles(self) -> list[dict]:
        return character_profiles.available_profiles()

    def assign_character_profile(self, name_realm: str, dir_name: str) -> dict:
        """Real, user-driven fix for the "No profile" dead end (code review
        §1.2) - a character with no sim profile yet can now be assigned one
        directly from the GUI instead of requiring a source edit.
        character_profiles.refresh() makes it usable immediately, in this
        same running process, not just after a restart."""
        valid_dirs = {p["dir_name"] for p in character_profiles.available_profiles()}
        if dir_name not in valid_dirs:
            return {"ok": False, "error": f"Unknown profile {dir_name!r}."}
        local_config.set_character_profile(name_realm, dir_name)
        character_profiles.refresh()
        return {"ok": True, "has_profile": name_realm in SUPPORTED_CHARACTERS}

    def get_debug_mode(self) -> bool:
        return local_config.debug_mode()

    def set_debug_mode(self, enabled: bool) -> bool:
        local_config.set_debug_mode(bool(enabled))
        return local_config.debug_mode()

    def get_show_low_level_characters(self) -> bool:
        return local_config.show_low_level_characters()

    def set_show_low_level_characters(self, enabled: bool) -> bool:
        local_config.set_show_low_level_characters(bool(enabled))
        return local_config.show_low_level_characters()

    def get_resolve_iterations(self) -> dict:
        return {"value": local_config.resolve_iterations(),
                "default": local_config.DEFAULT_RESOLVE_ITERATIONS,
                "is_configured": bool(local_config.load().get("resolve_iterations"))}

    def set_resolve_iterations(self, n: int | None) -> dict:
        """n<=0 or None resets to the default. Floor of 1000 on any real
        override - below that isn't a "faster, less precise" tradeoff
        anymore, it's fast enough to be meaningless noise for a reported
        number (see local_config.resolve_iterations()'s own docstring)."""
        if n is not None and n > 0:
            n = max(1000, int(n))
        else:
            n = None
        local_config.set_resolve_iterations(n)
        return self.get_resolve_iterations()

    def get_available_sources(self, name_realm: str, phase: str) -> dict:
        """Backlog #5 (CLAUDE.md Future Scope) - every real loot source
        (raid/dungeon zone, crafting profession, reputation) actually
        present at this phase, for the Run Report modal's "Choose
        Sources..." checklist. Uses sweep_all_loot.eligible_items() - the
        PRE-truncation set - so a real zone never silently vanishes from the
        checklist just because none of its items survived the top-N
        crude-score cut for their armor type. `enabled` reflects the
        character's currently saved exclusions (local_config); anything not
        in that saved list defaults to enabled - a brand-new zone that
        appears after a phase bump is included by default, same as every
        character not using this feature at all."""
        if name_realm not in SUPPORTED_CHARACTERS or phase not in PHASES:
            return {"zones": [], "crafts": [], "rep": []}
        profile_dir = SUPPORTED_CHARACTERS[name_realm]
        phase_num = int(phase.removeprefix("phase"))
        items = sweep_all_loot.eligible_items(phase_num, profile_dir)
        zone_by_id = {z["id"]: z["name"] for z in idb.zones()}
        sources = source_scope.available_sources(items, zone_by_id)
        excluded = set(local_config.source_scope_exclusions(name_realm))
        for entries in sources.values():
            for entry in entries:
                entry["enabled"] = entry["key"] not in excluded
        return sources

    def set_source_scope_exclusions(self, name_realm: str, excluded_keys: list[str]) -> dict:
        local_config.set_source_scope_exclusions(name_realm, excluded_keys)
        return {"saved": True}

    def get_melee_weave_mode(self, name_realm: str) -> dict:
        """Backlog #20 follow-up (2026-09-06) - only meaningful for a real
        weave-capable profile (Survival/Beastmastery Hunter); the frontend
        gates the whole selector on `is_weave_profile` (checked via
        `profile_dir_name` - see list_characters()'s own docstring) rather
        than relying on this endpoint to say so, per the user's own
        reminder that other classes shouldn't see this control at all."""
        return {"mode": local_config.melee_weave_mode(name_realm),
                "is_configured": name_realm in local_config.load().get("melee_weave_mode", {})}

    def set_melee_weave_mode(self, name_realm: str, mode: str | None) -> dict:
        local_config.set_melee_weave_mode(name_realm, mode)
        return self.get_melee_weave_mode(name_realm)

    # Real, curated 3-option set (2026-09-06, per the user: "some classes
    # like arcane mage gain more dps from mana pot over destro pot") - see
    # NOTES.md's dated entry for why these 3 specifically (mechanically
    # distinct, real, verified via Wowhead + the sim's own db.json, not the
    # noisy 11-item raw alternates array some profiles happen to carry).
    CASTER_POTION_OPTIONS = (22839, 22832, 31677)

    def get_potion_options(self, name_realm: str) -> dict:
        """Only meaningful for a real caster profile
        (run_upgrade_sweep.CASTER_POTION_PROFILES) - the frontend gates the
        whole selector the same way it already does for
        get_melee_weave_mode(), via `profile_dir_name`, not by relying on
        this endpoint to say so."""
        profile_dir = SUPPORTED_CHARACTERS[name_realm]
        current = local_config.consumable_potion_id(name_realm, profile_dir)
        options = []
        for item_id in self.CASTER_POTION_OPTIONS:
            c = idb.consumable_by_id(item_id)
            options.append({"item_id": item_id, "name": c["name"] if c else f"item {item_id}"})
        return {"options": options, "current": current}

    def set_potion_choice(self, name_realm: str, potion_id: int | None) -> dict:
        local_config.set_consumable_potion_id(name_realm, potion_id)
        return self.get_potion_options(name_realm)

    def get_reports(self, name_realm: str) -> dict:
        """Backlog #13 - nested {profile_dir_name: {phase: {...}}}, migrated
        automatically from the old flat schema if needed - see
        report_storage.load_reports()'s own docstring.

        Real fix, 2026-09-06: filtered through report_storage.
        filter_missing_reports() before returning - a phase whose real
        underlying report file no longer exists (moved, deleted, or a
        pre-2026-08-29 path from before the repo-relative data/ directory
        was removed - found live this session, every one of Lerynia's 3
        reports and 3 of Béarforceone's 4 were stale in exactly this way)
        is dropped from what the GUI sees and renders as "No report
        published yet" instead of a dead "View Report" button that throws
        when clicked. Display-only - this filtered view is never the thing
        passed to save_reports() anywhere, so reports.json's own real
        history is never touched by this check."""
        return report_storage.filter_missing_reports(report_storage.load_reports(name_realm))

    def open_url(self, url: str) -> None:
        """Allowlisted by scheme (code review §4.3) - the JS bridge only
        ever sends http(s) links (Wowhead/GitHub/Patreon/Discord/report
        artifact URLs) or a file:// URI for a locally-rendered report
        (Path(out_path).as_uri(), always under USER_DATA_DIR - see
        run_report() above), but webbrowser.open() on Windows will
        happily invoke a registered protocol handler for anything else
        it's given. Safe by construction rather than by assumption about
        what today's frontend happens to send."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme in ("http", "https"):
            webbrowser.open(url)
            return
        if parsed.scheme == "file":
            local_path = os.path.normcase(os.path.abspath(urllib.request.url2pathname(parsed.path)))
            allowed_root = os.path.normcase(os.path.abspath(USER_DATA_DIR))
            if local_path.startswith(allowed_root + os.sep):
                webbrowser.open(url)
                return
        raise ValueError(f"open_url: refusing unrecognized/out-of-scope URL {url!r}")

    def get_supported_phases(self) -> list[str]:
        return PHASES

    def check_oom(self, name_realm: str, phase: str, duration: int) -> dict:
        """Real, cheap pre-sweep OOM check (2026-09-06) - called from
        app.js BEFORE the real, multi-minute sweep starts, so the GUI can
        offer a shorter, more realistic duration instead of silently
        producing a skewed report. Synchronous (not the background-job/
        polling pattern run_report() below uses) - the underlying sim call
        is cheap (SCREEN_ITERATIONS, cache-assisted) and a repeat check at
        an already-tried duration is near-instant, same reasoning as
        get_melee_weave_mode()'s own synchronous convention. See
        core/oom_check.py's own docstring for the real mechanism.

        Real bug found and fixed 2026-09-07 - this is the actual root cause
        of the long-standing "Run Report doesn't start, simserver.exe never
        appears" TODO item (reported 2026-09-06, reproduced multiple times
        by renaming/emptying a character's data folder): `oom_check.check()`
        reads `character.json` directly with no fallback, so a genuinely
        first-run character (no character.json yet - the exact real-world
        case of a fresh install, or the folder-rename repro) raised an
        uncaught FileNotFoundError here. This method runs SYNCHRONOUSLY from
        app.js's click handler, awaited with no try/catch on the JS side
        (see app.js's runReportStartBtn listener) - so the exception became
        a rejected promise that silently stopped the click handler dead
        before it ever reached `startRunReport()`/`run_report()` below,
        which is the ONLY place that actually knows how to build/sync a
        missing character.json (see `_run_report_job()`'s own real handling
        of exactly this case). Confirmed by direct reproduction: deleting a
        real synthetic profile's character.json and calling this method
        raised `FileNotFoundError` every time, matching the user's own real
        report precisely ("even when all folders exist the error still
        occurs - it only starts working when I copy in the character.json").
        Fix: treat any failure to read/use the character's data here as "no
        OOM signal available yet" rather than letting it propagate - this is
        only ever a pre-flight nicety, never the thing that should gate
        whether Run Report can start at all. The real sync/build still
        happens correctly inside `run_report()` immediately afterward."""
        if name_realm not in SUPPORTED_CHARACTERS:
            return {"oom_seconds": 0.0, "oom_fraction": 0.0, "flagged": False, "recommended_duration": None}
        try:
            return oom_check.check(name_realm, SUPPORTED_CHARACTERS[name_realm], duration, phase)
        except Exception:
            traceback.print_exc()
            return {"oom_seconds": 0.0, "oom_fraction": 0.0, "flagged": False, "recommended_duration": None}

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
        """The direct-install path this method backs still exists alongside
        the CurseForge listing (2026-08-31) - a one-click install from
        inside the GUI, no manual file copying into the right WoW folder,
        easy to get wrong or forget after an update by hand.
        `up_to_date` stays real, content-hash-based (never a version-string
        comparison alone) - a real edit with a forgotten version bump would
        otherwise report clean when it isn't. `shipped_version`/
        `installed_version` (added once the .toc gained a real `##
        Version:` field, 2026-08-30) are DISPLAY values only, read straight
        from each side's own .toc - never invented if missing. install_path
        is always returned (even when not installed yet) so the UI can show
        where it WOULD go."""
        install_path = os.path.join(local_config.wow_root(), "Interface", "AddOns", "GearingToolCompanion")
        shipped = _addon_file_hashes(ADDON_SRC_DIR)
        installed = _addon_file_hashes(install_path)
        return {
            "install_path": install_path,
            "installed": installed is not None,
            "up_to_date": installed is not None and installed == shipped,
            "shipped_version": _addon_version(ADDON_SRC_DIR),
            "installed_version": _addon_version(install_path) if installed is not None else None,
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

    def get_tool_version(self) -> str:
        """RGT's own version (see core/version.py) - separate from the
        vendored sim's own version shown right below it in the Settings
        modal (get_sim_credits() below)."""
        return version.version_string()

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

    def check_for_sim_update(self) -> dict:
        """Real GitHub Releases check against this repo's own remote
        (GITHUB_REPO) - the scheduled sim-update agent (designed, not yet
        running) is expected to publish a new release there, tagged to
        match the sim's own version, whenever it rebuilds. Every real
        failure mode (offline, GitHub down, rate-limited, no release
        published yet) is reported as a distinct, honest state - never
        silently treated as "no update", which would be indistinguishable
        from a real, successful "you're current" check. `update_available`
        is None (not False) when a comparison genuinely can't be made
        (e.g. the local version is a fallback short-SHA, not a clean tag) -
        the UI must show that as "can't tell", not claim you're current."""
        current = repo_root.sim_version_label()
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
                headers={"Accept": "application/vnd.github+json", "User-Agent": "GearingTool"},
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"checked": True, "error": None, "current_version": current,
                        "latest_version": None, "update_available": False, "release_url": None,
                        "note": "No release has been published yet."}
            return {"checked": False, "error": f"HTTP {e.code}", "current_version": current,
                    "latest_version": None, "update_available": None, "release_url": None}
        except (urllib.error.URLError, OSError, ValueError) as e:
            return {"checked": False, "error": str(e), "current_version": current,
                    "latest_version": None, "update_available": None, "release_url": None}

        latest_tag = data.get("tag_name")
        return {
            "checked": True, "error": None,
            "current_version": current, "latest_version": latest_tag,
            "update_available": _version_is_newer(latest_tag, current) if latest_tag else False,
            "release_url": data.get("html_url"),
        }
