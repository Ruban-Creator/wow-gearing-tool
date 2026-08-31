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

MAX_WORKERS = 2  # matches run_upgrade_sweep.py - see its comment for why 4 was 7.4x slower

TOP_N_PER_SLOT = 3
EXTRA_SCAN_LIMIT = 7  # how far beyond TOP_N_PER_SLOT to look for Hit/Expertise
# extras - bounds pool growth for slots with a large full pool (e.g. Ranged's
# 54 real candidates) instead of scanning the entire remaining pool.
# proto/common.proto Stat indices - real numbers confirmed via core/stat_weights.py,
# not guessed.
HIT_STAT_IDX = 20   # MeleeHitRating
EXPERTISE_STAT_IDX = 24  # ExpertiseRating
EXTRA_STAT_INDICES = (HIT_STAT_IDX, EXPERTISE_STAT_IDX)

# Display-label slot groups where TWO different candidates can genuinely
# both be worn at once (one per physical slot) - same-slot pairs here are
# valid, unlike every other slot label where only one item can be worn.
PAIRED_SLOT_GROUPS = {"Ring", "Trinket", "Weapon"}

# Physical slots feeding each paired display group - used to pull her
# CURRENTLY OWNED items into the candidate pool too. Per the user
# (2026-08-23): only 2 trinkets/rings/weapons can ever be worn, so "is this
# new candidate worth it" has to be checked against what she already has in
# the OTHER slot, not just against other new candidates - a pool of only
# acquisition targets can never surface "X isn't actually better than my
# current Y" (real example: Tsunami Talisman looked like a solid pairing
# candidate until checked against her real Bloodlust Brooch, which it does
# NOT beat in trinket1).
OWNED_ANCHOR_SLOTS = {
    "Ring": ["ring1", "ring2"],
    "Trinket": ["trinket1", "trinket2"],
    "Weapon": ["mainhand", "offhand"],
}

# Three-tier funnel, per the user (2026-08-23): pre-screen very cheap to cut
# the pair list before spending even the mid-cost screen on each one. The
# pre-screen gate is deliberately more LENIENT (lower multiple) than the
# real screen gate - pre-screen noise is much higher (SEM ~sqrt(10)x worse
# than the 1000-iteration screen), so it should err toward promoting
# borderline pairs to the more precise next stage rather than dropping them
# too early on a noisy first look.
PRESCREEN_ITERATIONS = 100
PRESCREEN_GATE_MULTIPLE = 2

# A pair's screened interaction has to clear this many multiples of the
# screening-noise floor before it's worth paying for the resolve pass -
# same logic/multiplier as marginal_value.CLEAR_MARGIN_MULTIPLE, applied
# to whether the interaction itself looks like it could be real at all.
SCREEN_GATE_MULTIPLE = 3


# Every SINGLE-occupancy display slot - deliberately NOT limited to the
# classic 5 tier-armor slots (head/shoulder/chest/hands/legs). Per the user
# (2026-08-23): Phase 5 has real sets that include boots/belt/wrist too, not
# just the traditional tier pattern - hardcoding to the classic 5 would
# silently miss an active set bonus sitting on any other slot. Ring/
# Trinket/Weapon are excluded here since those are paired groups with their
# own separate owned-anchor handling (see owned_anchor_candidates), not
# single-occupancy slots.
SINGLE_OCCUPANCY_SLOT_NAMES = {
    "head": "Head", "neck": "Neck", "shoulder": "Shoulder", "back": "Back",
    "chest": "Chest", "wrist": "Wrist", "hands": "Hands", "waist": "Waist",
    "legs": "Legs", "feet": "Feet", "ranged": "Ranged",
}


