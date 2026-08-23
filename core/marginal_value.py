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
import expose_weakness  # noqa: E402

# From §0's stated raid comp (8-10 other physical attackers) - midpoint,
# already used once for the by-hand worked example in NOTES.md's Stage 2
# entry. Not re-derived or estimated here.
PHYSICAL_ATTACKER_COUNT = 9

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
              baseline_result: dict, iterations: int, seed: int = opt.SEED,
              baseline_agility: float | None = None) -> dict:
    """MV of swapping ONE candidate into baseline_config's matching slot(s).
    For shared-pool items (rings/trinkets/weapons), tries every slot the
    item could occupy and reports whichever gives the bigger DPS gain -
    that's what a real player would actually do with it.

    baseline_agility is optional and opt-in (default None): per CLAUDE.md's
    Stage 2 ground rule, personal DPS and raid AP contribution must be
    reported as two separate columns, never collapsed into one number - but
    computing it costs an extra ComputeStats call per candidate, so callers
    that don't pass baseline_agility get the exact same result as before
    (raid_ap_contribution simply comes back None, not silently computed
    wrong). Callers that DO pass it must compute it once for baseline_config
    themselves (via valuation.get_agility) and reuse it across every
    candidate call, not recompute it per candidate - it doesn't depend on
    the candidate at all."""
    if candidate.excluded_reason:
        return {"name": candidate.name, "excluded_reason": candidate.excluded_reason}

    slots = _SLOT_HINT.get(candidate.item_id, [])
    if not slots:
        return {"name": candidate.name, "excluded_reason": "no known slot for this item id - call set_slot_hints() first"}

    best = None
    best_trial = None
    for slot in slots:
        slot_idx = gc.SLOT_ORDER.index(slot)
        if opt.is_unique_conflict(baseline_config, slot_idx, candidate.item_id):
            continue
        trial = list(baseline_config)
        trial[slot_idx] = candidate.as_entry()
        result = valuation.evaluate(settings_path, trial, iterations, seed)
        if best is None or result["combined"] > best["combined"]:
            best = result
            best_trial = trial

    if best is None:
        return {"name": candidate.name, "excluded_reason": "unique conflict in every candidate slot"}

    delta = best["combined"] - baseline_result["combined"]
    noise = delta_noise(baseline_result, best, iterations)

    raid_ap_contribution = None
    if baseline_agility is not None:
        new_agility = valuation.get_agility(settings_path, best_trial)
        baseline_uptime = baseline_result.get("ew_uptime")
        new_uptime = best.get("ew_uptime")
        if new_agility is not None and baseline_uptime is not None and new_uptime is not None:
            base_ap = expose_weakness.raid_ap_contribution(baseline_agility, baseline_uptime, PHYSICAL_ATTACKER_COUNT)
            new_ap = expose_weakness.raid_ap_contribution(new_agility, new_uptime, PHYSICAL_ATTACKER_COUNT)
            raid_ap_contribution = new_ap - base_ap

    return {
        "name": candidate.name,
        "mv": delta,
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,  # ~95% confidence band
        "new_combined": best["combined"],
        # Marginal raid-wide AP this candidate grants the raid's other
        # physical attackers via Expose Weakness, ON TOP OF personal DPS
        # (already inside "mv" above) - never collapsed into one number,
        # per the ground rule. None when baseline_agility wasn't supplied.
        "raid_ap_contribution": raid_ap_contribution,
    }


SCREEN_ITERATIONS = 2000
RESOLVE_ITERATIONS = 30000
# If a candidate's screening delta is already this many multiples of the
# SCREENING noise away from zero, resolving at 30k practically never flips
# the verdict (it can only sharpen the number) - not worth the 15x compute
# cost. Generous on purpose: false "needs resolving" costs a few extra
# seconds, false "doesn't need resolving" costs an actual wrong verdict.
CLEAR_MARGIN_MULTIPLE = 8


def mv_single_tiered(settings_path: str, baseline_config: list[dict], candidate: "opt.Candidate",
                      baseline_screen: dict, baseline_resolve_cache: dict, seed: int = opt.SEED) -> dict:
    """Screens at 2k iterations first; only pays for a 30k resolve pass when
    the screening result is close enough to the noise floor that resolving
    could plausibly change the verdict. Most candidates in a real pool are
    clear upgrades or clear downgrades - this is where most of the runtime
    was going for no accuracy benefit. baseline_resolve_cache is a 1-item
    dict used as a lazy cache slot so the (expensive) baseline resolve only
    ever runs once across the whole report, not once per close candidate."""
    screen = mv_single(settings_path, baseline_config, candidate, baseline_screen, SCREEN_ITERATIONS, seed)
    if "excluded_reason" in screen:
        return screen

    if abs(screen["mv"]) >= CLEAR_MARGIN_MULTIPLE * screen["noise_stdev"]:
        screen["resolved"] = False
        screen["iterations"] = SCREEN_ITERATIONS
        return screen

    if "value" not in baseline_resolve_cache:
        baseline_resolve_cache["value"] = valuation.evaluate(settings_path, baseline_config, RESOLVE_ITERATIONS, seed)
    baseline_resolve = baseline_resolve_cache["value"]

    resolved = mv_single(settings_path, baseline_config, candidate, baseline_resolve, RESOLVE_ITERATIONS, seed)
    resolved["resolved"] = True
    resolved["iterations"] = RESOLVE_ITERATIONS
    return resolved


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
