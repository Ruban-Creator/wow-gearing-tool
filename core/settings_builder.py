"""Assembles one full sim-settings dict from real, sourced pieces - the
Stage 6 (multi-class support) replacement for hand-maintaining a static
settings_template.json per class/spec. Plain dicts only, no proto types,
per CLAUDE.md's core/ rule.

Proven by regenerating Survival Hunter's own settings_template.json from
character.json + profile.json + its real profile files and diffing against
the hand-maintained file (see core/prove_settings_builder.py) - Stage 6.0's
actual regression check, not just a design on paper.
"""
from __future__ import annotations

RACE_PREFIX = "Race"
CLASS_PREFIX = "Class"

# Fixed, class-agnostic boilerplate - confirmed real across every existing
# settings file checked this session (Lerynia's own, always the exact same
# shape regardless of class), not per-character or per-profile data.
_ZERO_STATS_42 = [0] * 42
_ZERO_PSEUDOSTATS_27 = [0] * 27
_BONUS_STATS = {"apiVersion": 14, "stats": _ZERO_STATS_42, "pseudoStats": _ZERO_PSEUDOSTATS_27}
_ITEM_SWAP = {
    "items": [{}] * 17,
    "prepullBonusStats": {"apiVersion": 14, "stats": _ZERO_STATS_42, "pseudoStats": _ZERO_PSEUDOSTATS_27},
}

# Fixed encounter - same target dummy every current profile already uses
# (180s, level-73 "Raid Target" - real armor/health/etc in its stats
# vector, not zeros, copied verbatim from the real settings file this was
# migrated from). Deliberately NOT part of any profile per CLAUDE.md's
# determinism rule - the encounter is the same regardless of who's simmed.
_ENCOUNTER = {
    "apiVersion": 14,
    "duration": 180,
    "durationVariation": 5,
    "executeProportion20": 0.2,
    "executeProportion25": 0.25,
    "executeProportion35": 0.35,
    "executeProportion45": 0.45,
    "executeProportion90": 0.9,
    "targets": [{
        "id": 31146, "name": "Raid Target", "level": 73, "mobType": "MobTypeMechanical",
        "stats": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 320, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                  54, 0, 0, 0, 7685, 0, 6070400, 0, 0, 0, 0, 0, 0, 0, 0],
        "minBaseDamage": 15113, "damageSpread": 0.5, "swingSpeed": 2, "parryHaste": True,
    }],
}


def _race_enum(race: str) -> str:
    return RACE_PREFIX + race


def _class_enum(class_name: str) -> str:
    return CLASS_PREFIX + class_name[:1].upper() + class_name[1:]


def build_settings(character: dict, profile: dict, raid_buffs_received: dict,
                    rotation: dict, class_options: dict, consumables: dict) -> dict:
    """Assembles a full settings dict.

    character: the "character" block of data/characters/<name>/character.json
      (real race/equipment/talentsString/profession1-2 - equipment must
      already be in gear_config.item_entry() shape, one entry per SLOT_ORDER
      position).
    profile: the profiles/tbc/<class>_<spec>/profile.json manifest.
    raid_buffs_received: already-MERGED (base ⊕ profile overlay) dict with
      raidBuffs/debuffs/partyBuffs/playerBuffs keys - caller does the merge,
      this function stays a dumb assembler.
    rotation: the real player.rotation-shaped dict. For Survival Hunter
      today this is extracted from the existing hand-maintained
      settings_template.json (its rotation was never sourced from a
      separate apl.json file to begin with - see profile.json's
      apl_source: null). For a new profile this needs to be a REAL
      transform of wowsims' own shipped apls/*.apl.json - that transform
      is NOT YET VERIFIED (Stage 6.1's actual work), don't assume this
      function already does it correctly for an untested class.
    class_options: the real player.<class>.options block, e.g.
      {"hunter": {"options": {...}}}.
    consumables: the real player.consumables block.
    """
    equipment = character["equipment"]
    return {
        "apiVersion": 14,
        "raidBuffs": raid_buffs_received["raidBuffs"],
        "debuffs": raid_buffs_received["debuffs"],
        "partyBuffs": raid_buffs_received["partyBuffs"],
        "player": {
            "apiVersion": 14,
            "name": "Player",
            "race": _race_enum(character["race"]),
            "class": _class_enum(profile["class"]),
            "equipment": equipment,
            "consumables": consumables,
            "bonusStats": _BONUS_STATS,
            "itemSwap": _ITEM_SWAP,
            "buffs": raid_buffs_received["playerBuffs"],
            **class_options,
            "talentsString": character["talents"],
            "profession1": character["professions"][0]["name"] if len(character["professions"]) > 0 else None,
            "profession2": character["professions"][1]["name"] if len(character["professions"]) > 1 else None,
            "cooldowns": {},
            "rotation": rotation,
            "reactionTimeMs": 100,
            "distanceFromTarget": profile.get("distance_from_target", 7),
            "healingModel": {},
        },
        "encounter": _ENCOUNTER,
    }
