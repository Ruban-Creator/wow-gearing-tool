"""Gem choice for a given item's real sockets - currently just pure
Agility (gear_config.DEFAULT_GEM) in every non-meta socket, matched
position-for-position to gemSockets. Applied consistently to BOTH
non-owned candidates AND her currently-equipped items when building
baseline_config - the tool's own MV(i) = DPS*(P∪{i}) - DPS*(P) formula
means DPS*(P) is the BEST achievable from P (gems included), not
"whatever happens to be socketed right now".

Caught from a real report: the user flagged Gloves of Dexterous
Manipulation + Ranger-General's Chestguard (commonly cited P2 SV BiS) as
looking like a downgrade despite community consensus - tracing it down
found her own currently-equipped Rift Stalker Hauberk was still socketed
with the older Delicate Living Ruby (phase 1, agi 8) instead of Delicate
Crimson Spinel (phase 3, agi 10, DEFAULT_GEM) - a free re-gem she hadn't
done, silently understating her own baseline.

A "smart" version of this function existed briefly: chase an item's
socket bonus (TBC's bonuses are all-or-nothing per item - every socket
must color-match simultaneously) by picking AP/RAP/Crit hybrid gems
instead of pure Agility, whenever a crude STAT_WEIGHTS-based score said
the hybrid + bonus beat pure Agility. Real-sim-tested against Ranger-
General's Chestguard and disproven decisively: pure Agility on her
current gear scored 2701.4, her real (partly outdated) actual gems
scored 2656.0, and the "smart" bonus-chasing choice scored 2651.6 -
WORSE than even her suboptimal real gems, not better. STAT_WEIGHTS'
linear per-point weighting doesn't capture that Agility is a Hunter
multi-stat-conversion stat (RAP/Crit/Armor), so it systematically
undervalues Agility relative to flat AP/RAP stacking. Reverted rather
than guessed back into a "better" heuristic - a real fix would need each
candidate gem choice verified against the actual sim (CLAUDE.md's "never
shortcut to EP-only ranking" rule, applied to gem choice, not just item
choice), which isn't built yet. The gem catalog + color-matching helpers
below are kept as real, DB-grounded groundwork for that, just not wired
into the decision until it's proven against the sim.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import stat_weights  # noqa: E402
import time_horizon  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT

sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))
import valuation  # noqa: E402

# Real TBC gem color enum, confirmed from db.json's own gem name patterns
# (not guessed): "Blood Garnet"=Red, "Azure Moonstone"=Blue, "Golden
# Draenite"=Yellow, "Deep Peridot"=Green (Blue+Yellow hybrid), "Flame
# Spessarite"=Orange (Red+Yellow hybrid), "Shadow Draenite"=Purple
# (Red+Blue hybrid), "Sphere"=Prismatic (matches any of the three).
RED, BLUE, YELLOW, GREEN, ORANGE, PURPLE, PRISMATIC = 2, 3, 4, 5, 6, 7, 8
GEM_MATCHES = {
    RED: {RED}, BLUE: {BLUE}, YELLOW: {YELLOW},
    GREEN: {BLUE, YELLOW}, ORANGE: {RED, YELLOW}, PURPLE: {RED, BLUE},
    PRISMATIC: {RED, BLUE, YELLOW},
}

def _all_gems() -> list[dict]:
    """Real, confirmed bug fixed 2026-09-06: this used to return every gem in the DB
    regardless of phase, so _best_gem_of_color()/_best_green_gem() (and therefore the
    default gem itself, see _phase_legal_default_gem()) could pick a gem that isn't
    actually obtainable yet at the report's own current phase - unlike candidate GEAR
    items, which were already phase-gated (item["phase"] <= current_phase) everywhere
    else in this pipeline. All 15 profiles' real primary_gem_id resolves to a Phase 3
    gem, so every Phase 1/2 report was affected. Filtered here, once, so every real
    caller (_best_gem_of_color, _best_green_gem) is automatically phase-legal.

    Also excludes `unique` and `requiredProfession`-gated gems - a real, second bug
    caught while testing the phase fix itself (2026-09-06): the naive phase-only filter
    picked "Don Julio's Heart" (33133, real Phase 1, +14/+14) as Balance Druid's
    Phase 1 substitute - a unique, Jewelcrafting-only item. This function fills the
    SAME gem into every matching socket, so a unique item would be illegally
    "equipped" multiple times at once, and a profession-gated one assumes a
    profession never confirmed - same conservative principle as achievable_enchant()'s
    ring-profession gate elsewhere in this pipeline (default to NOT assuming a
    profession unless proven). Excluding both leaves real, generally-equippable gems
    like "Bright Living Ruby" (24031, +16/+16, no restrictions) - confirmed via direct
    DB query, not guessed."""
    current_phase = time_horizon.get_current_phase()
    return [g for g in idb.gems()
            if g.get("phase", 1) <= current_phase
            and not g.get("unique")
            and not g.get("requiredProfession")]


def _crude_score(stats: list[float]) -> float:
    return sum(stat_weights.get_active().get(str(i), 0) * v for i, v in enumerate(stats) if v)


def _best_gem(candidates: list[dict]) -> tuple[int, float] | None:
    best = None
    for g in candidates:
        score = _crude_score(g["stats"])
        if best is None or score > best[1]:
            best = (g["id"], score)
    return best


def _default_gem_score() -> float:
    default_gem = gc.get_active_default_gem()
    for g in _all_gems():
        if g["id"] == default_gem:
            return _crude_score(g["stats"])
    return 0.0


# Her actual meta gem. Its real in-game activation requirement - confirmed
# from the user's own in-game tooltip screenshot, not guessed (three web
# sources disagreed with each other first): "Requires at least 2 Red
# Gems / at least 2 Yellow Gems / at least 2 Blue Gems", counted across
# her WHOLE gear, not per item. The sim itself does NOT model or check
# this at all (ApplyMetaGemCriticalDamageEffect in item_effects.go applies
# the 3% crit damage bonus unconditionally, confirmed from source - no
# color-count check anywhere) - so a pure-Agility-everywhere gem choice
# would silently fail this requirement in REAL gameplay (0 Blue, 0 Yellow)
# even though the sim's own reported number wouldn't reflect the loss.
# This is specific to THIS meta gem's real requirement, not a general
# rule - a different meta gem would need its own confirmed requirement
# before this logic should apply to it.
RELENTLESS_EARTHSTORM_DIAMOND = 32409
_META_REQUIREMENT = {RELENTLESS_EARTHSTORM_DIAMOND: {RED: 2, YELLOW: 2, BLUE: 2}}


def _best_green_gem() -> int | None:
    """No pure-Agility (or even hunter-relevant AP/RAP/Crit/Hit) gem
    exists in Blue at all (checked directly against the DB - every
    quality-4 Blue gem is Stamina/Spirit/Intellect, none relevant to a
    physical DPS build), so satisfying the Blue+Yellow requirement always
    costs real stat value regardless of which gem is picked. A Green gem
    (Blue+Yellow hybrid) counts toward BOTH requirements from one socket,
    so 2 Green gems satisfy "2 Blue AND 2 Yellow" - fewer sockets given up
    than any other real combination (a pure-Yellow + pure-Blue pair would
    need one MORE socket for the same coverage, since Green counts twice)."""
    green_gems = [g for g in _all_gems() if g["color"] == GREEN]
    best = _best_gem(green_gems)
    return best[0] if best else None


def ensure_meta_requirement(config: list[dict], equipped_items: list, meta_gem_id: int | None) -> list[dict]:
    """Swaps the fewest possible pure-Agility (Red) sockets to Green gems
    so her actual meta gem's real activation requirement is met, if it
    isn't already. No-op for any meta gem other than the one confirmed
    above, and a no-op if the requirement's already satisfied by whatever
    real gems already happen to be socketed."""
    requirement = _META_REQUIREMENT.get(meta_gem_id)
    if not requirement:
        return config

    counts = {RED: 0, BLUE: 0, YELLOW: 0}
    for it in config:
        for gem_id in it.get("gems") or []:
            gem = idb.gem_by_id(gem_id) if gem_id else None
            if not gem:
                continue
            for pure_color in GEM_MATCHES.get(gem["color"], set()):
                if pure_color in counts:
                    counts[pure_color] += 1

    missing_blue = max(0, requirement.get(BLUE, 0) - counts[BLUE])
    missing_yellow = max(0, requirement.get(YELLOW, 0) - counts[YELLOW])
    swaps_needed = max(missing_blue, missing_yellow)  # one Green gem covers one of each simultaneously
    if swaps_needed == 0:
        return config

    green_gem = _best_green_gem()
    if green_gem is None:
        return config  # nothing real to swap to - leave as-is rather than invent one

    default_gem = _phase_legal_default_gem()
    new_config = [dict(entry) for entry in config]
    swapped = 0
    for entry_idx, it in enumerate(equipped_items):
        if swapped >= swaps_needed or not it:
            continue
        item = idb.by_id(it["id"])
        sockets = item.get("gemSockets") or [] if item else []
        gems = list(new_config[entry_idx].get("gems") or [])
        for socket_idx, color in enumerate(sockets):
            if swapped >= swaps_needed:
                break
            if socket_idx < len(gems) and gems[socket_idx] == default_gem:
                gems[socket_idx] = green_gem
                swapped += 1
        if gems:
            new_config[entry_idx]["gems"] = gems
    return new_config


def _best_gem_of_color(color: int) -> int | None:
    """Best real gem of an EXACT pure color (Red/Blue/Yellow), by the same
    crude STAT_WEIGHTS score used for _best_green_gem - a legal, reasonable
    representative gem for that color, not a claim that it's the objectively
    best choice. Only ever used to build ONE candidate loadout for
    verify_gem_choice to real-sim-test against pure Agility - the crude
    score never decides the final answer here, the sim does."""
    matching = [g for g in _all_gems() if g["color"] == color]
    best = _best_gem(matching)
    return best[0] if best else None


def _phase_legal_default_gem() -> int:
    """Real fix, 2026-09-06: the profile's own curated primary_gem_id (gear_config.
    get_active_default_gem()) is a single, phase-unaware value - all 15 profiles
    resolve to a real Phase 3 gem (confirmed via db.json), so using it unconditionally
    means every Phase 1/2 report computes with gear that isn't actually legal yet.
    Mechanical, DB-driven fix, not invented data: if the curated gem's own real phase
    is already legal for the current report, return it unchanged (the common case,
    Phase 3+ reports - no behavior change at all). Otherwise derive its real socket
    color and fall back to the best real, phase-legal gem of that SAME color via the
    already-trusted _best_gem_of_color() stat_weights scoring (the same function
    chase-bonus picks already use) - reusing real, existing scoring rather than
    hand-curating a "phase 1 gem"/"phase 2 gem" per profile."""
    default_gem = gc.get_active_default_gem()
    current_phase = time_horizon.get_current_phase()
    gem = idb.gem_by_id(default_gem)
    if gem is None or gem.get("phase", 1) <= current_phase:
        return default_gem
    legal = _best_gem_of_color(gem["color"])
    return legal if legal is not None else default_gem


def chase_bonus_gems_for_item(item: dict, meta_gem_id: int | None) -> list[int]:
    """The alternate candidate: color-match every non-meta socket to the
    item's OWN declared color exactly (TBC armor sockets are always pure
    Red/Blue/Yellow or Meta - never a hybrid requirement themselves, checked
    directly against every 2+ socket item in the real candidate pool), so
    the item's real socketBonus actually triggers. This is real, legal gear -
    just a specific candidate loadout, not yet a claim it's better than pure
    Agility. See verify_gem_choice for the real sim comparison that decides
    that, replacing the old STAT_WEIGHTS-based "smart" heuristic this
    function's predecessor was disproven on (NOTES.md, 2026-08-2x)."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    meta_gem = meta_gem_id if meta_gem_id is not None else 0
    gems = []
    for color in sockets:
        if color == idb.META_GEM_COLOR:
            gems.append(meta_gem)
        else:
            gems.append(_best_gem_of_color(color) or _phase_legal_default_gem())
    return gems


