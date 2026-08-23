"""Stage 5 (§7): the interaction matrix.

I(i, j) = MV(i, j) - MV(i) - MV(j)

MV(i, j) is the DPS gain from taking BOTH i and j at once, over the same
baseline - a real joint sim (nothing else in this tool evaluates two-item
swaps together). I(i, j) > 0 means the pair is worth MORE together than
their individual MVs would suggest (a complement - e.g. two items that each
look modest alone because neither pushes a shared threshold past the line,
but together they do). I(i, j) < 0 means the pair is worth LESS together
(a substitute - e.g. two Hit-heavy items whose combined Hit overshoots the
cap, so the second one's Hit is partly wasted once the first is worn).

Candidate selection, per the user (2026-08-23): the top 3 real-upgrade
candidates per slot (from the tiered report), PLUS any candidate beyond the
top 3 that carries nonzero Hit Rating (stat index 20) or Expertise Rating
(index 24) - these are exactly the items whose true value depends on a cap
threshold elsewhere in the set, the kind of interaction a solo MV(i) number
can't see (that's the whole reason this stage exists - see CLAUDE.md's
opening paragraph on where EP-only ranking breaks).

Two candidates in the same TRUE single-occupancy slot can't both be worn -
skipped, no I(i,j) to compute. Two candidates from the same PAIRED slot
group (ring1/ring2, trinket1/trinket2, mainhand/offhand dual-wield) CAN
both be worn at once (one per physical slot) and are real, valid, often
the MOST interesting pairs to test - not excluded.
"""
from __future__ import annotations

import concurrent.futures
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402
import set_bonus  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "tbc"))
import valuation  # noqa: E402

MAX_WORKERS = 2  # matches run_full_sweep_mv.py - see its comment for why 4 was 7.4x slower

TOP_N_PER_SLOT = 3
# proto/common.proto Stat indices - real numbers confirmed via core/stat_weights.py,
# not guessed.
HIT_STAT_IDX = 20   # MeleeHitRating
EXPERTISE_STAT_IDX = 24  # ExpertiseRating
EXTRA_STAT_INDICES = (HIT_STAT_IDX, EXPERTISE_STAT_IDX)

# Display-label slot groups where TWO different candidates can genuinely
# both be worn at once (one per physical slot) - same-slot pairs here are
# valid, unlike every other slot label where only one item can be worn.
PAIRED_SLOT_GROUPS = {"Ring", "Trinket", "Weapon"}

# A pair's screened interaction has to clear this many multiples of the
# screening-noise floor before it's worth paying for the 30k resolve -
# same logic/multiplier as marginal_value.CLEAR_MARGIN_MULTIPLE, applied
# to whether the interaction itself looks like it could be real at all.
SCREEN_GATE_MULTIPLE = 3


def select_candidates(tiers: dict, top_n: int = TOP_N_PER_SLOT,
                       extra_stat_indices: tuple[int, ...] = EXTRA_STAT_INDICES) -> list[dict]:
    """tiers is tiered_report.json's raw "tiers" dict-of-dicts
    ({tier_name: {slot_label: [item_row, ...]}}). Returns a flat,
    deduplicated list of {item_id, name, slot} for the interaction matrix's
    candidate pool."""
    by_slot: dict[str, list[dict]] = {}
    for slot_dict in tiers.values():
        for slot, items in slot_dict.items():
            by_slot.setdefault(slot, []).extend(items)

    selected: list[dict] = []
    seen_ids: set[int] = set()
    for slot, items in by_slot.items():
        items = sorted(items, key=lambda r: r["mv"], reverse=True)
        chosen = list(items[:top_n])
        chosen_ids = {r["item_id"] for r in chosen}
        for r in items[top_n:]:
            vec = set_bonus.item_stat_vector(r["item_id"], None)
            if r["item_id"] not in chosen_ids and any(vec[i] for i in extra_stat_indices):
                chosen.append(r)
                chosen_ids.add(r["item_id"])
        for r in chosen:
            if r["item_id"] in seen_ids:
                continue
            seen_ids.add(r["item_id"])
            selected.append({"item_id": r["item_id"], "name": r["name"], "slot": slot})
    return selected


def enumerate_pairs(selected: list[dict]) -> list[tuple[dict, dict]]:
    pairs = []
    for a_idx in range(len(selected)):
        for b_idx in range(a_idx + 1, len(selected)):
            a, b = selected[a_idx], selected[b_idx]
            if a["slot"] == b["slot"] and a["slot"] not in PAIRED_SLOT_GROUPS:
                continue  # true single-occupancy slot - can't wear both
            pairs.append((a, b))
    return pairs


