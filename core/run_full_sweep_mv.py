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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_TEMPLATE = os.path.join(REPO_ROOT, "profiles", "tbc", "canonical_settings_survival.json")
# Same buffs/debuffs/talents/encounter as SETTINGS_TEMPLATE - only the
# "Melee weave" APL constant differs (see NOTES.md, 2026-08-23 melee weave
# entry). 2H weapons are only ever evaluated under this variant since a 2H
# weapon without weaving is a strict downgrade (loses the offhand item for
# nothing) - there's no reason to test one under the non-weave settings.
SETTINGS_2H = os.path.join(REPO_ROOT, "profiles", "tbc", "canonical_settings_survival_2h.json")
POOL_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "candidate_pool_survival.json")
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")
SWEEP_PATH = os.path.join(REPO_ROOT, "data", "cache", "full_sweep_candidates.json")
MAX_WORKERS = 2  # matches valuation.SIMSERVER_POOL_SIZE - see its comment for why 4 was 7.4x slower

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
# number that gets shown as final.
RESOLVE_ITERATIONS = 30000  # precise, only spent on each (tier, slot) leaderboard
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

TYPE_TO_SLOT = {
    1: "head", 2: "neck", 3: "shoulder", 4: "back", 5: "chest", 6: "wrist",
    7: "hands", 8: "waist", 9: "legs", 10: "feet", 11: "ring", 12: "trinket",
    14: "ranged",
}
TWO_HAND = 4

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


def slot_for_item(item: dict) -> str | None:
    t = item.get("type")
    if t == 13:
        if item.get("handType") == TWO_HAND:
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
    return "Source unclear", "Other", None


def run_with_progress(fn, items: list, label: str, workers: int = MAX_WORKERS, log_every_pct: int = 5) -> list:
    """Same concurrent map as `ThreadPoolExecutor(...).map(fn, items)`, plus
    periodic "label: done/total (pct%)" progress lines - real precursor to
    the GUI progress indicator already noted in CLAUDE.md's future-scope
    section (candidates screened so far / total, not a blank wait). Order of
    the returned list is NOT the same as `items` (completion order, not
    submission order) - both call sites here already only build a dict/set
    from the results, so this is safe; a future caller that needs input
    order preserved would need to carry an index through `fn` itself."""
    total = len(items)
    if total == 0:
        return []
    results = []
    done = 0
    last_logged_pct = -1
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(fn, item) for item in items]
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
            done += 1
            pct = done * 100 // total
            if done == total or (pct != last_logged_pct and pct % log_every_pct == 0):
                print(f"{label}: {done}/{total} ({pct}%)")
                last_logged_pct = pct
    return results