def verify_gem_choice(item: dict, meta_gem_id: int | None, settings_path: str,
                       baseline_config: list[dict], slot_idx: int,
                       iterations: int, seed: int) -> dict:
    """Real-sim compare pure Agility (best_gems_for_item) against the item's
    own socket-bonus-chased loadout (chase_bonus_gems_for_item), with the
    item actually equipped in slot_idx of baseline_config so its printed
    socketBonus is genuinely active. Returns whichever wins, with the real
    DPS delta and noise - never a STAT_WEIGHTS score standing in for this
    decision, per CLAUDE.md's "never shortcut to EP-only ranking" rule
    applied to gem choice specifically (see gem_optimizer.py's module
    docstring for the earlier, disproven attempt at a crude-score shortcut
    here)."""
    if not (item.get("gemSockets") or []):
        return {"applicable": False}

    pure_agility_gems = best_gems_for_item(item, meta_gem_id)
    chase_gems = chase_bonus_gems_for_item(item, meta_gem_id)
    if chase_gems == pure_agility_gems:
        return {"applicable": False}  # every socket was already Red/Meta - nothing to compare

    base_entry = dict(baseline_config[slot_idx])

    pure_config = list(baseline_config)
    pure_entry = dict(base_entry)
    pure_entry["gems"] = pure_agility_gems
    pure_config[slot_idx] = pure_entry
    pure_result = valuation.evaluate(settings_path, pure_config, iterations, seed)

    chase_config = list(baseline_config)
    chase_entry = dict(base_entry)
    chase_entry["gems"] = chase_gems
    chase_config[slot_idx] = chase_entry
    chase_result = valuation.evaluate(settings_path, chase_config, iterations, seed)

    delta = chase_result["combined"] - pure_result["combined"]
    sem_a = pure_result["player_stdev"] / (iterations ** 0.5)
    sem_b = chase_result["player_stdev"] / (iterations ** 0.5)
    noise = (sem_a ** 2 + sem_b ** 2) ** 0.5

    return {
        "applicable": True,
        "pure_agility_dps": pure_result["combined"],
        "chase_bonus_dps": chase_result["combined"],
        "delta": delta,  # positive = chasing the socket bonus wins
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,
        "winner": "chase_bonus" if delta > 0 else "pure_agility",
        "pure_agility_gems": pure_agility_gems,
        "chase_bonus_gems": chase_gems,
    }


