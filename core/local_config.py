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


def report_output_path(name_realm: str, profile_dir_name: str, phase: str) -> str:
    """Backlog #13 - profile_dir_name is now a real, required part of the
    filename (`<profile_dir_name>_<phase>.html`, not just `<phase>.html`) so
    a character reassigned to a different sim profile doesn't overwrite her
    prior spec's report - see core/report_storage.py's own docstring for
    the full real bug this fixes."""
    filename = f"{profile_dir_name}_{phase}.html"
    root = report_output_root()
    if root:
        return os.path.join(root, name_realm, filename)
    return os.path.join(USER_DATA_DIR, "characters", name_realm, "reports", filename)


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


MELEE_WEAVE_MODES = ("turret", "weave")
DEFAULT_MELEE_WEAVE_MODE = "turret"


def melee_weave_mode(name_realm: str) -> str:
    """Backlog #20 follow-up (2026-09-06, per the user, real live finding):
    a weave-capable profile's (Survival/Beastmastery Hunter) real DPS can
    differ by 500+ points depending on whether she actually melee-weaves or
    plays pure ranged "turret" style - confirmed live for Lerynia (2812.8
    no-weave vs 3338.6 weave-on, same exact real gear). This was previously
    silently baked into which settings file (`settings_template.json` vs
    `settings_template_2h.json`) happened to be treated as "primary" for
    the WHOLE report (every slot's MV, not just the weapon-choice side
    analysis) - the user's own explicit call: "we should not assume if the
    use is weaving or not" - a real, per-character, user-visible choice,
    not a silent default baked into which file a profile happens to load.

    Defaults to "turret" (no weave) - matches this tool's own real,
    historical default behavior for every existing Survival/Beastmastery
    Hunter report before this setting existed, so nothing changes for an
    existing character until they actually open the new selector and pick
    "Melee Weave" - per the user's own follow-up: "we could default to
    turret and add a red info text about the selector" (the GUI's own job,
    not this function's - this just needs an honest, unsurprising default).
    Meaningless for every non-weave-capable profile - callers should gate
    on `is_weave_profile` themselves rather than rely on this returning
    anything meaningful for e.g. a caster."""
    return load().get("melee_weave_mode", {}).get(name_realm, DEFAULT_MELEE_WEAVE_MODE)


def set_melee_weave_mode(name_realm: str, mode: str | None) -> None:
    """Pass None (or "turret", the default) to reset back to the default -
    only a real, explicit "weave" choice needs to be persisted at all."""
    if mode is not None and mode not in MELEE_WEAVE_MODES:
        raise ValueError(f"Unknown melee_weave_mode {mode!r} - expected one of {MELEE_WEAVE_MODES}")
    config = load()
    overrides = config.setdefault("melee_weave_mode", {})
    if mode is None or mode == DEFAULT_MELEE_WEAVE_MODE:
        overrides.pop(name_realm, None)
    else:
        overrides[name_realm] = mode
    if not overrides:
        config.pop("melee_weave_mode", None)
    save(config)


def consumable_potion_id(name_realm: str, profile_dir: str) -> int:
    """Real, per-character combat-potion choice for a caster profile (2026-09-06,
    per the user: "some classes like arcane mage gain more dps from mana pot
    over destro pot" - a real, per-gear-state tradeoff, not a fixed
    per-class truth) - same "we should not assume" precedent as
    melee_weave_mode() above, but the DEFAULT here isn't one fixed constant:
    it's whatever that profile's own `consumables.json` already commits to
    today (Destruction Potion/22839 for 6 of the 7 real caster profiles,
    Super Mana Potion/22832 for Balance Druid specifically - confirmed via
    direct grep during planning, she's already the outlier) - so nothing
    changes for an existing character until they actually open the new
    selector and pick something else. Needs profile_dir (unlike
    melee_weave_mode(), which never varies its own single fixed default)
    to read that real per-profile default."""
    override = load().get("consumable_potion_id", {}).get(name_realm)
    if override is not None:
        return override
    consumables = repo_root.load_json(os.path.join(profile_dir, "consumables.json"))
    return consumables["potId"]


def set_consumable_potion_id(name_realm: str, potion_id: int | None) -> None:
    """Pass None to reset back to the profile's own real default - only a
    real, explicit override needs to be persisted at all. No fixed
    MODES-style validation tuple here (unlike melee_weave_mode) since the
    real valid set is curated in gui/api.py's own get_potion_options(), not
    a small closed enum this module should duplicate."""
    config = load()
    overrides = config.setdefault("consumable_potion_id", {})
    if potion_id is None:
        overrides.pop(name_realm, None)
    else:
        overrides[name_realm] = potion_id
    if not overrides:
        config.pop("consumable_potion_id", None)
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


def show_low_level_characters() -> bool:
    """Off by default - the character picker only shows real max-level (70)
    characters plus anything whose level isn't known yet (no identity
    captured, e.g. a fresh GTCompanion-only export) - a known-sub-70
    character is hidden, never one this tool simply can't judge yet.
    ingest/list_characters.py's own 2026-08-31 decision keeps EVERY real
    character discoverable regardless of level (a genuinely-being-played
    leveling alt shouldn't be invisible to this tool), but per the user the
    same day, that shouldn't mean the default GUI view gets cluttered with
    them either - this setting is the toggle back to the wider view."""
    return bool(load().get("show_low_level_characters", False))


def set_show_low_level_characters(enabled: bool) -> None:
    config = load()
    if enabled:
        config["show_low_level_characters"] = True
    else:
        config.pop("show_low_level_characters", None)
    save(config)
