"""Single source of truth for REPO_ROOT - every other module used to
compute its own copy via `os.path.dirname(os.path.dirname(os.path.abspath(
__file__)))`, which is correct when running from source but silently wrong
under a frozen PyInstaller build: `__file__` for a bundled module resolves
inside the temp extraction directory (`sys._MEIPASS`), not the real,
permanent install location - so every `data/`-relative path built from it
(settings, character caches, reports) would write into a folder that gets
wiped the moment the app closes, with no error at all.

gui/api.py hit exactly this class of bug once already (a real crash the
first time the packaged exe was double-clicked - see its own docstring)
and fixed it there with a walk-up-from-the-real-exe-location search. That
fix only lived in gui/api.py; every other module kept the naive pattern.
Consolidated here (2026-08-26, prompted by the user asking whether the tool
was actually ready for a bundled installer - it wasn't) so there's exactly
one REPO_ROOT resolution to get right, not 27 copies that can silently
drift out of sync with each other.
"""
import os
import subprocess
import sys


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
        f"looked for ingest/list_characters.py. Make sure this is running from "
        f"somewhere inside (or in dist/ inside) a real Gearing-Tool checkout."
    )


if getattr(sys, "frozen", False):
    # sys.executable is the real, permanent .exe path even when frozen -
    # never sys._MEIPASS or __file__, both of which point into the
    # per-launch temp extraction dir instead.
    REPO_ROOT = _find_repo_root(os.path.dirname(os.path.abspath(sys.executable)))
else:
    # In source mode this file's own location IS the real, permanent
    # location - core/repo_root.py's immediate parent directory already
    # contains ingest/list_characters.py, so this resolves in one step.
    REPO_ROOT = _find_repo_root(os.path.dirname(os.path.abspath(__file__)))


def _user_data_dir() -> str:
    """Where Production Data (per-character caches/reports, sim_cache.json,
    local_config.json) actually lives - 2026-08-29 folder-structure rework,
    prompted by the "is this ready for a bundled installer" question. Used
    to be REPO_ROOT/data/, which only works for a dev checkout: an installed
    copy sitting in Program Files can't write there without admin rights,
    and a reinstall/update would wipe it if it lived next to the tool's own
    source. %LOCALAPPDATA%\\GearingTool\\ on Windows - created on first use,
    not at install time, so a fresh install "just works" with no separate
    installer-side data step. Falls back to REPO_ROOT/data only if
    LOCALAPPDATA genuinely isn't set (never happens on real Windows; kept
    only so this doesn't hard-crash in some exotic environment instead of
    degrading to the old dev-checkout behavior)."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return os.path.join(REPO_ROOT, "data")
    return os.path.join(base, "GearingTool")


# Real, permanent fallback location for a baked commit SHA (see
# sim_commit_sha()'s own docstring) - build/bin/ already holds every other
# piece of real Build Output this project produces (wowsimcli.exe,
# bridge.exe, simserver.exe), so a small text file lands there too rather
# than inventing a second Build Output location for one file.
SIM_COMMIT_SHA_FALLBACK_PATH = os.path.join(REPO_ROOT, "build", "bin", "sim_commit_sha.txt")

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def sim_commit_sha() -> str:
    """The sim submodule's real commit SHA - CLAUDE.md's ground rule
    requires this on every output ("so 'ranking changed because I got
    gear' is told apart from 'ranking changed because the sim updated'").
    Three call sites (adapters/tbc/adapter.py's version(),
    ingest/build_character.py's sim_commit_sha(), core/build_ledger_data.py)
    used to each run their own `git -C sim/tbc-new rev-parse HEAD` -
    consolidated here (2026-08-30, the real installer-blocker prompted by
    the user) since a flat installer copy has no `.git` for any of them to
    read, and having three independent copies of the same fallback logic
    would just be the pre-REPO_ROOT-consolidation mistake again.

    Prefers the live git call (correct immediately after a local submodule
    bump, no rebuild step needed - real, not hypothetical, this repo's own
    dev workflow bumps the pinned submodule commit directly sometimes) and
    falls back to a static file baked at build time
    (SIM_COMMIT_SHA_FALLBACK_PATH) only when git itself isn't usable -
    exactly the packaged-install case this exists for. Raises rather than
    returning a fake/empty SHA if both fail - "never invent data" applies
    to provenance stamps as much as to item stats."""
    sim_dir = os.path.join(REPO_ROOT, "sim", "tbc-new")
    try:
        out = subprocess.run(
            ["git", "-C", sim_dir, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, creationflags=_NO_WINDOW,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        pass
    if os.path.isfile(SIM_COMMIT_SHA_FALLBACK_PATH):
        with open(SIM_COMMIT_SHA_FALLBACK_PATH, encoding="utf-8") as f:
            sha = f.read().strip()
        if sha:
            return sha
    raise RuntimeError(
        f"Could not determine the sim's commit SHA - `git -C {sim_dir!r} rev-parse HEAD` "
        f"failed (no .git? git not installed?) and no baked fallback exists at "
        f"{SIM_COMMIT_SHA_FALLBACK_PATH!r}. In a real git checkout this should never happen; "
        f"for a packaged install, run the build-time step that writes the fallback file "
        f"(see packaging/README.md) before packaging."
    )


USER_DATA_DIR = _user_data_dir()
