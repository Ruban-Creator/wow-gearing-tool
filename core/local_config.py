"""Local, per-machine config that never travels via git - lives under
repo_root.USER_DATA_DIR (%LOCALAPPDATA%\\GearingTool\\ on a real install,
never repo-relative - see repo_root.py's own docstring for why). Today
just where the GUI's Run Report writes finished HTML reports. Plain
load()/save() rather than a class, and kept at core/ level rather than
gui/ - a future CLI command could read/write it too, not just the GUI.
"""
import json
import os
import sys
import string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
CONFIG_PATH = os.path.join(USER_DATA_DIR, "local_config.json")


def load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def report_output_root() -> str | None:
    """None means "use the default" (USER_DATA_DIR/characters/<name>/reports/) - a
    user-configured root overrides that entirely, e.g. if they'd rather the
    HTML files live somewhere they'll actually browse to day to day."""
    return load().get("report_output_root")


def set_report_output_root(path: str | None) -> None:
    """Pass None to clear back to the default."""
    config = load()
    if path is None:
        config.pop("report_output_root", None)
    else:
        config["report_output_root"] = path
    save(config)


def report_output_path(name_realm: str, phase: str) -> str:
    root = report_output_root()
    if root:
        return os.path.join(root, name_realm, f"{phase}.html")
    return os.path.join(USER_DATA_DIR, "characters", name_realm, "reports", f"{phase}.html")


# The only hardcoded fallback left once wow_root() has no configured value
# AND autodetect_wow_root() finds nothing real - matches this project's own
# original hardcoded WOW_ROOT (ingest/build_character.py, now sourced from
# here instead). Real on the machine this was developed on, but genuinely
# just one person's install location - never assume it's right elsewhere,
# which is the whole reason this got made configurable (per the user,
# 2026-08-26).
_LEGACY_DEFAULT_WOW_ROOT = r"C:\Games\World of Warcraft\_anniversary_"

# Real, common install roots (relative to a drive letter) for the
# Anniversary client specifically - Battle.net's own historical default
# (Program Files (x86)), a newer-install default (Program Files), a flat
# drive-root install, and this project's own original hardcoded location.
# Each candidate is verified via the client's own real .flavor.info file
# (confirmed real content on the dev machine: literally "wow_anniversary")
# before being trusted - never just assumed present because the folder
# exists, since a retail/Classic/Cata-Classic install can sit right next to
# it under a differently-named flavor folder.
_CANDIDATE_SUBPATHS = [
    r"Program Files (x86)\World of Warcraft\_anniversary_",
    r"Program Files\World of Warcraft\_anniversary_",
    r"World of Warcraft\_anniversary_",
    r"Games\World of Warcraft\_anniversary_",
]


def _looks_like_anniversary_client(path: str) -> bool:
    flavor_path = os.path.join(path, ".flavor.info")
    if not os.path.isfile(flavor_path):
        return False
    try:
        with open(flavor_path, encoding="utf-8", errors="ignore") as f:
            return "wow_anniversary" in f.read()
    except OSError:
        return False


def autodetect_wow_root() -> str | None:
    """Scans real drive letters present on this machine for a real
    Anniversary-client install, verified via the client's own .flavor.info
    file rather than just a matching folder name. Returns the first real
    match found, or None if nothing real was found anywhere - callers must
    handle None (fall back to _LEGACY_DEFAULT_WOW_ROOT, or ask the user),
    never invent a path when this comes back empty.

    Real GUI-startup-blocking risk (code review §4.2): os.path.isdir() on
    a mapped-but-disconnected network drive or an empty optical drive can
    block for real seconds, and this runs on the GUI's own startup path
    (see wow_root(), which now caches the result specifically so this
    expensive scan only ever runs once). Checks the real SystemDrive
    (almost always C:, the common case) FIRST so a normal install returns
    immediately without touching any other letter, and skips A:/B: - the
    historical floppy-drive letters, still occasionally mapped to a slow
    or prompting device on an old machine even though real floppy drives
    are gone."""
    system_drive = os.environ.get("SystemDrive", "C:").upper()
    ordered_letters = [system_drive.rstrip(":")] + [
        letter for letter in string.ascii_uppercase
        if letter not in ("A", "B", system_drive.rstrip(":"))
    ]
    for letter in ordered_letters:
        drive = f"{letter}:\\"
        if not os.path.isdir(drive):
            continue
        for subpath in _CANDIDATE_SUBPATHS:
            candidate = os.path.join(drive, subpath)
            if _looks_like_anniversary_client(candidate):
                return candidate
    return None


