"""Full-sweep MV, tiered by acquisition source (T6/T5/T4/Heroics/Vanilla
carryover/Crafted/Reputation) and then broken down by equipment slot within
each tier - top 5 per (tier, slot), not one blended top-5 per tier, per the
user's correction. Compute budget: screen EVERYTHING cheap (1k iterations)
first, then only pay for the 30k resolve pass on each (tier, slot)
leaderboard's top ~8 (slack in case resolving reorders things near the
cutoff) - and even then, only the ones still close enough to the noise
floor that resolving could plausibly change the verdict (CLEAR_MARGIN_MULTIPLE,
same rule marginal_value.mv_single_tiered already uses). A candidate pool
this large has hundreds of items clustered near zero (most random raid
drops don't beat an already-decent-itemized character) - resolving all of
them was the actual reason the first run of this was taking so long, not
the sim being slow. Items she already owns (equipped/bags/bank) are excluded
from every tier - not an acquisition target - but stay in the working
candidate pool so set-bonus math (see the "Set-bonus rescue check" below)
still sees them. A piece that's a downgrade alone but part of a set whose
combined MV is a real upgrade gets included anyway, flagged with an info
note, rather than silently dropped - exactly the case §1 warns EP-only
ranking misses.
"""
import concurrent.futures
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402
import set_bonus  # noqa: E402
import acquisition_gate  # noqa: E402
import time_horizon  # noqa: E402
import stat_weights  # noqa: E402
import gem_optimizer  # noqa: E402
import sweep_all_loot  # noqa: E402
import local_config  # noqa: E402
import source_scope  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
# Real, deleted 2026-08-31 (code review §5.4): this file used to define
# module-level PROFILE_DIR/SETTINGS_TEMPLATE/SETTINGS_2H/POOL_PATH
# constants, all pointing at survival_hunter - historical leftover from
# before Stage 6 (multi-class support). main()'s own real profile_dir
# parameter (required, no default) is what actually drives every real
# call site - it builds its own LOCAL SETTINGS_TEMPLATE/SETTINGS_2H/
# POOL_PATH from that parameter (see below), and every real usage in this
# file reads those, never the module-level ones. Confirmed via a real
# grep before deleting: zero references to the module-level names
# anywhere outside their own now-deleted definitions, in this file or any
# other. This is exactly the shape of bug documented in
# core/character_profiles.py's own docstring - a default that silently
# produces a plausible-but-wrong report for the wrong class - the
# defensive fix there (character_profiles.SUPPORTED_CHARACTERS) was
# good, but the loaded gun sitting here was still on the table until now.
# Derived, not hardcoded to one machine's core count (code review §4.4) -
# see local_config.sim_concurrency()'s own docstring for the real
# reasoning and measurement. adapters/tbc/valuation.SIMSERVER_POOL_SIZE
# calls the same function, so the two stay in lockstep automatically.
MAX_WORKERS = local_config.sim_concurrency()

SCREEN_ITERATIONS = 500  # cheap ranking pass across the whole pool
# Lowered from 1000 to 500 on 2026-08-24, validated empirically (not guessed):
# screened the full real ~650-candidate pool at both 500 and 1000 iterations and
# compared every (tier,slot) bucket's top-8 SET, not just per-item mv agreement -
# the actual decision this constant drives. 77/80 buckets matched exactly; the 3
# that didn't were all old-content/vanilla-carryover weapon buckets where EVERY
# swapped item sat at mv ~= -61.3 DPS (deep downgrades clustered within a
# fraction of a DPS of each other, nowhere near a real upgrade) - reordering
# noise among items that could never appear in the report regardless. Real
# per-call cost measured too: 100/250/500/1000/2000 iter -> 0.204/0.219/0.249/
# 0.305/0.415s/call - the fixed per-call floor (~0.19-0.20s) dominates even at
# 1000 iter, so this alone is a modest ~15-20s win on ~650 candidates, not the
# main lever (that was the confirm@5k tier below) - see NOTES.md 2026-08-24.
# Tried lowering this to 5000 on 2026-08-23 based on an initial "looks about
# the same" observation - reverted the same session once the user directly
# tested it side-by-side in the wowsims web UI: the same swap comparison
# read +1.06 DPS at 30k iterations but -3.50 DPS at 5k - not just noisier,
# the sign flipped. That's exactly the failure mode noise-honesty exists to
# prevent (a near-zero true effect misreported as a confident directional
# finding), so 30k stays as the real resolve precision. Real numbers from
# that test: stdev~73 both times: SEM(30k)~=0.42, combined delta-noise
# ~=0.6 (the +1.06 result was ALREADY borderline at 30k); SEM(5k)~=1.03,
# combined delta-noise ~=1.5 (nowhere near tight enough to trust for an
# effect this small). 30k is the floor for a REPORTED number - a lower
# iteration count is fine for a screening/pre-screening GATE decision
# (worst case there is wasted compute, not a wrong answer), never for a
# number that gets shown as final. Exposed as a real, per-machine tunable
# setting (backlog item #6, CLAUDE.md Future Scope, 2026-08-31) via
# local_config.resolve_iterations() rather than hardcoded here directly -
# the real speed/precision tradeoff above is exactly the kind of thing a
# user might want to tune with their eyes open, not something this file
# should force on everyone. Default (30000, unset) is the same real value
# this comment already argues for.
RESOLVE_ITERATIONS = local_config.resolve_iterations()  # precise, only spent on each (tier, slot) leaderboard
# 2026-08-24: added as a genuinely ADDITIVE confirm tier between SCREEN_ITERATIONS
# and RESOLVE_ITERATIONS, not a replacement for either - per the user, and per the
# real 10-item A/B test already on file (see the SCREEN_ITERATIONS comment above and
# CLAUDE.md's "Status" note): every item with a real, decision-relevant magnitude
# (+/-7 to +/-51 DPS) matched the 30k number at 5k iterations exactly; the ONE
# disagreement was a razor-thin near-zero effect (+1.3 DPS) already right at the
# noise floor. So: every `to_resolve` candidate gets a cheap 5k confirm pass first;
# if THAT result is already CONFIRM_CLEAR_MARGIN_MULTIPLE widths from zero, it's
# trustworthy enough to report as final - flagged "(confirmed @5k)", never silently
# presented as a 30k number. Only genuinely borderline items (plus the #1 pick per
# (tier,slot), which always gets full precision regardless, per the existing
# policy) escalate to the real 30k pass. Noise-honesty is preserved by disclosure,
# not by pretending 5k is as precise as 30k - see `resolve_iterations` on each
# report row.
CONFIRM_ITERATIONS = 5000
# A SEPARATE margin from mv.CLEAR_MARGIN_MULTIPLE (8x, calibrated for the much
# noisier 1k screen -> 30k jump) - reusing 8x here was needlessly conservative,
# confirmed empirically 2026-08-24: pulled real paired confirm@5k/resolve@30k
# values for all 140 leaderboard candidates from one real clean run (cache hits,
# no new compute) and swept multiplier 2-8. Result: ZERO sign flips or verdict
# changes among items that would skip 30k at ANY tested multiplier - the only 3
# real 5k/30k sign disagreements were all near-zero effects (ratio 0.19-0.79)
# that never clear even a 2x threshold to begin with, and both tiers already
# correctly flag them "tied within noise" regardless. Worst-case drift among
# skipped items stayed flat at 1.37 DPS from mult=2 through mult=8 - the risk
# genuinely doesn't grow as the threshold loosens, only the skip rate does (35/60
# non-top items at 8x vs 48/60 at 3x). Set to 3x: a full step above the 2x
# tie-check boundary (so a "confirmed" item is never just barely outside "tied"),
# while reclaiming most of the efficiency 8x was leaving on the table. See
# NOTES.md's 2026-08-24 entry for the full data.
CONFIRM_CLEAR_MARGIN_MULTIPLE = 3
LEADERBOARD_SIZE = 8  # per (tier, slot), resolved - a little slack over "top 5"
# in case resolving nudges the screening order around near the cutoff
TOP_N_2H = 5  # flat leaderboard across ALL tiers/zones, not grouped per tier -
# per the user, tier-grouped 2H output was mostly clutter (every zone's own
# weak options padding the list); the real question is just "what are her
# best few 2H options, period", so only the overall top N are shown at all.

# Real, empirically-grounded threshold, not a round guess (2026-09-06) - see
# NOTES.md's own dated entry for the full trail. Probed Béarforceone's real
# gear across a real duration sweep during planning: 0.0% OOM at 90s, 3.9% at
# 120s, already 19.9% at this tool's own long-standing 180s default. Per the
# user's own real mechanical reasoning: the GCD is 1.5s and her real casts run
# 2-3s each, so even a couple seconds of OOM already costs a real, whole lost
# cast - 1.5% (not the initially-floated 5%) is the real bar for "this baseline
# was meaningfully OOM, treat mana/spirit item values in this report with
# real caution."
OOM_WARNING_THRESHOLD_FRACTION = 0.015

# Real, curated list (2026-09-06, per the user's own "the 7 real caster
# profiles" confirmation) - the classes that actually cast for their damage
# and can run into a real Destruction-vs-Mana-Potion tradeoff. Deliberately
# NOT derived from a generic "uses mana" resource check - Enhancement
# Shaman/Retribution Paladin/Hunters also use mana but aren't part of this
# real choice, same curation principle as gui/assets/app.js's own
# WEAVE_CAPABLE_PROFILES.
CASTER_POTION_PROFILES = {
    "balance_druid", "elemental_shaman", "shadow_priest", "arcane_mage",
    "affliction_warlock", "demonology_warlock", "destruction_warlock",
}

TYPE_TO_SLOT = {
    1: "head", 2: "neck", 3: "shoulder", 4: "back", 5: "chest", 6: "wrist",
    7: "hands", 8: "waist", 9: "legs", 10: "feet", 11: "ring", 12: "trinket",
    14: "ranged",
}
TWO_HAND = 4
# Real HandType enum values (proto/common.proto) - Stage 6.2 needs the other
# three, not just TWO_HAND, for a real one_hand_plus_offhand_item profile
# (Balance Druid: a real, distinct "held in off-hand" item type exists,
# HandTypeOffHand - not a weapon a caster would ever dual-wield, confirmed
# separate from HandTypeOneHand in the proto).
MAIN_HAND = 1
ONE_HAND = 2
OFF_HAND = 3

# Display grouping for the per-slot leaderboards: ring1/ring2, trinket1/
# trinket2, and mainhand/offhand share one pool each (an item can go in
# either half of the pair) so they're reported as one slot, not two.
SLOT_DISPLAY = {
    "head": "Head", "neck": "Neck", "shoulder": "Shoulder", "back": "Back",
    "chest": "Chest", "wrist": "Wrist", "hands": "Hands", "waist": "Waist",
    "legs": "Legs", "feet": "Feet", "ranged": "Ranged",
    "ring1": "Ring", "ring2": "Ring",
    "trinket1": "Trinket", "trinket2": "Trinket",
    "mainhand": "Weapon", "offhand": "Weapon",
}
SLOT_DISPLAY_ORDER = [
    "Head", "Neck", "Shoulder", "Back", "Chest", "Wrist", "Hands", "Waist",
    "Legs", "Feet", "Ring", "Trinket", "Ranged", "Weapon",
]

TIER_ZONES = {
    "T6 (Black Temple / Mount Hyjal)": {3606, 3959},
    "T5 (Serpentshrine Cavern / Tempest Keep)": {3607, 3845},
    "T4 (Karazhan / Gruul's Lair / Magtheridon's Lair)": {3457, 3923, 3836},
    "TBC Heroics": {3562, 3713, 3714, 3715, 3716, 3717, 3789, 3790, 3791, 3792, 3847, 3848, 3849, 2366, 2367},
    "Vanilla carryover": {1583, 1584, 1977, 2017, 2057, 2159, 2557, 2677, 2717, 3428, 3429, 3456},
}

# Real, data-derived fallback (found and fixed 2026-08-31, live user report:
# real Elemental Shaman T6 tier pieces - Skyshatter Regalia - were showing
# up bucketed under "Other" instead of "T6"). Root cause, confirmed via a
# direct DB query, not assumed: 200+ real item sets across every class have
# `sources: None` for EVERY piece - not just Skyshatter/Cyclone Regalia,
# a genuine, widespread gap in the sim's own DB, not a bug in this file.
# Real raid tier sets (Skyshatter/Cyclone/Thunderheart/Lightbringer/
# Malefic/Onslaught/Gronnstalker's/Vestments of Absolution, etc.) have NO
# sibling piece with resolvable source data to borrow a real zone from
# either - every single piece of the same set is equally missing it.
# item["phase"] IS still real, present DB data though, and confirmed via a
# direct query (not assumed) to correspond 1:1 with TIER_ZONES's own real
# zone-resolvable items: every real item with a zoneId in the T4 bucket is
# phase 1, every T5-bucket item is phase 2, every T6-bucket item is phase 3
# - so phase alone is enough to bucket a sourceless item into the correct
# real tier, without claiming a specific zone/boss this DB doesn't actually
# know. Only ever reached for CURATED-pool items (sweep_all_loot.eligible()
# already requires real `sources` before a SWEPT item is even considered),
# so this never risks bucketing a random unvetted item - only real,
# already-curated BiS candidates missing this one DB field.
PHASE_TO_TIER_ZONE_KEY = {
    1: "T4 (Karazhan / Gruul's Lair / Magtheridon's Lair)",
    2: "T5 (Serpentshrine Cavern / Tempest Keep)",
    3: "T6 (Black Temple / Mount Hyjal)",
}

# Backlog #15 (2026-09-06) - real, structural finding, verified directly
# against Wowhead across 11 different tier-set families spanning every real
# raid tier (T4: Voidheart/Cyclone/Warbringer/Justicar - two different real
# tokens confirmed, "Helm of the Fallen X" from Karazhan's Prince Malchezaar
# for most, but a Magtheridon's-Lair-dropped token for at least Justicar; T5:
# Rift Stalker/Nordrassil/Deathmantle; T6: Skyshatter/Onslaught/Thunderheart,
# plus the user's own real confirmation that T6 tokens drop inside Black
# Temple/Hyjal itself, turned in to Tydormu): every real TBC raid tier set is
# acquired via a boss-dropped TOKEN turned in to a real vendor, never a
# direct drop of the finished piece - explaining why the DB's own
# drop/crafted/rep-only sources[] schema has nothing for any of them. T4
# tokens go to Asuur/Arodis Sunblade <Keeper of Sha'tari Artifacts> in
# Shattrath City; T5 tokens to Kelara/Veynna Dawnstar <Keeper of Sha'tari
# Heirlooms>, also Shattrath City; T6 tokens to Tydormu <Keeper of Lost
# Artifacts>, inside Black Temple/Hyjal itself.
#
# Tier is derived from the SET's own real minimum phase across every piece
# sharing its setId (_SET_MIN_PHASE below), not the individual item's own
# phase field - several real T6 sets (Gronnstalker's/Malefic/Onslaught/
# Skyshatter/Thunderheart) have some pieces itemized at phase 3 and others
# at phase 5, but they're all still the same real T6 set, dropping from the
# same real raid.
#
# Real, deliberate scope limit, not an oversight: 19 of the ~30 distinct set
# families in the real gap list were individually confirmed this way before
# Wowhead's own CDN started real-rate-limiting further lookups (CloudFront
# 403s, not a page-content problem) - the remaining families were NOT
# individually re-verified, this general rule is applied to them on the
# strength of the now cross-class-confirmed mechanism itself, not per-item
# guessing. Flag if a future check finds a real exception.
_TIER_TOKEN_DESC = {
    1: "Tier token (Karazhan / Gruul's Lair / Magtheridon's Lair) -> Aldor/Scryers vendor",
    2: "Tier token (Serpentshrine Cavern / Tempest Keep) -> Sha'tari Heirlooms vendor",
    3: "Tier token (Black Temple / Mount Hyjal) -> Tydormu",
}
_SET_MIN_PHASE: dict[int, int] = {}
for _item in idb.items():
    _sid, _phase = _item.get("setId"), _item.get("phase")
    if _sid and _phase and (_sid not in _SET_MIN_PHASE or _phase < _SET_MIN_PHASE[_sid]):
        _SET_MIN_PHASE[_sid] = _phase

