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


# Real, capped-stat awareness for crude gem scoring - added 2026-09-07, per
# the user, after a real gem-candidate mis-pick was traced to exactly this
# gap. `_crude_score()`'s plain linear sum treats every point of every stat
# as worth its flat per-point weight forever - true for Spell Damage/Crit/
# Haste, but Hit Rating (spell and melee) is a real THRESHOLD stat: once a
# character's total hit rating clears the real miss-chance-vs-a-raid-boss
# threshold, every further point is worth exactly zero (miss chance can't
# go negative). Confirmed live: Balance Druid's own real stat_weights.json
# weights Spell Hit Rating at 1.91/point (by far her highest weight), so a
# crude score picked a pure +8 Hit Rating gem over a +5 Spell Damage/+4
# Crit hybrid - but her real character sheet already shows 17.35% Spell
# Hit, past the real 17% cap (see below), so those 8 points were worth
# ZERO in practice; the real sim (which does model the true threshold)
# picked the Spell Damage/Crit gem instead, exactly as this fix now does.
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
# separate real conversion) is NOT modeled here yet - a real, flagged gap,
# not silently assumed equivalent.
SPELL_HIT_RATING_PER_PERCENT = 12.615385
MELEE_HIT_RATING_PER_PERCENT = 15.769233
SPELL_HIT_STAT_IDX = 12
MELEE_HIT_STAT_IDX = 20
_CAP_RATING = {
    SPELL_HIT_STAT_IDX: 17.0 * SPELL_HIT_RATING_PER_PERCENT,   # ~214.5 rating
    MELEE_HIT_STAT_IDX: 8.0 * MELEE_HIT_RATING_PER_PERCENT,    # ~126.2 rating
}


def _capped_stat_totals(equipped_items: list, settings_path: str | None = None) -> dict[int, float]:
    """Real, current total rating for each capped stat (see _CAP_RATING).

    When `settings_path` is given, uses the TRUE, real, fully-buffed/
    talented total via `valuation.get_final_stats()` (a real ComputeStats
    RPC, cached) - the authoritative number, including raid buffs/talents/
    set bonuses/racials that a hand-summed total can never fully capture.
    Real bug found and fixed 2026-09-07: this function originally ALWAYS
    hand-summed from raw item/gem data, which disagreed with wowsims.com's
    own reported total for a real character by a wide margin (Balance
    Druid: hand-sum found ~106 rating, her real total is materially
    higher) - close enough to matter for a cap threshold decision, not a
    rounding difference to shrug off.

    Falls back to the hand-summed approximation (items' own
    scalingOptions stats + socketed gems, NOT raid buffs/talents/racials -
    a real, documented limitation) when `settings_path` isn't given (e.g.
    ensure_meta_requirement()'s own call site doesn't have one readily
    available) or when the real ComputeStats call degrades to None -
    directionally useful even when imperfect, never silently skipped.
    Accepts either real `equipped_items` (character.json's own shape) or a
    baseline/trial config list (optimizer.Candidate.as_entry()'s shape) -
    both carry the same real `id`/`gems` fields, so either works here."""
    if settings_path is not None:
        final_stats = valuation.get_final_stats(settings_path, equipped_items)
        if final_stats is not None:
            return {idx: final_stats[idx] if idx < len(final_stats) else 0.0 for idx in _CAP_RATING}

    totals = {idx: 0.0 for idx in _CAP_RATING}
    for it in equipped_items:
        if not it:
            continue
        item = idb.by_id(it["id"])
        if item:
            # Real items carry their stats in scalingOptions["0"]["stats"] -
            # a sparse {stat_index_str: value} dict, NOT a flat array like
            # gems use (confirmed bug fixed 2026-09-07: this originally
            # read item.get("stats"), which real items never have at all -
            # `idb.by_id()`'s own item dicts have no "stats" key, so this
            # silently summed to zero for every real character, matching
            # the established real pattern already used elsewhere in this
            # codebase, e.g. core/set_bonus.py's own identical lookup).
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
    return totals


def _crude_score(stats: list[float], capped_totals: dict[int, float] | None = None) -> float:
    """`capped_totals`, when given, is the character's CURRENT total rating
    per capped stat EXCLUDING this candidate gem's own contribution - any
    of `stats`' own points that would push the total past the real cap are
    discounted to zero value (see _CAP_RATING's own module comment)."""
    weights = stat_weights.get_active()
    total = 0.0
    for i, v in enumerate(stats):
        if not v:
            continue
        if capped_totals is not None and i in _CAP_RATING:
            headroom = max(0.0, _CAP_RATING[i] - capped_totals.get(i, 0.0))
            v = min(v, headroom) if v > 0 else v
        total += weights.get(str(i), 0) * v
    return total


