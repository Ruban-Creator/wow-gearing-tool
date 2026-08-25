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
import stat_weights  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAT_VECTOR_LEN = 42

# Per-profile since Stage 6 (multi-class support) - real source path VERIFIED
# per class, never templated (Hunter and Druid both have sim/<class>/
# item_sets.go, but Warrior's set bonuses live in sim/warrior/items.go
# instead - confirmed by direct check, not assumed from either convention).
# Same "set once at startup" pattern as stat_weights.py/gear_config.py.
_active_item_sets_go: str | None = None
_thresholds_cache: dict[str, list[int]] | None = None


def set_active_item_sets_go(path: str) -> None:
    global _active_item_sets_go, _thresholds_cache
    _active_item_sets_go = path
    _thresholds_cache = None  # a different profile's source invalidates the cache


def _extract_thresholds(body: str) -> list[int]:
    # Tab depth varies: a set's own inline Bonuses map is nested one level
    # deeper (two tabs) than a top-level `var sharedFoo = map[...]{...}`
    # bonus map a set can instead reference by name (one tab) - real bug
    # found via Warrior's shared PvP-set bonus map, fixed by matching either
    # depth rather than assuming the inline-only case's fixed two tabs.
    return sorted(int(x) for x in re.findall(r'\n\t+(\d+):\s*func\(agent core\.Agent', body))


def set_bonus_thresholds() -> dict[str, list[int]]:
    """Real bonus threshold piece counts per set name, parsed directly from
    the vendored sim's own Go source - never guessed. db.json has no
    separate table for this (setId/setName only on each item), so the
    active profile's real Go source (set via set_active_item_sets_go(),
    e.g. sim/hunter/item_sets.go's `Bonuses: map[int32]core.ApplySetBonus{
    2: func(...){...}, 4: func(...){...} }` per set) is the only real
    source. Verified against a live in-game tooltip once (Rift Stalker
    Armor: 2/4, matching exactly).

    Two-stage, block-scoped parse (Stage 6.1 fix - a real bug, not
    theoretical): the original single-regex version let a non-greedy `.*?`
    between one set's "Name:" and the NEXT "Bonuses: map[...]{" literal
    ANYWHERE later in the file skip straight over sets whose own Bonuses
    is a bare variable reference (e.g. warrior/items.go's PvP sets share
    one `sharedPvpSetBonus` map instead of each having an inline one) -
    confirmed live: it silently attributed Warbringer Battlegear's real
    T4 thresholds to "Oathbound's Savage Plate Battlegear"'s name instead,
    and Warbringer Battlegear (and the PvP sets themselves) never appeared
    in the result at all. Bounding each set's own search to its own
    `core.NewItemSet(core.ItemSet{ ... })` block prevents that cross-block
    skip; a bare-identifier `Bonuses: sharedFoo,` reference is then resolved
    against that identifier's own top-level `var sharedFoo = map[int32]
    core.ApplySetBonus{...}` definition, so shared-bonus sets (real, common
    for PvP set pairs that share identical bonuses) get their real
    thresholds too, not silently dropped."""
    global _thresholds_cache
    if _thresholds_cache is not None:
        return _thresholds_cache
    if _active_item_sets_go is None:
        raise RuntimeError(
            "set_bonus.set_active_item_sets_go() was never called - a pipeline entry "
            "point must load a profile's profile.json (set_bonus_go_source) and call "
            "set_active_item_sets_go() before any set-bonus code runs."
        )
    text = open(_active_item_sets_go, encoding="utf-8").read()

    # Top-level shared bonus-map variables (var sharedFoo = map[int32]core.ApplySetBonus{...}),
    # defined OUTSIDE any NewItemSet(...) block, resolved lazily below only
    # for sets that actually reference one by name.
    shared_bonus_bodies = {
        m.group(1): m.group(2)
        for m in re.finditer(r'var (\w+)\s*=\s*map\[int32\]core\.ApplySetBonus\{(.*?)\n\}',
                              text, re.DOTALL)
    }

    # A THIRD real reference form found via Druid's own PvP sets (Stage 6.2,
    # not theoretical): `Bonuses: someFunc(46437),` - a function CALL that
    # returns a map[int32]core.ApplySetBonus, rather than a bare variable.
    # The argument (a spell id, confirmed by reading the real function body)
    # is only used inside the returned map for ExposeToAPL bookkeeping, not
    # part of the threshold key structure - so the same function body's
    # thresholds are correct regardless of which call site's argument is
    # being resolved, and don't need to be re-parsed per call.
    function_bonus_bodies = {
        m.group(1): m.group(2)
        for m in re.finditer(
            r'func (\w+)\([^)]*\)\s*map\[int32\]core\.ApplySetBonus\s*\{.*?'
            r'return map\[int32\]core\.ApplySetBonus\{(.*?)\n\t\}\n\}',
            text, re.DOTALL)
    }

    result = {}
    for block in re.finditer(r'core\.NewItemSet\(core\.ItemSet\{(.*?)\n\}\)', text, re.DOTALL):
        body = block.group(1)
        name_m = re.search(r'Name:\s*"([^"]+)"', body)
        if not name_m:
            continue
        set_name = name_m.group(1)

        inline_m = re.search(r'Bonuses:\s*map\[int32\]core\.ApplySetBonus\{(.*?)\n\t\}', body, re.DOTALL)
        if inline_m:
            thresholds = _extract_thresholds(inline_m.group(1))
        else:
            thresholds = []
            call_m = re.search(r'Bonuses:\s*(\w+)\(', body)
            if call_m and call_m.group(1) in function_bonus_bodies:
                thresholds = _extract_thresholds(function_bonus_bodies[call_m.group(1)])
            else:
                ref_m = re.search(r'Bonuses:\s*(\w+),', body)
                if ref_m and ref_m.group(1) in shared_bonus_bodies:
                    thresholds = _extract_thresholds(shared_bonus_bodies[ref_m.group(1)])

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


