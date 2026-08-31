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

# No longer baked into the reported number (see raid_ap_per_attacker below,
# per the user - report per-attacker, not a total pre-multiplied by an
# assumed raid size) - kept here as a documented reference point only.
# From §0's stated raid comp (8-10 other physical attackers), midpoint.
PHYSICAL_ATTACKER_COUNT = 9

# Populated by set_slot_hints() from the optimizer's own pool structure, so
# mv_single only tries the slot(s) a candidate could actually occupy
# (ring1/ring2 share one pool, trinket1/trinket2 share one; mainhand/offhand
# sharing one pool is real for a dual-wield profile only - see
# set_shared_slot_groups(), Stage 6) instead of guessing from item metadata.
_SLOT_HINT: dict[int, list[str]] = {}

# Ring/trinket pairing is universal (every class has 2 ring + 2 trinket
# slots); mainhand/offhand is NOT (a two_hand profile has no real offhand
# weapon pool at all - see optimizer.build_pool_key_to_slots). Defaults to
# Survival Hunter's real dual-wield shape so every existing caller's
# behavior is unchanged (Stage 6.0 regression check); a new profile calls
# set_shared_slot_groups() with its own real topology-appropriate pairs.
_BASE_SHARED_SLOT_GROUPS = [("ring1", "ring2"), ("trinket1", "trinket2")]
_SHARED_SLOT_GROUPS = _BASE_SHARED_SLOT_GROUPS + [("mainhand", "offhand")]


