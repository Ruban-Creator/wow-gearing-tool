"""17-slot gear config: canonical representation + hashing for the sim cache.
Matches EquipmentSpec.lua's itemLayout order exactly (see NOTES.md).
"""
from __future__ import annotations

import hashlib
import json

SLOT_ORDER = [
    "head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist",
    "legs", "feet", "ring1", "ring2", "trinket1", "trinket2",
    "mainhand", "offhand", "ranged",
]

# Precomputed once (code review §2.3) - SLOT_ORDER.index(slot) is a linear
# scan; optimizer.py's greedy_sweep() called it fresh on every (slot, pass)
# iteration, up to 15 slots x 6 passes per run. Same lookup, O(1) instead.
SLOT_INDEX = {s: i for i, s in enumerate(SLOT_ORDER)}

# Per-profile since Stage 6 (multi-class support) - a pure-Agility Hunter gem is
# meaningless for a Strength Warrior or an Intellect/Spell Damage Druid. Was a flat
# module constant (32194, Delicate Crimson Spinel, +10 Agility - the gem actually
# used in Lerynia's reference BiS set, not an invented EP-based pick); now loaded
# once per pipeline run via set_active_default_gem(), same "set once at startup,
# read by many functions" pattern as stat_weights.py - get_active_default_gem()
# raises if unset rather than silently reusing whatever profile ran last.
_active_default_gem: int | None = None


def set_active_default_gem(gem_id: int) -> None:
    global _active_default_gem
    _active_default_gem = gem_id


def get_active_default_gem() -> int:
    if _active_default_gem is None:
        raise RuntimeError(
            "gear_config.set_active_default_gem() was never called - a pipeline entry "
            "point must load a profile's profile.json (primary_gem_id) and call "
            "set_active_default_gem() before any gem-choice code runs."
        )
    return _active_default_gem


# Real per-slot BiS enchant ids, same "set once, read by many functions"
# pattern as _active_default_gem above. Added 2026-08-25, per the user:
# optimizer.py used to default a non-owned candidate's enchant to whatever
# she currently has equipped in that slot - meaning an under-enchanted (or
# unenchanted) current item silently understated every candidate for that
# slot too. Real, sim-verified per-profile data (never a raw, untested
# wowsims-preset id - see core/verify_default_enchants.py) lives in each
# profile's default_enchants.json; a slot with no real verified entry
# simply isn't in the dict, and lookups fall back to 0 (no enchant) same
# as before this existed.
_active_default_enchants: dict[str, int] | None = None


def set_active_default_enchants(enchants: dict[str, int]) -> None:
    global _active_default_enchants
    _active_default_enchants = enchants


def get_active_default_enchants() -> dict[str, int]:
    if _active_default_enchants is None:
        raise RuntimeError(
            "gear_config.set_active_default_enchants() was never called - a pipeline "
            "entry point must load a profile's default_enchants.json and call "
            "set_active_default_enchants() before any enchant-choice code runs."
        )
    return _active_default_enchants


def item_entry(item_id: int, enchant: int = 0, gems: list[int] | None = None,
               variant: str | None = None) -> dict:
    """`variant` distinguishes same-item_id itemization variants (e.g. WotLK's
    10/25/heroic versions of one item) that TBC's own DB doesn't produce today -
    see CLAUDE.md's "day one" architecture rule. Always None/omitted for real TBC
    data right now; carried here so identity doesn't need retrofitting later.
    """
    entry = {"id": item_id}
    if enchant:
        entry["enchant"] = enchant
    if gems:
        entry["gems"] = gems
    if variant:
        entry["variant"] = variant
    return entry


def config_hash(items: list[dict]) -> str:
    """Stable hash of a 17-item gear config, for the sim cache key."""
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
