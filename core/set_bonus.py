"""Set-aware loot verdicts: a tier piece can be a downgrade to equip alone
today while still being correct to take from the raid, because it's on the
path to a package that IS an upgrade. Splits "equip now" from "bank it" per
the user's ask, and checks partial completion (2 of 4 pieces, not just
0-vs-4) since a mid-transition state might already be worth wearing.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ITEM_SETS_GO = os.path.join(REPO_ROOT, "sim", "tbc-new", "sim", "hunter", "item_sets.go")
STAT_VECTOR_LEN = 42

_thresholds_cache: dict[str, list[int]] | None = None


def set_bonus_thresholds() -> dict[str, list[int]]:
    """Real bonus threshold piece counts per set name, parsed directly from
    the vendored sim's own Go source - never guessed. db.json has no
    separate table for this (setId/setName only on each item), so the Go
    source (sim/hunter/item_sets.go's `Bonuses: map[int32]core.ApplySetBonus{
    2: func(...){...}, 4: func(...){...} }` per set) is the only real
    source. Verified against a live in-game tooltip once (Rift Stalker
    Armor: 2/4, matching exactly)."""
    global _thresholds_cache
    if _thresholds_cache is not None:
        return _thresholds_cache
    text = open(ITEM_SETS_GO, encoding="utf-8").read()
    result = {}
    for m in re.finditer(r'Name:\s*"([^"]+)".*?Bonuses:\s*map\[int32\]core\.ApplySetBonus\{(.*?)\n\t\},',
                          text, re.DOTALL):
        set_name = m.group(1)
        body = m.group(2)
        thresholds = sorted(int(x) for x in re.findall(r'\n\t\t(\d+):\s*func\(agent core\.Agent', body))
        if thresholds:
            result[set_name] = thresholds
    _thresholds_cache = result
    return result


def item_stat_vector(item_id: int | None, gems: list[int] | None) -> list[float]:
    """Full 42-element stat vector (same indexing as bonusStats.stats and
    a gem's own stats array) for one item PLUS its socketed gems - real
    numbers straight from the DB. Used to build a bonusStats correction
    that exactly cancels a swap's own raw stat contribution, isolating a
    set bonus's behavioral effect (a proc, a spell mod) from any stat
    difference the swap itself would otherwise introduce."""
    vec = [0.0] * STAT_VECTOR_LEN
    if item_id:
        item = idb.by_id(item_id)
        if item:
            for k, v in item.get("scalingOptions", {}).get("0", {}).get("stats", {}).items():
                idx = int(k)
                if idx < STAT_VECTOR_LEN:
                    vec[idx] += v
    for gem_id in (gems or []):
        if not gem_id:
            continue
        gem = idb.gem_by_id(gem_id)
        if gem:
            for i, v in enumerate(gem.get("stats", [])):
                if i < STAT_VECTOR_LEN:
                    vec[i] += v
    return vec


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


def isolate_bonus_value(settings_path: str, set_name: str, threshold: int,
                         candidates: dict[str, list["opt.Candidate"]], baseline_config: list[dict],
                         iterations: int) -> dict | None:
    """Real, sim-measured value of ONE specific bonus threshold (e.g. the
    4pc bonus alone), isolated from the raw stat difference of whichever
    pieces happen to cross it - per the user: "we can manipulate stats for
    this test so baseline character stats stay the same but set bonus
    activates or deactivates." Builds two configs that differ ONLY in
    whether `threshold` real pieces of set_name are present (one has
    threshold-1, one has threshold) and applies a bonusStats correction so
    both have the SAME total character stats as true baseline - so the
    measured delta between them is the bonus's own behavioral effect (a
    proc, a spell mod) and nothing else.

    Real total piece count in the true baseline can sit above, at, or
    below threshold-1; pieces are removed (baseline already owns enough)
    or added (from pool candidates) as needed to reach exactly
    threshold-1 and exactly threshold, each with its own stat correction
    accumulated along the way. Returns None if there aren't enough real
    pieces (owned + pool) to reach `threshold` at all."""
    slot_order = gc.SLOT_ORDER
    current_slots = [s for s in slot_order
                      if (lambda e: e and e.get("id") and (idb.by_id(e["id"]) or {}).get("setName") == set_name)
                      (baseline_config[slot_order.index(s)])]
    current_count = len(current_slots)

    below_config = list(baseline_config)
    below_correction = [0.0] * STAT_VECTOR_LEN

    if current_count >= threshold:
        # Remove enough currently-equipped set pieces to land at exactly
        # threshold-1, restoring each removed piece's own stats via the
        # correction so total stats don't drop with it.
        to_remove = current_count - (threshold - 1)
        for slot in current_slots[:to_remove]:
            idx = slot_order.index(slot)
            entry = below_config[idx]
            vec = item_stat_vector(entry.get("id"), entry.get("gems"))
            below_correction = [c + v for c, v in zip(below_correction, vec)]
            below_config[idx] = {}
    else:
        # Add enough pool candidates (in unfilled, non-set slots) to reach
        # threshold-1, subtracting each added piece's own NET stat gain
        # via the correction so total stats don't rise with it.
        needed = (threshold - 1) - current_count
        available = [(slot, cand) for slot, cand in set_pieces_in_pool(set_name, candidates)
                     if slot not in current_slots]
        if len(available) < needed:
            return None  # not enough real candidates in the pool to even reach threshold-1
        for slot, cand in available[:needed]:
            idx = slot_order.index(slot)
            old_entry = below_config[idx] or {}
            old_vec = item_stat_vector(old_entry.get("id"), old_entry.get("gems"))
            new_vec = item_stat_vector(cand.item_id, cand.gems)
            below_correction = [c - (n - o) for c, n, o in zip(below_correction, new_vec, old_vec)]
            below_config[idx] = cand.as_entry()

    # "at" = "below" plus exactly one more real piece, crossing the
    # threshold, with its own additional stat correction on top.
    remaining_slots_with_set = [s for s in slot_order
                                 if (lambda e: e and e.get("id") and (idb.by_id(e["id"]) or {}).get("setName") == set_name)
                                 (below_config[slot_order.index(s)])]
    still_needed_slot = None
    if len(remaining_slots_with_set) < threshold:
        available = [(slot, cand) for slot, cand in set_pieces_in_pool(set_name, candidates)
                     if slot not in remaining_slots_with_set]
        if not available:
            return None
        still_needed_slot, still_needed_cand = available[0]

    at_config = list(below_config)
    at_correction = list(below_correction)
    if still_needed_slot is not None:
        idx = slot_order.index(still_needed_slot)
        old_entry = at_config[idx] or {}
        old_vec = item_stat_vector(old_entry.get("id"), old_entry.get("gems"))
        new_vec = item_stat_vector(still_needed_cand.item_id, still_needed_cand.gems)
        at_correction = [c - (n - o) for c, n, o in zip(at_correction, new_vec, old_vec)]
        at_config[idx] = still_needed_cand.as_entry()

    below_result = mv.valuation.evaluate(settings_path, below_config, iterations, opt.SEED,
                                          bonus_stats_override=below_correction)
    at_result = mv.valuation.evaluate(settings_path, at_config, iterations, opt.SEED,
                                       bonus_stats_override=at_correction)
    delta = at_result["combined"] - below_result["combined"]
    noise = mv.delta_noise(below_result, at_result, iterations)
    return {
        "set_name": set_name,
        "threshold": threshold,
        "isolated_value": delta,
        "noise": noise,
        "real": abs(delta) > 2 * noise,
    }


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