# Backlog #15 (2026-09-06) - a small, real, individually-verified overlay for
# items the DB itself has no sources[] data for at all. STRICTLY a fallback:
# describe_source_and_tier() only ever consults this AFTER a real DB source
# comes back empty - an overlay entry can never override real DB data, only
# fill a gap the DB genuinely has none for. Every entry is individually
# checked against Wowhead before being added (see the file's own _comment
# key) - never bulk-filled from general knowledge, same verification bar
# every other real curation pass in this project already holds itself to.
_SOURCE_OVERLAY = repo_root.load_json(
    os.path.join(REPO_ROOT, "profiles", "tbc", "_shared", "source_overlay.json"))


def horizon_tag(r: dict) -> str:
    """'[BiS through P5]' when it's the guide's genuine top pick all the
    way to the final phase; '[BiS until P4]' when it stops being the top
    pick after that phase (whether or not it's still technically listed
    later, e.g. as a leftover option). Empty when it was never confirmed
    as a real top pick at all - per the user, that case doesn't need a
    tag, it's already obvious a stepping-stone item is a stepping stone."""
    phase = r.get("bis_until_phase")
    if phase is None:
        return ""
    return f"  [BiS through P{phase}]" if r.get("final_phase") else f"  [BiS until P{phase}]"


def rank_value(r: dict) -> float:
    """Real leaderboard sort key - a set piece's own isolated mv understates
    its true worth whenever it's the specific piece that crosses a real,
    currently-achievable set-bonus threshold (given what's already owned of
    that set elsewhere): isolated mv alone would rank it against standalone
    items using a number that ignores the bonus it's actually delivering.
    set_bonus_credit (attached per-candidate in the row-assembly loop below,
    from threshold_values_by_set - the same isolate_bonus_value() sim calls
    the set_note text already pays for, never re-run) is 0/None for any
    candidate that isn't the piece completing a real threshold, so this is
    a no-op for the common case. Per the user (2026-08-25): order set
    pieces higher than singular items when their real combined value
    (isolated mv + the threshold bonus they complete) is actually higher."""
    return r["mv"] + (r.get("set_bonus_credit") or 0)


def slot_for_item(item: dict, weapon_topology: str = "dual_wield") -> str | None:
    """weapon_topology matters here (Stage 6.1/6.2, real bugs found and
    fixed, not a hypothetical):
    - dual_wield (Hunter): a 2H weapon is an OPTIONAL alternate to her real
      spec - own side-pool ("weapon_2h", evaluated separately below under
      its own melee-weave settings), never the normal tiered report. A 1H
      weapon goes to the shared "weapon_dual_wield" pool (either hand).
    - two_hand (Arms Warrior): 2H IS the real, only mainhand slot - routing
      it into the Hunter-only side-pool would mean every one of his real
      weapon candidates silently never appears in his main report at all.
      A 1H weapon has no real slot for this topology (strict downgrade,
      loses 2H-specialization talents) - excluded rather than guessed into
      a nonexistent offhand pool.
    - one_hand_plus_offhand_item (Balance Druid, Stage 6.2): mainhand and
      offhand are REAL, INDEPENDENT single-item pools (not a shared
      dual-wield pool - a caster's real offhand item, HandTypeOffHand, is
      never itself a weapon she'd equip in mainhand). A 2H weapon is still
      a real optional alternate here (her actual BiS weapon choice varies
      by phase between a 2H staff and a 1H+offhand combo - confirmed from
      real wowsims gear-set data) - same side-pool treatment as dual_wield."""
    t = item.get("type")
    if t == 13:
        hand_type = item.get("handType")
        is_two_hand = hand_type == TWO_HAND
        if weapon_topology == "two_hand":
            return "mainhand" if is_two_hand else None
        if weapon_topology == "one_hand_plus_offhand_item":
            if is_two_hand:
                return "weapon_2h"  # own pool, own settings/baseline - see the 2H section below
            if hand_type == OFF_HAND:
                return "offhand"
            if hand_type in (MAIN_HAND, ONE_HAND):
                return "mainhand"
            return None  # unknown/unclassified handType - exclude rather than guess
        if is_two_hand:
            return "weapon_2h"  # own pool, own settings/baseline - see the 2H section below
        return "weapon_dual_wield"
    return TYPE_TO_SLOT.get(t)


def tier_from_text(text: str, zone_by_id: dict) -> str | None:
    """Fallback for items the DB has no sources[] data for at all (e.g. the
    Gronnstalker's Armor set - setId 669, no sources field in db.json,
    presumably a custom loot-table item on this server rather than a normal
    honor/arena purchase) but Wowhead's curated text still names a real zone
    ("Drop: The Illidari Council (Black Temple)"). Matches the tier's own
    zone names as substrings of that text rather than leaving these items
    stuck in "Other" just because the DB's own source metadata is missing."""
    for tier, zids in TIER_ZONES.items():
        for zid in zids:
            zname = zone_by_id.get(zid)
            if zname and zname in text:
                return tier
    return None


# Real Stat enum id (common.proto) for Armor Penetration Rating. Flagged
# separately from the normal MV number (not folded into it) because ArP's
# real value is nonlinear in a way a single-item MV against one baseline
# can't fully capture: each ArP item's marginal DPS depends on how much ArP
# is already stacked from OTHER equipped items, up to the 100%-armor-
# reduction cap - two ArP items evaluated independently can each look
# modest while their real combined value (a joint sim) is bigger than the
# sum, or a second ArP item can look great in isolation while actually
# pushing the character past the cap where it stops helping at all. Per the
# user (2026-08-25): flag it so a human knows to sanity-check ArP-heavy
# multi-item picks, rather than silently trust one-at-a-time MV ranking for
# a stat this pipeline doesn't currently joint-sim (Stage 5's interaction
# matrix, which would catch this properly, is dropped from the active
# pipeline - see the 2026-08-23 NOTES.md entry on why).
ARMOR_PEN_STAT_ID = "23"


def item_arp_rating(item: dict) -> int:
    """Real Armor Penetration Rating on an item's base stats (gems/enchants
    not included - the common, visible case is the item's own itemization,
    not a gem choice)."""
    if not item:
        return 0
    return item.get("scalingOptions", {}).get("0", {}).get("stats", {}).get(ARMOR_PEN_STAT_ID, 0)


def describe_source_and_tier(item: dict, npc_by_id: dict, zone_by_id: dict) -> tuple[str, str, int | None]:
    for s in item.get("sources", []):
        if "drop" in s:
            zid = s["drop"].get("zoneId")
            npc = npc_by_id.get(s["drop"].get("npcId"))
            zone = zone_by_id.get(zid, f"zone {zid}")
            tier = next((t for t, zones in TIER_ZONES.items() if zid in zones), "Other drop")
            desc = f"Drop: {npc} ({zone})" if npc else f"Drop: ({zone})"
            return desc, tier, None
        if "crafted" in s:
            prof = idb.PROFESSION_NAMES.get(s["crafted"].get("profession"), "Profession")
            return f"Crafted: {prof}", "Crafted", s["crafted"].get("spellId")
        if "rep" in s:
            return "Reputation reward", "Reputation reward", None
    # Backlog #15 (2026-09-06, per the user's own suggestion) - a real,
    # STRUCTURAL rule, not a per-item guess: every real "Gladiator's"-named
    # item in TBC is PvP-sourced, a 100% reliable Blizzard naming convention
    # across every arena season (Merciless/Vengeful/Brutal/plain Gladiator's).
    # Deliberately says "PvP purchase", not "Arena purchase" specifically -
    # real correction, caught by the user directly: a given season's
    # Gladiator's gear starts as an arena-rating-gated arena-point purchase,
    # but becomes plain honor-purchasable (no rating needed) once a later
    # season replaces it as current - the exact mechanism depends on which
    # season is live when a character is being profiled, not something the
    # name alone (or this rule) can resolve, so it isn't claimed. Confirmed
    # via check_missing_sources.py: 6 of the 255 real gap items match this
    # (Gladiator's Slicer/Cleaver, Merciless Gladiator's Quickblade/Maul,
    # Vengeful Gladiator's Staff/Rifle) - correctly "no source" in the DB's
    # own drop/crafted/rep schema (PvP purchases have no real drop
    # location), not a gap to individually verify.
    if "gladiator's" in item.get("name", "").lower():
        tier = PHASE_TO_TIER_ZONE_KEY.get(item.get("phase"), "Other")
        return "PvP purchase (Arena/Honor)", tier, None
    # Backlog #15 - real, structural tier-token rule (see _TIER_TOKEN_DESC's
    # own comment above for the full real evidence) - checked before the
    # individual overlay/generic fallback below since a real raid tier set
    # is identifiable structurally (a real setId) rather than needing
    # per-item curation the way a standalone accessory does.
    set_id = item.get("setId")
    if set_id:
        set_phase = _SET_MIN_PHASE.get(set_id)
        token_desc = _TIER_TOKEN_DESC.get(set_phase)
        if token_desc:
            return token_desc, PHASE_TO_TIER_ZONE_KEY[set_phase], None
    # Backlog #15 - real, individually-verified overlay, checked BEFORE the
    # generic phase-bucket fallback below (a real, specific source beats a
    # generic "Source unclear" bucket) but only ever reached once the real
    # DB source above has already come back empty - see _SOURCE_OVERLAY's
    # own comment for why this ordering is load-bearing, not incidental.
    overlay_entry = _SOURCE_OVERLAY.get(str(item.get("id")))
    if overlay_entry:
        tier = overlay_entry.get("tier") or PHASE_TO_TIER_ZONE_KEY.get(item.get("phase"), "Other")
        return overlay_entry["desc"], tier, None
    # Real DB gap fallback (see PHASE_TO_TIER_ZONE_KEY's own comment above) -
    # no `sources` entry at all, but the item's own real `phase` field still
    # reliably places it in a real tier bucket, so it doesn't get silently
    # dumped in "Other" just because this one field is missing.
    tier = PHASE_TO_TIER_ZONE_KEY.get(item.get("phase"))
    if tier:
        return "Source unclear (real DB gap - see NOTES.md 2026-08-31)", tier, None
    return "Source unclear", "Other", None


def run_with_progress(fn, items: list, label: str, workers: int = MAX_WORKERS, log_every_pct: int = 5,
                       progress_cb=None, stage_sequence: list[str] | None = None) -> list:
    """Same concurrent map as `ThreadPoolExecutor(...).map(fn, items)`, plus
    periodic "label: done/total (pct%)" progress lines - real precursor to
    the GUI progress indicator already noted in CLAUDE.md's future-scope
    section (candidates screened so far / total, not a blank wait), now
    real: progress_cb(dict) is called at the same cadence as the print, so a
    GUI caller gets live stage/done/total/pct without scraping stdout, plus
    a real per-stage eta_seconds (linear extrapolation from this stage's own
    live rate) and stage_index/stage_total (per the user, 2026-08-25 - "so
    people know there's something else coming") when `stage_sequence` (the
    real, profile-aware ordered list of every stage this run will emit,
    built once in main()) is passed through. Order of the returned list is
    NOT the same as `items` (completion order, not submission order) - both
    call sites here already only build a dict/set
    from the results, so this is safe; a future caller that needs input
    order preserved would need to carry an index through `fn` itself."""
    total = len(items)
    if total == 0:
        return []
    results = []
    done = 0
    last_logged_pct = -1
    stage_start = time.time()
    stage_index = stage_sequence.index(label) + 1 if stage_sequence and label in stage_sequence else None
    stage_total = len(stage_sequence) if stage_sequence else None
    # Real bug the user caught live, 2026-08-25: a plain "elapsed-since-
    # stage-start / done" rate barely moves once done is large, so a single
    # burst of several items finishing near-simultaneously (MAX_WORKERS
    # threads, real items with real varying per-call cost) swung the whole-
    # stage average and the shown ETA visibly jumped around instead of
    # counting down. A single-tick exponential moving average was tried
    # first and still wasn't robust enough - caught live, same session: it
    # pinned at "0:00" for over 20 real seconds while 53 of 153 items
    # (a real, confirmed ~1 item/sec rate) genuinely remained, because one
    # fast concurrent burst inflated the "recent rate" and even a 0.3 alpha
    # didn't damp a single outlier tick enough. Replaced with a real rolling
    # window instead (last up to RATE_WINDOW_SIZE ticks' worth of done/time,
    # rate computed oldest-to-newest across the whole window) - a single
    # lumpy tick can only ever be 1 sample in the window, not the dominant
    # signal. Widened 5->9 the same session (still not smooth enough per
    # the user's own live feedback - see app.js's blended-recheck comment
    # for the matching frontend-side half of this fix).
    rate_window: list[tuple[float, int]] = [(stage_start, 0)]
    RATE_WINDOW_SIZE = 9
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn, item) for item in items]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            done += 1
            pct = done * 100 // total
            if done == total or (pct != last_logged_pct and pct % log_every_pct == 0):
                print(f"{label}: {done}/{total} ({pct}%)")
                if progress_cb:
                    # Per-stage ETA only (per the user, 2026-08-25 - a whole-
                    # run estimate was considered and dropped: later stages'
                    # real item counts aren't known until earlier ones
                    # finish, and per-item cost varies ~60x between a 500-
                    # iteration screen and a 30000-iteration resolve, so any
                    # whole-run number would be a rough guess dressed up as
                    # precision).
                    now = time.time()
                    rate_window.append((now, done))
                    if len(rate_window) > RATE_WINDOW_SIZE:
                        rate_window.pop(0)
                    oldest_time, oldest_done = rate_window[0]
                    interval = now - oldest_time
                    items_since = done - oldest_done
                    eta_seconds = ((total - done) * interval / items_since) if interval > 0 and items_since > 0 else None
                    progress_cb({"stage": label, "done": done, "total": total, "pct": pct,
                                 "eta_seconds": eta_seconds,
                                 "stage_index": stage_index, "stage_total": stage_total})
                last_logged_pct = pct
    return results