def active_set_slot_labels(baseline_config: list[dict]) -> set[str]:
    """Which of her single-occupancy slot labels currently hold a piece of
    a set that's AT OR ABOVE one of its own real bonus thresholds right now
    (e.g. all 4 of Head/Shoulder/Chest/Hands for Rift Stalker Armor's 4pc,
    confirmed from her real equipped gear - never hardcoded to one set name
    OR one fixed slot list, so this still works correctly if her gear, the
    active set, or which slots that set even occupies changes in a future
    session/phase). These are exactly the slots where a candidate's SOLO
    verdict is least trustworthy - swapping any one of them alone pays the
    full cost of breaking the set, which a paired swap elsewhere might not
    actually cost twice (see _threshold_notes) or might even avoid paying
    at all (a genuine rescue)."""
    thresholds = set_bonus.set_bonus_thresholds()
    labels = set()
    for slot_name, label in SINGLE_OCCUPANCY_SLOT_NAMES.items():
        idx = gc.SLOT_ORDER.index(slot_name)
        entry = baseline_config[idx] if idx < len(baseline_config) else None
        if not entry or not entry.get("id"):
            continue
        item = idb.by_id(entry["id"])
        set_name = item.get("setName") if item else None
        ths = thresholds.get(set_name) if set_name else None
        if not ths:
            continue
        count = set_bonus.count_set_pieces_in_config(set_name, baseline_config)
        if any(count >= th for th in ths):
            labels.add(label)
    return labels


# Display slot label -> the physical SLOT_ORDER name(s) it draws from -
# needed to find what's CURRENTLY worn there (see select_candidates' owned
# Hit/Expertise check below).
DISPLAY_SLOT_TO_PHYSICAL = {
    "Head": ["head"], "Neck": ["neck"], "Shoulder": ["shoulder"], "Back": ["back"],
    "Chest": ["chest"], "Wrist": ["wrist"], "Hands": ["hands"], "Waist": ["waist"],
    "Legs": ["legs"], "Feet": ["feet"], "Ranged": ["ranged"],
    "Ring": ["ring1", "ring2"], "Trinket": ["trinket1", "trinket2"], "Weapon": ["mainhand", "offhand"],
}


def _owned_hit_exp(baseline_config: list[dict], slot_label: str, stat_indices: tuple[int, ...]) -> float:
    """Largest Hit+Expertise total currently sitting in any physical slot
    this display group maps to. A candidate with ZERO Hit/Expertise for a
    slot that currently HAS it is just as cap-relevant as one that ADDS
    Hit/Expertise where there was none - giving up Hit in one slot to gain
    it in another only works as a real strategy if both directions are
    caught, not just "does the candidate itself carry Hit/Expertise"."""
    best = 0.0
    for slot_name in DISPLAY_SLOT_TO_PHYSICAL.get(slot_label, []):
        idx = gc.SLOT_ORDER.index(slot_name)
        entry = baseline_config[idx] if idx < len(baseline_config) else None
        if not entry or not entry.get("id"):
            continue
        vec = set_bonus.item_stat_vector(entry["id"], entry.get("gems"))
        best = max(best, sum(vec[i] for i in stat_indices))
    return best