def _best_gem(candidates: list[dict], capped_totals: dict[int, float] | None = None) -> tuple[int, float] | None:
    best = None
    for g in candidates:
        score = _crude_score(g["stats"], capped_totals)
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


def _best_gem_matching_any(colors: set[int], capped_totals: dict[int, float] | None = None) -> int | None:
    """Best real, phase-legal gem (by crude score) whose own GEM_MATCHES
    set intersects `colors` - i.e., any gem that counts toward at least one
    of the still-missing pure colors passed in. Prefers a gem covering MORE
    of `colors` simultaneously (a hybrid satisfying two missing colors at
    once costs one socket instead of two - the same real saving
    `_best_green_gem()` already made for the one previously-hardcoded
    meta), tie-broken by cap-aware crude score (see `_crude_score()`)."""
    best_gem, best_coverage, best_score = None, -1, -1.0
    for g in _all_gems():
        coverage = len(GEM_MATCHES.get(g["color"], set()) & colors)
        if coverage == 0:
            continue
        score = _crude_score(g["stats"], capped_totals)
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

    capped_totals = _capped_stat_totals(equipped_items)
    new_config = [dict(entry) for entry in config]
    for entry_idx, socket_idx, _native_color in available:
        still_missing = {c for c, n in missing.items() if n > 0}
        if not still_missing:
            break
        gem_id = _best_gem_matching_any(still_missing, capped_totals)
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