def _best_single(settings_path: str, baseline_config: list[dict], cand: "opt.Candidate",
                  iterations: int, seed: int) -> tuple[dict, list[dict]] | tuple[None, None]:
    """Same 'try every slot this item could occupy, keep the best' logic as
    marginal_value.mv_single, but returns (raw sim result, winning trial
    config) instead of just a delta - the raw result is needed to combine
    noise across four independent sim results (see interaction noise
    below), not just two; the trial config is needed to detect set-bonus
    threshold crossings (see _threshold_notes). Cache-backed via
    valuation.evaluate's own sim_cache - if run_full_sweep_mv.py already
    resolved this exact trial at this iteration count, this is a cache hit,
    not a new sim run."""
    best = None
    best_trial = None
    for slot in mv._SLOT_HINT.get(cand.item_id, []):
        slot_idx = gc.SLOT_ORDER.index(slot)
        if opt.is_unique_conflict(baseline_config, slot_idx, cand.item_id):
            continue
        if opt.is_hand_restricted_conflict(cand.item_id, slot):
            continue
        trial = list(baseline_config)
        trial[slot_idx] = cand.as_entry()
        result = valuation.evaluate(settings_path, trial, iterations, seed)
        if best is None or result["combined"] > best["combined"]:
            best = result
            best_trial = trial
    return best, best_trial


def _best_joint(settings_path: str, baseline_config: list[dict], cand_a: "opt.Candidate",
                 cand_b: "opt.Candidate", iterations: int, seed: int) -> tuple[dict, list[dict]] | tuple[None, None]:
    """Same idea as _best_single but for two items worn simultaneously -
    tries every valid (slot_a, slot_b) combination (skipping unique/hand-
    restriction conflicts and never placing both items in the identical
    physical slot) and keeps whichever placement gives the higher DPS, i.e.
    what a real player would actually do with both items in hand.
    (None, None) if no valid simultaneous placement exists at all."""
    best = None
    best_trial = None
    slots_a = mv._SLOT_HINT.get(cand_a.item_id, [])
    slots_b = mv._SLOT_HINT.get(cand_b.item_id, [])
    for sa in slots_a:
        sa_idx = gc.SLOT_ORDER.index(sa)
        if opt.is_unique_conflict(baseline_config, sa_idx, cand_a.item_id):
            continue
        if opt.is_hand_restricted_conflict(cand_a.item_id, sa):
            continue
        for sb in slots_b:
            if sb == sa:
                continue
            sb_idx = gc.SLOT_ORDER.index(sb)
            if opt.is_unique_conflict(baseline_config, sb_idx, cand_b.item_id):
                continue
            if opt.is_hand_restricted_conflict(cand_b.item_id, sb):
                continue
            trial = list(baseline_config)
            trial[sa_idx] = cand_a.as_entry()
            trial[sb_idx] = cand_b.as_entry()
            result = valuation.evaluate(settings_path, trial, iterations, seed)
            if best is None or result["combined"] > best["combined"]:
                best = result
                best_trial = trial
    return best, best_trial


def _sem(result: dict, iterations: int) -> float:
    return mv.standard_error(result["player_stdev"], iterations)