# Real, resolved (30k-iteration) sim results from core/verify_gem_choices.py,
# 2026-08-24: pure-stat gem vs each item's own socket-bonus-chased loadout.
# Per-profile since Stage 6 (multi-class support) - this was Hunter/Agility-
# specific verified data (Survival Hunter's 37 real candidates with sockets;
# 9 had a real, resolved DPS gain from chasing their own bonus instead) and
# must never be silently assumed to apply to another class's candidate pool.
# Loaded from profiles/tbc/<class>_<spec>/chase_bonus_gems.json via
# set_active_chase_bonus_ids() (same "set once at startup" pattern as
# stat_weights.py/gear_config.py) - a new profile starts with an EMPTY set
# until verify_gem_choices.py is actually re-run against its own real
# candidate pool, never inheriting another profile's verified items.
_active_chase_bonus_ids: set[int] | None = None


def set_active_chase_bonus_ids(item_ids: set[int]) -> None:
    global _active_chase_bonus_ids
    _active_chase_bonus_ids = item_ids


def get_active_chase_bonus_ids() -> set[int]:
    if _active_chase_bonus_ids is None:
        raise RuntimeError(
            "gem_optimizer.set_active_chase_bonus_ids() was never called - a pipeline "
            "entry point must load a profile's chase_bonus_gems.json and call "
            "set_active_chase_bonus_ids() before any gem-choice code runs."
        )
    return _active_chase_bonus_ids