def wow_root() -> str:
    """The real WoW Anniversary install root used to find addon
    SavedVariables (ingest/build_character.py's find_savedvariables(),
    which feeds both the sync pipeline and the GUI's character picker).
    Precedence: explicit user config > a CACHED prior real autodetection >
    a fresh real autodetection (verified via .flavor.info, never just a
    folder-name guess) > the one legacy hardcoded default, kept only so a
    machine that had this working before wow_root() existed doesn't
    regress.

    Caches a successful autodetection under its own separate key (code
    review §4.2) - NOT into the same "wow_root" key gui/api.py's
    get_wow_root() checks for its own is_configured flag (that flag means
    "the user explicitly chose this", which stays false for something
    this function found on its own) - so the real, potentially-slow drive
    scan (os.path.isdir() can block for real seconds on a mapped-but-
    disconnected network drive) only ever runs once per machine, not once
    on every GUI launch."""
    configured = load().get("wow_root")
    if configured:
        return configured
    cached = load().get("_autodetected_wow_root")
    if cached and _looks_like_anniversary_client(cached):
        return cached
    detected = autodetect_wow_root()
    if detected:
        config = load()
        config["_autodetected_wow_root"] = detected
        save(config)
        return detected
    return _LEGACY_DEFAULT_WOW_ROOT


def set_wow_root(path: str | None) -> None:
    """Pass None to clear back to autodetect/legacy-default behavior - also
    clears wow_root()'s own cached prior autodetection, so "Reset to
    auto-detect" in the GUI genuinely re-scans instead of silently
    returning whatever was cached from before."""
    config = load()
    if path is None:
        config.pop("wow_root", None)
        config.pop("_autodetected_wow_root", None)
    else:
        config["wow_root"] = path
    save(config)


def character_profile_overrides() -> dict:
    """name_realm -> profile dir_name (e.g. "arms_warrior") for a real
    user's own characters. Added 2026-08-31 (code review §1.2): this used
    to be three real characters hardcoded directly in
    core/character_profiles.py, tying a real person's first name to their
    real WoW characters and realm in source - a privacy problem in a
    public repo, and it also meant the tool only ever worked for that one
    person. Empty by default; grows via set_character_profile() (the GUI's
    "assign a profile" flow, or called directly)."""
    return load().get("character_profiles", {})


def set_character_profile(name_realm: str, profile_dir_name: str | None) -> None:
    """Pass None to remove the override."""
    config = load()
    overrides = config.setdefault("character_profiles", {})
    if profile_dir_name is None:
        overrides.pop(name_realm, None)
    else:
        overrides[name_realm] = profile_dir_name
    if not overrides:
        config.pop("character_profiles", None)
    save(config)


def source_scope_exclusions(name_realm: str) -> list[str]:
    """Backlog #5 (CLAUDE.md Future Scope) - real loot sources (raid/dungeon
    zones, crafting professions, reputation) this character has chosen to
    exclude from their candidate pool, layered UNDER the Phase selector (see
    core/source_scope.py for the real motivating gap - Phase 3 alone bundles
    both Hyjal Summit and Black Temple, which aren't equally accessible in
    real TBC progression). Persisted per character, not per run - real raid
    access changes over weeks, not per report. Empty by default (nothing
    excluded - matches every existing character's behavior before this
    setting existed)."""
    return load().get("source_scope_exclusions", {}).get(name_realm, [])


