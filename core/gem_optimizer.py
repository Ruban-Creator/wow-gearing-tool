"""Gem choice for a given item's real sockets. Applied consistently to
BOTH non-owned candidates AND her currently-equipped items when building
baseline_config - the tool's own MV(i) = DPS*(P∪{i}) - DPS*(P) formula
means DPS*(P) is the BEST achievable from P (gems included), not
"whatever happens to be socketed right now".

Current design (`best_gems_for_item()`, rebuilt 2026-09-07): a LIVE,
automatic combined score, no manual per-item curation - for any item with
sockets, compares (a) the best default gem in every socket (max raw
stats, no bonus) against (b) the best real color-matching gem in every
socket (triggers the item's own real socketBonus - TBC's socket bonuses
are all-or-nothing per item, so "chase" always means every socket at
once, never a partial/combinatorial choice) plus that bonus's own real
stat value, both scored cap-aware (see `_crude_score()`/
`set_active_capped_totals()`), and picks whichever wins.

Real history worth keeping, since it explains why this design looks the
way it does rather than something more elaborate:

1. An early "smart" version chased sockets whenever a crude STAT_WEIGHTS
   score said to, with no cap-awareness at all. Real-sim-tested against
   Ranger-General's Chestguard (Survival Hunter) and disproven
   decisively: pure Agility scored 2701.4, her real (partly outdated)
   gems scored 2656.0, the "smart" choice scored 2651.6 - WORSE than even
   her suboptimal real gems. Linear per-point weighting doesn't capture
   that Agility is a Hunter multi-stat-conversion stat (RAP/Crit/Armor) -
   a real, permanent caution about trusting crude EP scoring for
   multi-stat-conversion classes specifically, not fully solved by
   anything below.
2. A later rebuild added real-sim verification per candidate
   (`verify_gem_choice()`) feeding a hand-curated, per-profile static
   list (`chase_bonus_gems.json`) - correct for whatever had been
   checked, silently "don't chase" for everything else until a human
   re-ran the check. Dropped 2026-09-07 per the user ("a combined score
   is still better and especially future-proof compared to a static
   list") in favor of the live formula above - `verify_gem_choice()`
   remains as a real-sim AUDIT of that formula's own decisions (see its
   own docstring), not something production depends on.
3. Cap-awareness (Hit Rating past its real threshold scoring as zero
   value) was tried, reverted the same day on a self-inflicted bug (it
   was checked against the tool's own IDEALIZED baseline gear, not her
   real equipped gear, silently understating her real total), then
   restored correctly once that was found - see `_crude_score()`'s own
   module comment for the full story.

None of this claims to match wowsims.com's own real Suggest Gems tool
exactly - confirmed by the user that their tool also mis-chases sometimes
too, so parity with an imperfect reference was never the right bar.
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


# Real, capped-stat awareness for crude gem scoring. Real, confirmed
# failure mode without it: a pure Hit Rating gem scores enormous by crude
# linear weight even when every one of its points is actually worthless
# past her real hit cap - reproduced live against Pauldrons of Malorne
# (Great Lionseye, +10 Spell Hit, outscored a real +5 Spell Dmg/+4 Crit
# hybrid despite the hybrid being the actually-correct pick).
#
# This was tried once already, 2026-09-07, via a ComputeStats RPC call
# (`valuation.get_final_stats()`) - reverted the same day for TWO real
# reasons, but only one of them was actually a reason to drop the
# CONCEPT: (1) interleaving ComputeStats calls with the existing RunSim
# calls on the same pooled simserver.exe processes triggered the already-
# documented "crashes under sustained load" instability (see the
# project_bridge_exe_overhead memory) - a real, valid reason to stop
# making that RPC call, not a reason cap-awareness itself is wrong. (2)
# it "didn't fix" the Pauldrons case - but that was a self-inflicted bug,
# not a limitation of cap-awareness: the check was run against
# `baseline_config` (optimizer.build_owned_config()'s IDEALIZED gear,
# which fills any empty/uncurated socket with the profile's own default
# Spell Damage gem), not her REAL, actual equipped gear - the exact same
# "106 vs 118" mistake this file's own earlier investigation had already
# found and fixed once (her real Hit Rating, summed from her ACTUAL
# equipped items, is 118 - matching wowsims.com exactly; the idealized
# baseline understates it at 106 because it doesn't reflect what she's
# really wearing). Conflating "this specific test was wrong" with "the
# whole feature is wrong" was a real mistake, caught by the user.
#
# Fixed properly this time: hand-summed only (no RPC, no simserver.exe
# call at all - completely immune to the interleaving bug that caused the
# actual regression), computed from the character's REAL, current
# equipped gear (`set_active_capped_totals()`, called once per report/
# character with `character.json`'s own real `equipped.items` - NEVER
# `build_owned_config()`'s idealized substitute).
#
# Real constants, from the sim's own Go source, not guessed:
# - SpellHitRatingPerHitPercent/PhysicalHitRatingPerHitPercent
#   (sim/tbc-new/sim/core/base_stats_auto_gen.go) - exact rating-per-percent
#   conversion the sim itself uses.
# - The real base miss chance vs a level+3 raid boss target
#   (sim/tbc-new/sim/core/target.go's UnitLevelFloat64(...) calls -
#   BaseSpellMissChance's own last argument, 0.17, and BaseMissChance's,
#   0.08) - the standard TBC "3 levels above you" raid-boss case, matching
#   every profile's own real encounter target in this tool.
# Stat indices per proto/common.proto's real Stat enum: 12=SpellHitRating,
# 20=MeleeHitRating. Expertise (a related but structurally different
# mechanic - reduces dodge/parry chance, not miss chance, with its own
# separate real conversion) is NOT modeled here yet - a real, flagged gap.
# Real target-side hit debuffs (Totem of Wrath +3%, Misery +3%) also
# reduce effective miss chance on top of gear-based Hit Rating - not
# modeled here either, so this threshold is slightly more generous
# (understates how capped a character really is) than her true in-raid
# cap - a real, flagged approximation that makes this check too
# PERMISSIVE if anything, never too aggressive.
SPELL_HIT_RATING_PER_PERCENT = 12.615385
MELEE_HIT_RATING_PER_PERCENT = 15.769233
SPELL_HIT_STAT_IDX = 12
MELEE_HIT_STAT_IDX = 20
_CAP_RATING = {
    SPELL_HIT_STAT_IDX: 17.0 * SPELL_HIT_RATING_PER_PERCENT,   # ~214.5 rating
    MELEE_HIT_STAT_IDX: 8.0 * MELEE_HIT_RATING_PER_PERCENT,    # ~126.2 rating
}
# Empty dict = "no cap data yet" = no discount applied (never divide-by-
# zero or crash a caller that hasn't set this up) - a pipeline entry point
# MUST call set_active_capped_totals() with the character's real equipped
# gear before any gem-choice code runs, same "set once at startup"
# convention as stat_weights.py/gear_config.py.
_active_capped_totals: dict[int, float] = {}


def set_active_capped_totals(real_equipped_items: list) -> None:
    """Hand-summed total rating per capped stat (see _CAP_RATING) from the
    character's REAL, currently-equipped gear (character.json's own
    `equipped.items` - real item ids + real socketed gems, exactly as she
    actually has them). Must NOT be called with optimizer.build_owned_config()'s
    idealized substitute - see this section's own module comment for the
    real bug that mistake caused. No ComputeStats RPC, no simserver.exe
    call at all - purely local arithmetic over already-loaded DB data, so
    this can never trigger the RunSim/ComputeStats pool-interleaving
    instability the earlier RPC-based attempt hit.

    A real, acknowledged approximation, not full precision: doesn't
    include raid buffs/talents/racials (a hand-summed gear-only total,
    same real, documented limitation the rest of this codebase's gear-only
    sums share, e.g. core/set_bonus.py's own item lookups), and doesn't
    subtract whichever specific socket a given candidate gem would
    actually replace - it's her whole gear's current total, held constant
    for the lifetime of one report. Both mean this check is, if anything,
    slightly too conservative/permissive (it can slightly over-count
    headroom already used by the very socket being reconsidered) rather
    than too aggressive - an accepted tradeoff for staying fast and simple,
    not a precision this tool claims."""
    global _active_capped_totals
    totals = {idx: 0.0 for idx in _CAP_RATING}
    for it in real_equipped_items:
        if not it:
            continue
        item = idb.by_id(it["id"])
        if item:
            # Real items carry their stats in scalingOptions["0"]["stats"] -
            # a sparse {stat_index_str: value} dict, NOT a flat array like
            # gems use, matching the established pattern already used in
            # core/set_bonus.py/core/sweep_all_loot.py.
            item_stats = item.get("scalingOptions", {}).get("0", {}).get("stats", {})
            for idx in totals:
                totals[idx] += item_stats.get(str(idx), 0)
        for gem_id in it.get("gems") or []:
            gem = idb.gem_by_id(gem_id) if gem_id else None
            if gem:
                gem_stats = gem.get("stats") or []
                for idx in totals:
                    if idx < len(gem_stats):
                        totals[idx] += gem_stats[idx]
    _active_capped_totals = totals


def _crude_score(stats: list[float]) -> float:
    """Cap-aware: any of `stats`' own points in a stat tracked by
    _CAP_RATING get discounted to whatever real headroom is left (per
    `_active_capped_totals`, see `set_active_capped_totals()`) before
    being weighted - a raw, uncapped Hit Rating point that's already past
    her real cap is worth exactly zero here, matching the real in-game
    mechanic (miss chance can't go negative)."""
    weights = stat_weights.get_active()
    total = 0.0
    for i, v in enumerate(stats):
        if not v:
            continue
        if v > 0 and i in _CAP_RATING:
            headroom = max(0.0, _CAP_RATING[i] - _active_capped_totals.get(i, 0.0))
            v = min(v, headroom)
        total += weights.get(str(i), 0) * v
    return total


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
    once costs one socket instead of two), tie-broken by crude score
    (see `_crude_score()`)."""
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
    """The alternate candidate: fill every non-meta socket with a real gem
    that MATCHES the item's own declared socket color (TBC armor sockets
    are always pure Red/Blue/Yellow or Meta, never a hybrid requirement
    themselves), so the item's real socketBonus actually triggers. Real
    legal gear, cap-aware (see `_crude_score()`) - just not yet a claim
    it's better than pure default gems everywhere; `best_gems_for_item()`
    is what actually decides that, via a real combined score (see its own
    docstring).

    Real bug fixed 2026-09-07, caught live comparing against a real
    wowsims.com gem-optimizer run: this used to call _best_gem_of_color()
    (an EXACT pure-color match only) - conflating "the SOCKET's own color is
    always pure" (true) with "the GEM placed there must also be pure"
    (false - a HYBRID gem satisfies a pure-colored socket requirement too,
    e.g. a Purple (Red+Blue) gem matches a Blue socket, per real WoW
    mechanics). For a caster this mattered a lot: the best pure Blue/Yellow
    gems in this DB carry Spirit/Intellect only, zero spellpower, while the
    best Purple/Orange hybrids carry real spellpower alongside the matching
    color. Uses _best_gem_matching_any({color}), the same hybrid-aware
    helper ensure_meta_requirement() already uses.

    TBC's own socket-bonus mechanic is all-or-nothing PER ITEM (every
    socket must color-match simultaneously or the bonus doesn't trigger at
    all) - there is no cross-socket tradeoff to search over once an item
    is being "chased" at all, since every socket independently just needs
    its own single best color-matching gem. A per-socket independent pick
    like this already IS the combination-optimal chase loadout for that
    mechanic - no combinatorial search needed, unlike a game with
    partial/tiered socket bonuses."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    meta_gem = meta_gem_id if meta_gem_id is not None else 0
    gems = []
    for color in sockets:
        if color == idb.META_GEM_COLOR:
            gems.append(meta_gem)
        else:
            gems.append(_best_gem_matching_any({color}) or _phase_legal_default_gem())
    return gems


