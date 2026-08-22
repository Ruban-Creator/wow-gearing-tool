"""Per-slot gap analysis: owned gear vs. a reference BiS list (§5).

Engine-agnostic in principle (dicts in, dicts out) - the TBC-specific piece
is just the reference JSON and the item DB it's resolved against, both
passed in by the caller.
"""
from __future__ import annotations

EQUIP_SLOT_ORDER = [
    "head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist",
    "legs", "feet", "ring1", "ring2", "trinket1", "trinket2",
    "mainhand", "offhand", "ranged",
]

# Maps our 17-slot equipped-item-array positions to reference-list slot keys.
# ring1/ring2 and trinket1/trinket2 both draw from the same reference "ring"/
# "trinket" pool; mainhand/offhand draw from weapon_dual_wield (this
# character dual-wields, confirmed from her actual equipped gear).
POSITION_TO_REF_SLOT = {
    "head": "head", "neck": "neck", "shoulder": "shoulder", "back": "back",
    "chest": "chest", "wrist": "wrist", "hands": "hands", "waist": "waist",
    "legs": "legs", "feet": "feet", "ring1": "ring", "ring2": "ring",
    "trinket1": "trinket", "trinket2": "trinket",
    "mainhand": "weapon_dual_wield", "offhand": "weapon_dual_wield",
    "ranged": "ranged",
}


def resolve_reference_ids(reference: dict, item_db: dict[str, int]) -> dict:
    """item_db: {item_name: item_id}. Returns the reference dict with an 'id'
    added to every entry it could resolve, and a top-level 'unresolved' list
    of item names that didn't match anything in the sim DB - never silently
    dropped."""
    unresolved = []
    for slot, entries in reference["slots"].items():
        for entry in entries:
            item_id = item_db.get(entry["item"])
            if item_id is None:
                unresolved.append(entry["item"])
            entry["id"] = item_id
    reference["unresolved"] = sorted(set(unresolved))
    return reference


def per_slot_gap(equipped_items: list[dict], reference: dict) -> list[dict]:
    """equipped_items: the 17-entry list from character.json (may include
    duplicates for ring1/ring2, trinket1/trinket2 sharing a reference pool -
    handled by just checking membership, not position, within that pool)."""
    results = []
    for position, item in zip(EQUIP_SLOT_ORDER, equipped_items):
        ref_slot = POSITION_TO_REF_SLOT[position]
        candidates = reference["slots"].get(ref_slot, [])
        owned_id = item.get("id") if item else None
        owned_name = item.get("name") if item else None

        match = next((c for c in candidates if c.get("id") == owned_id), None)
        best_rank_item = candidates[0] if candidates else None

        results.append({
            "position": position,
            "owned_id": owned_id,
            "owned_name": owned_name,
            "matches_reference_rank": match["rank"] if match else None,
            "on_reference_list_at_all": match is not None,
            "best_reference_item": best_rank_item["item"] if best_rank_item else None,
            "best_reference_rank": best_rank_item["rank"] if best_rank_item else None,
            "is_best": bool(match and best_rank_item and match["item"] == best_rank_item["item"]),
        })
    return results
