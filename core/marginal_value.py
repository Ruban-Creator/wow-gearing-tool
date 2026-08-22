"""The actual point of this whole tool (§1): MV(i) = DPS*(P u {i}) - DPS*(P).

Not "what's the single best set" (that's optimizer.py, useful for finding
where the ceiling is) but "this specific item, is it worth it, how much" -
the question that gets asked per-drop, per-currency-spend decision. Ties
within noise are reported as ties, never silently ranked - see CLAUDE.md's
noise-honesty ground rule.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import optimizer as opt  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "tbc"))
import valuation  # noqa: E402

# Populated by set_slot_hints() from the optimizer's own pool structure, so
# mv_single only tries the slot(s) a candidate could actually occupy
# (ring1/ring2 share one pool, trinket1/trinket2 share one, mainhand/offhand
# share one) instead of guessing from item metadata.
_SLOT_HINT: dict[int, list[str]] = {}

_SHARED_SLOT_GROUPS = [("ring1", "ring2"), ("trinket1", "trinket2"), ("mainhand", "offhand")]


def set_slot_hints(candidates_by_slot: dict[str, list]):
    global _SLOT_HINT
    _SLOT_HINT = {}
    grouped_slots = {s for pair in _SHARED_SLOT_GROUPS for s in pair}
    for slot, cands in candidates_by_slot.items():
        for c in cands:
            if c.item_id is None:
                continue
            if slot in grouped_slots:
                pair = next(p for p in _SHARED_SLOT_GROUPS if slot in p)
                _SLOT_HINT.setdefault(c.item_id, list(pair))
            else:
                _SLOT_HINT.setdefault(c.item_id, [slot])


def standard_error(player_stdev: float, iterations: int) -> float:
    """The sim's player_stdev is the spread across INDIVIDUAL simulated
    fights, not the uncertainty on the reported average - conflating the
    two was a real bug here (it made a 30k-iteration average look as noisy
    as a single fight, so almost everything read as 'tied'). The standard
    error of the mean is stdev/sqrt(n)."""
    return player_stdev / math.sqrt(iterations)


def delta_noise(baseline_result: dict, candidate_result: dict, iterations: int) -> float:
    """Two independent 30k-iteration Monte Carlo estimates being compared -
    their SEMs combine as sqrt(SEM_a^2 + SEM_b^2)."""
    sem_a = standard_error(baseline_result["player_stdev"], iterations)
    sem_b = standard_error(candidate_result["player_stdev"], iterations)
    return math.sqrt(sem_a**2 + sem_b**2)


def mv_single(settings_path: str, baseline_config: list[dict], candidate: "opt.Candidate",
              baseline_result: dict, iterations: int, seed: int = opt.SEED) -> dict:
    """MV of swapping ONE candidate into baseline_config's matching slot(s).
    For shared-pool items (rings/trinkets/weapons), tries every slot the
    item could occupy and reports whichever gives the bigger DPS gain -
    that's what a real player would actually do with it."""
    if candidate.excluded_reason:
        return {"name": candidate.name, "excluded_reason": candidate.excluded_reason}

    slots = _SLOT_HINT.get(candidate.item_id, [])
    if not slots:
        return {"name": candidate.name, "excluded_reason": "no known slot for this item id - call set_slot_hints() first"}

    best = None
    for slot in slots:
        slot_idx = gc.SLOT_ORDER.index(slot)
        if opt.is_unique_conflict(baseline_config, slot_idx, candidate.item_id):
            continue
        trial = list(baseline_config)
        trial[slot_idx] = candidate.as_entry()
        result = valuation.evaluate(settings_path, trial, iterations, seed)
        if best is None or result["combined"] > best["combined"]:
            best = result

    if best is None:
        return {"name": candidate.name, "excluded_reason": "unique conflict in every candidate slot"}

    delta = best["combined"] - baseline_result["combined"]
    noise = delta_noise(baseline_result, best, iterations)
    return {
        "name": candidate.name,
        "mv": delta,
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,  # ~95% confidence band
        "new_combined": best["combined"],
    }


def mv_bundle(settings_path: str, baseline_config: list[dict], bundle_config: list[dict],
              baseline_result: dict, iterations: int, seed: int = opt.SEED) -> dict:
    """MV of a whole package (e.g. a set bonus) at once - for cases where no
    single item in it looks worthwhile alone, per §7's complements finding."""
    result = valuation.evaluate(settings_path, bundle_config, iterations, seed)
    delta = result["combined"] - baseline_result["combined"]
    noise = delta_noise(baseline_result, result, iterations)
    return {
        "mv": delta,
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,
        "new_combined": result["combined"],
    }