def _pure_gems_for_item(item: dict, meta_gem_id: int | None) -> list[int]:
    """The profile's own single best default gem in every non-meta socket,
    ignoring socket color entirely - maximizes raw stats, never triggers a
    socket bonus. Position-matched to gemSockets so a meta socket never
    silently loses its gem."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    meta_gem = meta_gem_id if meta_gem_id is not None else 0
    default_gem = _phase_legal_default_gem()
    return [meta_gem if color == idb.META_GEM_COLOR else default_gem for color in sockets]


def _gems_stat_score(gem_ids: list[int]) -> float:
    """Cap-aware crude score (see `_crude_score()`) of a list of real gem
    ids, summed. Used to compare a full socket loadout against another."""
    total = 0.0
    for gid in gem_ids:
        gem = idb.gem_by_id(gid) if gid else None
        if gem:
            total += _crude_score(gem["stats"])
    return total


def verify_gem_choice(item: dict, meta_gem_id: int | None, settings_path: str,
                       baseline_config: list[dict], slot_idx: int,
                       iterations: int, seed: int) -> dict:
    """AUDIT tool, not a production decision-maker: real-sim compares pure
    default gems (_pure_gems_for_item) against this item's own socket-
    bonus-chased loadout (chase_bonus_gems_for_item), with the item
    actually equipped in slot_idx of baseline_config so its printed
    socketBonus is genuinely active. Used by core/verify_gem_choices.py to
    check whether `best_gems_for_item()`'s own LIVE combined-score decision
    (see that function's docstring) actually agrees with what a real sim
    finds - a spot-check on the crude/EP scoring's own accuracy (and, by
    extension, on `stat_weights.json`'s own calibration for this profile),
    not a gate production has to pass before trusting a gem choice.
    Production never calls this - `best_gems_for_item()` decides live,
    every time, with no sim call."""
    if not (item.get("gemSockets") or []):
        return {"applicable": False}

    pure_gems = _pure_gems_for_item(item, meta_gem_id)
    chase_gems = chase_bonus_gems_for_item(item, meta_gem_id)
    if chase_gems == pure_gems:
        return {"applicable": False}  # every socket was already Red/Meta - nothing to compare

    base_entry = dict(baseline_config[slot_idx])

    # Real bug found and fixed 2026-09-07, caught live by the user ("this is
    # bullshit you would deactivate meta gems we established that"): simply
    # dropping pure_gems into this slot can silently break her real
    # meta-gem requirement if THIS item happened to be one of the (possibly
    # several) real gems satisfying it - the sim doesn't model meta
    # activation at all, so it would score that broken state as if nothing
    # were wrong, unfairly making "pure stats" look better than it really
    # is in actual gameplay. Both trial configs now get ensure_meta_
    # requirement() re-applied afterward, so whichever ELSE is the cheapest
    # real fix (possibly this exact socket again, if it's genuinely the
    # cheapest off-color option in her whole gear) gets applied consistently
    # to both sides - a fair, meta-respecting comparison either way.
    pure_config = list(baseline_config)
    pure_entry = dict(base_entry)
    pure_entry["gems"] = pure_gems
    pure_config[slot_idx] = pure_entry
    pure_config = ensure_meta_requirement(pure_config, baseline_config, meta_gem_id)
    pure_result = valuation.evaluate(settings_path, pure_config, iterations, seed)

    chase_config = list(baseline_config)
    chase_entry = dict(base_entry)
    chase_entry["gems"] = chase_gems
    chase_config[slot_idx] = chase_entry
    chase_config = ensure_meta_requirement(chase_config, baseline_config, meta_gem_id)
    chase_result = valuation.evaluate(settings_path, chase_config, iterations, seed)

    delta = chase_result["combined"] - pure_result["combined"]
    sem_a = pure_result["player_stdev"] / (iterations ** 0.5)
    sem_b = chase_result["player_stdev"] / (iterations ** 0.5)
    noise = (sem_a ** 2 + sem_b ** 2) ** 0.5
    real_winner_gems = chase_gems if delta > 0 else pure_gems
    formula_gems = best_gems_for_item(item, meta_gem_id)

    return {
        "applicable": True,
        "pure_dps": pure_result["combined"],
        "chase_bonus_dps": chase_result["combined"],
        "delta": delta,  # positive = chasing the socket bonus really wins
        "noise_stdev": noise,
        "tied_within_noise": abs(delta) < 2 * noise,
        "winner": "chase_bonus" if delta > 0 else "pure",
        "pure_gems": pure_gems,
        "chase_bonus_gems": chase_gems,
        # Did the live combined-score formula (best_gems_for_item, what
        # production actually uses) pick the same gems the real sim just
        # confirmed are genuinely better? False here means the formula got
        # this ONE item wrong - worth a look (a stat_weights.json miscalibration,
        # most likely), not silently ignored.
        "formula_agrees_with_sim": formula_gems == real_winner_gems,
    }


def best_gems_for_item(item: dict, meta_gem_id: int | None) -> list[int]:
    """LIVE, automatic combined-score decision - no static per-item list,
    no manual curation, works for any real item the first time it's seen.
    Replaced 2026-09-07, per the user ("i want a combined score, it is
    still better and especially future proof compared to a static list"):
    the prior design (CHASE_BONUS_ITEM_IDS -> chase_bonus_gems.json) needed
    a human to run core/verify_gem_choices.py and hand-curate every single
    item's real-sim-verified answer into a per-profile file before that
    item's own socket bonus was ever considered - correct only for
    whatever had already been checked, silently defaulting to "don't
    chase" for everything else, forever, until someone remembered to
    re-check it.

    Computes both real candidates and picks whichever scores higher, cap-
    aware (see `_crude_score()`/`set_active_capped_totals()`):
    - `_pure_gems_for_item()`: best default gem in every socket, ignoring
      color - maximum raw stats, no socket bonus.
    - `chase_bonus_gems_for_item()`: best real gem that color-matches each
      socket - triggers the item's own real socketBonus, at some stat
      cost.
    The chase score is `_gems_stat_score(chase_gems) + _crude_score(item's
    own real socketBonus stats)` - crediting the bonus's own real stat
    value, since it only actually applies once every socket matches (TBC's
    socket bonuses are all-or-nothing per item, so there's no partial
    credit and no cross-socket combination search needed - see
    `chase_bonus_gems_for_item()`'s own docstring).

    A real, accepted limitation, same as wowsims' own real Suggest Gems
    tool (confirmed by the user to also chase badly sometimes): this is
    still linear/EP-based scoring, not a real sim - it can occasionally
    get a specific item wrong the same way any EP approximation can
    (STAT_WEIGHTS' own historical Ranger-General's-Chestguard case is the
    proof this isn't purely theoretical - a hybrid gem's real value from a
    multi-stat-conversion stat like Agility isn't fully linear). Cap-
    awareness (Hit Rating specifically) closes the single largest,
    concretely-reproduced gap; `core/verify_gem_choices.py` remains as a
    real-sim AUDIT of this formula's own decisions (not a gate production
    depends on), so a genuine miscalibration surfaces for a human to
    investigate (likely a `stat_weights.json` fix) rather than staying
    invisible."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    pure_gems = _pure_gems_for_item(item, meta_gem_id)
    chase_gems = chase_bonus_gems_for_item(item, meta_gem_id)
    if chase_gems == pure_gems:
        return pure_gems  # every socket was already the default color/Meta - nothing to compare

    pure_score = _gems_stat_score(pure_gems)
    chase_score = _gems_stat_score(chase_gems) + _crude_score(item.get("socketBonus") or [])
    return chase_gems if chase_score > pure_score else pure_gems
