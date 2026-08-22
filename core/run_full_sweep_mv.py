"""Runs MV for the full DB sweep (sweep_all_loot.py's shortlist), merged
with the existing Wowhead-curated pool, so nothing already found is lost
and nothing the guide omitted stays invisible. See NOTES.md for why this
exists - the curated pool alone was a hard exclusion, not a heuristic.
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

TYPE_TO_SLOT = {
    1: "head", 2: "neck", 3: "shoulder", 4: "back", 5: "chest", 6: "wrist",
    7: "hands", 8: "waist", 9: "legs", 10: "feet", 11: "ring", 12: "trinket",
    14: "ranged",
}
TWO_HAND = 4  # HandType enum


def slot_for_item(item: dict) -> str | None:
    t = item.get("type")
    if t == 13:  # Weapon
        if item.get("handType") == TWO_HAND:
            # Not just "she's dual-wield so 2H doesn't apply" - even to
            # evaluate a 2H candidate fairly, the rotation itself needs to
            # switch to melee weave (meleeWeave:true, present in the 2h_9p
            # preset's specRotationJson, absent from dw_9p's - see NOTES.md
            # Stage 1) wherever the boss allows it. Running a 2H weapon
            # under the current dual-wield settings (character parked at
            # range, no weave) would score it under the wrong playstyle
            # entirely, not just a worse one. That branching isn't built -
            # excluding 2H here rather than reporting a number that looks
            # real but tested the wrong rotation.
            return None
        return "weapon_dual_wield"
    return TYPE_TO_SLOT.get(t)


def describe_source(item: dict, npc_by_id: dict, zone_by_id: dict) -> str:
    for s in item.get("sources", []):
        if "drop" in s:
            npc = npc_by_id.get(s["drop"].get("npcId"))
            zone = zone_by_id.get(s["drop"].get("zoneId"))
            if npc and zone:
                return f"Drop: {npc} ({zone})"
            if npc:
                return f"Drop: {npc}"
        if "crafted" in s:
            prof = idb.PROFESSION_NAMES.get(s["crafted"].get("profession"), "Profession")
            return f"Crafted: {prof}"
        if "rep" in s:
            return "Reputation reward"
    return "Source unclear (in sim DB, acquisition method not tagged)"


def main():
    start = time.time()
    db = json.load(open(DB_PATH, encoding="utf-8"))
    npc_by_id = {n["id"]: n["name"] for n in db.get("npcs", [])}
    zone_by_id = {z["id"]: z["name"] for z in db.get("zones", [])}

    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]

    # Existing curated pool, as before.
    candidates = opt.load_candidates(POOL_PATH, owned_items)
    curated_ids = {c.item_id for cands in candidates.values() for c in cands if c.item_id}

    # Sweep additions: build Candidate objects directly (already have real
    # ids, no name-lookup ambiguity), same enchant/gem defaulting rules as
    # load_candidates (owned slot's real enchant/gems if owned, else her
    # established default gem + inherited slot enchant).
    sweep_items = json.load(open(SWEEP_PATH, encoding="utf-8"))
    owned_by_id = {it["id"]: it for it in owned_items if it}
    meta_gem_id = opt.find_owned_meta_gem(owned_items)
    added_sources = {}
    new_count = 0
    for item in sweep_items:
        if item["id"] in curated_ids:
            continue  # already covered by the curated pool
        slot = slot_for_item(item)
        if slot is None:
            continue
        req_prof = idb.required_profession_name(item)
        if req_prof and req_prof not in ("Herbalism", "Mining"):
            continue  # can't use it either way, no point reporting it

        # candidates (from opt.load_candidates) is keyed by real SLOT_ORDER
        # names, not pool-key names - ring/trinket/weapon_dual_wield each
        # fan out to the two real slots they share, same as
        # POOL_KEY_TO_SLOTS does internally for the curated pool.
        target_slots = {
            "weapon_dual_wield": ["mainhand", "offhand"],
            "ring": ["ring1", "ring2"],
            "trinket": ["trinket1", "trinket2"],
        }.get(slot, [slot])

        owned_here = owned_by_id.get(item["id"])
        if owned_here:
            cand = opt.Candidate(item["name"], item["id"], owned_here.get("enchant", 0), owned_here.get("gems"))
        else:
            # Rings/trinkets never carry enchants in this game - nothing to
            # inherit, correctly stays 0.
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
        added_sources[item["id"]] = describe_source(item, npc_by_id, zone_by_id)
        new_count += 1

    print(f"Curated pool: {len(curated_ids)} items. Sweep added {new_count} new candidates not on the guide.\n")

    mv.set_slot_hints(candidates)
    baseline_config = opt.build_owned_config(owned_items)
    baseline_screen = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, mv.SCREEN_ITERATIONS, opt.SEED)
    print(f"Baseline (current gear) @ {mv.SCREEN_ITERATIONS} iter: combined={baseline_screen['combined']:.1f}\n")

    seen_ids = set()
    all_candidates = []
    for slot, cands in candidates.items():
        for c in cands:
            if c.item_id is not None and c.item_id not in seen_ids:
                seen_ids.add(c.item_id)
                all_candidates.append(c)
    all_candidates.sort(key=lambda c: c.name)

    baseline_resolve_cache: dict = {}

    def run_one(c):
        return c, mv.mv_single_tiered(SETTINGS_TEMPLATE, baseline_config, c, baseline_screen, baseline_resolve_cache)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        pairs = list(ex.map(run_one, all_candidates))

    results = []
    for c, r in pairs:
        r["is_new_from_sweep"] = c.item_id in added_sources
        r["source"] = added_sources.get(c.item_id, "")
        results.append(r)

    new_upgrades = [r for r in results if r.get("is_new_from_sweep") and not r.get("excluded_reason")
                     and not r.get("tied_within_noise") and r.get("mv", 0) > 0]
    new_upgrades.sort(key=lambda r: r["mv"], reverse=True)

    print(f"NEW real upgrades found by the sweep that weren't on Wowhead's guide ({len(new_upgrades)}):")
    print(f"{'Item':<38} {'MV':>8}  Source")
    print("-" * 100)
    for r in new_upgrades:
        print(f"{r['name']:<38} {r['mv']:>+8.1f}  {r['source']}")

    elapsed = time.time() - start
    print(f"\nElapsed: {elapsed:.1f}s")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "mv_report_full_sweep.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline": baseline_screen, "items": results}, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