def select_candidates(by_tier_slot: dict, active_set_slots: set[str], baseline_config: list[dict],
                       top_n: int = TOP_N_PER_SLOT,
                       extra_stat_indices: tuple[int, ...] = EXTRA_STAT_INDICES) -> list[dict]:
    """by_tier_slot is run_upgrade_sweep.py's full SCREENED pool -
    {(tier, slot_label): [(Candidate, result_dict), ...]} - deliberately
    NOT the already-filtered "real upgrades only" tiered report. Per the
    user (2026-08-23): a candidate pool built only from things that already
    look like solo upgrades can never find a "rescued" pair - an item that's
    a real downgrade ALONE (because it breaks her currently-active set
    bonus, or simply because a Hit/Expertise item's extra rating looks
    wasted in isolation) but a real upgrade once paired with the right
    other swap. Real example this missed before the fix: Attumen's "Gloves
    of Dexterous Manipulation" never entered the pool at all (a solo
    downgrade, no set of its own), so the matrix could never discover it
    was a real +13-14 DPS gain once paired with a T6 shoulder swap that
    already breaks the same set bonus.

    For active_set_slots (her current set's own slots), EVERY real screened
    candidate is included, not just the top N - any of them could plausibly
    be the "other half" of a rescue. For every other slot, keeps the
    original top-N-by-mv-plus-Hit/Expertise-extras logic, but now checking
    Hit/Expertise against the FULL screened pool too (not just the already-
    filtered real-upgrade list), AND against what's currently worn there,
    not just the candidate's own stats - per the user, "giving up Hit on
    slot X to gain it on slot Y" only gets tested if the slot-X candidate
    (which typically has LESS Hit than what's currently there, not more)
    is in the pool too, not just the slot-Y candidate that adds it."""
    by_slot: dict[str, list[tuple]] = {}
    for (_tier, slot), rows in by_tier_slot.items():
        by_slot.setdefault(slot, []).extend(rows)

    selected: list[dict] = []
    seen_ids: set[int] = set()
    for slot, rows in by_slot.items():
        rows = sorted(rows, key=lambda cr: cr[1]["mv"], reverse=True)
        if slot in active_set_slots:
            # Every candidate EXCEPT ones already screened as tied-within-
            # noise (statistically indistinguishable from doing nothing) -
            # per the user, a candidate whose own solo effect is noise can't
            # be the "real downgrade" half of a rescue, and including it
            # anyway was pure wasted screen/resolve compute on pairs that
            # were never going to show anything. A REAL downgrade (even a
            # small one, as long as it's a statistically real effect) still
            # gets through - this only cuts candidates that are provably no
            # different from the status quo, not ones that are merely small.
            # Tried an EP-based cutoff here on 2026-08-23 (keep only set
            # members/Hit-Expertise carriers/candidates within
            # EP_CUTOFF_FRACTION of the slot's best) - reverted the same
            # session once real verification caught it excluding Attumen's
            # "Gloves of Dexterous Manipulation" (crude_ep 154 vs a 165
            # cutoff), the exact validated rescue this pool-gap fix exists
            # to catch. Not a tuning problem - it's a structural
            # contradiction: ANY pre-filter that scores a candidate by "how
            # good does it look alone" (EP or otherwise) will, by
            # construction, exclude exactly the items that only look good
            # in combination. Real pool reduction for these slots has to
            # come from the pair-level funnel (pre-screen/screen), which
            # tests the actual joint effect instead of a solo proxy.
            chosen = [(c, r) for c, r in rows if not r.get("tied_within_noise")]
        else:
            chosen = list(rows[:top_n])
            chosen_ids = {c.item_id for c, _r in chosen}
            owned_hit_exp = _owned_hit_exp(baseline_config, slot, extra_stat_indices)
            # Bounded scan window, not the whole remaining pool - a slot
            # like Ranged has 54 real candidates in the full screened pool,
            # and "owned_hit_exp > 0" alone (true for her current Ranged
            # weapon) would otherwise flag literally every one of them as
            # an "extra", since a candidate merely having LESS Hit/Expertise
            # than owned satisfies the check regardless of how far down the
            # ranking it sits. Capping the scan to the next EXTRA_SCAN_LIMIT
            # candidates by mv still catches "close contender, held back by
            # its Hit/Expertise trade-off" without pulling in irrelevant
            # bottom-of-the-pool items that were never going to matter.
            for c, _r in rows[top_n:top_n + EXTRA_SCAN_LIMIT]:
                vec = set_bonus.item_stat_vector(c.item_id, None)
                cand_hit_exp = sum(vec[i] for i in extra_stat_indices)
                if c.item_id not in chosen_ids and (cand_hit_exp or owned_hit_exp):
                    chosen.append((c, _r))
                    chosen_ids.add(c.item_id)
        for c, _r in chosen:
            if c.item_id in seen_ids:
                continue
            seen_ids.add(c.item_id)
            selected.append({"item_id": c.item_id, "name": c.name, "slot": slot, "owned": False})
    return selected