def best_gems_for_item(item: dict, meta_gem_id: int | None) -> list[int]:
    """Pure Agility (DEFAULT_GEM) in every non-meta socket, position-
    matched to gemSockets so a meta socket never silently loses its gem -
    EXCEPT for the small, real-sim-verified set in CHASE_BONUS_ITEM_IDS,
    where chasing the item's own socket bonus is a confirmed, resolved DPS
    win instead.

    An earlier version of this function used STAT_WEIGHTS to decide
    whether chasing an item's socket bonus (color-matching every socket,
    accepting an AP/RAP/Crit hybrid instead of pure Agility) scored higher
    than ignoring it. Real-sim-tested against Ranger-General's Chestguard
    and disproven decisively: pure Agility on her current gear scored
    2701.4, her real (partly mismatched) actual gems scored 2656.0, and the
    "smart" bonus-chasing choice scored 2651.6 - WORSE than even her
    current suboptimal gems, not better. STAT_WEIGHTS' linear per-point
    weighting doesn't capture that Agility is a Hunter multi-stat-
    conversion stat (RAP/Crit/Armor), so it systematically undervalues
    Agility relative to flat AP/RAP stacking - so the crude heuristic was
    disabled rather than guessed back into a "better" one.

    That was N=1, though - core/verify_gem_choices.py later ran the SAME
    real-sim comparison (gem_optimizer.verify_gem_choice, not STAT_WEIGHTS)
    across all 37 of her real candidates with sockets and found "pure
    Agility always wins" does NOT generalize: 9 items have a real, resolved
    (30k-iteration) DPS gain from chasing their own bonus instead. Those 9
    are CHASE_BONUS_ITEM_IDS, sourced from real per-item sim results, not a
    formula - every other item defaults to pure Agility, including every
    item never checked, since nothing broader than what was actually
    verified is ever claimed here.
    """
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    if item.get("id") in get_active_chase_bonus_ids():
        return chase_bonus_gems_for_item(item, meta_gem_id)
    meta_gem = meta_gem_id if meta_gem_id is not None else 0
    default_gem = _phase_legal_default_gem()
    return [meta_gem if color == idb.META_GEM_COLOR else default_gem for color in sockets]