ARMOR_SET_SLOTS = ["head", "shoulder", "chest", "hands", "legs"]


def best_non_set_alt(slot: str, set_name: str,
                      candidates: dict[str, list["opt.Candidate"]]) -> "opt.Candidate | None":
    """Best candidate for `slot` that ISN'T part of set_name, by the same
    disclosed crude-score prefilter used elsewhere in this codebase
    (STAT_WEIGHTS) - a real, non-set alternative for a slot that currently
    holds a set piece, since leaving that slot untouched wouldn't be a
    real exclusion at all. Extracted from best_four_of_five() so other
    callers (e.g. a "what if this set weren't active" rescue check) can
    reuse it instead of re-deriving the same crude score a third time."""
    best, best_score = None, None
    for cand in candidates.get(slot, []):
        item = idb.by_id(cand.item_id) if cand.item_id else None
        if not item or item.get("setName") == set_name:
            continue
        stats = item.get("scalingOptions", {}).get("0", {}).get("stats", {})
        score = sum(stat_weights.get_active().get(k, 0) * v for k, v in stats.items())
        if best_score is None or score > best_score:
            best, best_score = cand, score
    return best


def best_four_of_five(settings_path: str, set_name: str, candidates: dict[str, list["opt.Candidate"]],
                       baseline_config: list[dict], owned_items: list[dict], iterations: int) -> dict | None:
    """Which 4 of a 5-piece armor set's slots should actually hold the set
    piece, and which slot is better left to its real BiS alternative
    instead - determined by comparing all five real 4-piece combinations
    (leave-one-slot-out) plus the full 5-piece set against real sim
    numbers, not assumed from guide convention or a fixed add-order.

    Per the user: BiS guides almost always recommend 4 of 5 tier pieces,
    occasionally all 5 (rare) or fewer (when the bonuses are weak) - the
    excluded slot keeps whatever real, non-tier item is already in
    baseline_config for it (her current gear there, which the rest of
    this pipeline has already separately confirmed/optimized), not a
    guessed alternative. Returns None if fewer than 5 of the 5 canonical
    armor slots have a real tier piece available (owned or in the pool) -
    the leave-one-out comparison isn't meaningful for an incomplete set."""
    tier_item_by_slot: dict[str, "opt.Candidate"] = {}
    for slot in ARMOR_SET_SLOTS:
        idx = gc.SLOT_ORDER.index(slot)
        owned_entry = owned_items[idx] if idx < len(owned_items) else None
        if owned_entry:
            owned_db_item = idb.by_id(owned_entry["id"])
            if owned_db_item and owned_db_item.get("setName") == set_name:
                # Real BiS enchant for the slot, not her literal current one
                # (Missing Enchants fix, 2026-08-25) - same unconditional
                # treatment as optimizer.py's build_owned_config()/
                # load_candidates().
                enchant = gc.get_active_default_enchants().get(slot, 0)
                tier_item_by_slot[slot] = opt.Candidate(
                    owned_db_item["name"], owned_entry["id"],
                    enchant, owned_entry.get("gems"))
    for slot, cand in set_pieces_in_pool(set_name, candidates):
        if slot in ARMOR_SET_SLOTS:
            tier_item_by_slot[slot] = cand  # pool entry (real gems/enchant already resolved) wins if both exist

    if len(tier_item_by_slot) < 5:
        return None

    def build_config(included_slots: frozenset[str]) -> list[dict]:
        cfg = list(baseline_config)
        for slot in ARMOR_SET_SLOTS:
            idx = gc.SLOT_ORDER.index(slot)
            if slot in included_slots:
                cfg[idx] = tier_item_by_slot[slot].as_entry()
            else:
                current = baseline_config[idx]
                current_item = idb.by_id(current["id"]) if current and current.get("id") else None
                if current_item and current_item.get("setName") == set_name:
                    alt = best_non_set_alt(slot, set_name, candidates)
                    if alt is not None:
                        cfg[idx] = alt.as_entry()
                    # else: no real non-set alternative found in the pool at
                    # all - leave the tier piece as a last resort rather
                    # than inventing a substitute; this combo's number will
                    # then honestly reflect "still 5pc effectively" for
                    # that slot, not a false 4pc claim.
        return cfg

    all_five = frozenset(ARMOR_SET_SLOTS)
    combos = {all_five: build_config(all_five)}
    for leave_out in ARMOR_SET_SLOTS:
        four = all_five - {leave_out}
        combos[four] = build_config(four)

    results = {}
    for combo_slots, cfg in combos.items():
        r = mv.valuation.evaluate(settings_path, cfg, iterations, opt.SEED)
        results[combo_slots] = r["combined"]

    best_combo = max(results, key=results.get)
    excluded = sorted(all_five - best_combo)
    return {
        "set_name": set_name,
        "best_combo_slots": sorted(best_combo),
        "excluded_slot": excluded[0] if excluded else None,
        "combined_dps": results[best_combo],
        "full_five_dps": results[all_five],
        "all_options": {tuple(sorted(k)): v for k, v in results.items()},
    }