def set_source_scope_exclusions(name_realm: str, keys: list[str] | None) -> None:
    """Pass an empty list or None to clear the character's exclusions back
    to "everything included"."""
    config = load()
    overrides = config.setdefault("source_scope_exclusions", {})
    if not keys:
        overrides.pop(name_realm, None)
    else:
        overrides[name_realm] = list(keys)
    if not overrides:
        config.pop("source_scope_exclusions", None)
    save(config)


def sim_concurrency() -> int:
    """The real, single source of truth for sim-call concurrency (code
    review §4.4) - core/run_upgrade_sweep.py's MAX_WORKERS and
    adapters/tbc/valuation.py's SIMSERVER_POOL_SIZE both call this instead
    of each hardcoding their own literal that has to be kept in sync by
    hand (they must stay equal - the sim already uses ALL logical threads
    per call internally via Go's runtime.NumCPU(), so a larger pool
    oversubscribes; measured on the original dev machine, 6C/12T: 4
    workers was 7.4x SLOWER than 2). Lives here (not in either of those
    two modules) specifically to avoid a circular import between them -
    run_upgrade_sweep imports marginal_value imports valuation, so
    valuation can't import run_upgrade_sweep or vice versa; local_config
    has no dependency on either.

    Derives from real per-machine logical-core count (//6 reproduces the
    original dev machine's own measured-safe 2, floored there since a
    machine with fewer logical threads wasn't part of what was actually
    measured), overridable via local_config for anyone who wants to tune
    it themselves."""
    override = load().get("max_workers")
    if override:
        return int(override)
    return max(2, (os.cpu_count() or 12) // 6)


def set_max_workers_override(n: int | None) -> None:
    """Pass None to clear back to the derived default."""
    config = load()
    if n is None:
        config.pop("max_workers", None)
    else:
        config["max_workers"] = int(n)
    save(config)


# The real, historical constant - 30000 is what run_upgrade_sweep.py's own
# RESOLVE_ITERATIONS was hardcoded to before this setting existed (see
# NOTES.md's real A/B data: 30k was the floor for a REPORTED number, not
# just a screening gate - 5000 missed a real, decision-relevant +1.3 DPS
# effect that only showed up at 30k). Kept here as the one real default,
# not duplicated as a second literal in run_upgrade_sweep.py.
DEFAULT_RESOLVE_ITERATIONS = 30000


def resolve_iterations() -> int:
    """Backlog item #6 (CLAUDE.md Future Scope) - the final resolve pass's
    iteration count, exposed as a real, per-machine tunable setting instead
    of a hardcoded constant, since the right value is a genuine speed/
    precision tradeoff a user might want to tune (a higher count is slower
    but tighter noise bounds; see run_upgrade_sweep.py's own real A/B
    write-up for what happens if this is set too low - NOT recommended
    below 30000 for a number that gets reported as final, only for
    deliberately trading precision for speed with eyes open)."""
    override = load().get("resolve_iterations")
    if override:
        return int(override)
    return DEFAULT_RESOLVE_ITERATIONS


def set_resolve_iterations(n: int | None) -> None:
    """Pass None to clear back to the default (30000)."""
    config = load()
    if n is None:
        config.pop("resolve_iterations", None)
    else:
        config["resolve_iterations"] = int(n)
    save(config)


def debug_mode() -> bool:
    """Off by default - the GUI's real, addon-sourced character picker
    (ingest/list_characters.py) never includes the synthetic test
    characters built for profile verification (Test-*-Synthetic), since
    they have no real WowSimsExporter/GearingToolCompanion SavedVariables
    entry to be discovered from. Debug mode opts into also listing those,
    so a new profile can be smoke-tested through the actual GUI instead of
    only ever the CLI/direct-Python path - per the user, 2026-08-26."""
    return bool(load().get("debug_mode", False))


def set_debug_mode(enabled: bool) -> None:
    config = load()
    if enabled:
        config["debug_mode"] = True
    else:
        config.pop("debug_mode", None)
    save(config)
