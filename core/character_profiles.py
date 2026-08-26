"""Real character -> profile_dir map, shared by every real entry point
(CLI, GUI) that runs a sweep for a specific character - moved here from
gui/api.py 2026-08-25 after a real bug: run_full_sweep_mv.main()'s
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
`run_full_sweep_mv.main(args.character, phase, ...)` with no `profile_dir`
at all; a matching gap was already caught and fixed in `gui/api.py` before
this (see its own comment, now superseded by this shared module), but the
CLI path was never updated to match.

Computing this from identity.class/spec is still unreliable in general (a
GTCompanion-sourced identity block has no spec field at all - see
ingest/list_characters.py), so this stays a literal mapping rather than
derived logic - add a line here once a new profile is proven, same as
every existing one was."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT

SUPPORTED_CHARACTERS = {
    "Lerynia-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter"),
    "Rubán-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "arms_warrior"),
    "Béarforceone-Thunderstrike": os.path.join(REPO_ROOT, "profiles", "tbc", "balance_druid"),
    # Synthetic test characters (Stage 6.3/6.4) - no real Shaman export
    # exists yet, see each profile.json's synthetic_character_note. Real,
    # proven pipeline runs (full sweep, real report), just not real
    # personal characters.
    "Test-Elemental-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "elemental_shaman"),
    "Test-Enhancement-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "enhancement_shaman"),
    "Test-Beastmastery-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "beastmastery_hunter"),
    "Test-Fury-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "fury_warrior"),
    "Test-FeralCat-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "feral_cat_druid"),
    "Test-CombatRogue-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "combat_rogue"),
    "Test-ShadowPriest-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "shadow_priest"),
    "Test-ArcaneMage-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "arcane_mage"),
    "Test-RetPaladin-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "retribution_paladin"),
    "Test-Affliction-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "affliction_warlock"),
    "Test-Demonology-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "demonology_warlock"),
    "Test-Destruction-Synthetic": os.path.join(REPO_ROOT, "profiles", "tbc", "destruction_warlock"),
}
