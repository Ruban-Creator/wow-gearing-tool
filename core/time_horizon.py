"""How long an item stays the guide's actual top pick, per the user's two
corrections to the first version of this:

1. "Cursed Vision of Sargeras is not BiS in P5... it should read BiS until
   Phase 4" - being merely LISTED in a later phase's guide (even as a
   real, usable item) isn't the interesting signal; STAYING the genuine
   top recommendation is. Cursed Vision is Phase 4's "Best Personal" (a
   real top-tier pick for one gearing route) but Phase 5's "Best Previous
   Phase Option" (explicitly a leftover, not actually recommended anymore)
   - the tag needs to reflect that it stops being BiS after Phase 4, not
   that it's technically still mentioned in Phase 5.
2. "our cloak... a Phase 2 item that will only get replaced in Phase 5,
   that's important to know" vs. "it's not important to know that tier 5
   is an alternative to tier 6, we understand that without a tag" - an old
   item staying genuinely BEST for many phases is a real, non-obvious
   finding worth surfacing; an item that was only ever a stepping-stone
   alternative (never the guide's real top pick, even now) doesn't need a
   tag at all - that's already obvious.

So the only thing tracked is bis_until_phase: the last phase (3/4/5) for
which the item's rank in that phase's reference list genuinely reads as
the top pick, not a fallback. None when it was never that (in which case
no tag is shown by the caller at all).

Phase 4 and Phase 5 reference BiS lists are treated as truth for now, per
the user - not simmed ourselves; that's later work (sim these phases
directly and find the real best set per phase).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "reference_bis")

# The user's own real character is currently in Phase 3 - CLAUDE.md's
# planned GUI phase toggle will need to change this (and the candidate
# pool's own MAX_PHASE filter in sweep_all_loot.py) to view the ledger as
# of a different "current" phase. Named here as a single constant rather
# than a scattered literal so that toggle only has to change one thing;
# not built yet, this is just keeping the seam ready.
CURRENT_PHASE = 3
FINAL_PHASE = 5  # confirmed by Phase 5's own guide text ("the fifth and final phase of TBC")
ALL_PHASES = tuple(range(CURRENT_PHASE, FINAL_PHASE + 1))

# WoW's own item-quality color language, reused here since it's already a
# shared vocabulary: green (uncommon) < blue (rare) < purple (epic) <
# orange (legendary). Purple and orange are layered, not parallel - orange
# is the rarer SUBSET of "reaches Phase 5" where the item was ALSO already
# BiS from an early phase (its own DB phase <= EARLY_ORIGIN_PHASE), per the
# user's own example: Dragonspine Trophy, a real Phase 1 drop that's never
# replaced. Purple catches every other "permanent from here on" item - a
# brand-new piece (e.g. a T6 drop) that happens to never get replaced
# still deserves recognition, just not the "spans nearly the whole
# expansion" distinction orange makes.
EARLY_ORIGIN_PHASE = 2

_phase_item_ranks_cache: dict[int, dict[str, str]] | None = None

# Rank strings that start with "Best" but explicitly signal "not actually
# the current top pick" - a temporary stepping stone within the phase
# ("Until Tier X"), a leftover from an earlier phase kept only because
# nothing better has dropped yet ("Previous Phase Option"), or a named
# runner-up presented alongside a plain "Best" in the same slot
# ("Alternative", "Second Best"). Everything else starting with "Best"
# (plain "Best", "Best Personal", "Best 6%", "Best x2", "Best Overall",
# "Best Raid Wide Increase", ...) represents a genuine top pick for at
# least one legitimate gearing route, not a fallback.
_NOT_ACTUALLY_BEST = ("until", "previous", "alternative", "second")


def _is_true_bis(rank: str) -> bool:
    r = rank.lower()
    if not r.startswith("best"):
        return False
    return not any(bad in r for bad in _NOT_ACTUALLY_BEST)


def _load_phase_item_ranks() -> dict[int, dict[str, str]]:
    """Loads whatever phase{N}_survival.json files actually exist, N from 1
    up to FINAL_PHASE - not hardcoded to (3,4,5). phase2_survival.json
    already exists (built earlier for Stage 3's candidate pool) and is
    picked up here for free; a future phase1 file would be too, with no
    code change needed, since CURRENT_PHASE won't always be 3 - per the
    user, this tool should work starting from any phase a character is
    actually in, not just the one it happened to be built during."""
    global _phase_item_ranks_cache
    if _phase_item_ranks_cache is not None:
        return _phase_item_ranks_cache
    result = {}
    for phase in range(1, FINAL_PHASE + 1):
        path = os.path.join(REF_DIR, f"phase{phase}_survival.json")
        if not os.path.exists(path):
            continue
        data = json.load(open(path, encoding="utf-8"))
        ranks = {}
        for entries in data.get("slots", {}).values():
            for e in entries:
                ranks[e["item"]] = e.get("rank", "")
        result[phase] = ranks
    _phase_item_ranks_cache = result
    return result


def lasts_until_phase(item_name: str, item_id: int | None = None) -> dict:
    """{"bis_until_phase": N or None, "final_phase": bool, "tier_color": str or None}.

    Walks CURRENT_PHASE -> ... -> FINAL_PHASE. Absence from CURRENT_PHASE's
    own table is treated as unknown, not disqualifying - the current
    phase's curated list is already known to have real completeness gaps
    (items our own sim finds as real upgrades that the guide's table just
    doesn't happen to rank), so skipping it there avoids under-claiming.
    Absence from any LATER phase's table, by contrast, is treated as "no
    longer relevant" and stops the walk - those lists are comprehensive
    per-slot rankings, so an item that's dropped out entirely really has
    been superseded. A rank that's present but fails _is_true_bis also
    stops the walk immediately (whatever phase it was true BiS through is
    already recorded).

    None means never confirmed as a genuine top pick in any list - the
    caller should show no tag at all for these, not a vague "alternative"
    label; that case was already obvious without a tag, per the user.

    tier_color follows WoW's own item-quality language, relative to
    CURRENT_PHASE (per the user - green/blue/purple/orange should still
    make sense if this tool is ever run starting from Phase 1 or 2, not
    just today's Phase 3): green (BiS for the current phase only), blue
    (one more phase), purple (two or more additional phases - in
    practice this only ever means "all the way to FINAL_PHASE", since
    there's nothing beyond it), orange (purple's condition AND the item's
    own real DB phase is <= EARLY_ORIGIN_PHASE - genuinely spans nearly
    the whole expansion, not just "permanent from wherever this run
    starts"). None when bis_until_phase is None. item_id is optional only
    so old callers don't break; passing it is what unlocks the orange
    tier - without it a FINAL_PHASE-lasting item always reads purple."""
    by_phase = _load_phase_item_ranks()
    bis_until = None
    for phase in ALL_PHASES:
        rank = by_phase.get(phase, {}).get(item_name)
        if rank is None:
            if phase == CURRENT_PHASE:
                continue
            break
        if _is_true_bis(rank):
            bis_until = phase
        else:
            break

    final_phase = bis_until == FINAL_PHASE
    tier_color = None
    if bis_until == CURRENT_PHASE:
        tier_color = "green"
    elif bis_until == CURRENT_PHASE + 1:
        tier_color = "blue"
    elif bis_until is not None and bis_until >= CURRENT_PHASE + 2:
        origin_phase = None
        if item_id is not None:
            item = idb.by_id(item_id)
            origin_phase = item.get("phase") if item else None
        tier_color = "orange" if origin_phase is not None and origin_phase <= EARLY_ORIGIN_PHASE else "purple"

    return {"bis_until_phase": bis_until, "final_phase": final_phase, "tier_color": tier_color}