def set_shared_slot_groups(weapon_topology: str) -> None:
    global _SHARED_SLOT_GROUPS
    weapon_pairs = {"dual_wield": [("mainhand", "offhand")], "two_hand": [], "one_hand_plus_offhand_item": []}
    if weapon_topology not in weapon_pairs:
        raise ValueError(f"Unknown weapon_topology {weapon_topology!r}")
    _SHARED_SLOT_GROUPS = _BASE_SHARED_SLOT_GROUPS + weapon_pairs[weapon_topology]


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
              baseline_agility: float | None = None, only_slot: str | None = None) -> list[dict]:
    """MV of swapping ONE candidate into baseline_config's matching slot(s).
    Real bug found and fixed 2026-08-31 (backlog #16, live user report): for
    a shared-pool item (rings/trinkets/dual-wield weapons - occupies EITHER
    of two real slots), this used to try every real slot and report only
    whichever gave the bigger DPS gain, discarding the other trial's real
    result entirely. Since whichever of her two current items is weaker
    always gives the bigger gain, EVERY candidate's own best trial
    consistently landed on that same weaker slot - the stronger slot's
    current item could never be beaten by anything, even a candidate that
    would genuinely improve it too, because nothing ever independently
    checked. Confirmed live on real data: 22 of 22 real trinket candidates
    for one real character all resolved to the same real slot, none ever
    evaluated against the other.

    Now returns a LIST - one real, independent result per real slot tried
    (both slots for a shared-pool item, normally just one for anything
    else) - so each real slot gets its own leaderboard/achieved-BiS check
    against its own real candidates, per the user's own fix design ("we do
    not need to know the 2 best ring combination, all we have to do is make
    sure we always value rings vs ring 1 and 2 then put the higher MV value
    in our ledger"). Screening cost is unchanged (both trials were already
    being run before this fix, just discarding one) - see run_upgrade_sweep
    .py's own resolve-tier comment for the real, bounded cost this adds
    there specifically.

    only_slot restricts the loop to one specific already-known slot - used
    by the resolve tier to re-evaluate just ONE real slot's borderline
    trial at higher precision, not both (resolving a slot that already had
    a clear screening verdict would be wasted compute).

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
        return [{"name": candidate.name, "excluded_reason": candidate.excluded_reason}]

    slots = _SLOT_HINT.get(candidate.item_id, [])
    if not slots:
        return [{"name": candidate.name, "excluded_reason": "no known slot for this item id - call set_slot_hints() first"}]
    if only_slot is not None:
        slots = [s for s in slots if s == only_slot]

    results = []
    sim_error = None
    for slot in slots:
        slot_idx = gc.SLOT_ORDER.index(slot)
        if opt.is_unique_conflict(baseline_config, slot_idx, candidate.item_id):
            continue
        if opt.is_hand_restricted_conflict(candidate.item_id, slot):
            continue
        trial = list(baseline_config)
        trial[slot_idx] = candidate.as_entry()
        try:
            result = valuation.evaluate(settings_path, trial, iterations, seed)
        except RuntimeError as e:
            # Real bug found and fixed Stage 6.1 (not theoretical): some
            # items with no classAllowlist in the DB still have a per-item
            # Go effect that unconditionally type-asserts a SPECIFIC class's
            # Agent (e.g. Beast-tamer's Shoulders' hunter.Pet buff panics
            # for any non-Hunter - "interface conversion: *dps.DpsWarrior is
            # not hunter.HunterAgent"). Neither the DB nor a static
            # exclusion list can enumerate every such item ahead of time
            # (they're scattered across each class's own vendored Go
            # source, keyed by item id, not by any DB field) - so this
            # candidate is excluded, honestly, with the real error message,
            # same as any other unusable candidate, rather than one bad
            # item crashing the whole multi-candidate sweep.
            sim_error = str(e)
            continue

        delta = result["combined"] - baseline_result["combined"]
        noise = delta_noise(baseline_result, result, iterations)

        raid_ap_per_attacker = None
        if baseline_agility is not None:
            new_agility = valuation.get_agility(settings_path, trial)
            baseline_uptime = baseline_result.get("ew_uptime")
            new_uptime = result.get("ew_uptime")
            if new_agility is not None and baseline_uptime is not None and new_uptime is not None:
                # Per ONE physical attacker (count=1), not multiplied by an
                # assumed raid size - per the user: report how much
                # stronger/weaker the debuff itself gets, not a total
                # pre-multiplied by PHYSICAL_ATTACKER_COUNT's assumed 9.
                # This lets a raid lead or loot council apply their OWN
                # actual physical-attacker count (which varies week to
                # week) rather than trusting a baked-in midpoint assumption
                # in the headline number.
                base_ap = expose_weakness.raid_ap_contribution(baseline_agility, baseline_uptime, 1)
                new_ap = expose_weakness.raid_ap_contribution(new_agility, new_uptime, 1)
                raid_ap_per_attacker = new_ap - base_ap

        results.append({
            "name": candidate.name,
            "mv": delta,
            "noise_stdev": noise,
            "tied_within_noise": abs(delta) < 2 * noise,  # ~95% confidence band
            "new_combined": result["combined"],
            # Marginal AP this candidate grants to EACH of the raid's other
            # physical attackers via Expose Weakness, ON TOP OF personal DPS
            # (already inside "mv" above) - never collapsed into one number,
            # per the ground rule. Multiply by your raid's actual physical-
            # attacker count for a total. None when baseline_agility wasn't
            # supplied.
            "raid_ap_per_attacker": raid_ap_per_attacker,
            # The REAL slot (e.g. "ring1" not "Ring") THIS result applies to
            # - for a shared-pool item this is now one of potentially TWO
            # real, independent results for the same candidate (see the
            # function's own docstring for the real bug this fixes), not a
            # "best among several" winner.
            "best_slot": slot,
        })

    if not results:
        reason = f"sim error: {sim_error}" if sim_error else "unique conflict in every candidate slot"
        return [{"name": candidate.name, "excluded_reason": reason}]

    return results


SCREEN_ITERATIONS = 2000
RESOLVE_ITERATIONS = 30000
# If a candidate's screening delta is already this many multiples of the
# SCREENING noise away from zero, resolving at 30k practically never flips
# the verdict (it can only sharpen the number) - not worth the 15x compute
# cost. Generous on purpose: false "needs resolving" costs a few extra
# seconds, false "doesn't need resolving" costs an actual wrong verdict.
CLEAR_MARGIN_MULTIPLE = 8


def mv_single_tiered(settings_path: str, baseline_config: list[dict], candidate: "opt.Candidate",
                      baseline_screen: dict, baseline_resolve_cache: dict, seed: int = opt.SEED) -> list[dict]:
    """Screens at 2k iterations first; only pays for a 30k resolve pass when
    the screening result is close enough to the noise floor that resolving
    could plausibly change the verdict. Most candidates in a real pool are
    clear upgrades or clear downgrades - this is where most of the runtime
    was going for no accuracy benefit. baseline_resolve_cache is a 1-item
    dict used as a lazy cache slot so the (expensive) baseline resolve only
    ever runs once across the whole report, not once per close candidate.

    Backlog #16 (2026-08-31) - mv_single() now returns a list (one real,
    independent result per real slot a shared-pool candidate could occupy,
    see its own docstring for the real bug this fixes) - this function
    mirrors that: each real slot's screening result independently decides
    whether IT needs a resolve pass, not one shared verdict for both."""
    screened = mv_single(settings_path, baseline_config, candidate, baseline_screen, SCREEN_ITERATIONS, seed)
    if len(screened) == 1 and "excluded_reason" in screened[0]:
        return screened

    final = []
    baseline_resolve = None
    for r in screened:
        if abs(r["mv"]) >= CLEAR_MARGIN_MULTIPLE * r["noise_stdev"]:
            r["resolved"] = False
            r["iterations"] = SCREEN_ITERATIONS
            final.append(r)
            continue
        if baseline_resolve is None:
            if "value" not in baseline_resolve_cache:
                baseline_resolve_cache["value"] = valuation.evaluate(settings_path, baseline_config, RESOLVE_ITERATIONS, seed)
            baseline_resolve = baseline_resolve_cache["value"]
        resolved = mv_single(settings_path, baseline_config, candidate, baseline_resolve, RESOLVE_ITERATIONS, seed,
                              only_slot=r["best_slot"])[0]
        resolved["resolved"] = True
        resolved["iterations"] = RESOLVE_ITERATIONS
        final.append(resolved)
    return final


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