def _sets_in_config(config: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in config:
        if not entry or not entry.get("id"):
            continue
        item = idb.by_id(entry["id"])
        if item and item.get("setName"):
            counts[item["setName"]] = counts.get(item["setName"], 0) + 1
    return counts


def _bucket(n: int, sorted_thresholds: list[int]) -> int:
    """How many of this set's thresholds a piece count clears - e.g. for
    Rift Stalker Armor's [2, 4], n=3 clears just the 2pc threshold (bucket
    1), n=4 clears both (bucket 2). Two piece counts in the SAME bucket
    have identical active-bonus tiers, even if the raw counts differ (3
    pieces and 2 pieces are both "only the 2pc bonus" for a [2,4] set) -
    that's the distinction a plain per-threshold >=/< check misses (see
    _threshold_notes)."""
    return sum(1 for th in sorted_thresholds if n >= th)


def _threshold_notes(baseline_config: list[dict], trial_a: list[dict], trial_b: list[dict],
                      trial_joint: list[dict]) -> list[str]:
    """Per the user (2026-08-23): label pairs whose interaction is actually a
    set-bonus piece-count effect, with the real threshold (2pc/4pc, whatever
    it actually is - read from the sim's own source, never guessed) instead
    of leaving the interaction looking like unexplained item synergy.

    Uses BUCKETS (how many thresholds cleared), not a naive per-threshold
    >=/< flip - a first version of this compared "did piece count cross
    4pc" directly and always saw "yes" for both alone AND together (4->3
    and 4->2 both read as "no longer >=4"), so the real distinguishing
    signal - togther drops to the SAME tier as either alone, not a lower
    one - never fired. Real example that caught this: Gronnstalker's Helmet
    + Beast Lord Handguards each drop her from Rift Stalker Armor's 4pc
    tier (bucket 2) to just the 2pc tier (bucket 1) alone; together she's
    still only at bucket 1 (2 pieces, 2pc tier), not bucket 0 - same tier
    either way, so no additional loss from combining them.

    Two distinct real cases, both worth surfacing but meaning opposite
    things:
    - Both alone already drop to a lower tier, and together doesn't drop
      any further -> the "artifact" case: the interaction number is just
      un-double-counting a shared cost, not real synergy between these two
      specific items.
    - Neither alone changes her tier, but together it does (gained or
      lost) -> a genuinely real threshold interaction, exactly what this
      stage exists to catch."""
    thresholds = set_bonus.set_bonus_thresholds()
    baseline_counts = _sets_in_config(baseline_config)
    notes = []
    for set_name, base_n in baseline_counts.items():
        ths = sorted(thresholds.get(set_name, []))
        if not ths:
            continue
        a_n = set_bonus.count_set_pieces_in_config(set_name, trial_a)
        b_n = set_bonus.count_set_pieces_in_config(set_name, trial_b)
        joint_n = set_bonus.count_set_pieces_in_config(set_name, trial_joint)
        base_bucket = _bucket(base_n, ths)
        a_bucket = _bucket(a_n, ths)
        b_bucket = _bucket(b_n, ths)
        joint_bucket = _bucket(joint_n, ths)

        if a_bucket < base_bucket and b_bucket < base_bucket and joint_bucket == min(a_bucket, b_bucket):
            lost = "/".join(f"{t}pc" for t in ths[joint_bucket:base_bucket])
            notes.append(f"{set_name} {lost} bonus: already lost by either item alone "
                         f"({base_n}->{a_n}/{b_n} pieces), not lost again together "
                         f"({base_n}->{joint_n} pieces) - not real synergy between these two items")
        elif a_bucket == base_bucket and b_bucket == base_bucket and joint_bucket < base_bucket:
            lost = "/".join(f"{t}pc" for t in ths[joint_bucket:base_bucket])
            notes.append(f"{set_name} {lost} bonus: only lost when BOTH are taken together "
                         f"({base_n}->{joint_n} pieces) - a real threshold interaction")
        elif a_bucket == base_bucket and b_bucket == base_bucket and joint_bucket > base_bucket:
            gained = "/".join(f"{t}pc" for t in ths[base_bucket:joint_bucket])
            notes.append(f"{set_name} {gained} bonus: only gained when BOTH are taken together "
                         f"({base_n}->{joint_n} pieces) - a real threshold interaction")
        elif min(a_bucket, b_bucket) < base_bucket == max(a_bucket, b_bucket) == joint_bucket:
            # Exactly one of the two alone breaks a tier; the other backfills
            # the displaced piece when both are worn together, so the pair
            # fully restores the tier neither swap disturbs it in the end.
            # Real example: Beast Lord Cuirass alone drops Rift Stalker
            # Armor from 4pc to 3pc; Rift Stalker Leggings alone (a slot she
            # doesn't currently fill with this set) keeps it at 4pc; worn
            # together the count nets back to 4 - the bonus never actually
            # goes anywhere, so the interaction number isn't item synergy,
            # it's an accounting artifact of the swap that removes a piece
            # happening to be paired with the swap that adds one back.
            restored = "/".join(f"{t}pc" for t in ths[min(a_bucket, b_bucket):base_bucket])
            notes.append(f"{set_name} {restored} bonus: one item's swap alone would lose it, but "
                         f"the other backfills the displaced piece when both are taken together "
                         f"({base_n}->{joint_n} pieces, fully preserved) - not real synergy "
                         f"between these two specific items")
    return notes


def compute(settings_path: str, candidates_by_slot: dict, baseline_config: list[dict],
            tiers: dict, screen_iterations: int, resolve_iterations: int, seed: int) -> list[dict]:
    """Returns a list of interaction rows, sorted by |interaction| descending,
    already filtered to real (non-tied-within-noise) pairs only - 549+
    candidate pairs is far too many to report raw, and the vast majority
    have no meaningful interaction at all (unrelated slots/stats)."""
    cand_by_id = {c.item_id: c for cands in candidates_by_slot.values()
                  for c in cands if c.item_id is not None}

    selected = select_candidates(tiers)
    selected = [s for s in selected if s["item_id"] in cand_by_id]
    pairs = enumerate_pairs(selected)
    if not pairs:
        return []

    baseline_resolve = valuation.evaluate(settings_path, baseline_config, resolve_iterations, seed)
    baseline_screen = valuation.evaluate(settings_path, baseline_config, screen_iterations, seed)

    # Each selected candidate's OWN MV, resolved at the same 30k precision
    # the joint numbers will use - mostly free (cache hits): a top-3-per-
    # slot item almost always already got the 30k resolve during the main
    # sweep pass (LEADERBOARD_SIZE=8 comfortably covers every slot's real-
    # upgrade count here). Only a genuinely new hit/expertise "extra" pays
    # for a real new sim call.
    single_resolved: dict[int, dict] = {}
    single_trial: dict[int, list[dict]] = {}
    for s in selected:
        cand = cand_by_id[s["item_id"]]
        result, trial = _best_single(settings_path, baseline_config, cand, resolve_iterations, seed)
        if result is not None:
            single_resolved[s["item_id"]] = result
            single_trial[s["item_id"]] = trial

    pairs = [(a, b) for a, b in pairs if a["item_id"] in single_resolved and b["item_id"] in single_resolved]

    # --- Pass 1: screen every pair's joint config, cheap ---
    def screen_pair(pair):
        a, b = pair
        joint, _trial = _best_joint(settings_path, baseline_config, cand_by_id[a["item_id"]],
                                     cand_by_id[b["item_id"]], screen_iterations, seed)
        return a, b, joint

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        screened = list(ex.map(screen_pair, pairs))

    # --- Gate: is this pair's interaction even plausibly non-zero? ---
    to_resolve = []
    for a, b, joint in screened:
        if joint is None:
            continue  # no valid simultaneous placement (e.g. both hand-restricted to mainhand)
        mv_ij_screen = joint["combined"] - baseline_screen["combined"]
        i_resolved = single_resolved[a["item_id"]]["combined"] - baseline_resolve["combined"]
        j_resolved = single_resolved[b["item_id"]]["combined"] - baseline_resolve["combined"]
        interaction_screen = mv_ij_screen - i_resolved - j_resolved
        gate_noise = math.sqrt(_sem(joint, screen_iterations) ** 2 + _sem(baseline_screen, screen_iterations) ** 2)
        if abs(interaction_screen) >= SCREEN_GATE_MULTIPLE * gate_noise:
            to_resolve.append((a, b))

    # --- Pass 2: resolve only the pairs that cleared the gate ---
    def resolve_pair(pair):
        a, b = pair
        cand_a, cand_b = cand_by_id[a["item_id"]], cand_by_id[b["item_id"]]
        joint, trial = _best_joint(settings_path, baseline_config, cand_a, cand_b, resolve_iterations, seed)
        return a, b, joint, trial

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        resolved = list(ex.map(resolve_pair, to_resolve))

    rows = []
    for a, b, joint, joint_trial in resolved:
        if joint is None:
            continue
        i_result = single_resolved[a["item_id"]]
        j_result = single_resolved[b["item_id"]]
        mv_a = i_result["combined"] - baseline_resolve["combined"]
        mv_b = j_result["combined"] - baseline_resolve["combined"]
        mv_joint = joint["combined"] - baseline_resolve["combined"]
        interaction = mv_joint - mv_a - mv_b
        # I = joint - i - j + baseline (algebraically, the baseline term
        # appears three times and cancels to one) - four independent
        # 30k-iteration sim results, each contributing its own SEM.
        noise = math.sqrt(_sem(joint, resolve_iterations) ** 2 + _sem(i_result, resolve_iterations) ** 2
                           + _sem(j_result, resolve_iterations) ** 2 + _sem(baseline_resolve, resolve_iterations) ** 2)
        tied = abs(interaction) < 2 * noise
        if tied:
            continue  # noise-honesty: not a real interaction, don't report it as one
        notes = _threshold_notes(baseline_config, single_trial[a["item_id"]], single_trial[b["item_id"]], joint_trial)
        # "complement"/"substitute" imply an actionable recommendation
        # ("pursue this pairing" / "don't"), which is exactly wrong for a
        # set_notes row - per the user, a row explained by a shared
        # set-bonus cost isn't item synergy at all, it's an accounting
        # artifact, and calling it a "complement" reads as advice to chase
        # a pairing that means nothing. Those get a neutral "artifact"
        # kind instead; complement/substitute are reserved for pairs with
        # no set-bonus explanation, i.e. the genuinely novel ones.
        kind = "artifact" if notes else ("complement" if interaction > 0 else "substitute")
        rows.append({
            "item_a": a, "item_b": b,
            "mv_a": mv_a, "mv_b": mv_b, "mv_joint": mv_joint,
            "interaction": interaction, "noise_stdev": noise,
            "kind": kind,
            "set_notes": notes,
        })

    # Real (non-artifact) findings first, largest |interaction| within each
    # group - per the user, set-bonus artifact rows are noise, not signal,
    # and shouldn't bury the genuinely novel pairs at the bottom of the list.
    rows.sort(key=lambda r: (r["kind"] == "artifact", -abs(r["interaction"])))
    return rows
