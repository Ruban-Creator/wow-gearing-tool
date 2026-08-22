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


def set_progression(settings_path: str, set_name: str, candidates: dict[str, list["opt.Candidate"]],
                     baseline_config: list[dict], baseline_result: dict, owned_items: list[dict],
                     iterations: int) -> dict:
    """MV at each piece count from 0 up to the full set, adding pieces in a
    fixed (pool) order - NOT an exhaustive search over which specific
    pieces to add first, so this finds "how many pieces before it's worth
    it" but not necessarily the single best partial subset. Disclosed
    simplification, not hidden."""
    pieces = set_pieces_in_pool(set_name, candidates)
    if len(pieces) < 2:
        return {"set_name": set_name, "note": "fewer than 2 pieces found in the candidate pool - nothing to check"}

    progression = []
    config = list(baseline_config)
    for count in range(1, len(pieces) + 1):
        slot, cand = pieces[count - 1]
        slot_idx = gc.SLOT_ORDER.index(slot)
        config = list(config)
        config[slot_idx] = cand.as_entry()
        result = mv.valuation.evaluate(settings_path, config, iterations, opt.SEED)
        delta = result["combined"] - baseline_result["combined"]
        noise = mv.delta_noise(baseline_result, result, iterations)
        progression.append({
            "pieces_held": count,
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