def chase_bonus_gems_for_item(item: dict, meta_gem_id: int | None,
                               equipped_items: list | None = None,
                               settings_path: str | None = None) -> list[int]:
    """The alternate candidate: fill every non-meta socket with a real gem
    that MATCHES the item's own declared socket color (TBC armor sockets
    are always pure Red/Blue/Yellow or Meta, never a hybrid requirement
    themselves - that part was always true), so the item's real socketBonus
    actually triggers. This is real, legal gear - just a specific candidate
    loadout, not yet a claim it's better than the profile's own pure
    default gem. See verify_gem_choice for the real sim comparison that
    decides that, replacing the old STAT_WEIGHTS-based "smart" heuristic
    this function's predecessor was disproven on (NOTES.md, 2026-08-2x).

    Real bug fixed 2026-09-07, caught live comparing against a real
    wowsims.com gem-optimizer run: this used to call _best_gem_of_color()
    (an EXACT pure-color match only) - conflating "the SOCKET's own color is
    always pure" (true) with "the GEM placed there must also be pure"
    (false - a HYBRID gem satisfies a pure-colored socket requirement too,
    e.g. a Purple (Red+Blue) gem matches a Blue socket, per real WoW
    mechanics). For a caster this mattered a lot: the best pure Blue/Yellow
    gems in this DB carry Spirit/Intellect only, zero spellpower, while the
    best Purple/Orange hybrids carry real spellpower alongside the matching
    color - real-sim-verified for Pauldrons of Malorne (Balance Druid): the
    pure-color version LOST to the profile's own default gem (-6.51 DPS),
    the hybrid-aware version (matching wowsims' own real picks) WON
    (+2.15 DPS) - the same item, the only difference being which real gem
    fills the matching-color slot. Now uses _best_gem_matching_any({color}),
    the same hybrid-aware helper ensure_meta_requirement() already uses.

    `equipped_items`, when given, makes this cap-aware too (see
    _CAP_RATING's own module comment) - without it, the tie-break between
    two same-coverage hybrid candidates falls back to plain crude score,
    which can pick an over-capped Hit Rating gem over a real, uncapped
    upgrade (confirmed live: exactly this, for this same shoulder item's
    second socket, before this parameter existed). `settings_path`, when
    ALSO given, makes the cap check itself accurate (a real ComputeStats
    total, not a hand-summed approximation - see _capped_stat_totals()).

    Real, exact per-item overrides checked FIRST (set_active_chase_bonus_
    gem_overrides()) - crude/cap-aware scoring alone was confirmed, live,
    to sometimes disagree with what a real sim-verification run actually
    found to be the winning gem (Pauldrons of Malorne: crude score picks
    Great Dawnstone, real-sim-tested best is Potent Noble Topaz) - once an
    item has been through that real verification, the EXACT winning gems
    get used every time, not silently re-derived and possibly wrong
    again."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    override = _active_chase_bonus_gem_overrides.get(item.get("id"))
    if override is not None:
        return list(override)
    meta_gem = meta_gem_id if meta_gem_id is not None else 0
    capped_totals = _capped_stat_totals(equipped_items, settings_path) if equipped_items is not None else None
    gems = []
    for color in sockets:
        if color == idb.META_GEM_COLOR:
            gems.append(meta_gem)
        else:
            gems.append(_best_gem_matching_any({color}, capped_totals) or _phase_legal_default_gem())
    return gems


def _candidates_matching_any(colors: set[int], n: int,
                              capped_totals: dict[int, float] | None = None) -> list[int]:
    """Top `n` real, phase-legal gems whose own GEM_MATCHES intersects
    `colors` - same ranking _best_gem_matching_any() uses (coverage first,
    then cap-aware crude score), just keeping the top N instead of only
    the single best, so a caller can real-sim-test between them instead of
    trusting crude score alone to pick the winner."""
    scored = []
    for g in _all_gems():
        coverage = len(GEM_MATCHES.get(g["color"], set()) & colors)
        if coverage == 0:
            continue
        scored.append((coverage, _crude_score(g["stats"], capped_totals), g["id"]))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    return [gid for _, _, gid in scored[:n]]


# Real, FIXED, cheap iteration budget for _real_sim_refine_chase_gems()'s
# own internal candidate search - added 2026-09-07, per the user, after
# the first version reused whatever `iterations` the OUTER caller passed
# in (3000 during verify_gem_choices.py's cheap screen pass, but a real
# 30000 during its resolve pass for any item close enough to need one).
# With top_n=8 candidates across a 2-socket item, that's up to 14 EXTRA
# real sim calls per item ON TOP of the existing screen+resolve funnel -
# at 30000 iterations each, this would have multiplied an already-real
# 15-minute-class full-profile run well past that, not a small overhead.
# The refinement's own job is choosing WHICH gem is likely best (a
# discovery/screening task), not producing the final, publication-quality
# DPS number - that final number still comes from verify_gem_choice()'s
# own real evaluate() call at the CALLER's actual requested precision,
# using whichever gem this cheap search found. Matches the same
# "SCREEN_ITERATIONS way cheaper than RESOLVE_ITERATIONS" cost-tiering
# convention already used throughout this whole pipeline.
_GEM_REFINE_ITERATIONS = 1500


def _real_sim_refine_chase_gems(item: dict, meta_gem_id: int | None, settings_path: str,
                                 baseline_config: list[dict], slot_idx: int,
                                 equipped_items: list, seed: int,
                                 top_n: int = 8) -> list[int]:
    """Greedy, per-socket REAL-SIM refinement of chase_bonus_gems_for_item()'s
    crude-score guess - added 2026-09-07, per the user, after cap-awareness
    alone was confirmed NOT sufficient. Real, correct picture (found by
    actually tracing the discrepancy rather than trusting either side's
    number blindly): Balance Druid's TRUE current Hit Rating from her real
    gear is 118 (matches wowsims exactly, confirmed via a direct item-by-
    item sum) - but her real EFFECTIVE hit chance also includes real,
    separate TARGET-side debuffs (Totem of Wrath +3%, Misery +3%) that
    reduce the target's own chance to avoid her spells, on top of her own
    gear-based Hit Rating - a genuinely different mechanic layer a
    gear-only rating sum can never see. Modeling the TRUE combined
    threshold correctly would need both layers together, which is real,
    non-trivial complexity - not something to keep hand-rolling after
    getting it wrong twice already. `top_n` widened from 3 to 8 instead:
    real-sim-testing a wider shortlist means the genuinely-best candidate
    still gets found and correctly evaluated by the ACTUAL sim (which
    natively models gear, debuffs, and caps together, correctly) even when
    crude/cap-aware scoring alone ranks it outside a narrow top-3 - the
    same 'never shortcut to EP-only ranking' principle, applied by
    widening the pre-filter rather than perfecting an inherently
    approximate score.

    This applies the SAME 'never shortcut to EP-only ranking' rule
    verify_gem_choice() already applies to the outer chase-vs-default
    decision, one level deeper: for each non-meta socket, real-sim-tests
    up to `top_n` crude-score candidates (holding every other socket at
    its current best pick), keeping whichever real DPS is highest - a
    bounded, cheap greedy search (at most top_n-1 extra real sim calls per
    socket, always at the cheap, fixed _GEM_REFINE_ITERATIONS - see that
    constant's own module comment for why this must NOT scale with the
    caller's own requested precision), not a full combinatorial search
    across every socket at once."""
    sockets = item.get("gemSockets") or []
    if not sockets:
        return []
    capped_totals = _capped_stat_totals(equipped_items, settings_path) if equipped_items is not None else None
    gems = list(chase_bonus_gems_for_item(item, meta_gem_id, equipped_items, settings_path))
    base_entry = dict(baseline_config[slot_idx])

    def dps_for(gems_trial: list[int]) -> float:
        entry = dict(base_entry)
        entry["gems"] = gems_trial
        trial_config = list(baseline_config)
        trial_config[slot_idx] = entry
        return valuation.evaluate(settings_path, trial_config, _GEM_REFINE_ITERATIONS, seed)["combined"]

    best_dps = dps_for(gems)
    for socket_idx, color in enumerate(sockets):
        if color == idb.META_GEM_COLOR:
            continue
        for candidate in _candidates_matching_any({color}, top_n, capped_totals):
            if candidate == gems[socket_idx]:
                continue
            trial_gems = list(gems)
            trial_gems[socket_idx] = candidate
            dps = dps_for(trial_gems)
            if dps > best_dps:
                best_dps = dps
                gems[socket_idx] = candidate
    return gems


def verify_gem_choice(item: dict, meta_gem_id: int | None, settings_path: str,
                       baseline_config: list[dict], slot_idx: int,
                       iterations: int, seed: int, refine_chase_gems: bool = False) -> dict:
    """Real-sim compare pure Agility (best_gems_for_item) against the item's
    own socket-bonus-chased loadout (chase_bonus_gems_for_item, optionally
    refined by _real_sim_refine_chase_gems - see that function's own
    docstring for why crude/cap-aware score alone isn't trusted to pick
    WHICH real gem fills a matching socket, only whether chasing is worth
    it at all), with the item actually equipped in slot_idx of
    baseline_config so its printed socketBonus is genuinely active.
    Returns whichever wins, with the real DPS delta and noise - never a
    STAT_WEIGHTS score standing in for this decision, per CLAUDE.md's
    "never shortcut to EP-only ranking" rule applied to gem choice
    specifically (see gem_optimizer.py's module docstring for the earlier,
    disproven attempt at a crude-score shortcut here).

    `refine_chase_gems` defaults to False (real, deliberate cost control,
    per the user, 2026-09-07): _real_sim_refine_chase_gems() is itself
    cheap per item (~10s, at the fixed _GEM_REFINE_ITERATIONS budget), but
    verify_gem_choices.py's own SCREEN pass calls this function for EVERY
    real candidate with sockets - a full profile can easily have 150+ of
    those, which would multiply into 25-30+ minutes added to what's
    already a real ~15-minute-class budget if every screen call refined.
    Pass True only for the SMALL number of items that clear the screen and
    are being resolved at full precision - the same "cheap broad screen,
    expensive narrow resolve" funnel discipline already used everywhere
    else in this pipeline, just applied to gem selection too."""
    if not (item.get("gemSockets") or []):
        return {"applicable": False}

    pure_agility_gems = best_gems_for_item(item, meta_gem_id)
    crude_chase_gems = chase_bonus_gems_for_item(item, meta_gem_id, equipped_items=baseline_config,
                                                  settings_path=settings_path)
    if crude_chase_gems == pure_agility_gems:
        return {"applicable": False}  # every socket was already Red/Meta - nothing to compare

    if refine_chase_gems:
        chase_gems = _real_sim_refine_chase_gems(item, meta_gem_id, settings_path, baseline_config,
                                                  slot_idx, baseline_config, seed)
    else:
        chase_gems = crude_chase_gems

    base_entry = dict(baseline_config[slot_idx])

    # Real bug found and fixed 2026-09-07, caught live by the user ("this is
    # bullshit you would deactivate meta gems we established that"): simply
    # dropping pure_agility_gems into this slot can silently break her real
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
    pure_entry["gems"] = pure_agility_gems
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
# Real, exact winning gem ids per item id, added 2026-09-07 - optional,
# separate from _active_chase_bonus_ids (a plain "yes/no" flag). Needed
# because chase_bonus_gems_for_item()'s own crude-score fallback (used
# when no override exists here) doesn't always land on the SAME gem a real
# sim-verification run confirmed as the actual winner (see gem_optimizer.py's
# own module docstring on crude score's real, confirmed unreliability for
# this decision) - without persisting the EXACT verified gems, production
# use of an already-curated "yes, chase this" item could re-derive a
# DIFFERENT, unverified (and possibly worse) gem choice every time, not the
# one that was actually proven correct. Defaults to empty (never breaking
# an existing profile that hasn't set one) - set via
# set_active_chase_bonus_gem_overrides(), sourced from chase_bonus_gems.json's
# own optional "gems" map.
_active_chase_bonus_gem_overrides: dict[int, list[int]] = {}


def set_active_chase_bonus_ids(item_ids: set[int]) -> None:
    global _active_chase_bonus_ids
    _active_chase_bonus_ids = item_ids


def set_active_chase_bonus_gem_overrides(overrides: dict[int, list[int]]) -> None:
    global _active_chase_bonus_gem_overrides
    _active_chase_bonus_gem_overrides = overrides


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