def owned_anchor_candidates(baseline_config: list[dict]) -> list[tuple[dict, "opt.Candidate"]]:
    """Her real currently-worn items in each paired slot group (e.g.
    Bloodlust Brooch + Hourglass of the Unraveller for Trinket), as real
    Candidate objects built from their actual id/enchant/gems in
    baseline_config - not defaults, not guessed. These aren't acquisition
    targets (she already has them), but they belong in the SAME pairwise
    pool as new candidates so a new item's value gets checked against what
    it would actually have to beat: whichever owned item stays in the other
    slot."""
    anchors = []
    for group_label, slot_names in OWNED_ANCHOR_SLOTS.items():
        for slot_name in slot_names:
            slot_idx = gc.SLOT_ORDER.index(slot_name)
            entry = baseline_config[slot_idx] if slot_idx < len(baseline_config) else None
            if not entry or not entry.get("id"):
                continue
            item = idb.by_id(entry["id"])
            if not item:
                continue
            cand = opt.Candidate(item["name"], entry["id"], entry.get("enchant", 0), entry.get("gems"))
            info = {"item_id": entry["id"], "name": item["name"], "slot": group_label, "owned": True}
            anchors.append((info, cand))
    return anchors


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
    valuation.evaluate's own sim_cache - if run_upgrade_sweep.py already
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


