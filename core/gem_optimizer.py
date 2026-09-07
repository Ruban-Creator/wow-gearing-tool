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
    regardless of phase, so _best_gem_of_color()/_best_gem_matching_any() (and therefore
    the default gem itself, see _phase_legal_default_gem()) could pick a gem that isn't
    actually obtainable yet at the report's own current phase - unlike candidate GEAR
    items, which were already phase-gated (item["phase"] <= current_phase) everywhere
    else in this pipeline. All 15 profiles' real primary_gem_id resolves to a Phase 3
    gem, so every Phase 1/2 report was affected. Filtered here, once, so every real
    caller (_best_gem_of_color, _best_gem_matching_any) is automatically phase-legal.

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


# Real, COMPLETE meta-gem activation requirements for every meta gem in the
# game - loaded from profiles/tbc/reference/meta_gem_conditions.json, itself
# transcribed verbatim from wowsims' own authoritative source
# (sim/tbc-new/ui/core/proto_utils/gems.ts's MetaGemCondition definitions -
# their real, maintained catalogue, not something worth re-deriving or
# hand-curating one entry at a time ourselves). The sim's own Go engine does
# NOT model or check this at all (ApplyMetaGemCriticalDamageEffect in
# item_effects.go applies a meta's stat bonus unconditionally, confirmed
# from source - no color-count check anywhere) - so a pure-default-gem-
# everywhere choice can silently fail a real meta's real in-game activation
# requirement even though the sim's own reported number wouldn't reflect the
# loss. Real bug found 2026-09-07: this used to be a single hand-curated
# entry (only Relentless Earthstorm Diamond, the one meta actually observed
# on a real character so far) - any OTHER real meta gem (found dynamically
# per-character via find_owned_meta_gem(), never a profile-level constant)
# silently got no enforcement at all, confirmed live for Balance Druid's own
# real meta (Chaotic Skyfire Diamond, "at least 2 Blue Gems") producing an
# all-Red gem choice that would leave her real meta inactive in game.
_META_GEM_CONDITIONS = repo_root.load_json(
    os.path.join(REPO_ROOT, "profiles", "tbc", "reference", "meta_gem_conditions.json"))
_COLOR_NAME_TO_CONST = {"red": RED, "yellow": YELLOW, "blue": BLUE}


def _best_gem_matching_any(colors: set[int]) -> int | None:
    """Best real, phase-legal gem (by crude score) whose own GEM_MATCHES
    set intersects `colors` - i.e., any gem that counts toward at least one
    of the still-missing pure colors passed in. Prefers a gem covering MORE
    of `colors` simultaneously (a hybrid satisfying two missing colors at
    once costs one socket instead of two - the same real saving
    `_best_green_gem()` already made for the one previously-hardcoded
    meta), tie-broken by crude score."""
    best_gem, best_coverage, best_score = None, -1, -1.0
    for g in _all_gems():
        coverage = len(GEM_MATCHES.get(g["color"], set()) & colors)
        if coverage == 0:
            continue
        score = _crude_score(g["stats"])
        if coverage > best_coverage or (coverage == best_coverage and score > best_score):
            best_gem, best_coverage, best_score = g["id"], coverage, score
    return best_gem


def ensure_meta_requirement(config: list[dict], equipped_items: list, meta_gem_id: int | None) -> list[dict]:
    """Swaps the fewest possible default-gem sockets to real gems so her
    actual meta gem's real in-game activation requirement is met, if it
    isn't already - using the complete, real meta-gem catalogue in
    _META_GEM_CONDITIONS (see that table's own module-level comment).
    No-op for an unknown meta gem id (never invent a requirement), a
    'compare_colors' meta (a genuinely different mechanic - "more X than Y"
    has no fixed target to swap toward the way a minimum does; none of this
    tool's own 15 profiles have hit one of these 4 real metas yet, flagged
    rather than guessed at), or if the requirement's already satisfied by
    whatever real gems already happen to be socketed.

    Real refinement, 2026-09-07 (per the user, comparing against wowsims'
    own real gem-optimizer output): when multiple default-gem sockets are
    available to swap, prefers one whose OWN native declared socket color
    is NOT pure Red - i.e., prefers converting an already-off-color socket
    (Blue/Yellow/hybrid) to the needed hybrid gem over converting a
    naturally-Red socket. This costs nothing extra (the swap's stat cost is
    the same either way - some default-gem value is unavoidably given up
    for the meta regardless of which socket), but an off-color socket is
    also more likely to be part of that same item's own real socket bonus
    color requirement, so this can incidentally keep or gain a socket bonus
    for free rather than for no reason converting a socket that was already
    correctly Red for its own bonus."""
    condition = _META_GEM_CONDITIONS.get(str(meta_gem_id))
    if not condition or condition["type"] != "min_colors":
        return config

    counts = {RED: 0, YELLOW: 0, BLUE: 0}
    for it in config:
        for gem_id in it.get("gems") or []:
            gem = idb.gem_by_id(gem_id) if gem_id else None
            if not gem:
                continue
            for pure_color in GEM_MATCHES.get(gem["color"], set()):
                if pure_color in counts:
                    counts[pure_color] += 1

    missing = {
        RED: max(0, condition["minRed"] - counts[RED]),
        YELLOW: max(0, condition["minYellow"] - counts[YELLOW]),
        BLUE: max(0, condition["minBlue"] - counts[BLUE]),
    }
    if not any(missing.values()):
        return config

    default_gem = _phase_legal_default_gem()
    default_gem_color = (idb.gem_by_id(default_gem) or {}).get("color")

    # Every currently-swappable (still-default-gemmed) real socket, tagged
    # with its own native color - off-color sockets sorted first (the real
    # refinement above).
    available = []
    for entry_idx, it in enumerate(equipped_items):
        if not it:
            continue
        item = idb.by_id(it["id"])
        sockets = item.get("gemSockets") or [] if item else []
        gems = config[entry_idx].get("gems") or []
        for socket_idx, native_color in enumerate(sockets):
            if socket_idx < len(gems) and gems[socket_idx] == default_gem:
                available.append((entry_idx, socket_idx, native_color))
    available.sort(key=lambda t: t[2] == default_gem_color)

    new_config = [dict(entry) for entry in config]
    for entry_idx, socket_idx, _native_color in available:
        still_missing = {c for c, n in missing.items() if n > 0}
        if not still_missing:
            break
        gem_id = _best_gem_matching_any(still_missing)
        if gem_id is None:
            break  # nothing real left to swap to - leave the rest as-is rather than invent one
        gem = idb.gem_by_id(gem_id)
        gems = list(new_config[entry_idx].get("gems") or [])
        gems[socket_idx] = gem_id
        new_config[entry_idx]["gems"] = gems
        for pure_color in GEM_MATCHES.get(gem["color"], set()):
            if pure_color in missing:
                missing[pure_color] = max(0, missing[pure_color] - 1)
    return new_config


def _best_gem_of_color(color: int) -> int | None:
    """Best real gem of an EXACT pure color (Red/Blue/Yellow), by the same
    crude STAT_WEIGHTS score used for _best_gem_matching_any - a legal, reasonable
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
