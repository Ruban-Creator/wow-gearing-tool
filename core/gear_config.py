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

DEFAULT_GEM = 24028  # Delicate Living Ruby (+Agility, red) - her own established default;
# see NOTES.md, Stage 4, for why this isn't an invented EP-based gem choice.


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