def main():
    start = time.time()
    db = json.load(open(DB_PATH, encoding="utf-8"))
    npc_by_id = {n["id"]: n["name"] for n in db.get("npcs", [])}
    zone_by_id = {z["id"]: z["name"] for z in db.get("zones", [])}

    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]
    # Everything she already possesses - equipped AND sitting in bags/bank -
    # isn't something to go acquire, so it's excluded from every tier below
    # (not just filtered by "would it improve DPS", which could still say
    # yes for a bagged item she hasn't bothered equipping).
    owned_all_ids = {it["id"] for it in owned_items if it}
    owned_all_ids |= {it["id"] for it in char["owned"]["bags"] if it}
    owned_all_ids |= {it["id"] for it in char["owned"]["bank"] if it}

    acquisition_status = acquisition_gate.load_status()

    candidates = opt.load_candidates(POOL_PATH, owned_items)
    curated_ids = {c.item_id for cands in candidates.values() for c in cands if c.item_id}
    # Curated-pool items' real Wowhead source text/tier, so they show up in
    # the right tier bucket too, not just the sweep additions.
    curated_source_text = {}
    p3_ref = json.load(open(os.path.join(REPO_ROOT, "profiles", "tbc", "reference_bis", "phase3_survival.json"), encoding="utf-8"))
    for entries in p3_ref["slots"].values():
        for e in entries:
            curated_source_text[e["item"]] = e["source"]

    sweep_items = json.load(open(SWEEP_PATH, encoding="utf-8"))
    owned_by_id = {it["id"]: it for it in owned_items if it}
    meta_gem_id = opt.find_owned_meta_gem(owned_items)
    item_meta = {}  # item_id -> (source_text, tier)
    new_count = 0

    # 2H weapons get their own pool, evaluated separately below (own
    # settings variant - meleeWeave, own baseline with the offhand
    # physically empty). They must NOT flow through the shared
    # `candidates`/all_candidates machinery further down, which assumes one
    # global SETTINGS_TEMPLATE and a normal DW offhand - exactly the "wrong
    # number, not just worse" trap this was excluded from before.
    weapon_2h_candidates: list[opt.Candidate] = []

    for item in sweep_items:
        if item["id"] in curated_ids:
            continue
        slot = slot_for_item(item)
        if slot is None:
            continue
        req_prof = idb.required_profession_name(item)
        if req_prof and req_prof not in ("Herbalism", "Mining"):
            continue

        if slot == "weapon_2h":
            owned_here = owned_by_id.get(item["id"])
            gems = owned_here.get("gems") if owned_here else opt.gems_for_item(item, meta_gem_id)
            enchant = owned_here.get("enchant", 0) if owned_here else 0
            weapon_2h_candidates.append(opt.Candidate(item["name"], item["id"], enchant, gems))
            item_meta[item["id"]] = describe_source_and_tier(item, npc_by_id, zone_by_id)
            new_count += 1
            continue

        target_slots = {
            "weapon_dual_wield": ["mainhand", "offhand"],
            "ring": ["ring1", "ring2"],
            "trinket": ["trinket1", "trinket2"],
        }.get(slot, [slot])

        owned_here = owned_by_id.get(item["id"])
        if owned_here:
            cand = opt.Candidate(item["name"], item["id"], owned_here.get("enchant", 0), owned_here.get("gems"))
        else:
            default_enchant = 0
            for s in target_slots:
                s_idx = gc.SLOT_ORDER.index(s)
                oi = owned_items[s_idx] if s_idx < len(owned_items) else None
                if oi and oi.get("enchant"):
                    default_enchant = oi["enchant"]
                    break
            gems = opt.gems_for_item(item, meta_gem_id)
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

    # Owned items stay IN the candidate pool (set-bonus progression below
    # needs to see a bagged/banked piece to correctly credit it toward a
    # set bonus) - they're filtered out only at the final report-row step,
    # so an already-owned item never appears as something to go acquire,
    # while still counting toward whether a set is worth completing.
    print(f"Curated pool: {len(curated_ids)} items. Sweep added {new_count} new candidates "
          f"({len(owned_all_ids)} already owned - kept for set-bonus math, hidden from acquisition tiers).\n")

    item_slot_label = {}
    for slot, cands in candidates.items():
        label = SLOT_DISPLAY.get(slot, slot.capitalize())
        for c in cands:
            if c.item_id is not None:
                item_slot_label.setdefault(c.item_id, label)

    mv.set_slot_hints(candidates)
    baseline_config = opt.build_owned_config(owned_items)
    baseline_screen = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, SCREEN_ITERATIONS, opt.SEED)
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
    for set_name in sorted(set_names):
        thresholds = set_bonus.set_bonus_thresholds().get(set_name, [])
        if not thresholds:
            continue
        parts = []
        any_real = False
        for threshold in thresholds:
            iso = set_bonus.isolate_bonus_value(SETTINGS_TEMPLATE, set_name, threshold,
                                                 candidates, baseline_config, SCREEN_ITERATIONS)
            if iso is None:
                continue
            tag = "" if iso["real"] else " (tied)"
            any_real = any_real or iso["real"]
            parts.append(f"{threshold}pc bonus {iso['isolated_value']:+.1f}{tag}")
        # Only flag items with this note if at least one threshold is a
        # real (non-tied) bonus - matches the original gating intent (a
        # set with no meaningful bonus anywhere shouldn't count as a
        # "real upgrade" for achieved-BiS/report-inclusion purposes).
        if not parts or not any_real:
            continue
        note = f"part of {set_name}: " + " · ".join(parts)
        for _, cand in set_bonus.set_pieces_in_pool(set_name, candidates):
            set_notes_by_item[cand.item_id] = note

        # Which 4 of the 5 armor slots should actually hold the set piece,
        # per the user: guides almost always recommend 4pc, occasionally
        # all 5 (rare) or fewer (weak bonuses) - determined by real sim
        # comparison across all five leave-one-out combos, not assumed.
        combo = set_bonus.best_four_of_five(SETTINGS_TEMPLATE, set_name, candidates,
                                             baseline_config, owned_items, SCREEN_ITERATIONS)
        if combo is not None:
            if combo["excluded_slot"] is not None:
                print(f"  Best combo for {set_name}: {', '.join(combo['best_combo_slots'])} "
                      f"(leave {combo['excluded_slot']} non-tier) - "
                      f"full 5pc is {combo['full_five_dps'] - combo['combined_dps']:+.1f} vs this (screened)")
            else:
                print(f"  Best combo for {set_name}: all 5 pieces ({combo['combined_dps']:.1f})")

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

    screened = run_with_progress(screen_one, all_candidates, "Screening")
    print(f"[+{time.time()-start:.1f}s] Screened {len(screened)} candidates @ {SCREEN_ITERATIONS} iter")

    # --- Pick each (tier, slot) leaderboard from the screening results ---
    by_tier_slot: dict[tuple[str, str], list] = {}
    for c, r in screened:
        if r.get("excluded_reason"):
            continue
        if c.item_id in owned_all_ids:
            continue  # already hers - not an acquisition target, see note above
        source, tier, craft_spell_id = item_meta.get(c.item_id, ("", "Other", None))
        slot_label = item_slot_label.get(c.item_id, "Other")
        r = dict(r, source=source, tier=tier, slot=slot_label, item_id=c.item_id,
                 craft_spell_id=craft_spell_id,
                 set_note=set_notes_by_item.get(c.item_id),
                 gate=acquisition_gate.gate_for_item(source, slot_label, acquisition_status),
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
        rows.sort(key=lambda cr: cr[1]["mv"], reverse=True)
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

    def confirm_one(cr):
        c, _ = cr
        return c.item_id, mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_confirm,
                                        CONFIRM_ITERATIONS, opt.SEED, baseline_agility=baseline_agility)

    confirmed_pairs = run_with_progress(confirm_one, to_resolve, "Confirming")
    confirmed_by_id = dict(confirmed_pairs)

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
        if abs(confirmed_by_id[c.item_id]["mv"]) < CONFIRM_CLEAR_MARGIN_MULTIPLE * confirmed_by_id[c.item_id]["noise_stdev"]
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

    # raid_ap_per_attacker is computed at whichever precision tier produces
    # the final number for a given item (confirm or resolve) - only items
    # that skip BOTH (screened-only) miss it here (handled by the separate
    # screened_upgrades_needing_ap pass below), same "already clear, don't
    # spend more compute on it" principle already applied to DPS.
    def resolve_one(cr):
        c, _ = cr
        return c.item_id, mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_resolved,
                                        RESOLVE_ITERATIONS, opt.SEED, baseline_agility=baseline_agility)

    resolved_pairs = run_with_progress(resolve_one, need_full_resolve, "Resolving")
    resolved_by_id = dict(resolved_pairs)

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            if c.item_id in resolved_by_id:
                res = resolved_by_id[c.item_id]
                r["mv"] = res["mv"]
                r["noise_stdev"] = res["noise_stdev"]
                r["tied_within_noise"] = res["tied_within_noise"]
                r["raid_ap_per_attacker"] = res.get("raid_ap_per_attacker")
                r["resolved"] = True
                r["resolve_iterations"] = RESOLVE_ITERATIONS
            elif c.item_id in confirmed_by_id:
                res = confirmed_by_id[c.item_id]
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
                                            baseline_config, candidates, RESOLVE_ITERATIONS, opt.SEED)
            return c.item_id, set_name, check

        rescue_results = run_with_progress(rescue_one, rescue_candidates, "Rescue-checking")
        for item_id, set_name, check in rescue_results:
            if check and not check["tied_within_noise"] and check["mv_if_set_broken"] > 0:
                rescue_notes_by_item[item_id] = (
                    f"Not an upgrade today (breaks {set_name}'s bonus), but a real "
                    f"{check['mv_if_set_broken']:+.1f} DPS gain once that bonus is "
                    f"already broken elsewhere (e.g. via {check['via_item']} in {check['via_slot']})."
                )
                rescue_mv_by_item[item_id] = check["mv_if_set_broken"]
        if rescue_notes_by_item:
            print(f"Rescue check: {len(rescue_notes_by_item)} item(s) found to be real upgrades "
                  f"once their set-bonus break is already priced in elsewhere.\n")

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            r["rescue_note"] = rescue_notes_by_item.get(c.item_id)
            r["rescue_mv"] = rescue_mv_by_item.get(c.item_id)

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

    def add_ap_only(cr):
        c, _ = cr
        return c.item_id, mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_screen,
                                        SCREEN_ITERATIONS, opt.SEED, baseline_agility=baseline_agility)

    ap_only_pairs = run_with_progress(add_ap_only, screened_upgrades_needing_ap, "Raid-AP lookups")
    ap_only_by_id = dict(ap_only_pairs)

    for key, rows in by_tier_slot.items():
        for c, r in rows:
            if not r["resolved"] and c.item_id in ap_only_by_id:
                r["raid_ap_per_attacker"] = ap_only_by_id[c.item_id].get("raid_ap_per_attacker")

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

    slots_with_upgrades = set()
    for (tier, slot), rows in by_tier_slot.items():
        if any(is_available_upgrade(r) for _, r in rows):
            slots_with_upgrades.add(slot)

    display_to_real_slots = {}
    for real, disp in SLOT_DISPLAY.items():
        display_to_real_slots.setdefault(disp, []).append(real)

    achieved_bis = []
    for slot in SLOT_DISPLAY_ORDER:
        if slot in slots_with_upgrades:
            continue
        items_here = []
        for real in display_to_real_slots.get(slot, []):
            idx = gc.SLOT_ORDER.index(real)
            owned = owned_items[idx] if idx < len(owned_items) else None
            if owned:
                items_here.append({"name": owned.get("name", "?"), "item_id": owned.get("id")})
        if items_here:
            achieved_bis.append({"slot": slot, "items": items_here})

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
        print("=== Achieved BiS (nothing in the Phase 3 pool beats these) ===")
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
            upgrades.sort(key=lambda r: r["rescue_mv"] if r.get("rescue_note") else r["mv"], reverse=True)
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
    # Compared against her CURRENT DW gear WITH weave enabled (not the
    # no-weave baseline) - per the user, weave only happens "on bosses that
    # allow for it", so on those specific bosses the real decision is
    # "given I'm already weaving, does switching to a 2H weapon help
    # further" - not "should I abandon DW entirely". The no-weave baseline
    # is printed alongside for context, never silently dropped.
    print(f"[+{time.time()-start:.1f}s] Tiered report built. Starting 2H weapon analysis...")

    two_hand_out: list[dict] = []
    two_hand_meta: dict = {}
    if weapon_2h_candidates:
        weave_dw_result = mv.valuation.evaluate(SETTINGS_2H, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
        no_weave_result = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, RESOLVE_ITERATIONS, opt.SEED)
        print(f"=== 2H Weapon Options (melee weave rotation) ===")
        print(f"Baseline, current DW gear, weave OFF: {no_weave_result['combined']:.1f}")
        print(f"Baseline, current DW gear, weave ON:  {weave_dw_result['combined']:.1f} "
              f"(+{weave_dw_result['combined'] - no_weave_result['combined']:.1f} from weave alone)\n")
        two_hand_meta = {"no_weave_dw": no_weave_result["combined"], "weave_dw": weave_dw_result["combined"]}

        mh_idx = gc.SLOT_ORDER.index("mainhand")
        oh_idx = gc.SLOT_ORDER.index("offhand")

        def screen_2h(c: opt.Candidate):
            trial = list(baseline_config)
            trial[mh_idx] = c.as_entry()
            trial[oh_idx] = {}
            r = mv.valuation.evaluate(SETTINGS_2H, trial, SCREEN_ITERATIONS, opt.SEED)
            return c, trial, r

        screened_2h = run_with_progress(screen_2h, weapon_2h_candidates, "Screening 2H weapons")

        rows_2h = []
        for c, trial, r in screened_2h:
            delta = r["combined"] - weave_dw_result["combined"]
            noise = mv.delta_noise(weave_dw_result, r, SCREEN_ITERATIONS)
            source, tier, craft_spell_id = item_meta.get(c.item_id, ("Source unclear", "Other", None))
            rows_2h.append({"name": c.name, "item_id": c.item_id, "trial": trial,
                             "mv": delta, "noise_stdev": noise,
                             "tied_within_noise": abs(delta) < 2 * noise,
                             "source": source, "tier": tier, "craft_spell_id": craft_spell_id,
                             "resolved": False, **time_horizon.lasts_until_phase(c.name, c.item_id)})
        rows_2h.sort(key=lambda r: r["mv"], reverse=True)

        def resolve_2h_row(r):
            resolved = mv.valuation.evaluate(SETTINGS_2H, r["trial"], RESOLVE_ITERATIONS, opt.SEED)
            r["mv"] = resolved["combined"] - weave_dw_result["combined"]
            r["noise_stdev"] = mv.delta_noise(weave_dw_result, resolved, RESOLVE_ITERATIONS)
            r["tied_within_noise"] = abs(r["mv"]) < 2 * r["noise_stdev"]
            r["resolved"] = True

        to_resolve_2h = [r for r in rows_2h[:LEADERBOARD_SIZE]
                          if abs(r["mv"]) < mv.CLEAR_MARGIN_MULTIPLE * r["noise_stdev"]]
        run_with_progress(resolve_2h_row, to_resolve_2h, "Resolving 2H")

        real_upgrades_2h = [r for r in rows_2h if not r["tied_within_noise"] and r["mv"] > 0]
        top_2h = real_upgrades_2h[:TOP_N_2H]

        # Same rule as the main leaderboard: whatever's actually shown always
        # gets the real resolve, regardless of margin - per the user, if a
        # screened item ends up in the visible list, actually sim it.
        for r in top_2h:
            if not r["resolved"]:
                resolve_2h_row(r)
        top_2h.sort(key=lambda r: r["mv"], reverse=True)
        two_hand_out = top_2h

        for r in rows_2h:
            r.pop("trial")

        if top_2h:
            print(f"  -- Top {len(top_2h)} 2H upgrade(s) across all tiers/zones vs weaving with current DW gear --")
            for r in top_2h:
                flag = "" if r["resolved"] else "  (screened only)"
                horizon = horizon_tag(r)
                print(f"    {r['name']:<36} Player: {r['mv']:>+7.1f} DPS  {r['tier']}: {r['source']}{flag}{horizon}")
            if len(real_upgrades_2h) > len(top_2h):
                print(f"    ...and {len(real_upgrades_2h) - len(top_2h)} more real upgrade(s) not shown.")
        else:
            print("  No 2H weapon beats weaving with her current DW gear.")
        print()
    else:
        print("=== 2H Weapon Options (melee weave rotation) ===\n  No eligible 2H weapons in the pool.\n")

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

    out_path = os.path.join(REPO_ROOT, "data", "cache", "tiered_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline_screened": baseline_screen["combined"], "achieved_bis": achieved_bis,
                   "tiers": tiered_out, "two_hand": two_hand_out, "two_hand_meta": two_hand_meta}, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