def rescue_check(settings_path: str, candidate: "opt.Candidate", slot: str, set_name: str,
                  baseline_config: list[dict], candidates: dict[str, list["opt.Candidate"]],
                  iterations: int, seed: int) -> dict | None:
    """For a candidate that's currently a real downgrade in `slot` only
    because it breaks set_name's currently-active bonus, checks whether
    it's a real upgrade against a baseline where set_name is ALREADY
    broken elsewhere - a real, non-set alternative swapped into one of
    set_name's OTHER currently-held slots - i.e. "is this genuinely a
    strong item once the set bonus isn't in play at all."

    Per the user (2026-08-23): built specifically because the interaction
    matrix's pairwise search was too expensive to run in a reasonable time
    for this same question - Attumen's "Gloves of Dexterous Manipulation"
    is the real, validated case this exists to catch (a real +13-14 DPS
    gain once paired with a swap that already breaks the same set bonus,
    invisible if only checked against the untouched baseline). This is a
    SINGLE extra real sim call per downgrade candidate, not a combinatorial
    search over every possible pairing - deliberately not an analytical
    stat-correction estimate either (tried computing this via
    isolate_bonus_value's isolated bonus number added back to the net MV;
    a real side-by-side check showed that analytical shortcut disagreeing
    with an actual paired sim by a wide margin, so this always runs the
    real sim instead of estimating).

    Returns None if there's no other real non-set alternative available to
    break the set with (e.g. only one slot currently holds the set)."""
    slot_order = gc.SLOT_ORDER
    current_set_slots = [s for s in slot_order
                          if s != slot
                          and (lambda e: e and e.get("id") and (idb.by_id(e["id"]) or {}).get("setName") == set_name)
                          (baseline_config[slot_order.index(s)])]
    if not current_set_slots:
        return None
    other_slot = current_set_slots[0]
    alt = best_non_set_alt(other_slot, set_name, candidates)
    if alt is None:
        return None

    other_idx = slot_order.index(other_slot)
    broken_baseline = list(baseline_config)
    broken_baseline[other_idx] = alt.as_entry()
    broken_result = mv.valuation.evaluate(settings_path, broken_baseline, iterations, seed)

    slot_idx = slot_order.index(slot)
    trial = list(broken_baseline)
    trial[slot_idx] = candidate.as_entry()
    trial_result = mv.valuation.evaluate(settings_path, trial, iterations, seed)

    delta = trial_result["combined"] - broken_result["combined"]
    noise = mv.delta_noise(broken_result, trial_result, iterations)
    return {
        "mv_if_set_broken": delta,
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,
        "via_slot": other_slot,
        "via_item": alt.name,
    }


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
