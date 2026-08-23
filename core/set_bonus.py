"""Set-aware loot verdicts: a tier piece can be a downgrade to equip alone
today while still being correct to take from the raid, because it's on the
path to a package that IS an upgrade. Splits "equip now" from "bank it" per
the user's ask, and checks partial completion (2 of 4 pieces, not just
0-vs-4) since a mid-transition state might already be worth wearing.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402


def set_pieces_in_pool(set_name: str, candidates: dict[str, list["opt.Candidate"]]) -> list[tuple[str, "opt.Candidate"]]:
    """(slot, candidate) pairs for every candidate belonging to set_name,
    across the whole pool - not just one slot."""
    out = []
    seen_ids = set()
    for slot, cands in candidates.items():
        for c in cands:
            if c.item_id is None or c.item_id in seen_ids:
                continue
            item = idb.by_id(c.item_id)
            if item and item.get("setName") == set_name:
                out.append((slot, c))
                seen_ids.add(c.item_id)
    return out


def owned_set_count(set_name: str, owned_items: list[dict]) -> int:
    count = 0
    for it in owned_items:
        if not it:
            continue
        item = idb.by_id(it["id"])
        if item and item.get("setName") == set_name:
            count += 1
    return count


def count_set_pieces_in_config(set_name: str, config: list[dict]) -> int:
    """Real total pieces of set_name actually present in a gear config -
    NOT how many pool candidates have been swapped in so far. These differ
    whenever the baseline already owns some pieces of the set (the normal
    case for a set she's already partway or fully into): swapping a pool
    candidate into a slot that already held a same-set piece doesn't change
    the total count at all, and set bonuses (2pc/4pc thresholds etc.) key
    off this real total, not off "swaps performed"."""
    count = 0
    for entry in config:
        if not entry or not entry.get("id"):
            continue
        item = idb.by_id(entry["id"])
        if item and item.get("setName") == set_name:
            count += 1
    return count


def set_progression(settings_path: str, set_name: str, candidates: dict[str, list["opt.Candidate"]],
                     baseline_config: list[dict], baseline_result: dict, owned_items: list[dict],
                     iterations: int) -> dict:
    """MV at each piece count from 0 up to the full set, adding pieces in a
    fixed (pool) order - NOT an exhaustive search over which specific
    pieces to add first, so this finds "how many pieces before it's worth
    it" but not necessarily the single best partial subset. Disclosed
    simplification, not hidden.

    `pieces_held` reports the REAL total set-piece count in each trial
    config (via count_set_pieces_in_config), not "how many pool candidates
    have been swapped so far" - those differ whenever baseline_config
    already owns some pieces of the set, which is the normal case, not an
    edge case (caught from a real report: Rift Stalker Armor's actual 4pc
    bonus - Steady Shot +5% crit, confirmed in sim/hunter/item_sets.go -
    was already active throughout the ENTIRE reported progression because
    she already owns all 4 pieces it needs, and the old count-based label
    made every step look like a flat, bonus-free stat swap since the real
    jump from 0->4 pieces happened before the reported range even starts)."""
    pieces = set_pieces_in_pool(set_name, candidates)
    if len(pieces) < 2:
        return {"set_name": set_name, "note": "fewer than 2 pieces found in the candidate pool - nothing to check"}

    progression = []
    config = list(baseline_config)
    for swap_num in range(1, len(pieces) + 1):
        slot, cand = pieces[swap_num - 1]
        slot_idx = gc.SLOT_ORDER.index(slot)
        config = list(config)
        config[slot_idx] = cand.as_entry()
        result = mv.valuation.evaluate(settings_path, config, iterations, opt.SEED)
        delta = result["combined"] - baseline_result["combined"]
        noise = mv.delta_noise(baseline_result, result, iterations)
        progression.append({
            "pieces_held": count_set_pieces_in_config(set_name, config),
            "added": cand.name,
            "mv_vs_current_gear": delta,
            "noise": noise,
            "upgrade": delta > 2 * noise,
        })

    return {
        "set_name": set_name,
        "total_pieces_in_pool": len(pieces),
        "currently_owned": owned_set_count(set_name, owned_items),
        "progression": progression,
    }


def verdict(equip_mv_result: dict, set_name: str | None, package_progression: dict | None) -> str:
    """Three-way verdict per the user's ask: equip now / bank for later / pass."""
    if equip_mv_result.get("excluded_reason"):
        return f"excluded ({equip_mv_result['excluded_reason']})"
    if not equip_mv_result.get("tied_within_noise") and equip_mv_result.get("mv", 0) > 0:
        return "EQUIP NOW"
    if set_name and package_progression and "progression" in package_progression:
        full = package_progression["progression"][-1]
        if full["upgrade"]:
            held = package_progression["currently_owned"]
            total = package_progression["total_pieces_in_pool"]
            return f"BANK - part of {set_name} ({held}/{total} held, full set +{full['mv_vs_current_gear']:.1f})"
    return "PASS"