def main(name_realm: str, phase: str, profile_dir: str, progress_cb=None,
         duration: int | None = None):
    """name_realm e.g. "Lerynia-Thunderstrike"; phase e.g. "phase3" (matches
    reference_bis/<phase>.json and gui/api.py's PHASES list). profile_dir is
    REQUIRED, no default - see core/character_profiles.py's docstring for
    why: this used to default to Survival Hunter's own profile (a leftover
    from before multi-profile support existed), and that silent default
    twice caused a real, wrong sweep for a non-Hunter character (found live
    2026-08-25, in both cli/gear.py and this session's own ad-hoc test
    scripts) before either caller passed profile_dir explicitly. Resolve it
    via core/character_profiles.py's SUPPORTED_CHARACTERS map, never guess.
    progress_cb, if given, is
    called with {"stage", "done", "total", "pct"} at the same points this
    already prints progress to stdout (see run_with_progress) plus a few
    milestone-only stages (no done/total, just "stage") bracketing the parts
    of the run that aren't a parallel item sweep.

    duration: real fight-length override in seconds (None = use the
    profile's own settings_template.json default, currently 180s for every
    profile - see settings_builder.py's _ENCOUNTER). Per the user
    (2026-08-25): real encounters vary a lot in length (some raid fights
    run ~90s, others much longer), and which items rank best can genuinely
    depend on fight length (their own real example: Teeth of Gruul's real
    verdict for Béarforceone). Every sim_cache entry's key already includes
    a hash of the full settings dict (settings_fingerprint(), excluding
    only player.equipment.items) - a different duration is a different
    fingerprint is a different cache entry, so overriding it here can never
    silently serve a wrong-duration cached number."""
    # Populated below once `profile` loads (weapon_topology decides whether
    # the 2H section's two stages are even reachable this run) - a plain
    # list mutated in place (`[:]=`), not reassigned, so this closure and
    # every run_with_progress() call site that receives it by reference see
    # the real, final sequence once it's built, even though milestone() and
    # its first call ("Starting sweep") both fire before profile loads.
    stage_sequence: list[str] = []

    def milestone(stage: str):
        if progress_cb:
            idx = stage_sequence.index(stage) + 1 if stage in stage_sequence else None
            progress_cb({"stage": stage, "done": None, "total": None, "pct": None, "eta_seconds": None,
                         "stage_index": idx, "stage_total": len(stage_sequence) or None})

    phase_num = int(phase.removeprefix("phase"))
    # Backlog #13 (CLAUDE.md Future Scope) - real, required part of every
    # output filename below, so a character reassigned to a different sim
    # profile doesn't silently overwrite her prior spec's report/ledger -
    # see core/report_storage.py's own docstring for the full real bug.
    profile_dir_name = os.path.basename(os.path.normpath(profile_dir))
    # Backlog #5 (CLAUDE.md Future Scope) - real loot sources this character
    # has chosen to exclude, layered under the phase gate above (see
    # source_scope.py's docstring for the real motivating gap). Empty for
    # every character that hasn't touched this GUI setting - same "read
    # local_config directly" pattern RESOLVE_ITERATIONS already established.
    excluded_source_keys = set(local_config.source_scope_exclusions(name_realm))
    milestone("Starting sweep")
    start = time.time()
    npc_by_id = {n["id"]: n["name"] for n in idb.npcs()}
    zone_by_id = {z["id"]: z["name"] for z in idb.zones()}

    char_path = os.path.join(USER_DATA_DIR, "characters", name_realm, "character.json")
    char = repo_root.load_json(char_path)

    # Stage 6 (multi-class support): load this profile's real manifest and
    # wire every per-profile subsystem's active state from it, once, here -
    # everything downstream (gem_optimizer, set_bonus, stat_weights) reads
    # this active state rather than a hardcoded Hunter constant. For
    # Survival Hunter specifically this must reproduce today's exact
    # existing values (Stage 6.0's regression check) - see profile.json.
    # Shadows the module-level defaults of the same name (both point at the
    # same files when profile_dir == PROFILE_DIR, today's only real caller) -
    # every nested function below (screen_one, confirm_one, ...) is defined
    # inside main() and so closes over these locals, not the module globals,
    # once a future Stage 6.1/6.2 caller passes a different profile_dir.
    SETTINGS_TEMPLATE = os.path.join(profile_dir, "settings_template.json")
    # Stage 6.2 finding: a separate 2H settings variant is a real, Hunter-
    # specific need (her rotation itself changes - a "melee weave" APL
    # constant only relevant when using a 2H weapon in melee as a Survival
    # Hunter). A profile whose rotation doesn't change with weapon choice
    # (Balance Druid: still just casting spells either way) has no reason to
    # need a second settings file at all - falls back to the real
    # SETTINGS_TEMPLATE itself rather than requiring every
    # one_hand_plus_offhand_item profile to hand-maintain a redundant copy.
    _settings_2h_path = os.path.join(profile_dir, "settings_template_2h.json")
    SETTINGS_2H = _settings_2h_path if os.path.exists(_settings_2h_path) else SETTINGS_TEMPLATE
    POOL_PATH = os.path.join(profile_dir, "candidate_pool.json")

    # Real fight-duration override (see main()'s own docstring for why this
    # is safe re: sim_cache) - writes a real, distinct temp settings file
    # per (profile, duration) rather than mutating the profile's own
    # committed settings_template.json, so the on-disk file a human might
    # be reading/diffing never silently changes. Unique per profile+duration
    # (not per-run) so repeated runs at the same duration reuse the same
    # temp file/cache entries instead of piling up garbage.
    actual_duration = duration
    if duration is not None:
        cache_dir = os.path.join(USER_DATA_DIR, "cache")
        os.makedirs(cache_dir, exist_ok=True)
        profile_tag = os.path.basename(os.path.normpath(profile_dir))
        has_real_2h_settings = os.path.exists(_settings_2h_path)

        def _override_duration(path: str, tag: str) -> str:
            settings = repo_root.load_json(path)
            settings["encounter"]["duration"] = duration
            out_path = os.path.join(cache_dir, f"_settings_{profile_tag}_{tag}_d{duration}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(settings, f)
            return out_path

        overridden_2h = _override_duration(SETTINGS_2H, "2h") if has_real_2h_settings else None
        SETTINGS_TEMPLATE = _override_duration(SETTINGS_TEMPLATE, "main")
        SETTINGS_2H = overridden_2h if overridden_2h else SETTINGS_TEMPLATE
    else:
        actual_duration = repo_root.load_json(SETTINGS_TEMPLATE)["encounter"]["duration"]

    # Real, permanent (never swapped below) references to the real
    # no-weave/weave-on files, captured HERE (after any real duration
    # override above, so they stay correctly duration-adjusted) - the 2H
    # Weapon Options / Dual-Wield Alternative sections print real labels
    # ("weave ON"/"weave OFF") that must stay honest regardless of which
    # file the main sweep below ends up treating as "primary".
    SETTINGS_NO_WEAVE_REAL = SETTINGS_TEMPLATE
    SETTINGS_WEAVE_REAL = SETTINGS_2H

    # Backlog #20 follow-up (2026-09-06, per the user's own real, live
    # finding): a weave-capable profile's real DPS differs by 500+ points
    # depending on whether she melee-weaves or plays pure-ranged "turret" -
    # this used to be silently baked into which file happened to be
    # "primary" (SETTINGS_TEMPLATE, used for the WHOLE report's tier list,
    # every slot's own MV) vs which was only ever consulted by the
    # 2H-options/dual-wield-alternative side analysis. Per the user: "we
    # should not assume if the use is weaving or not" - a real, explicit,
    # per-character GUI choice (local_config.melee_weave_mode()) now
    # decides which file is primary for the WHOLE sweep. The `!=` check
    # means this only ever does anything for a profile that actually HAS a
    # real weave variant (Survival/Beastmastery Hunter) - every other
    # profile's SETTINGS_2H already equals SETTINGS_TEMPLATE by the
    # fallback above, so melee_weave_mode() is never even consulted for
    # e.g. a caster, matching the user's own reminder that this choice only
    # exists for Hunters. Only SETTINGS_TEMPLATE/SETTINGS_2H (which decide
    # what the MAIN sweep uses) are swapped - SETTINGS_NO_WEAVE_REAL/
    # SETTINGS_WEAVE_REAL above stay fixed, so the 2H-Options/Dual-Wield-
    # Alternative sections' own "weave ON"/"weave OFF" labels can never go
    # stale just because the primary settings changed.
    if SETTINGS_2H != SETTINGS_TEMPLATE and local_config.melee_weave_mode(name_realm) == "weave":
        SETTINGS_TEMPLATE, SETTINGS_2H = SETTINGS_2H, SETTINGS_TEMPLATE

    # Real, per-character Combat Potion choice for a real caster profile
    # (2026-09-06, per the user: "some classes like arcane mage gain more
    # dps from mana pot over destro pot" - see
    # local_config.consumable_potion_id()'s own docstring for the full real
    # motivation/data). Only ever does anything for the curated
    # CASTER_POTION_PROFILES set - a caster profile never has a real
    # SETTINGS_2H weave variant (no overlap with WEAVE_CAPABLE_PROFILES),
    # so only SETTINGS_TEMPLATE itself needs mutating here.
    if profile_dir_name in CASTER_POTION_PROFILES:
        chosen_potion_id = local_config.consumable_potion_id(name_realm, profile_dir)
        real_default_potion_id = repo_root.load_json(os.path.join(profile_dir, "consumables.json"))["potId"]
        if chosen_potion_id != real_default_potion_id:
            settings = repo_root.load_json(SETTINGS_TEMPLATE)
            settings["player"]["consumables"]["potId"] = chosen_potion_id

            def _replace_item_id(node):
                if isinstance(node, dict):
                    if node.get("itemId") == real_default_potion_id:
                        node["itemId"] = chosen_potion_id
                    for v in node.values():
                        _replace_item_id(v)
                elif isinstance(node, list):
                    for v in node:
                        _replace_item_id(v)

            # Real, necessary beyond the plain potId swap above: at least 2
            # of the 7 real caster profiles (Balance Druid, Shadow Priest -
            # confirmed via direct grep during planning) ALSO hardcode their
            # potion's exact itemId directly inside their own rotation's
            # explicit mana-gated cast action, on top of the generic
            # Major-Cooldown auto-cast the plain potId swap alone drives
            # (`sim/tbc-new/sim/core/consumes.go`'s `registerPotionCD()`) -
            # a potId-only swap would leave those two profiles' rotations
            # still trying to cast the OLD, no-longer-registered potion. A
            # generic recursive replace is a safe no-op for the other 5
            # profiles with no such reference, real and necessary for the 2
            # that have one.
            _replace_item_id(settings)
            cache_dir = os.path.join(USER_DATA_DIR, "cache")
            os.makedirs(cache_dir, exist_ok=True)
            out_path = os.path.join(cache_dir, f"_settings_{profile_dir_name}_potion{chosen_potion_id}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(settings, f)
            SETTINGS_TEMPLATE = out_path

    profile = repo_root.load_json(os.path.join(profile_dir, "profile.json"))
    # Real, ordered list of every stage this run will show, for the GUI's
    # "Stage X of Y" indicator - the 2H section (its own two stages) is
    # structurally unreachable for a two_hand profile (its mainhand IS the
    # 2H slot already, routed through the normal candidates/tiers pipeline -
    # see slot_for_item()'s own docstring), known upfront from
    # weapon_topology alone. Whether weapon_2h_candidates then turns out
    # non-empty for a dual_wield/one_hand_plus_offhand_item profile isn't
    # knowable this early - an edge-case profile with zero real 2H
    # candidates would slightly overcount Y, an accepted, honest
    # simplification for an informational indicator, not a hard contract.
    #
    # is_weave_profile computed here (not just down at the 2H section
    # itself, where it used to live) because the GUI's stage count needs to
    # know upfront whether the real no-weave 2H comparison (Stage 6.3,
    # 2026-08-25 - per the user, "we do want to build the 2 hand without
    # weave for survival too") will run three EXTRA stages beyond the
    # weave-on pair - real, distinct settings/APL only exists for a melee-
    # weave-capable profile (Survival Hunter today; Beastmastery Hunter
    # once built shares this same code path), same real/fallback
    # distinction SETTINGS_2H already encodes.
    is_weave_profile = SETTINGS_2H != SETTINGS_TEMPLATE
    stage_sequence[:] = [
        "Starting sweep", "Building candidate pool", "Computing baseline",
        "Screening", "Confirming", "Resolving", "Sidegrade-checking", "Raid-AP lookups",
    ]
    if profile["weapon_topology"] != "two_hand":
        stage_sequence.extend(["Screening 2H weapons", "Resolving 2H", "Resolving top 2H picks"])
        if is_weave_profile:
            stage_sequence.extend(["Screening 2H weapons (no weave)", "Resolving 2H (no weave)",
                                    "Resolving top 2H picks (no weave)"])
    stage_sequence.append("Done")
    stat_weights.set_active(stat_weights.load(profile_dir))
    time_horizon.set_current_phase(phase_num)
    time_horizon.set_active_ref_dir(os.path.join(profile_dir, "reference_bis"))
    gc.set_active_default_gem(profile["primary_gem_id"])
    # Real, sim-verified per-slot BiS enchants (see gear_config.py's own
    # comment on why this exists) - optional file, same "honest empty
    # default" pattern as chase_bonus_gems.json for a profile that hasn't
    # had this built yet.
    _default_enchants_path = os.path.join(profile_dir, "default_enchants.json")
    default_enchants = (repo_root.load_json(_default_enchants_path)
                         if os.path.exists(_default_enchants_path) else {})
    gc.set_active_default_enchants(default_enchants)
    chase_bonus = repo_root.load_json(os.path.join(profile_dir, "chase_bonus_gems.json"))
    gem_optimizer.set_active_chase_bonus_ids(set(chase_bonus["item_ids"]))
    set_bonus.set_active_item_sets_go(os.path.join(REPO_ROOT, "sim", "tbc-new", profile["set_bonus_go_source"]))
    mv.set_shared_slot_groups(profile["weapon_topology"])
    known_professions = {p["name"] for p in char["character"]["professions"]}
    pool_key_to_slots = opt.build_pool_key_to_slots(profile["weapon_topology"])

    owned_items = char["equipped"]["items"]
    # Real bug found and fixed 2026-08-31: EQUIPPED gear is still fully
    # excluded (already wearing it, nothing to recommend), but bags/bank
    # items are now real candidates again, tagged with owned_location
    # instead of being silently hidden. Root cause: a multi-spec player
    # logged out in a DIFFERENT spec's gear (e.g. Resto healing gear
    # equipped, real Elemental T4-T6 pieces sitting in bags/bank from
    # before the respec) had her own real, correct DPS gear excluded from
    # her own Elemental report as "already owned, not an acquisition
    # target" - true in spirit (she does own it) but the wrong UI verdict
    # (per the user: "no trace of any elemental tier pieces" is exactly
    # what this caused). Real fix, per the user: still real candidates,
    # still real MV numbers, just visibly tagged "In Bags"/"In Bank" so a
    # reader knows it's a re-equip, not a farm/AH target - not fixing the
    # baseline DPS itself (still her real, literal equipped-gear DPS,
    # honestly low if she's equipped for a different spec - that's a
    # separate, real "wrong spec equipped" data-quality signal, not
    # something to silently paper over here).
    owned_equipped_ids = {it["id"] for it in owned_items if it}
    owned_bag_ids = {it["id"] for it in char["owned"]["bags"] if it}
    owned_bank_ids = {it["id"] for it in char["owned"]["bank"] if it}

    acquisition_status = acquisition_gate.load_status(name_realm)

    candidates = opt.load_candidates(POOL_PATH, owned_items, known_professions, pool_key_to_slots)
    # Real bug found 2026-08-25: candidate_pool.json for a wowsims-preset-
    # sourced profile (Warrior/Druid) is a union across every phase wowsims
    # ships (P2-P5), unlike Hunter's own hand-curated candidate_pool_survival
    # .json which only ever contained Phase 3 items to begin with - so a
    # "Phase 3 Ledger" was listing real Phase 4/5 raid loot (Black Temple,
    # even Sunwell) as an actionable upgrade. sweep_all_loot.py's own
    # eligible() already gates its own additions on item["phase"] <=
    # max_phase; this pool never went through that gate at all. Same real DB
    # "phase" field, same standard - an item whose phase can't be determined
    # (id not in idb, shouldn't happen) is kept rather than silently
    # dropped, since there's no real evidence it's out of scope.
    for slot, cands in candidates.items():
        kept = []
        for c in cands:
            if not c.item_id:
                kept.append(c)
                continue
            db_item = idb.by_id(c.item_id)
            if db_item is not None and db_item.get("phase", 0) > phase_num:
                continue
            # Same source-scope check the swept pool goes through below
            # (sweep_all_loot.run()) - one shared implementation
            # (source_scope.is_in_scope()), since a curated-pool candidate
            # resolves to the same real DB item with the same real
            # `sources` field.
            if db_item is not None and not source_scope.is_in_scope(db_item, excluded_source_keys):
                continue
            kept.append(c)
        candidates[slot] = kept
    curated_ids = {c.item_id for cands in candidates.values() for c in cands if c.item_id}

    # Backlog #20 (2026-09-06) - real, complete fix per the user's explicit
    # requirement ("No partial fixes... WE have to compare dw to 2hand No
    # Matter what the starting point is"): a dual_wield-topology profile's
    # shared mainhand/offhand pool assumes she's actually dual-wielding two
    # 1H weapons right now. When she's genuinely 2H-equipped instead (a
    # real, live case - Survival/Beastmastery Hunter can legitimately be in
    # either state), testing a 1H candidate into either slot alone compares
    # against an illegal resulting gear state (2H mainhand + a lone 1H
    # item) - not just "worse", genuinely never a real option. The
    # unconditional per-slot testing that produced this bug is pulled out
    # of the normal pipeline entirely below; `dw_pair_candidates` collects
    # every real 1H weapon candidate (curated here + full-DB sweep
    # additions, see the sweep_items loop further below - curated_ids
    # above is computed BEFORE this clears mainhand/offhand, so the sweep
    # loop below correctly treats these ids as "already known" and routes
    # them into dw_pair_candidates too, never double-adding them) for a
    # real, honest joint best-pair search instead (see "Dual-wield
    # alternative analysis" further down) - this answers the real question
    # ("does dual-wield beat my current 2H") regardless of which one she
    # happens to have equipped right now, rather than silently hiding it.
    # Real, caught-before-shipping bug: this must be gated to dual_wield
    # topology specifically - a one_hand_plus_offhand_item profile (Balance
    # Druid) can ALSO legitimately have a 2H weapon equipped (her own real
    # "weapon_2h" side-pool already exists for exactly that), but her
    # "offhand" slot there is a real, independent single-item pool (a
    # caster off-hand frill, never itself a dual-wield weapon) - routing
    # her through this dual_wield-specific logic would incorrectly clear
    # that unrelated pool. Only Survival/Beastmastery Hunter ever have a
    # real "weapon_dual_wield" shared pool to begin with.
    real_mainhand_is_two_hand = (profile["weapon_topology"] == "dual_wield"
                                  and opt.real_gear_is_two_hand_mainhand(owned_items))
    dw_pair_candidates: list[opt.Candidate] = []
    seen_dw_ids: set[int] = set()
    if real_mainhand_is_two_hand:
        for c in candidates.get("mainhand", []) + candidates.get("offhand", []):
            if c.item_id and c.item_id not in seen_dw_ids and not c.excluded_reason:
                seen_dw_ids.add(c.item_id)
                dw_pair_candidates.append(c)
        candidates["mainhand"] = []
        candidates["offhand"] = []
    # Curated-pool items' real Wowhead source text/tier, so they show up in
    # the right tier bucket too, not just the sweep additions.
    curated_source_text = {}
    ref_path = os.path.join(profile_dir, "reference_bis", f"{phase}.json")
    ref_bis = repo_root.load_json(ref_path)
    for entries in ref_bis["slots"].values():
        for e in entries:
            curated_source_text[e["item"]] = e["source"]

    # Pure sub-second filter, no sim calls - run fresh every time rather than
    # trusting a possibly-stale cached file (this used to be a separate,
    # easy-to-forget manual step; see the plan's Context section).
    milestone("Building candidate pool")
    sweep_path = sweep_all_loot.run(phase_num, profile_dir, excluded_source_keys)
    sweep_items = repo_root.load_json(sweep_path)
    owned_by_id = {it["id"]: it for it in owned_items if it}
    meta_gem_id = opt.find_owned_meta_gem(owned_items)
    item_meta = {}  # item_id -> (source_text, tier)
    new_count = 0

    # For a dual_wield profile (Hunter), 2H weapons get their own pool,
    # evaluated separately below (own settings variant - meleeWeave, own
    # baseline with the offhand physically empty) - they must NOT flow
    # through the shared `candidates`/all_candidates machinery further down,
    # which assumes one global SETTINGS_TEMPLATE and a normal DW offhand -
    # exactly the "wrong number, not just worse" trap this was excluded
    # from before. For a two_hand profile, slot_for_item() itself already
    # routes 2H weapons straight to "mainhand" through the normal pipeline
    # instead (Stage 6.1 fix) - this pool simply stays empty for such a
    # profile, which is what correctly skips the whole Hunter-only 2H
    # side-analysis section below.
    weapon_2h_candidates: list[opt.Candidate] = []

    for item in sweep_items:
        if item["id"] in curated_ids:
            continue
        slot = slot_for_item(item, profile["weapon_topology"])
        if slot is None:
            continue
        req_prof = idb.required_profession_name(item)
        if req_prof and req_prof not in known_professions:
            continue
        if slot == "weapon_dual_wield" and real_mainhand_is_two_hand:
            # Backlog #20 - this full-DB sweep-additions path builds its
            # own opt.Candidate objects directly, bypassing
            # optimizer.py's load_candidates() entirely - so a 1H
            # candidate found ONLY here (not in the curated pool) still
            # needs the same real joint-search routing as a curated one
            # (see dw_pair_candidates' own construction above). This is
            # in fact where nearly every real "Weapon" tier candidate
            # actually comes from - the first attempted version of this
            # fix only handled the curated-pool path and had zero visible
            # effect on a live resweep for exactly this reason.
            if item["id"] not in seen_dw_ids:
                seen_dw_ids.add(item["id"])
                owned_here = owned_by_id.get(item["id"])
                gems = owned_here.get("gems") if owned_here else opt.gems_for_item(item, meta_gem_id)
                enchant = 0
                for s in ("mainhand", "offhand"):
                    enchant = opt.achievable_enchant(gc.get_active_default_enchants().get(s, 0), known_professions)
                    if enchant:
                        break
                dw_pair_candidates.append(opt.Candidate(item["name"], item["id"], enchant, gems))
                item_meta[item["id"]] = describe_source_and_tier(item, npc_by_id, zone_by_id)
                new_count += 1
            continue

        # Same treatment as optimizer.py's load_candidates() (Missing
        # Enchants fix, 2026-08-25): every candidate here - owned or not -
        # unconditionally gets the real, sim-verified BiS enchant for the
        # slot, never "whatever she currently has equipped there" or an
        # owned-but-not-worn item's own literal enchant. DPS*(P) assumes
        # the fully-optimal loadout, gems and enchants both.
        default_enchants = gc.get_active_default_enchants()

        if slot == "weapon_2h":
            owned_here = owned_by_id.get(item["id"])
            gems = owned_here.get("gems") if owned_here else opt.gems_for_item(item, meta_gem_id)
            enchant = opt.achievable_enchant(default_enchants.get("mainhand", 0), known_professions)
            weapon_2h_candidates.append(opt.Candidate(item["name"], item["id"], enchant, gems))
            item_meta[item["id"]] = describe_source_and_tier(item, npc_by_id, zone_by_id)
            new_count += 1
            continue

        target_slots = {
            "weapon_dual_wield": ["mainhand", "offhand"],
            "ring": ["ring1", "ring2"],
            "trinket": ["trinket1", "trinket2"],
        }.get(slot, [slot])

        default_enchant = 0
        for s in target_slots:
            default_enchant = opt.achievable_enchant(default_enchants.get(s, 0), known_professions)
            if default_enchant:
                break

        owned_here = owned_by_id.get(item["id"])
        gems = owned_here.get("gems") if owned_here else opt.gems_for_item(item, meta_gem_id)
        cand = opt.Candidate(item["name"], item["id"], default_enchant, gems)

        for s in target_slots:
            candidates.setdefault(s, []).append(cand)
        item_meta[item["id"]] = describe_source_and_tier(item, npc_by_id, zone_by_id)
        new_count += 1

    # Curated items: tier + description from the DB by id (never by name -
    # several names collide across multiple ids, e.g. "Band of Eternity" is
    # 12 distinct ids; a name-keyed lookup here silently pulled a random
    # same-named item's zone/source instead of the actual candidate's,
    # which is exactly how Gronnstalker's Leggings/Gloves ended up
    # miscategorized). Wowhead's text is used only as a nicer-formatted
    # override when it exists; the DB-derived description is the fallback
    # so P2-only reference items (missing from the P3 curated_source_text
    # dict entirely) still get a real source instead of going blank.
    for cands in candidates.values():
        for c in cands:
            if c.item_id in item_meta or c.item_id is None:
                continue
            db_item = idb.by_id(c.item_id)
            db_desc, tier, craft_spell_id = describe_source_and_tier(db_item, npc_by_id, zone_by_id) if db_item else ("Source unclear", "Other", None)
            source = curated_source_text.get(c.name) or db_desc
            if tier == "Other" and source != db_desc:
                tier = tier_from_text(source, zone_by_id) or tier
            item_meta[c.item_id] = (source, tier, craft_spell_id)

    # Owned items stay IN the candidate pool always (set-bonus progression
    # below needs to see a bagged/banked piece to correctly credit it toward
    # a set bonus). EQUIPPED items are filtered out at the final report-row
    # step (already wearing it, nothing to recommend); bags/bank items stay
    # visible as real candidates too now, tagged owned_location so the
    # report can badge them "In Bags"/"In Bank" instead of implying she
    # needs to go acquire something she already owns (real bug fixed
    # 2026-08-31 - see PHASE_TO_TIER_ZONE_KEY's own comment for the related
    # tier-bucketing fix from the same real user report).
    print(f"Curated pool: {len(curated_ids)} items. Sweep added {new_count} new candidates "
          f"({len(owned_equipped_ids)} equipped - hidden from acquisition tiers; "
          f"{len(owned_bag_ids | owned_bank_ids)} in bags/bank - shown, tagged owned_location).\n")

    item_slot_label = {}
    for slot, cands in candidates.items():
        label = SLOT_DISPLAY.get(slot, slot.capitalize())
        for c in cands:
            if c.item_id is not None:
                item_slot_label.setdefault(c.item_id, label)

    mv.set_slot_hints(candidates)
    milestone("Computing baseline")
    baseline_config = opt.build_owned_config(owned_items, known_professions)
    baseline_screen = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, SCREEN_ITERATIONS, opt.SEED)
    # Real bug found and fixed Stage 6.1: this flag used to be dead config
    # (always computed regardless) - harmless for Warrior at first only by
    # accident, because Hunter's own raid_buffs_overlay.json still had
    # exposeWeaknessUptime/exposeWeaknessHunterAgility declared Hunter-side,
    # so measured_ew_uptime() found nothing for a non-Hunter sim. Moving
    # those into _shared/raid_buffs_received.json (this stage's own real
    # boundary decision - Expose Weakness being up on the target affects
    # everyone's damage, not just Lerynia's) made that accident stop being
    # true: the debuff now shows up as active in EVERY profile's sim, so an
    # ungated baseline_agility would compute a real number for Warrior too
    # - one based on RUBÁN's own Agility, which has nothing to do with a
    # debuff only LERYNIA casts. Actually gating on the flag now, not
    # optional cleanup.
    baseline_agility = None
    if profile["raid_ap_contribution"]["enabled"]:
        # Deterministic (no Monte Carlo iterations involved - see valuation.get_agility),
        # computed once and reused for every candidate below, never per-candidate.
        baseline_agility = mv.valuation.get_agility(SETTINGS_TEMPLATE, baseline_config)
    print(f"Baseline @ {SCREEN_ITERATIONS} iter (screening): combined={baseline_screen['combined']:.1f}, "
          f"Agility={baseline_agility}\n")

    # Set-bonus rescue check (§1's whole reason to exist: a piece can look
    # like a downgrade alone and still be worth taking because it's on the
    # path to a set bonus - never drop those silently, flag them instead).
    set_names = {idb.by_id(c.item_id).get("setName")
                 for cands in candidates.values() for c in cands
                 if c.item_id is not None and idb.by_id(c.item_id) and idb.by_id(c.item_id).get("setName")}
    # Per user's ask: don't show every 1pc..5pc step (most piece counts
    # carry no bonus at all) - show the isolated value of each REAL bonus
    # threshold instead, holding total character stats constant via a
    # bonusStats correction so the number reflects the bonus's own
    # behavioral effect (a proc, a spell mod), not the raw stat difference
    # of whichever pieces happen to cross it. Thresholds come straight
    # from the sim's own Go source (set_bonus_thresholds), never guessed.
    set_notes_by_item: dict[int, str] = {}
    # Real per-threshold isolated bonus values, captured from the same sim
    # calls the note text above already pays for (isolate_bonus_value() -
    # never re-run separately below just to get the same number again).
    # Used to credit whichever specific candidate piece would actually be
    # the one crossing a threshold, given what she already owns of that
    # set elsewhere - see the "set bonus ranking credit" section below for
    # why a per-item leaderboard needs this instead of the flat isolated mv.
    threshold_values_by_set: dict[str, dict[int, float]] = {}
    for set_name in sorted(set_names):
        thresholds = set_bonus.set_bonus_thresholds().get(set_name, [])
        if not thresholds:
            continue
        parts = []
        any_real = False
        set_threshold_values: dict[int, float] = {}
        for threshold in thresholds:
            iso = set_bonus.isolate_bonus_value(SETTINGS_TEMPLATE, set_name, threshold,
                                                 candidates, baseline_config, SCREEN_ITERATIONS)
            if iso is None:
                continue
            tag = "" if iso["real"] else " (tied)"
            any_real = any_real or iso["real"]
            parts.append(f"{threshold}pc bonus {iso['isolated_value']:+.1f}{tag}")
            if iso["real"]:
                set_threshold_values[threshold] = iso["isolated_value"]
        # Only flag items with this note if at least one threshold is a
        # real (non-tied) bonus - matches the original gating intent (a
        # set with no meaningful bonus anywhere shouldn't count as a
        # "real upgrade" for achieved-BiS/report-inclusion purposes).
        if not parts or not any_real:
            continue
        # Which 4 of the 5 armor slots should actually hold the set piece,
        # per the user: guides almost always recommend 4pc, occasionally
        # all 5 (rare) or fewer (weak bonuses) - determined by real sim
        # comparison across all five leave-one-out combos, not assumed.
        combo = set_bonus.best_four_of_five(SETTINGS_TEMPLATE, set_name, candidates,
                                             baseline_config, owned_items, SCREEN_ITERATIONS,
                                             known_professions)
        if combo is not None:
            if combo["excluded_slot"] is not None:
                alt = combo["excluded_slot_alt"]
                alt_text = f", {alt['name']}" if alt else " (her current gear)"
                print(f"  Best combo for {set_name}: {', '.join(combo['best_combo_slots'])} "
                      f"(leave {combo['excluded_slot']} non-tier{alt_text}) - "
                      f"full 5pc is {combo['full_five_dps'] - combo['combined_dps']:+.1f} vs this (screened)")
            else:
                print(f"  Best combo for {set_name}: all 5 pieces ({combo['combined_dps']:.1f})")

        # Real bug, caught by the user (2026-08-24): the note used to get
        # attached to every piece of a set with ANY real bonus threshold
        # SOMEWHERE, regardless of whether that set is remotely competitive
        # with what she's already wearing - Beast Lord Armor's own 4pc bonus
        # is real in isolation, but her actual Rift Stalker Armor pieces
        # already strictly beat every Beast Lord combo (best_four_of_five
        # confirms this directly), so Beast Lord pieces (each -26 to -73 DPS
        # alone) were showing up in the "upgrades" list purely because they
        # carried a set_note, with no real case for switching to that set at
        # all. Gate on the SET's own best achievable DPS actually beating her
        # current baseline, not just "this bonus exists somewhere" - a set
        # `best_four_of_five` couldn't evaluate (fewer than 5 real tier
        # pieces available) still gets the note, since there's no real
        # transition number to compare against baseline in that case.
        #
        # Second real bug, same mechanism, caught by the user (2026-08-31):
        # `combined_dps` lets the excluded slot pick ANY real non-set
        # alternative, not just her current item there - gating on it
        # conflates "is this 4pc set worth it" with "is whatever unrelated
        # item won the excluded slot also worth it", which she'd want
        # regardless of this set. Real, live case: Beast Lord Armor's
        # winning combo swapped in Bow-stitched Leggings (not currently
        # worn) for the excluded legs slot - the gate said "beats baseline"
        # when the honest story was "4 Beast Lord pieces + an unrelated legs
        # upgrade beats baseline", not "the 4pc bonus is worth it". Gate on
        # `combined_dps_isolated` instead - same winning 4-piece combo, her
        # CURRENT gear held in the excluded slot - a true isolated
        # DPS*(P ∪ {4 set pieces}) − DPS*(P) comparison. `combined_dps`
        # itself is untouched and still used for the "best achievable
        # layout" console print/report just below.
        if combo is not None and combo["combined_dps_isolated"] <= baseline_screen["combined"]:
            continue

        note = f"part of {set_name}: " + " · ".join(parts)
        for _, cand in set_bonus.set_pieces_in_pool(set_name, candidates):
            set_notes_by_item[cand.item_id] = note
        threshold_values_by_set[set_name] = set_threshold_values

    if set_notes_by_item:
        print(f"Set-bonus check: {len(set_notes_by_item)} item(s) flagged across {len(set_names)} set(s).\n")

    seen_ids = set()
    all_candidates = []
    for cands in candidates.values():
        for c in cands:
            if c.item_id is not None and c.item_id not in seen_ids:
                seen_ids.add(c.item_id)
                all_candidates.append(c)

    # --- Pass 1: screen everything, cheap ---
    def screen_one(c):
        return c, mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_screen, SCREEN_ITERATIONS, opt.SEED)

    screened = run_with_progress(screen_one, all_candidates, "Screening", progress_cb=progress_cb, stage_sequence=stage_sequence)
    print(f"[+{time.time()-start:.1f}s] Screened {len(screened)} candidates @ {SCREEN_ITERATIONS} iter")

    # --- Pick each (tier, slot) leaderboard from the screening results ---
    # ArP flag only means anything for a profile that actually weights it -
    # a caster's stat_weights.json simply has no entry for it (see
    # item_arp_rating()'s comment above), so this is False by construction
    # for e.g. Balance Druid.
    arp_relevant = stat_weights.get_active().get(ARMOR_PEN_STAT_ID, 0) > 0
    # Real physical-slot lookup for the set-bonus-credit check below - needs
    # to know what she currently has equipped in a candidate's OWN slot (to
    # exclude it from the "already owned" count, since the candidate would
    # replace it, not stack with it).
    display_to_armor_slot = {SLOT_DISPLAY[s]: s for s in set_bonus.ARMOR_SET_SLOTS}
    by_tier_slot: dict[tuple[str, str], list] = {}
    for c, results in screened:
        # Backlog #16 (2026-08-31) - mv_single() now returns a list, one
        # real, independent result per real slot the candidate could
        # occupy (both ring1/ring2 for a shared-pool item, normally just
        # one for anything else) - see its own docstring for the real bug
        # this fixes. Each becomes its own row here, so ring1/ring2 (or
        # trinket1/trinket2, or mainhand/offhand) each get their own
        # independent leaderboard/achieved-BiS check.
        for r in results:
            if r.get("excluded_reason"):
                continue
            if c.item_id in owned_equipped_ids:
                continue  # already equipped - not an acquisition target
            owned_location = "bags" if c.item_id in owned_bag_ids else "bank" if c.item_id in owned_bank_ids else None
            source, tier, craft_spell_id = item_meta.get(c.item_id, ("", "Other", None))
            slot_label = item_slot_label.get(c.item_id, "Other")
            arp = item_arp_rating(idb.by_id(c.item_id)) if arp_relevant else 0
            # Real set-bonus ranking credit (per the user, 2026-08-25): if THIS
            # specific candidate is the piece that crosses a real, currently-
            # achievable set-bonus threshold (given what she already owns of
            # that set elsewhere), credit its isolated bonus value toward the
            # sort key (rank_value(), used below) - not toward the displayed mv
            # itself, which stays the honest isolated number.
            set_bonus_credit = 0
            item_dict = idb.by_id(c.item_id)
            cand_set_name = item_dict.get("setName") if item_dict else None
            if cand_set_name and cand_set_name in threshold_values_by_set:
                phys_slot = display_to_armor_slot.get(slot_label)
                if phys_slot:
                    idx = gc.SLOT_ORDER.index(phys_slot)
                    current_entry = baseline_config[idx] if idx < len(baseline_config) else None
                    current_item = idb.by_id(current_entry["id"]) if current_entry and current_entry.get("id") else None
                    owned_excl_slot = set_bonus.count_set_pieces_in_config(cand_set_name, baseline_config)
                    if current_item and current_item.get("setName") == cand_set_name:
                        owned_excl_slot -= 1
                    count_with_candidate = owned_excl_slot + 1
                    for threshold, value in threshold_values_by_set[cand_set_name].items():
                        if owned_excl_slot < threshold <= count_with_candidate:
                            set_bonus_credit += value
            r = dict(r, source=source, tier=tier, slot=slot_label, item_id=c.item_id,
                     craft_spell_id=craft_spell_id,
                     set_note=set_notes_by_item.get(c.item_id),
                     gate=acquisition_gate.gate_for_item(source, slot_label, acquisition_status),
                     arp_rating=arp or None,
                     set_bonus_credit=set_bonus_credit or None,
                     owned_location=owned_location,
                     **time_horizon.lasts_until_phase(c.name, c.item_id))
            by_tier_slot.setdefault((tier, slot_label), []).append((c, r))

    # A leaderboard item only needs the expensive 30k resolve if 1k screening
    # left it close enough to the noise floor that resolving could plausibly
    # change the verdict or move the shown number meaningfully - the same
    # CLEAR_MARGIN_MULTIPLE rule mv_single_tiered already uses elsewhere.
    # Resolving something already 8+ screening-noise-widths from zero can
    # only sharpen a number that was never in question, so it's skipped
    # (kept at its screened value, flagged "(screened only)" in the report).
    #
    # 2026-08-24: tried lowering this specific decision to a separate, less
    # conservative SCREEN_CLEAR_MARGIN_MULTIPLE=4 (validated safe on its own
    # terms - real screen-vs-30k data, zero sign flips), paired with a
    # correctness fix forcing every real-downgrade candidate in a currently-
    # active set-bonus slot into to_resolve regardless of margin (closing a
    # real gap: rescue-check only ever sees to_resolve items, so a candidate
    # excluded by a tighter margin would silently stop being checked for
    # rescue potential). The margin change alone would have saved ~16s on
    # the confirm phase - but the safety net, working exactly as intended,
    # surfaced far more real active-set-slot downgrades than expected (55
    # rescue-check candidates vs the previous 23), and rescue_check() is 2
    # real 30k calls each - that phase alone went from 91.8s to 204.3s,
    # a net 97s REGRESSION overall despite the margin change genuinely
    # working. Reverted both together rather than keep a net-negative
    # change - the underlying coverage gap is real but this fix for it
    # cost more than it was worth; a future attempt should scope the safety
    # net more narrowly (e.g. only the single least-bad downgrade per active
    # slot, not every leaderboard entry) rather than reopen this exact
    # implementation. See NOTES.md's 2026-08-24 entry for the full numbers.
    to_resolve = []
    for key, rows in by_tier_slot.items():
        rows.sort(key=lambda cr: rank_value(cr[1]), reverse=True)
        for i, (c, r) in enumerate(rows[:LEADERBOARD_SIZE]):
            # The #1-ranked item for a (tier, slot) always enters the confirm
            # pass at minimum, regardless of the clear-margin check - per the
            # user: if a screened item ends up on top, actually sim it further
            # rather than trust the noisier screening number. Whether it also
            # needs the full 30k pass is decided uniformly below, same as
            # every other candidate - see the note there for why the #1 pick
            # no longer gets an automatic escalation.
            if i == 0 or abs(r["mv"]) < mv.CLEAR_MARGIN_MULTIPLE * r["noise_stdev"]:
                to_resolve.append((c, r))

    print(f"[+{time.time()-start:.1f}s] Confirming {len(to_resolve)} (tier, slot) leaderboard candidates @ {CONFIRM_ITERATIONS} iter...")

    # --- Pass 2a: confirm @ 5k - cheap sharpening pass, see CONFIRM_ITERATIONS ---
    baseline_confirm = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, CONFIRM_ITERATIONS, opt.SEED)

    # Backlog #16 (2026-08-31) - only_slot scopes this to the ONE real slot
    # this leaderboard row already represents (mv_single() now returns a
    # list otherwise - see its own docstring). Keyed by (item_id, slot), not
    # item_id alone: a shared-pool candidate can now have TWO independent
    # leaderboard rows (one per real slot), and item_id alone would let the
    # second one silently overwrite the first's confirmed result.
    def confirm_one(cr):
        c, r = cr
        result = mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_confirm,
                               CONFIRM_ITERATIONS, opt.SEED, baseline_agility=baseline_agility,
                               only_slot=r["best_slot"])[0]
        return (c.item_id, r["best_slot"]), result

    confirmed_pairs = run_with_progress(confirm_one, to_resolve, "Confirming", progress_cb=progress_cb, stage_sequence=stage_sequence)
    confirmed_by_key = dict(confirmed_pairs)

    # Escalate to the full 30k pass only if still not clear at 5k's own noise
    # floor - INCLUDING #1 picks, per the user (2026-08-24): the earlier
    # "#1 always gets 30k regardless of margin" rule was dropped once the
    # visible "(confirmed @5k)" disclosure flag was also removed (below) -
    # the user's actual concern was never seeing a flag that could make them
    # doubt the sim, not the underlying precision tier itself. Validated
    # empirically before making this change: pulled real 5k-vs-30k pairs for
    # all 80 #1-pick items from a real run - zero sign flips, max drift 1.38
    # DPS, same safety margin already established for non-#1 items. See
    # NOTES.md 2026-08-24.
    need_full_resolve = [
        (c, r) for c, r in to_resolve
        if abs(confirmed_by_key[(c.item_id, r["best_slot"])]["mv"])
        < CONFIRM_CLEAR_MARGIN_MULTIPLE * confirmed_by_key[(c.item_id, r["best_slot"])]["noise_stdev"]
    ]

    # Printed BEFORE resolving starts, not after - per the user (2026-08-24):
    # the count is already known at this point, so there's no reason a
    # progress projection has to wait until the whole pass finishes to learn
    # its own denominator. Real precursor to the progress-indicator GUI
    # feature already noted in CLAUDE.md.
    print(f"[+{time.time()-start:.1f}s] Resolving {len(need_full_resolve)}/{len(to_resolve)} (tier, slot) leaderboard candidates "
          f"@ {RESOLVE_ITERATIONS} iter ({len(to_resolve) - len(need_full_resolve)} confirmed @ "
          f"{CONFIRM_ITERATIONS} already clear)...")

    # --- Pass 2b: resolve only what's still close enough to matter after confirm ---
    baseline_resolved = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
    # Real fix, 2026-09-06: baseline_resolved above is the IDEALIZED config (real
    # enchant if present, else curated default; always-optimal gems) - correct for
    # feeding every candidate's MV(i) trial (mv.mv_single() calls below), since that's
    # what keeps an upgrade comparison fair (never unenchanted-vs-enchanted), but wrong
    # for anything actually REPORTED to a human as "her current DPS" - a curated
    # default silently filled into a slot she hasn't actually enchanted/gemmed yet is
    # not what she's really getting right now. true_baseline_resolved answers that
    # honest question instead (opt.build_true_owned_config() - no substitution at all,
    # ever) - used ONLY for what gets reported: the OOM stat below, and
    # baseline_screened/used_consumables/Missing Enchants further down. Never fed into
    # an MV(i) trial.
    true_baseline_config = opt.build_true_owned_config(owned_items)
    true_baseline_resolved = mv.valuation.evaluate(SETTINGS_TEMPLATE, true_baseline_config, RESOLVE_ITERATIONS, opt.SEED)
    # Real OOM transparency (2026-09-06, see OOM_WARNING_THRESHOLD_FRACTION's own
    # comment above for the full motivation/data) - surfaced in the final report
    # regardless of whether it clears the warning threshold, so a reader always
    # has the real number, not just a binary flag. .get()-defensive, NOT a
    # direct index - real bug hit immediately while testing this: sim_cache
    # stores the final Python dict (not the raw sim result), so any
    # pre-existing cache entry from before this field existed lacks it
    # entirely, and a real cache hit raised a bare KeyError here. Matches
    # ew_uptime's own already-established .get()-based access pattern
    # elsewhere in this file - same real class of gotcha, same real fix.
    # Sourced from the TRUE baseline (her real rotation/gear), not the idealized one -
    # OOM should reflect what she'd actually experience, not a hypothetical loadout.
    baseline_oom_seconds = true_baseline_resolved.get("oom_seconds", 0.0)
    baseline_oom_fraction = baseline_oom_seconds / actual_duration if actual_duration else 0.0

    # raid_ap_per_attacker is computed at whichever precision tier produces
    # the final number for a given item (confirm or resolve) - only items
    # that skip BOTH (screened-only) miss it here (handled by the separate
    # screened_upgrades_needing_ap pass below), same "already clear, don't
    # spend more compute on it" principle already applied to DPS.
    def resolve_one(cr):
        c, r = cr
        result = mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_resolved,
                               RESOLVE_ITERATIONS, opt.SEED, baseline_agility=baseline_agility,
                               only_slot=r["best_slot"])[0]
        return (c.item_id, r["best_slot"]), result

    resolved_pairs = run_with_progress(resolve_one, need_full_resolve, "Resolving", progress_cb=progress_cb, stage_sequence=stage_sequence)
    resolved_by_key = dict(resolved_pairs)

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            row_key = (c.item_id, r["best_slot"])
            if row_key in resolved_by_key:
                res = resolved_by_key[row_key]
                r["mv"] = res["mv"]
                r["noise_stdev"] = res["noise_stdev"]
                r["tied_within_noise"] = res["tied_within_noise"]
                r["raid_ap_per_attacker"] = res.get("raid_ap_per_attacker")
                r["resolved"] = True
                r["resolve_iterations"] = RESOLVE_ITERATIONS
            elif row_key in confirmed_by_key:
                res = confirmed_by_key[row_key]
                r["mv"] = res["mv"]
                r["noise_stdev"] = res["noise_stdev"]
                r["tied_within_noise"] = res["tied_within_noise"]
                r["raid_ap_per_attacker"] = res.get("raid_ap_per_attacker")
                r["resolved"] = True
                r["resolve_iterations"] = CONFIRM_ITERATIONS
            else:
                r["raid_ap_per_attacker"] = None
                r["resolved"] = False
                r["resolve_iterations"] = SCREEN_ITERATIONS

    print(f"[+{time.time()-start:.1f}s] Resolved {len(need_full_resolve)} @ {RESOLVE_ITERATIONS} iter, "
          f"{len(to_resolve) - len(need_full_resolve)} confirmed @ {CONFIRM_ITERATIONS} iter.\n")

    # --- Pass 3: "rescue" check - is a real downgrade actually a strong
    # item once the active set bonus it breaks isn't in play at all? Per
    # the user (2026-08-23): built specifically to replace the interaction
    # matrix's much more expensive pairwise search for this exact question
    # (that search's real cost - 7558 pairs, ~19 minutes just for the
    # cheapest screening tier - blew well past a 15-minute total budget).
    # A single extra real sim call per real-downgrade leaderboard
    # candidate in a currently-set-active armor slot, not a combinatorial
    # search over every possible pairing. Real, validated motivating case:
    # Attumen's "Gloves of Dexterous Manipulation" - a real downgrade
    # today (breaks Rift Stalker Armor's 4pc bonus) but a genuine +13-14
    # DPS gain once that bonus is already broken by another slot.
    display_to_armor_slot = {SLOT_DISPLAY[s]: s for s in set_bonus.ARMOR_SET_SLOTS}
    thresholds = set_bonus.set_bonus_thresholds()
    active_set_by_slot: dict[str, str] = {}
    for slot in set_bonus.ARMOR_SET_SLOTS:
        idx = gc.SLOT_ORDER.index(slot)
        entry = baseline_config[idx] if idx < len(baseline_config) else None
        if not entry or not entry.get("id"):
            continue
        item = idb.by_id(entry["id"])
        set_name = item.get("setName") if item else None
        ths = thresholds.get(set_name) if set_name else None
        if ths and set_bonus.count_set_pieces_in_config(set_name, baseline_config) >= min(ths):
            active_set_by_slot[slot] = set_name

    rescue_notes_by_item: dict[int, str] = {}
    rescue_mv_by_item: dict[int, float] = {}
    rescue_via_item_id_by_item: dict[int, int] = {}
    rescue_via_item_by_item: dict[int, str] = {}
    if active_set_by_slot:
        rescue_candidates = []
        for c, r in to_resolve:
            if r.get("tied_within_noise") or r["mv"] >= 0:
                continue  # only real downgrades are candidates for a rescue note
            phys_slot = display_to_armor_slot.get(r["slot"])
            if phys_slot not in active_set_by_slot:
                continue
            rescue_candidates.append((c, phys_slot, active_set_by_slot[phys_slot]))

        # Was a plain sequential loop - each rescue_check() is 2 real 30k
        # sim calls, and this phase measured 20% of total sweep time on its
        # own (2026-08-24) despite every other pass already using
        # run_with_progress. Same helper, same MAX_WORKERS - no new
        # concurrency pattern, just applying the one already proven
        # elsewhere in this file to a pass that got missed.
        def rescue_one(item):
            c, phys_slot, set_name = item
            check = set_bonus.rescue_check(SETTINGS_TEMPLATE, c, phys_slot, set_name,
                                            baseline_config, candidates, RESOLVE_ITERATIONS, opt.SEED,
                                            baseline_resolved)
            return c.item_id, set_name, check

        rescue_results = run_with_progress(rescue_one, rescue_candidates, "Sidegrade-checking", progress_cb=progress_cb, stage_sequence=stage_sequence)
        for item_id, set_name, check in rescue_results:
            # Real, required second condition (2026-09-06, see
            # set_bonus.rescue_check()'s own docstring for the real bug this
            # fixes - a user-caught, real websim-verified case where the old
            # single-condition check recommended a combo that was a real
            # -88 DPS loss overall): a "sidegrade" must be a real gain BOTH
            # once the set is already broken AND for the full combined swap
            # against her actual current gear - never just the former.
            if (check and not check["tied_within_noise"] and check["mv_if_set_broken"] > 0
                    and not check["total_tied_within_noise"] and check["total_vs_current"] > 0):
                rescue_notes_by_item[item_id] = (
                    f"Don't compete for this - it's a downgrade with your current gear, "
                    f"so it's not worth outbidding someone with a real use for it. Worth "
                    f"banking if it's going free, though: paired with {check['via_item']} "
                    f"in {check['via_slot']}, it's a real {check['mv_if_set_broken']:+.1f} "
                    f"DPS sidegrade for later (breaks {set_name}'s bonus alone, but that "
                    f"bonus is already gone once you've made that other swap too), and the "
                    f"full combined swap is a real {check['total_vs_current']:+.1f} DPS gain "
                    f"over your current gear overall."
                )
                rescue_mv_by_item[item_id] = check["mv_if_set_broken"]
                # Real gap found live 2026-09-06 (user report): the note
                # names `via_item` in prose ("paired with Cowl of Defiance in
                # head") but that item is often NOT one of its own slot's
                # top-5 displayed candidates (it's picked by
                # best_non_set_alt() for being the best non-set option, which
                # can still rank outside the top 5 shown overall) - so the
                # reader has no way to see it anywhere else in the report,
                # making the claim unverifiable. Carrying its real item_id
                # through lets report_template.html render it as a real,
                # clickable Wowhead link even when it's otherwise invisible.
                rescue_via_item_id_by_item[item_id] = check["via_item_id"]
                rescue_via_item_by_item[item_id] = check["via_item"]
        if rescue_notes_by_item:
            print(f"Sidegrade check: {len(rescue_notes_by_item)} item(s) found to be real "
                  f"future sidegrades once their set-bonus break is already priced in elsewhere "
                  f"- not worth competing for now, but worth banking.\n")

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            r["rescue_note"] = rescue_notes_by_item.get(c.item_id)
            r["rescue_mv"] = rescue_mv_by_item.get(c.item_id)
            r["rescue_via_item_id"] = rescue_via_item_id_by_item.get(c.item_id)
            r["rescue_via_item"] = rescue_via_item_by_item.get(c.item_id)

    print(f"[+{time.time()-start:.1f}s] Rescue check pass done ({len(rescue_notes_by_item)} flagged).")

    # A "screened only" real upgrade (MV so far past the noise floor that
    # CLEAR_MARGIN_MULTIPLE skipped its 30k DPS resolve) was still showing
    # "Raid: n/a AP" - the DPS-skip decision had been silently skipping the
    # AP column too, but get_agility() is a cheap, deterministic ComputeStats
    # call (no Monte Carlo iterations, ~free compared to a resolve) and the
    # DPS side of this call hits the sim_cache instantly (identical config/
    # iterations/seed already ran in Pass 1) - so this costs one ComputeStats
    # RPC per screened-only leaderboard upgrade, not a real resolve.
    screened_upgrades_needing_ap = [
        (c, r) for key, rows in by_tier_slot.items()
        for c, r in rows[:LEADERBOARD_SIZE]
        if not r["resolved"] and not r["tied_within_noise"] and r["mv"] > 0
    ]

    # Backlog #16 - only_slot + (item_id, slot) keying, same reasoning as
    # confirm_one/resolve_one above.
    def add_ap_only(cr):
        c, r = cr
        result = mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_screen,
                               SCREEN_ITERATIONS, opt.SEED, baseline_agility=baseline_agility,
                               only_slot=r["best_slot"])[0]
        return (c.item_id, r["best_slot"]), result

    ap_only_pairs = run_with_progress(add_ap_only, screened_upgrades_needing_ap, "Raid-AP lookups", progress_cb=progress_cb, stage_sequence=stage_sequence)
    ap_only_by_key = dict(ap_only_pairs)

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            row_key = (c.item_id, r["best_slot"])
            if not r["resolved"] and row_key in ap_only_by_key:
                r["raid_ap_per_attacker"] = ap_only_by_key[row_key].get("raid_ap_per_attacker")

    if screened_upgrades_needing_ap:
        print(f"Filled Raid AP for {len(screened_upgrades_needing_ap)} screened-only real upgrades.\n")

    print(f"[+{time.time()-start:.1f}s] Raid-AP fill pass done. Building tiered report...")

    # --- Achieved BiS: slots where nothing in the whole P3 pool beats her
    # current gear (real upgrade = same filter every tier uses below) - a
    # gated upgrade she can't currently satisfy (reputation standing/arena
    # rating not met) doesn't count as beating her current gear TODAY, so
    # it doesn't disqualify the slot from Achieved BiS, even though it
    # still shows up normally in its tier (never silently hidden).
    def is_available_upgrade(r):
        real_upgrade = (not r["tied_within_noise"] and r["mv"] > 0) or r.get("set_note")
        if not real_upgrade:
            return False
        gate = r.get("gate")
        return gate is None or gate["satisfied"]

    # Real bug, found live 2026-08-27 by the user comparing Lerynia's own
    # real report against a wowsims.com reference: mainhand/offhand (and
    # equally, ring1/ring2 and trinket1/trinket2) share ONE display bucket
    # ("Weapon"/"Ring"/"Trinket" - see SLOT_DISPLAY above), but this used to
    # gate the WHOLE bucket on ANY real upgrade found anywhere in it - so a
    # real upgrade candidate for offhand alone hid mainhand's own real,
    # independently-BiS status from Achieved BiS too, even though nothing
    # about mainhand itself was actually beatable. Fixed by tracking real
    # upgrades per REAL slot instead of per display bucket, using each row's
    # own best_slot. A single-real-slot display bucket (Head, Neck, ...) is
    # unaffected either way - best_slot there is always that one real slot,
    # no ambiguity to begin with.
    #
    # Real SECOND bug in the same area, found live 2026-08-31 (backlog #16):
    # `best_slot` used to mean "whichever of the two real slots this
    # candidate's own best trial substituted into" - a single winner-take-
    # all pick per candidate, since replacing whichever of her two current
    # items is weaker always gives the bigger DPS gain. That meant EVERY
    # candidate's own best_slot consistently landed on the same weaker real
    # slot, so the stronger slot's current item could never be beaten by
    # ANYTHING - not because nothing was good enough, but because nothing
    # was ever independently checked against it. Confirmed live: 22 of 22
    # real trinket candidates for one real character all resolved to the
    # same real slot. Fixed at the source - marginal_value.py's mv_single()
    # now returns one real, independent result PER real slot a shared-pool
    # candidate could occupy, so each real slot gets its own real upgrade
    # check here, not a shared winner-take-all one.
    real_slots_with_upgrades = set()
    for (tier, slot), rows in by_tier_slot.items():
        for _c, r in rows:
            if is_available_upgrade(r):
                real_slot = r.get("best_slot")
                if real_slot:
                    real_slots_with_upgrades.add(real_slot)

    display_to_real_slots = {}
    for real, disp in SLOT_DISPLAY.items():
        display_to_real_slots.setdefault(disp, []).append(real)

    achieved_bis = []
    for slot in SLOT_DISPLAY_ORDER:
        items_here = []
        for real in display_to_real_slots.get(slot, []):
            if real in real_slots_with_upgrades:
                continue
            idx = gc.SLOT_ORDER.index(real)
            owned = owned_items[idx] if idx < len(owned_items) else None
            if owned:
                items_here.append({"name": owned.get("name", "?"), "item_id": owned.get("id")})
        if items_here:
            achieved_bis.append({"slot": slot, "items": items_here})

    # --- Missing Enchants: any real equipped slot with a real, sim-
    # verified BiS enchant on file (profile's default_enchants.json) that
    # she isn't actually wearing right now - per the user ("show the BiS
    # enchants available for that slot... make sure unenchanted items
    # never get compared to enchanted ones").
    #
    # Real fix, 2026-09-06: this used to measure against baseline_resolved
    # (the IDEALIZED config, already carrying the curated BiS enchant in every
    # slot by build_owned_config()'s own design) by REVERTING the tested slot
    # back to her real enchant and subtracting - i.e. curated-baseline minus
    # reverted-to-real. That only worked because the idealized config was
    # (wrongly) also being used as the reported "baseline DPS." Now that
    # true_baseline_resolved is the real, honest starting point (her actual
    # current enchant, or none), the comparison inverts cleanly to a simple
    # additive one: take the TRUE config and force just the tested slot's
    # enchant to the curated BiS value, then measure the gain over the real
    # baseline directly - same "hold everything else constant, isolate the
    # one real variable" methodology as set_bonus.isolate_bonus_value() and
    # core/verify_default_enchants.py, just measured from the honest side now.
    # Never a static "you're missing X" list with no sim number attached.
    default_enchants = gc.get_active_default_enchants()
    missing_enchants = []
    for slot, raw_bis_enchant_id in default_enchants.items():
        # Real gate (found live by the user, 2026-08-25): Ring enchants
        # need the wearer's own Enchanting - no report should tell her to
        # go chase one she structurally can't get. achievable_enchant()
        # returns 0 for a gated id, same "no data" treatment as a slot
        # with no default_enchants entry at all.
        bis_enchant_id = opt.achievable_enchant(raw_bis_enchant_id, known_professions)
        if not bis_enchant_id:
            continue
        idx = gc.SLOT_ORDER.index(slot)
        owned = owned_items[idx] if idx < len(owned_items) else None
        if not owned:
            continue
        current_enchant_id = owned.get("enchant") or None
        if current_enchant_id == bis_enchant_id:
            continue

        enchanted_trial = list(true_baseline_config)
        enchanted_trial[idx] = dict(enchanted_trial[idx])
        enchanted_trial[idx]["enchant"] = bis_enchant_id
        enchanted_result = mv.valuation.evaluate(SETTINGS_TEMPLATE, enchanted_trial, RESOLVE_ITERATIONS, opt.SEED)

        delta = enchanted_result["combined"] - true_baseline_resolved["combined"]
        noise = mv.delta_noise(true_baseline_resolved, enchanted_result, RESOLVE_ITERATIONS)
        tied_within_noise = abs(delta) < 2 * noise
        if tied_within_noise or delta <= 0:
            # A real, verified BiS enchant that's indistinguishable from what
            # she already has isn't a real actionable gap - same "never
            # recommend chasing a gain indistinguishable from noise" ground
            # rule the tiers list already applies (is_available_upgrade above).
            #
            # delta <= 0 is a real, separate finding, not just noise: it
            # means her CURRENT enchant clearly beats the profile's assumed
            # default_enchants.json value for this slot - proof the hand/
            # preset-sourced "BiS" pick for that slot is actually wrong, not
            # evidence of a gap to close. Caught live 2026-08-25 for
            # Lerynia's own feet slot (Enchant Boots - Dexterity, her real
            # current pick, verified +7.3 DPS over the file's old "Cat's
            # Swiftness" assumption) - default_enchants.json corrected, but
            # this check stays permanently: never show a downgrade as if it
            # were a recommendation, no matter what the data file claims.
            continue
        current_enchant = idb.enchant_by_id(current_enchant_id) if current_enchant_id else None
        bis_enchant = idb.enchant_by_id(bis_enchant_id)
        missing_enchants.append({
            "slot": SLOT_DISPLAY.get(slot, slot),
            "item_name": owned.get("name", "?"),
            "current_enchant_id": current_enchant_id,
            "current_name": current_enchant["name"] if current_enchant else None,
            "bis_enchant_id": bis_enchant_id,
            "bis_name": bis_enchant["name"] if bis_enchant else f"Enchant {bis_enchant_id}",
            "mv": delta,
            "noise_stdev": noise,
        })
    missing_enchants.sort(key=lambda e: e["mv"], reverse=True)

    if missing_enchants:
        print(f"=== Missing Enchants (real BiS enchant available, not currently equipped) ===")
        for e in missing_enchants:
            current = e["current_name"] or "(none)"
            print(f"  {e['slot']:<10} {e['item_name']:<35} {current} -> {e['bis_name']}  "
                  f"+{e['mv']:.1f} DPS")
        print()

    # Legend printed once, up front: Player and Raid are two distinct,
    # never-combined value dimensions (CLAUDE.md's Stage 2 ground rule).
    # No "Overall" score is computed here on purpose - collapsing Player
    # DPS (a real, sim-verified number) and Raid AP (an analytically
    # estimated contribution to OTHER raid members whose classes/weapons
    # aren't known to this tool) into one number would require inventing
    # an AP->DPS conversion for those unknown attackers - decided against,
    # per CLAUDE.md's "never invent data" rule. Sort/rank by Player.
    print("Player = DPS. Personal damage-per-second gain (real sim number, what this item does")
    print("         for YOUR damage).")
    print("Debuff = AP, PER physical attacker in the raid. How much stronger/weaker your Expose")
    print("         Weakness debuff gets - multiply by your raid's actual physical-attacker count")
    print("         for a total. A different unit entirely, not DPS, never added into Player.\n")

    if achieved_bis:
        print(f"=== Achieved BiS (nothing in the {phase} pool beats these) ===")
        for entry in achieved_bis:
            names = ", ".join(i["name"] for i in entry["items"])
            print(f"  {entry['slot']:<10} {names}")
        print()

    tier_order = list(TIER_ZONES.keys()) + ["Crafted", "Reputation reward", "Other", "Other drop"]
    tiered_out = {}
    for tier in tier_order:
        slots_here = {slot for (t, slot) in by_tier_slot if t == tier}
        tier_upgrades_total = 0
        tier_out = {}
        for slot in sorted(slots_here, key=lambda s: (SLOT_DISPLAY_ORDER.index(s) if s in SLOT_DISPLAY_ORDER else 99, s)):
            rows = by_tier_slot.get((tier, slot), [])
            upgrades = [r for _, r in rows
                        if (not r["tied_within_noise"] and r["mv"] > 0) or r.get("set_note") or r.get("rescue_note")]
            # Sort by the RESCUED value for rescue-flagged items, not the
            # raw (currently-negative) net mv - otherwise a genuinely
            # strong rescued item sorts to the bottom of its own slot and
            # never makes the top-5 cutoff below, defeating the point of
            # surfacing it at all.
            upgrades.sort(key=lambda r: r["rescue_mv"] if r.get("rescue_note") else rank_value(r), reverse=True)
            if not upgrades:
                continue
            tier_out[slot] = upgrades
            tier_upgrades_total += len(upgrades)

        if tier_upgrades_total == 0:
            print(f"=== {tier} ===\n  No real upgrades found.\n")
            tiered_out[tier] = {}
            continue

        print(f"=== {tier} ===")
        for slot, upgrades in tier_out.items():
            # Only show the set-bonus note where it's actually rescuing this
            # item (its own mv is a downgrade/tie) - an item already a real
            # upgrade on its own merits isn't "a downgrade alone", even if
            # it happens to belong to a set that was checked too.
            def rescued_by_set(u):
                return bool(u.get("set_note")) and not (not u["tied_within_noise"] and u["mv"] > 0)

            # Confirmed-@5k and resolved-@30k items are shown identically -
            # per the user (2026-08-24): once an item clears
            # CONFIRM_CLEAR_MARGIN_MULTIPLE (validated to carry the same
            # zero-sign-flip, <1.4 DPS drift safety margin as a full 30k
            # resolve - see NOTES.md), a visible per-item precision-tier flag
            # doesn't add real information, it just risks reading as doubt
            # about a specific recommendation. `resolve_iterations` stays on
            # the underlying data (JSON/tiered_report) for anyone who wants
            # it; only genuinely lower-confidence "(screened only)" items -
            # which never passed ANY confirm-precision check - still get a
            # visible flag, since that uncertainty is real and undisclosed
            # otherwise.
            n_resolved = sum(1 for u in upgrades[:5] if u.get("resolved"))
            n_setnote = sum(1 for u in upgrades if rescued_by_set(u))
            setnote_txt = f", {n_setnote} set-bonus-only" if n_setnote else ""
            print(f"  -- {slot} ({len(upgrades)} upgrades{setnote_txt}, top 5 shown, "
                  f"{n_resolved}/5 resolved) --")
            for r in upgrades[:5]:
                flag = "" if r.get("resolved") else "  (screened only)"
                # Personal DPS and raid AP contribution as two separate
                # columns, never collapsed into one number, per CLAUDE.md's
                # Stage 2 ground rule - "n/a" (not a silently blank column)
                # when it wasn't computed for this item (screened-only
                # items skip the extra ComputeStats call, same as they skip
                # the 30k DPS resolve).
                raid_ap = r.get("raid_ap_per_attacker")
                raid_ap_str = f"Debuff: {raid_ap:>+5.1f} AP/ea" if raid_ap is not None else "Debuff:    n/a AP/ea"
                gate = r.get("gate")
                lock = "  [LOCKED]" if gate and not gate["satisfied"] else ""
                horizon = horizon_tag(r)
                print(f"    {r['name']:<36} Player: {r['mv']:>+7.1f} DPS  {raid_ap_str}  {r['source']}{flag}{lock}{horizon}")
                if rescued_by_set(r):
                    print(f"        note: {r['set_note']}")
                if r.get("rescue_note"):
                    print(f"        note: {r['rescue_note']}")
                if gate:
                    print(f"        gate: {gate['note']}")
            if len(upgrades) > 5:
                print(f"    ...and {len(upgrades) - 5} more.")
        print()
        tiered_out[tier] = tier_out

    # --- 2H weapon options, own pool, own settings/baseline ---
    # Melee weave is a real, distinct rotation mechanic that currently only
    # exists for Survival Hunter (settings_template_2h.json's "melee weave"
    # APL variant - see NOTES.md's 2026-08-23 entry) - a caster like Balance
    # Druid choosing between a 2H staff and a 1H+offhand combo is a plain
    # weapon-choice comparison with no weave rotation involved at all. Real
    # bug found 2026-08-25: this section unconditionally used weave framing
    # (labels, a redundant "weave ON vs weave OFF" double-sim) for every
    # dual/one-hand-plus-offhand profile, not just Hunter's. is_weave_profile
    # is exactly SETTINGS_2H's own real/fallback distinction (line ~327) -
    # a profile with a real settings_template_2h.json has a real weave
    # mechanic to model; one that silently fell back to SETTINGS_TEMPLATE
    # does not, and running the "same settings twice" sim call there was
    # pure waste on top of being mislabeled. (is_weave_profile itself is
    # now computed earlier, alongside stage_sequence's own construction -
    # the GUI's stage count needs it before this point.)
    print(f"[+{time.time()-start:.1f}s] Tiered report built. Starting 2H weapon analysis...")

    two_hand_out: list[dict] = []
    two_hand_meta: dict = {}
    # Explicit topology gate, not just "pool happens to be empty" - this
    # whole section only means something for a profile with a real current
    # offhand slot weighing an optional 2H alternate (dual_wield AND, since
    # Stage 6.2, one_hand_plus_offhand_item - Balance Druid's real BiS
    # weapon choice genuinely varies by phase between a 2H staff and a
    # 1H+offhand combo). A two_hand profile's weapon_2h_candidates is
    # already always empty by construction (slot_for_item routes 2H
    # straight to "mainhand" for it), so this is defense-in-depth there,
    # not the only thing preventing it firing.
    if profile["weapon_topology"] != "two_hand" and weapon_2h_candidates:
        if is_weave_profile:
            # Compared against her CURRENT DW gear WITH weave enabled (not
            # the no-weave baseline) - per the user, weave only happens "on
            # bosses that allow for it", so on those specific bosses the
            # real decision is "given I'm already weaving, does switching
            # to a 2H weapon help further" - not "should I abandon DW
            # entirely". The no-weave baseline is printed alongside for
            # context, never silently dropped.
            weave_dw_result = mv.valuation.evaluate(SETTINGS_WEAVE_REAL, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
            no_weave_result = mv.valuation.evaluate(SETTINGS_NO_WEAVE_REAL, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
            print(f"=== 2H Weapon Options (melee weave rotation) ===")
            print(f"Baseline, current DW gear, weave OFF: {no_weave_result['combined']:.1f}")
            print(f"Baseline, current DW gear, weave ON:  {weave_dw_result['combined']:.1f} "
                  f"(+{weave_dw_result['combined'] - no_weave_result['combined']:.1f} from weave alone)\n")
            two_hand_meta = {"no_weave_dw": no_weave_result["combined"], "weave_dw": weave_dw_result["combined"],
                              "weave_supported": True}
        else:
            # No real weave mechanic for this profile - one real sim call,
            # plain "would a 2H weapon beat my current gear" comparison.
            baseline_2h_result = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
            print(f"=== 2H Weapon Options ===")
            print(f"Baseline, current gear: {baseline_2h_result['combined']:.1f}\n")
            weave_dw_result = baseline_2h_result
            two_hand_meta = {"no_weave_dw": baseline_2h_result["combined"], "weave_dw": baseline_2h_result["combined"],
                              "weave_supported": False}

        mh_idx = gc.SLOT_ORDER.index("mainhand")
        oh_idx = gc.SLOT_ORDER.index("offhand")

        # Stage 6.3 (2026-08-25, per the user: "we do want to build the 2
        # hand without weave for survival too"): the whole screen/resolve/
        # top-N-picks sequence is now a reusable pass, run once against the
        # profile's real primary baseline (weave-on for a weave profile,
        # the plain baseline otherwise) and, for a weave profile ONLY, a
        # SECOND time against the real weave-OFF baseline - "would a 2H
        # weapon's raw stat budget alone beat my DW pair, with zero melee
        # swings at all" was never actually answered before this (the
        # weave-OFF baseline existed and was printed, but no candidate was
        # ever compared against it). Each row is tagged `weave` so the
        # report can group them without needing a second output list.
        def run_2h_pass(settings_path: str, baseline_result: dict, stage_suffix: str, weave_tag: bool | None):
            def screen_2h(c: opt.Candidate):
                trial = list(baseline_config)
                trial[mh_idx] = c.as_entry()
                trial[oh_idx] = {}
                r = mv.valuation.evaluate(settings_path, trial, SCREEN_ITERATIONS, opt.SEED)
                return c, trial, r

            screened_2h = run_with_progress(screen_2h, weapon_2h_candidates, f"Screening 2H weapons{stage_suffix}",
                                             progress_cb=progress_cb, stage_sequence=stage_sequence)

            rows_2h = []
            for c, trial, r in screened_2h:
                delta = r["combined"] - baseline_result["combined"]
                noise = mv.delta_noise(baseline_result, r, SCREEN_ITERATIONS)
                source, tier, craft_spell_id = item_meta.get(c.item_id, ("Source unclear", "Other", None))
                arp = item_arp_rating(idb.by_id(c.item_id)) if arp_relevant else 0
                row = {"name": c.name, "item_id": c.item_id, "trial": trial,
                       "mv": delta, "noise_stdev": noise,
                       "tied_within_noise": abs(delta) < 2 * noise,
                       "source": source, "tier": tier, "craft_spell_id": craft_spell_id,
                       "resolved": False, "resolve_iterations": SCREEN_ITERATIONS,
                       "arp_rating": arp or None,
                       **time_horizon.lasts_until_phase(c.name, c.item_id)}
                if weave_tag is not None:
                    row["weave"] = weave_tag
                rows_2h.append(row)
            rows_2h.sort(key=lambda r: r["mv"], reverse=True)

            def resolve_2h_row(r):
                resolved = mv.valuation.evaluate(settings_path, r["trial"], RESOLVE_ITERATIONS, opt.SEED)
                r["mv"] = resolved["combined"] - baseline_result["combined"]
                r["noise_stdev"] = mv.delta_noise(baseline_result, resolved, RESOLVE_ITERATIONS)
                r["tied_within_noise"] = abs(r["mv"]) < 2 * r["noise_stdev"]
                r["resolved"] = True
                r["resolve_iterations"] = RESOLVE_ITERATIONS

            to_resolve_2h = [r for r in rows_2h[:LEADERBOARD_SIZE]
                              if abs(r["mv"]) < mv.CLEAR_MARGIN_MULTIPLE * r["noise_stdev"]]
            run_with_progress(resolve_2h_row, to_resolve_2h, f"Resolving 2H{stage_suffix}",
                               progress_cb=progress_cb, stage_sequence=stage_sequence)

            real_upgrades_2h = [r for r in rows_2h if not r["tied_within_noise"] and r["mv"] > 0]
            top_2h = real_upgrades_2h[:TOP_N_2H]

            # Same rule as the main leaderboard: whatever's actually shown
            # always gets the real resolve, regardless of margin - per the
            # user, if a screened item ends up in the visible list, actually
            # sim it. Real bug, found live by the user 2026-08-25: this used
            # to be a plain sequential `for` loop, not run_with_progress() -
            # a genuinely decisive real upgrade (far enough from the noise
            # floor that "Resolving 2H" above never needed to touch it)
            # still lands in top_2h and still needs a real 30000-iteration
            # resolve here, one at a time, with zero progress reporting -
            # silently, while the UI sat frozen on "Screening 2H weapons
            # ... 100%" the whole time (confirmed live: "stuck for a long
            # time" at exactly that state).
            run_with_progress(lambda r: resolve_2h_row(r) if not r["resolved"] else None, top_2h,
                               f"Resolving top 2H picks{stage_suffix}", progress_cb=progress_cb, stage_sequence=stage_sequence)
            top_2h.sort(key=lambda r: r["mv"], reverse=True)

            for r in rows_2h:
                r.pop("trial")
            return top_2h, len(real_upgrades_2h)

        top_2h, real_upgrades_2h_count = run_2h_pass(SETTINGS_WEAVE_REAL if is_weave_profile else SETTINGS_TEMPLATE,
                                                       weave_dw_result, "", True if is_weave_profile else None)
        two_hand_out = list(top_2h)

        vs_text = "vs weaving with current DW gear" if is_weave_profile else "vs current gear"
        if top_2h:
            print(f"  -- Top {len(top_2h)} 2H upgrade(s) across all tiers/zones {vs_text} --")
            for r in top_2h:
                flag = "" if r["resolved"] else "  (screened only)"
                horizon = horizon_tag(r)
                print(f"    {r['name']:<36} Player: {r['mv']:>+7.1f} DPS  {r['tier']}: {r['source']}{flag}{horizon}")
            if real_upgrades_2h_count > len(top_2h):
                print(f"    ...and {real_upgrades_2h_count - len(top_2h)} more real upgrade(s) not shown.")
        else:
            print(f"  No 2H weapon beats {vs_text.removeprefix('vs ')}.")
        print()

        if is_weave_profile:
            top_2h_no_weave, real_upgrades_2h_no_weave_count = run_2h_pass(
                SETTINGS_NO_WEAVE_REAL, no_weave_result, " (no weave)", False)
            two_hand_out.extend(top_2h_no_weave)

            print(f"  -- Top {len(top_2h_no_weave)} 2H upgrade(s), no weave, vs current DW gear (weave OFF) --")
            if top_2h_no_weave:
                for r in top_2h_no_weave:
                    flag = "" if r["resolved"] else "  (screened only)"
                    horizon = horizon_tag(r)
                    print(f"    {r['name']:<36} Player: {r['mv']:>+7.1f} DPS  {r['tier']}: {r['source']}{flag}{horizon}")
                if real_upgrades_2h_no_weave_count > len(top_2h_no_weave):
                    print(f"    ...and {real_upgrades_2h_no_weave_count - len(top_2h_no_weave)} more real upgrade(s) not shown.")
            else:
                print("  No 2H weapon beats current DW gear without weaving.")
            print()
    elif profile["weapon_topology"] != "two_hand":
        heading = "2H Weapon Options (melee weave rotation)" if is_weave_profile else "2H Weapon Options"
        print(f"=== {heading} ===\n  No eligible 2H weapons in the pool.\n")
    # else: a two_hand profile's mainhand IS her 2H slot already (routed
    # straight through the normal pipeline above) - there's no separate
    # "should I go 2H" question to print anything about at all.

    # Backlog #20 (2026-09-06) - "Dual-Wield Alternative" analysis: the
    # mirror-image question of the 2H section above, needed specifically
    # when she's REALLY 2H-equipped right now (dw_pair_candidates was
    # populated earlier precisely for this - see its own comment for the
    # real bug this replaces). Per the user's explicit requirement ("No
    # partial fixes... WE have to compare dw to 2hand No Matter what the
    # starting point is"), this can't just exclude these candidates - it
    # has to actually answer "would switching to dual-wield beat my
    # current 2H weapon" with a real, honest number. A full joint search
    # over every (mainhand, offhand) pair is combinatorially large for no
    # real benefit (weapon-pair interactions beyond additive stats are
    # rare) - bounded, sim-based greedy search instead, same "screen cheap,
    # verify the winner for real" discipline used everywhere else in this
    # file: screen every real mainhand-eligible candidate alone (offhand
    # empty) to find the best one, then screen every real offhand-eligible
    # candidate against THAT fixed mainhand to find the best pairing - both
    # passes are real sim calls (SCREEN_ITERATIONS), never an EP guess.
    #
    # Real, serious bug found and fixed the SAME day, caught live by the
    # user's own mechanical instinct ("i can't see a dagger beating a 2.6
    # speed weapon on weave") and confirmed by direct testing: the search
    # used to screen the best mainhand ONCE, using the no-weave settings
    # only, then reuse that same pick for BOTH the no-weave AND weave-on
    # final comparison. For Lerynia this picked Blade of the Unrequited
    # (1.6 speed) as "best mainhand" - correct for no-weave, but with weave
    # ON, Netherbane (2.6 speed) + Claw of the Phoenix beat Blade + Claw by
    # a real, decisive **+276.7 DPS** - a slower weapon hitting harder on
    # every real Raptor Strike, exactly the kind of weapon-speed/rotation
    # interaction a linear, single-scenario screen can silently miss (the
    # same class of error this whole tool exists to catch via real sims,
    # not EP). Fixed by screening mainhand/offhand SEPARATELY per real
    # settings variant when the profile is weave-capable - the best pair
    # for weave-on and the best pair for no-weave are now allowed to be
    # (and, confirmed live, actually are) two different real answers.
    # Real refinement, same day, per the user: "if on weaving off both
    # netherbane + claw and blade + claw are a dps increase we should maybe
    # show both - we should probably show top 3 dps increases on the dw vs
    # 2hand part aswell - but we don't have to show more than 1 decrease."
    # DW_TOP_N mainhand candidates (not just the single best) each get
    # their own real best-offhand pairing, producing up to DW_TOP_N
    # distinct real pairs - every real upgrade among them is shown (up to
    # DW_TOP_N), but if none of them are real upgrades, only the single
    # least-bad one is shown (matching the "Achieved BiS"/tier-list
    # convention elsewhere: a real downgrade is worth confirming exists,
    # never worth padding out with more downgrades).
    DW_TOP_N = 3
    dual_wield_alt: dict | None = None
    if real_mainhand_is_two_hand and dw_pair_candidates:
        dw_mh_idx = gc.SLOT_ORDER.index("mainhand")
        dw_oh_idx = gc.SLOT_ORDER.index("offhand")
        mainhand_eligible = [c for c in dw_pair_candidates if not opt.is_hand_restricted_conflict(c.item_id, "mainhand")]
        offhand_eligible = [c for c in dw_pair_candidates if not opt.is_hand_restricted_conflict(c.item_id, "offhand")]

        def find_top_dw_pairs(settings_path: str, stage_suffix: str, current_result: dict) -> list[dict]:
            def screen_mainhand(c):
                trial = list(baseline_config)
                trial[dw_mh_idx] = c.as_entry()
                trial[dw_oh_idx] = {}
                r = mv.valuation.evaluate(settings_path, trial, SCREEN_ITERATIONS, opt.SEED)
                return c, r["combined"]

            mh_screened = run_with_progress(screen_mainhand, mainhand_eligible, f"Screening dual-wield mainhand{stage_suffix}",
                                              progress_cb=progress_cb, stage_sequence=stage_sequence)
            mh_screened.sort(key=lambda t: t[1], reverse=True)
            top_mainhands = [c for c, _ in mh_screened[:DW_TOP_N]]

            # Each of the top mainhands gets its OWN real best-offhand
            # pairing - a strong 2nd-place mainhand can still pair with a
            # very different offhand than the 1st-place one (real weapon-
            # pair interactions, same reason a single greedy pick isn't
            # enough - see this whole section's own top comment).
            pairs: list[tuple["opt.Candidate", "opt.Candidate"]] = []
            for mh_c in top_mainhands:
                def screen_offhand(c, _mh=mh_c):
                    trial = list(baseline_config)
                    trial[dw_mh_idx] = _mh.as_entry()
                    trial[dw_oh_idx] = c.as_entry()
                    r = mv.valuation.evaluate(settings_path, trial, SCREEN_ITERATIONS, opt.SEED)
                    return c, r["combined"]

                oh_screened = run_with_progress(screen_offhand, offhand_eligible, f"Screening dual-wield offhand{stage_suffix}",
                                                  progress_cb=progress_cb, stage_sequence=stage_sequence)
                best_oh, _ = max(oh_screened, key=lambda t: t[1])
                pairs.append((mh_c, best_oh))

            milestone(f"Resolving dual-wield alternative{stage_suffix}")
            results = []
            for mh_c, oh_c in pairs:
                trial = list(baseline_config)
                trial[dw_mh_idx] = mh_c.as_entry()
                trial[dw_oh_idx] = oh_c.as_entry()
                resolved = mv.valuation.evaluate(settings_path, trial, RESOLVE_ITERATIONS, opt.SEED)
                delta = resolved["combined"] - current_result["combined"]
                noise = mv.delta_noise(current_result, resolved, RESOLVE_ITERATIONS)
                results.append({
                    "mainhand": {"name": mh_c.name, "item_id": mh_c.item_id},
                    "offhand": {"name": oh_c.name, "item_id": oh_c.item_id},
                    "dw_dps": resolved["combined"], "mv": delta, "noise_stdev": noise,
                    "tied_within_noise": abs(delta) < 2 * noise,
                })
            results.sort(key=lambda r: r["mv"], reverse=True)
            real_upgrades = [r for r in results if not r["tied_within_noise"] and r["mv"] > 0]
            return real_upgrades[:DW_TOP_N] if real_upgrades else results[:1]

        milestone("Screening dual-wield alternative")
        current_2h_no_weave = mv.valuation.evaluate(SETTINGS_NO_WEAVE_REAL, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
        pairs_no_weave = find_top_dw_pairs(SETTINGS_NO_WEAVE_REAL, " (no weave)" if is_weave_profile else "", current_2h_no_weave)

        dual_wield_alt = {
            "current_2h_dps": current_2h_no_weave["combined"],
            "pairs": pairs_no_weave,
            "weave_supported": is_weave_profile,
        }
        print(f"=== Dual-Wield Alternative{' (no weave)' if is_weave_profile else ''} ===")
        print(f"Your current 2H weapon: {current_2h_no_weave['combined']:.1f} DPS")
        for r in pairs_no_weave:
            print(f"  {r['mainhand']['name']} + {r['offhand']['name']}: {r['dw_dps']:.1f} DPS "
                  f"({r['mv']:+.1f}, tied={r['tied_within_noise']})")

        # A weave-capable profile can melee-weave with EITHER weapon setup
        # (Raptor Strike swings whatever's in mainhand regardless of hand
        # count - dual-wield was never actually required for it, a real
        # thing confirmed while investigating this same backlog item, see
        # NOTES.md) - so the fair comparison needs its OWN, separately
        # screened top pairs too, not the no-weave pairs re-resolved under
        # weave settings (see this whole section's own top comment for the
        # real, decisive case this matters for).
        if is_weave_profile:
            current_2h_weave = mv.valuation.evaluate(SETTINGS_WEAVE_REAL, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
            pairs_weave = find_top_dw_pairs(SETTINGS_WEAVE_REAL, " (weave)", current_2h_weave)
            dual_wield_alt["current_2h_dps_weave"] = current_2h_weave["combined"]
            dual_wield_alt["pairs_weave"] = pairs_weave
            print(f"=== Dual-Wield Alternative (weave) ===")
            print(f"Your current 2H weapon: {current_2h_weave['combined']:.1f} DPS")
            for r in pairs_weave:
                print(f"  {r['mainhand']['name']} + {r['offhand']['name']}: {r['dw_dps']:.1f} DPS "
                      f"({r['mv']:+.1f}, tied={r['tied_within_noise']})")
        print()

    # Stage 5 (§7, the pairwise interaction matrix) is dropped from the
    # active pipeline per the user (2026-08-23) - its real cost (128
    # candidates -> 7558 pairs, ~19 minutes just for the cheapest screening
    # tier) blew well past a 15-minute total-runtime budget, and every
    # sound way found to shrink that pool (an EP cutoff, in particular)
    # turned out to structurally conflict with the exact "rescue" items
    # it existed to find. Replaced by the much cheaper rescue_check pass
    # above (Pass 3) - a single extra real sim call per real-downgrade
    # leaderboard candidate, not a combinatorial search. The module
    # (core/interaction_matrix.py) stays in git history, just unused.

    elapsed = time.time() - start
    print(f"Elapsed: {elapsed:.1f}s")

    # Backlog #5 - real, human-readable labels for whatever was excluded, so
    # a report opened weeks later is self-documenting (same spirit as always
    # recording the sim commit SHA - never leave "why is this ranking
    # different" needing a git-diff/local_config.json spelunk to answer).
    def _source_key_label(key: str) -> str:
        if key == "rep":
            return "Reputation rewards"
        kind, _, raw_id = key.partition(":")
        if kind == "zone":
            return zone_by_id.get(int(raw_id), key)
        if kind == "craft":
            return idb.PROFESSION_NAMES.get(int(raw_id), key)
        return key

    source_scope_excluded = sorted(_source_key_label(k) for k in excluded_source_keys)

    # Backlog #19 (2026-09-06, the user's own suggestion) - every report
    # computes DPS against a real, but previously SILENT, raid-composition
    # assumption (which totems/buffs are active, whether a Shadow Priest's
    # mana return is modeled, etc.) baked into raid_buffs_overlay.json at
    # settings-build time - a reader had no way to see what was assumed
    # without reading source files. Read directly from the real, actual
    # settings file this sweep just ran against (never hand-typed, never
    # drifts out of sync with what was really simmed) - the four real
    # buff-carrying sections wowsims' own settings schema uses.
    _settings_for_buffs = repo_root.load_json(SETTINGS_TEMPLATE)
    assumed_buffs = {
        "raidBuffs": _settings_for_buffs.get("raidBuffs", {}),
        "debuffs": _settings_for_buffs.get("debuffs", {}),
        "partyBuffs": _settings_for_buffs.get("partyBuffs", {}),
        "playerBuffs": _settings_for_buffs.get("player", {}).get("buffs", {}),
    }

    # "Used Consumables" report section (2026-09-06, same real motivation as
    # assumed_buffs above - a reader has no way to see what flask/food/potion/
    # weapon-oil this sweep actually simmed with without reading source
    # files). Only the single real item ACTUALLY used per slot - never the
    # settings file's own "potions"/"conjuredItems" alternate-options arrays
    # (a separate, already-flagged judgment-call area, see QUESTIONS.md).
    # drumsId is deliberately excluded - it's a PARTY buff (partyBuffs.drums),
    # already covered by the existing Assumed Raid Buffs section, not a
    # personal consumable. Uses item_db.consumable_by_id() (NOT by_id() -
    # potions/flasks/food live in db.json's own separate "consumables"
    # section, confirmed while building this) since these are consumable
    # items, not gear.
    _consumables_used = _settings_for_buffs.get("player", {}).get("consumables", {})

    # Real, hand-maintained (not invented) - weapon imbues aren't reliably in
    # EITHER db.json section. Real bug chain found while building this:
    # mhImbueId 25122 resolved via item_db.by_id() to "Khorium Plated
    # Bludgeon" - a real, unrelated weapon. Tried sourcing names from the
    # sim's own hardcoded switch instead
    # (`sim/tbc-new/sim/core/consumes.go`'s `registerStaticImbue()`, which
    # IS authoritative for what mhImbueId actually triggers) - but a live
    # Wowhead check caught a SECOND real bug: that switch's own numeric ids
    # are the sim's own internal dispatch keys, NOT real Wowhead item ids -
    # id 25122 in the switch means "apply Brilliant Wizard Oil's effect" to
    # the sim, but 25122 on Wowhead is a real, unrelated weapon (confirmed
    # directly: page title "Khorium Plated Bludgeon"), so a whLink() built
    # from the switch's own id would link to the WRONG real item. Real,
    # verified REAL Wowhead ids looked up directly (not guessed) and
    # effect-cross-checked against the switch's own stat values for the two
    # spell-related ones (Wizard/Mana Oil - the only ones relevant to any
    # CASTER_POTION_PROFILES profile; the 3 physical ones aren't currently
    # consumed by any caster profile but are included for completeness/any
    # future melee profile use, name-verified via Wowhead search but not
    # independently effect-cross-checked):
    #   25123 (sim id) "Mana Oil" -> really "Brilliant Wizard Oil"'s mana
    #     sibling, real id 20748 "Brilliant Mana Oil" (effect confirmed:
    #     "restores 12 mana...increases healing...by up to 25" - exact match
    #     to the switch's HealingPower+25/MP5+12).
    #   25122 -> real id 20749 "Brilliant Wizard Oil" (effect confirmed:
    #     "spell damage by up to 36...critical strike rating by 14" - exact
    #     match).
    #   28017 -> real id 22522 "Superior Wizard Oil" (effect confirmed:
    #     "spell damage by up to 42" - exact match).
    #   29453 -> real id 23529 "Adamantite Sharpening Stone".
    #   34340 -> real id 28421 "Adamantite Weightstone".
    #   28891 -> real id 23122 "Consecrated Sharpening Stone".
    WEAPON_IMBUE_REAL_IDS = {
        25123: (20748, "Brilliant Mana Oil"), 25122: (20749, "Brilliant Wizard Oil"),
        28017: (22522, "Superior Wizard Oil"), 29453: (23529, "Adamantite Sharpening Stone"),
        34340: (28421, "Adamantite Weightstone"), 28891: (23122, "Consecrated Sharpening Stone"),
    }

    def _resolve_consumable(item_id, real_id_override_map=None):
        if not item_id:
            return None
        if real_id_override_map and item_id in real_id_override_map:
            real_id, name = real_id_override_map[item_id]
            return {"name": name, "item_id": real_id}
        c = idb.consumable_by_id(item_id)
        return {"name": c["name"], "item_id": item_id} if c else {"name": f"item {item_id}", "item_id": item_id}

    used_consumables = {
        "potion": _resolve_consumable(_consumables_used.get("potId")),
        "flask": _resolve_consumable(_consumables_used.get("flaskId")),
        "food": _resolve_consumable(_consumables_used.get("foodId")),
        "conjured": _resolve_consumable(_consumables_used.get("conjuredId")),
        "weapon_oil": _resolve_consumable(_consumables_used.get("mhImbueId"), WEAPON_IMBUE_REAL_IDS),
    }

    # "baseline_screened" key name predates this fix and is kept for compatibility
    # (build_ledger_data.py/check_ledger_consistency.py/report_template.html all
    # reference it) - its VALUE is now true_baseline_resolved["combined"] (her real,
    # honest current DPS, RESOLVE_ITERATIONS precision), not the old 500-iteration
    # idealized screen. baseline_screen itself is still real and still used above for
    # the actual MV(i) screening pass (mv.mv_single() calls) - only this one reported
    # value changed source.
    out_dir = os.path.join(USER_DATA_DIR, "characters", name_realm, "cache")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"tiered_report_{profile_dir_name}_{phase}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline_screened": true_baseline_resolved["combined"], "achieved_bis": achieved_bis,
                   "missing_enchants": missing_enchants,
                   "tiers": tiered_out, "two_hand": two_hand_out, "two_hand_meta": two_hand_meta,
                   "fight_duration_seconds": actual_duration,
                   "baseline_oom_seconds": baseline_oom_seconds,
                   "baseline_oom_fraction": baseline_oom_fraction,
                   "source_scope_excluded": source_scope_excluded,
                   "assumed_buffs": assumed_buffs, "used_consumables": used_consumables,
                   "dual_wield_alt": dual_wield_alt}, f, indent=2)
    print(f"Wrote {out_path}")
    milestone("Done")
    return out_path


if __name__ == "__main__":
    # Real CLI entry point is `gear best <character> <phase>` (cli/gear.py) -
    # this direct-invocation fallback exists only for quick manual debugging
    # against today's one real character/phase, matching the pipeline's
    # exact behavior before this file took real arguments. profile_dir became
    # a required arg under backlog #13 (no silent default - see main()'s own
    # docstring for the real bug that caused) - this fallback silently broke
    # then and has raised a bare TypeError on every direct invocation since;
    # fixed 2026-09-06 by resolving it the same way every other real caller
    # does, via character_profiles.SUPPORTED_CHARACTERS.
    import character_profiles
    _debug_name = "Lerynia-Thunderstrike"
    main(_debug_name, "phase3", character_profiles.SUPPORTED_CHARACTERS[_debug_name])
