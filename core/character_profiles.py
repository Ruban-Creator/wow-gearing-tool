"""Real character -> profile_dir map, shared by every real entry point
(CLI, GUI) that runs a sweep for a specific character - moved here from
gui/api.py 2026-08-25 after a real bug: run_upgrade_sweep.main()'s
`profile_dir` parameter silently defaults to Survival Hunter's own profile
directory (its historical single-character default, kept for backward
compatibility), so any call site that forgets to pass `profile_dir`
explicitly for a non-Hunter character doesn't error - it silently sweeps
that character's real gear against HUNTER's candidate_pool.json,
default_enchants.json, stat_weights.json, and settings_template.json
instead, producing a real-looking but wrong report. Found live via a
Missing Enchants sanity check: Rubán's (Arms Warrior) own Missing Enchants
list showed "Enchant Weapon - Agility" (Hunter's real weapon-enchant id,
2564) as the recommended BiS for his Hands slot - a name that could only
have come from Hunter's own default_enchants.json, since his own file has
no such value. Root cause: `cli/gear.py`'s `cmd_best` called
`run_upgrade_sweep.main(args.character, phase, ...)` with no `profile_dir`
at all; a matching gap was already caught and fixed in `gui/api.py` before
this (see its own comment, now superseded by this shared module), but the
CLI path was never updated to match.

Computing this from identity.class/spec is still unreliable in general (a
GTCompanion-sourced identity block has no spec field at all - see
ingest/list_characters.py), so there's no way to derive a real user's own
character -> profile mapping automatically; a human has to say which
profile a given character uses.

Real, explicit split as of 2026-08-31 (code review §1.2): a REAL named
character used to be hardcoded directly in this dict (three of them, tied
to one person's real first name and real WoW realm - a privacy problem in
a public repo, and it also meant this tool only ever worked for that one
person; a second user got an empty character list with no way to fix it
short of editing source). Only the built-in SYNTHETIC test-fixture
characters (ship with the tool, prove each profile works, not personal to
anyone) stay hardcoded below. A real user's own characters are assigned
through the GUI (Api.assign_character_profile(), see gui/api.py) or by
calling local_config.set_character_profile() directly, and live in
local_config.json - outside git, per-machine, same as wow_root/
report_output_root."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
import local_config  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
PROFILES_DIR = os.path.join(REPO_ROOT, "profiles", "tbc")

# Synthetic test characters (Stage 6.3+) - no real character export exists
# for these; built via ingest/build_synthetic_character.py. Real, proven
# pipeline runs (full sweep, real report), just not real personal
# characters - safe to ship in source, unlike a real person's own roster.
# Each profile's own profile.json used to carry a `synthetic_character: true`
# flag documenting "no real player has used this spec yet, don't fully trust
# its report" - removed 2026-08-31 (per the user, real players now testing
# these specs with their own live data) after also being the ROOT CAUSE of a
# real bug: gui/api.py used to check that flag (not the character's own
# identity) to decide whether to sync real data, so a real player assigned
# to any of the 12 profiles that still had it hit a FileNotFoundError for
# her own character.json. See is_synthetic_character() below - the correct,
# permanent check for "is THIS character one of the built-in fixtures."
_SYNTHETIC_CHARACTERS = {
    "Test-Elemental-Synthetic": "elemental_shaman",
    "Test-Enhancement-Synthetic": "enhancement_shaman",
    "Test-Beastmastery-Synthetic": "beastmastery_hunter",
    "Test-Fury-Synthetic": "fury_warrior",
    "Test-FeralCat-Synthetic": "feral_cat_druid",
    "Test-CombatRogue-Synthetic": "combat_rogue",
    "Test-ShadowPriest-Synthetic": "shadow_priest",
    "Test-ArcaneMage-Synthetic": "arcane_mage",
    "Test-RetPaladin-Synthetic": "retribution_paladin",
    "Test-Affliction-Synthetic": "affliction_warlock",
    "Test-Demonology-Synthetic": "demonology_warlock",
    "Test-Destruction-Synthetic": "destruction_warlock",
}


def _profile_dir(dir_name: str) -> str:
    return os.path.join(PROFILES_DIR, dir_name)


def is_synthetic_character(name_realm: str) -> bool:
    """True only for the built-in synthetic test-fixture characters above -
    never true for a real user's own character, even one assigned to a
    profile whose own profile.json still carries a historical
    `synthetic_character: true` flag. Real bug found and fixed 2026-08-31:
    that flag describes the PROFILE's own original validation data (e.g.
    elemental_shaman was built and verified only against
    Test-Elemental-Synthetic before any real Elemental Shaman player
    existed), not "every character assigned to this profile is fake" -
    gui/api.py's _run_report_job() used to check the profile's flag
    directly, so a real character assigned to a profile that still carries
    it (nothing yet clears it once a real player starts using that spec)
    skipped syncing her own real data and hit a FileNotFoundError for her
    own character.json, which is never pre-built for a real character the
    way it is for the built-in fixtures."""
    return name_realm in _SYNTHETIC_CHARACTERS


def available_profiles() -> list[dict]:
    """Every real, buildable profile under profiles/tbc/ - {dir_name, label,
    class}, label derived from the profile's own real class/spec fields
    (never hand-maintained, so a new profile shows up here automatically).
    `class` (the profile's own real lowercase class name, e.g. "shaman") is
    included so the GUI's "assign a profile to this character" dropdown can
    filter to profiles matching the character's own detected class -
    real bug found and fixed 2026-08-31: without it, every real profile
    (all 15, any class) was offered for every character, so a real Shaman
    could be assigned an Affliction Warlock profile and nothing would ever
    catch it."""
    result = []
    for dir_name in sorted(os.listdir(PROFILES_DIR)):
        profile_path = os.path.join(PROFILES_DIR, dir_name, "profile.json")
        if not os.path.isfile(profile_path):
            continue
        with open(profile_path, encoding="utf-8") as f:
            p = json.load(f)
        class_name = p.get("class", "")
        spec_label = p.get("spec", dir_name).replace("_", " ").title()
        class_label = class_name.title()
        result.append({"dir_name": dir_name, "label": f"{spec_label} {class_label}".strip(),
                        "class": class_name.lower()})
    return result


def _compute() -> dict:
    result = {name: _profile_dir(dir_name) for name, dir_name in _SYNTHETIC_CHARACTERS.items()}
    for name_realm, dir_name in local_config.character_profile_overrides().items():
        result[name_realm] = _profile_dir(dir_name)
    return result


SUPPORTED_CHARACTERS: dict[str, str] = {}


def refresh() -> None:
    """Recomputes SUPPORTED_CHARACTERS IN PLACE (mutates the existing dict
    object via clear()+update(), never reassigns the name to a new dict) -
    gui/api.py holds its own `SUPPORTED_CHARACTERS = character_profiles.
    SUPPORTED_CHARACTERS` alias from import time; reassigning this module's
    own attribute to a fresh dict object would leave that alias pointing at
    the old, stale one. Call this after assign_character_profile() so a
    newly-assigned character is usable immediately in the same running
    process, not just after a restart."""
    SUPPORTED_CHARACTERS.clear()
    SUPPORTED_CHARACTERS.update(_compute())


refresh()
