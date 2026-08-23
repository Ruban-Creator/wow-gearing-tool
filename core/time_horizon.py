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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "reference_bis")

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
    global _phase_item_ranks_cache
    if _phase_item_ranks_cache is not None:
        return _phase_item_ranks_cache
    result = {}
    for phase in (3, 4, 5):
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


def lasts_until_phase(item_name: str) -> dict:
    """{"bis_until_phase": N or None, "final_phase": bool}.

    Walks phase 3 -> 4 -> 5. Absence from Phase 3's own table is treated
    as unknown, not disqualifying - the Phase 3 curated list is already
    known to have real completeness gaps (items our own sim finds as real
    upgrades that the guide's table just doesn't happen to rank), so
    skipping it there avoids under-claiming. Absence from Phase 4 or 5's
    table, by contrast, is treated as "no longer relevant" and stops the
    walk - those lists are comprehensive per-slot rankings, so an item
    that's dropped out entirely really has been superseded. A rank that's
    present but fails _is_true_bis also stops the walk immediately
    (whatever phase it was true BiS through is already recorded).

    None means never confirmed as a genuine top pick in any list - the
    caller should show no tag at all for these, not a vague "alternative"
    label; that case was already obvious without a tag, per the user."""
    by_phase = _load_phase_item_ranks()
    bis_until = None
    for phase in (3, 4, 5):
        rank = by_phase.get(phase, {}).get(item_name)
        if rank is None:
            if phase == 3:
                continue
            break
        if _is_true_bis(rank):
            bis_until = phase
        else:
            break
    return {"bis_until_phase": bis_until, "final_phase": bis_until == 5}