def compute(settings_path: str, by_tier_slot: dict, baseline_config: list[dict],
            screen_iterations: int, resolve_iterations: int, seed: int) -> list[dict]:
    """by_tier_slot is run_upgrade_sweep.py's full screened pool -
    {(tier, slot_label): [(Candidate, result_dict), ...]}, NOT the already-
    filtered "real upgrades" tiered report (see select_candidates for why).
    Returns a list of interaction rows, sorted "rescue" findings first, then
    genuinely novel complement/substitute pairs, then set-bonus artifacts
    last - already filtered to real (non-tied-within-noise) pairs only,
    since even the expanded pool's pair count is far too many to report raw
    and the vast majority have no meaningful interaction at all."""
    cand_by_id = {c.item_id: c for rows in by_tier_slot.values() for c, _r in rows}

    active_set_slots = active_set_slot_labels(baseline_config)
    selected = select_candidates(by_tier_slot, active_set_slots, baseline_config)
    selected = [s for s in selected if s["item_id"] in cand_by_id]
    print(f"Interaction matrix: active-set slots={sorted(active_set_slots)}, "
          f"{len(selected)} candidates before owned anchors")

    # Her currently-worn items in each paired slot group (Ring/Trinket/
    # Weapon) join the pool too - a new candidate's real value has to be
    # checked against what it would actually have to beat (whichever owned
    # item stays in the other slot), not just against other new candidates.
    existing_ids = {s["item_id"] for s in selected}
    for info, cand in owned_anchor_candidates(baseline_config):
        if info["item_id"] in existing_ids:
            continue
        selected.append(info)
        cand_by_id[info["item_id"]] = cand
        existing_ids.add(info["item_id"])

    pairs = enumerate_pairs(selected)
    print(f"Interaction matrix: {len(selected)} total candidates (incl. owned anchors), "
          f"{len(pairs)} pairs to screen")
    if not pairs:
        return []

    baseline_resolve = valuation.evaluate(settings_path, baseline_config, resolve_iterations, seed)
    baseline_screen = valuation.evaluate(settings_path, baseline_config, screen_iterations, seed)
    baseline_prescreen = valuation.evaluate(settings_path, baseline_config, PRESCREEN_ITERATIONS, seed)

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

    # --- Pass 0: pre-screen every pair, very cheap, to cut the pair list
    # before spending the mid-cost screen on each one ---
    def prescreen_pair(pair):
        a, b = pair
        joint, _trial = _best_joint(settings_path, baseline_config, cand_by_id[a["item_id"]],
                                     cand_by_id[b["item_id"]], PRESCREEN_ITERATIONS, seed)
        return a, b, joint

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        prescreened = list(ex.map(prescreen_pair, pairs))

    pairs = []
    for a, b, joint in prescreened:
        if joint is None:
            continue
        mv_ij_prescreen = joint["combined"] - baseline_prescreen["combined"]
        i_resolved = single_resolved[a["item_id"]]["combined"] - baseline_resolve["combined"]
        j_resolved = single_resolved[b["item_id"]]["combined"] - baseline_resolve["combined"]
        interaction_prescreen = mv_ij_prescreen - i_resolved - j_resolved
        gate_noise = math.sqrt(_sem(joint, PRESCREEN_ITERATIONS) ** 2 + _sem(baseline_prescreen, PRESCREEN_ITERATIONS) ** 2)
        if abs(interaction_prescreen) >= PRESCREEN_GATE_MULTIPLE * gate_noise:
            pairs.append((a, b))
    print(f"Pre-screen @ {PRESCREEN_ITERATIONS} iter: {len(pairs)} of {len(prescreened)} pairs promoted to full screen")

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

        # The actual headline question, per the user (2026-08-23): does the
        # PAIR end up a real upgrade even though one (or both) of the items
        # alone would have been a real downgrade? That's a "rescue" - the
        # single most actionable finding this stage can produce, and takes
        # priority over the complement/substitute/artifact framing below.
        noise_a = mv.delta_noise(baseline_resolve, i_result, resolve_iterations)
        noise_b = mv.delta_noise(baseline_resolve, j_result, resolve_iterations)
        noise_joint = mv.delta_noise(baseline_resolve, joint, resolve_iterations)
        a_real_downgrade = mv_a < 0 and abs(mv_a) >= 2 * noise_a
        b_real_downgrade = mv_b < 0 and abs(mv_b) >= 2 * noise_b
        joint_real_upgrade = mv_joint > 0 and abs(mv_joint) >= 2 * noise_joint
        rescued = joint_real_upgrade and (a_real_downgrade or b_real_downgrade)

        # "complement"/"substitute" imply an actionable recommendation
        # ("pursue this pairing" / "don't"), which is exactly wrong for a
        # set_notes row - per the user, a row explained by a shared
        # set-bonus cost isn't item synergy at all, it's an accounting
        # artifact, and calling it a "complement" reads as advice to chase
        # a pairing that means nothing. Those get a neutral "artifact"
        # kind instead; complement/substitute are reserved for pairs with
        # no set-bonus explanation, i.e. the genuinely novel ones. "rescue"
        # overrides both when it applies - it's the most useful thing this
        # stage can say, whatever else is also true about the pair.
        if rescued:
            kind = "rescue"
        elif notes:
            kind = "artifact"
        else:
            kind = "complement" if interaction > 0 else "substitute"
        rows.append({
            "item_a": a, "item_b": b,
            "mv_a": mv_a, "mv_b": mv_b, "mv_joint": mv_joint,
            "interaction": interaction, "noise_stdev": noise,
            "kind": kind,
            "rescued": rescued,
            "set_notes": notes,
        })

    # Real (non-artifact) findings first, largest |interaction| within each
    # group - per the user, set-bonus artifact rows are noise, not signal,
    # and shouldn't bury the genuinely novel pairs at the bottom of the list.
    # Rescues sort first (the actual headline finding), then real
    # complement/substitute pairs, then artifacts last.
    kind_priority = {"rescue": 0, "complement": 1, "substitute": 1, "artifact": 2}
    rows.sort(key=lambda r: (kind_priority[r["kind"]], -abs(r["interaction"])))
    return rows
