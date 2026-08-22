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

DEFAULT_GEM = 32194  # Delicate Crimson Spinel (+10 Agility, red, phase 3) - was 24028
# (Delicate Living Ruby, +8 Agility, phase 1) until NOTES.md's "screening conclusion was
# wrong" correction: the phase-1 gem was quietly handicapping every non-owned candidate.
# This is the gem actually used in the reference BiS set she verified on wowsims.com, not
# an invented EP-based pick - same color, same stat, strictly better, no downside.


def item_entry(item_id: int, enchant: int = 0, gems: list[int] | None = None) -> dict:
    entry = {"id": item_id}
    if enchant:
        entry["enchant"] = enchant
    if gems:
        entry["gems"] = gems
    return entry


def config_hash(items: list[dict]) -> str:
    """Stable hash of a 17-item gear config, for the sim cache key."""
    canonical = json.dumps(items, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
