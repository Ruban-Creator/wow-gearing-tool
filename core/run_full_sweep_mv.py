"""Full-sweep MV, tiered by acquisition source (T6/T5/T4/Heroics/Vanilla
carryover/Crafted/Reputation) per the user's request - and per the user's
follow-up correction to how the compute budget gets spent: screen
EVERYTHING cheap first, then only pay for the 30k resolve pass on each
tier's leaderboard (top ~8, enough margin to keep "top 5" trustworthy after
resolving), not on every candidate that happens to be near the noise floor.
A candidate pool this large has hundreds of items clustered near zero
(most random raid drops don't beat an already-decent-itemized character) -
resolving all of them was the actual reason the first run of this was
taking so long, not the sim being slow.
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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_TEMPLATE = os.path.join(REPO_ROOT, "profiles", "tbc", "canonical_settings_survival.json")
POOL_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "candidate_pool_survival.json")
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")
SWEEP_PATH = os.path.join(REPO_ROOT, "data", "cache", "full_sweep_candidates.json")
MAX_WORKERS = 4

SCREEN_ITERATIONS = 1000  # cheap ranking pass across the whole pool
RESOLVE_ITERATIONS = 30000  # precise, only spent on each tier's leaderboard
LEADERBOARD_SIZE = 8  # per tier, resolved - a little slack over "top 5" in
# case resolving nudges the screening order around near the cutoff

TYPE_TO_SLOT = {
    1: "head", 2: "neck", 3: "shoulder", 4: "back", 5: "chest", 6: "wrist",
    7: "hands", 8: "waist", 9: "legs", 10: "feet", 11: "ring", 12: "trinket",
    14: "ranged",
}
TWO_HAND = 4

TIER_ZONES = {
    "T6 (Black Temple / Mount Hyjal)": {3606, 3959},
    "T5 (Serpentshrine Cavern / Tempest Keep)": {3607, 3845},
    "T4 (Karazhan / Gruul's Lair / Magtheridon's Lair)": {3457, 3923, 3836},
    "TBC Heroics": {3562, 3713, 3714, 3715, 3716, 3717, 3789, 3790, 3791, 3792, 3847, 3848, 3849, 2366, 2367},
    "Vanilla carryover": {1583, 1584, 1977, 2017, 2057, 2159, 2557, 2677, 2717, 3428, 3429, 3456},
}


def slot_for_item(item: dict) -> str | None:
    t = item.get("type")
    if t == 13:
        if item.get("handType") == TWO_HAND:
            return None  # needs the melee-weave rotation variant - not built, see NOTES.md
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


def describe_source_and_tier(item: dict, npc_by_id: dict, zone_by_id: dict) -> tuple[str, str]:
    for s in item.get("sources", []):
        if "drop" in s:
            zid = s["drop"].get("zoneId")
            npc = npc_by_id.get(s["drop"].get("npcId"))
            zone = zone_by_id.get(zid, f"zone {zid}")
            tier = next((t for t, zones in TIER_ZONES.items() if zid in zones), "Other drop")
            desc = f"Drop: {npc} ({zone})" if npc else f"Drop: ({zone})"
            return desc, tier
        if "crafted" in s:
            prof = idb.PROFESSION_NAMES.get(s["crafted"].get("profession"), "Profession")
            return f"Crafted: {prof}", "Crafted"
        if "rep" in s:
            return "Reputation reward", "Reputation reward"
    return "Source unclear", "Other"


def main():
    start = time.time()
    db = json.load(open(DB_PATH, encoding="utf-8"))
    npc_by_id = {n["id"]: n["name"] for n in db.get("npcs", [])}
    zone_by_id = {z["id"]: z["name"] for z in db.get("zones", [])}

    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]

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

    for item in sweep_items:
        if item["id"] in curated_ids:
            continue
        slot = slot_for_item(item)
        if slot is None:
            continue
        req_prof = idb.required_profession_name(item)
        if req_prof and req_prof not in ("Herbalism", "Mining"):
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
            db_desc, tier = describe_source_and_tier(db_item, npc_by_id, zone_by_id) if db_item else ("Source unclear", "Other")
            source = curated_source_text.get(c.name) or db_desc
            if tier == "Other" and source != db_desc:
                tier = tier_from_text(source, zone_by_id) or tier
            item_meta[c.item_id] = (source, tier)

    print(f"Curated pool: {len(curated_ids)} items. Sweep added {new_count} new candidates.\n")

    mv.set_slot_hints(candidates)
    baseline_config = opt.build_owned_config(owned_items)
    baseline_screen = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, SCREEN_ITERATIONS, opt.SEED)
    print(f"Baseline @ {SCREEN_ITERATIONS} iter (screening): combined={baseline_screen['combined']:.1f}\n")

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

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        screened = list(ex.map(screen_one, all_candidates))
    print(f"Screened {len(screened)} candidates @ {SCREEN_ITERATIONS} iter in {time.time()-start:.1f}s")

    # --- Pick each tier's leaderboard from the screening results ---
    by_tier: dict[str, list] = {}
    for c, r in screened:
        if r.get("excluded_reason"):
            continue
        source, tier = item_meta.get(c.item_id, ("", "Other"))
        r = dict(r, source=source, tier=tier, item_id=c.item_id)
        by_tier.setdefault(tier, []).append((c, r))

    to_resolve = []
    for tier, rows in by_tier.items():
        rows.sort(key=lambda cr: cr[1]["mv"], reverse=True)
        to_resolve.extend(rows[:LEADERBOARD_SIZE])

    # --- Pass 2: resolve only each tier's leaderboard, properly ---
    baseline_resolved = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, RESOLVE_ITERATIONS, opt.SEED)

    def resolve_one(cr):
        c, _ = cr
        return c.item_id, mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_resolved, RESOLVE_ITERATIONS, opt.SEED)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        resolved_pairs = list(ex.map(resolve_one, to_resolve))
    resolved_by_id = dict(resolved_pairs)

    for tier, rows in by_tier.items():
        for c, r in rows:
            if c.item_id in resolved_by_id:
                res = resolved_by_id[c.item_id]
                r["mv"] = res["mv"]
                r["noise_stdev"] = res["noise_stdev"]
                r["tied_within_noise"] = res["tied_within_noise"]
                r["resolved"] = True
            else:
                r["resolved"] = False

    print(f"Resolved {len(to_resolve)} leaderboard candidates @ {RESOLVE_ITERATIONS} iter.\n")

    order = list(TIER_ZONES.keys()) + ["Crafted", "Reputation reward", "Other", "Other drop"]
    tiered_out = {}
    for tier in order:
        rows = by_tier.get(tier, [])
        upgrades = [r for _, r in rows if not r["tied_within_noise"] and r["mv"] > 0]
        upgrades.sort(key=lambda r: r["mv"], reverse=True)
        tiered_out[tier] = upgrades
        if not upgrades:
            print(f"=== {tier} ===\n  No real upgrades found.\n")
            continue
        n_resolved = sum(1 for u in upgrades[:5] if u.get("resolved"))
        print(f"=== {tier} ({len(upgrades)} real upgrades, top 5 shown, {n_resolved}/5 resolved @ 30k) ===")
        for r in upgrades[:5]:
            flag = "" if r.get("resolved") else "  (screened only)"
            print(f"  {r['name']:<38} {r['mv']:>+7.1f}  {r['source']}{flag}")
        if len(upgrades) > 5:
            print(f"  ...and {len(upgrades) - 5} more.")
        print()

    elapsed = time.time() - start
    print(f"Elapsed: {elapsed:.1f}s")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "tiered_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline_screened": baseline_screen["combined"], "tiers": tiered_out}, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
