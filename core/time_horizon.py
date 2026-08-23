"""How long a candidate stays relevant, per the user: "lasts until Phase N" -
not the original spec's coarse three-bucket label, and no re-derivation of
cost-based "don't spend" advice (acquisition cost tracking was dropped this
session in favor of Wowhead linking).

Phase 4 and Phase 5 reference BiS lists are treated as truth for now, exactly
like the existing Phase 3 list already is - not simmed by us. A later build
is expected to sim these phases directly and find the real best set per
phase, per the user; this module is deliberately a thin, disclosed stand-in
until then, not a permanent design.

Matching is by item NAME against each list's flattened item set, the same
convention `run_full_sweep_mv.py` already uses for curated_source_text - an
exact string match, not fuzzy. A name that doesn't match anywhere (guide
wording drift, a slightly different string) fails safe: treated as "not
found in a later list" rather than asserting it lasts, since overclaiming
longevity is worse than under-claiming it.
"""
from __future__ import annotations

import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "reference_bis")

_phase_item_ranks_cache: dict[int, dict[str, str]] | None = None


def _load_phase_item_ranks() -> dict[int, dict[str, str]]:
    """phase -> {item_name: rank}. Where an item appears more than once in
    one phase's list (different slot entries, e.g. a trinket listed under
    two "Best" rows), the LAST-seen rank wins - a rare, harmless tie in
    practice since the ranks agree in every real case checked."""
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
    """{"lasts_until_phase": N, "final_phase": bool, "is_best": bool}. N is
    the highest phase (3/4/5) whose reference list still names this item
    anywhere (any rank, any slot) - not necessarily "Best", just still a
    real option; is_best reflects whether its rank AT THAT PHASE actually
    reads "Best..." (vs "Optional"/"Alternative"/"Good"/"Great" - a real
    pick, just not the top one) - per the user, a non-Best rank should
    read "alternative for Phase N", not implied to still be the top
    choice. Phase 3 is the floor (everything in the current pool is Phase
    3 or earlier by construction); an item absent from both the Phase 4
    and Phase 5 lists gets N=3, meaning it's expected to be replaced next
    phase. final_phase=True means it survives all the way to Phase 5, the
    confirmed last phase of TBC."""
    by_phase = _load_phase_item_ranks()
    last = 3
    rank = by_phase.get(3, {}).get(item_name, "")
    for phase in (4, 5):
        if item_name in by_phase.get(phase, {}):
            last = phase
            rank = by_phase[phase][item_name]
    return {"lasts_until_phase": last, "final_phase": last >= 5,
            "is_best": rank.lower().startswith("best")}
