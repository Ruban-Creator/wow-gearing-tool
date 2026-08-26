"""Per-item MV report: for each real candidate, is it an upgrade over her
current gear, and by how much - the actual question (§1), not a full-set
search. Baseline P = her current equipped gear (what "this item dropped,
bid or pass" is actually asked against).

Screens every candidate at 2k iterations first and only pays for a 30k
resolve pass on the ones close enough to the noise floor to matter (see
marginal_value.mv_single_tiered) - most candidates are clear upgrades or
downgrades already at 2k, resolving all 79 of them at 30k was pure waste.
Also runs candidates concurrently (each is an independent subprocess call;
wowsimcli parallelizes internally too, so this was leaving cores idle
before, not adding contention on top - see NOTES.md, "faster MV report").
"""
import concurrent.futures
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402
import gear_config as gc  # noqa: E402
import gem_optimizer as gopt  # noqa: E402
import stat_weights  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
PROFILE_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")
SETTINGS_TEMPLATE = os.path.join(PROFILE_DIR, "settings_template.json")
POOL_PATH = os.path.join(PROFILE_DIR, "candidate_pool.json")
REFERENCE_P3_PATH = os.path.join(PROFILE_DIR, "reference_bis", "phase3.json")
MAX_WORKERS = 4


def main():
    start = time.time()
    # Stage 6 (multi-class support): required active-profile setup - see
    # verify_gem_choices.py's identical block for why.
    stat_weights.set_active(stat_weights.load(PROFILE_DIR))
    profile = json.load(open(os.path.join(PROFILE_DIR, "profile.json"), encoding="utf-8"))
    gc.set_active_default_gem(profile["primary_gem_id"])
    _default_enchants_path = os.path.join(PROFILE_DIR, "default_enchants.json")
    gc.set_active_default_enchants(json.load(open(_default_enchants_path, encoding="utf-8"))
                                    if os.path.exists(_default_enchants_path) else {})
    chase_bonus = json.load(open(os.path.join(PROFILE_DIR, "chase_bonus_gems.json"), encoding="utf-8"))
    gopt.set_active_chase_bonus_ids(set(chase_bonus["item_ids"]))

    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]

    candidates = opt.load_candidates(POOL_PATH, owned_items)
    mv.set_slot_hints(candidates)

    baseline_config = opt.build_owned_config(owned_items)
    baseline_screen = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, mv.SCREEN_ITERATIONS, opt.SEED)
    print(f"Baseline (current gear) @ {mv.SCREEN_ITERATIONS} iter (screening): combined={baseline_screen['combined']:.1f}\n")

    # Every candidate across every slot, deduplicated by item id.
    seen_ids = set()
    all_candidates = []
    for slot, cands in candidates.items():
        for c in cands:
            if c.item_id is not None and c.item_id not in seen_ids:
                seen_ids.add(c.item_id)
                all_candidates.append(c)
    all_candidates.sort(key=lambda c: c.name)

    # Shared lazily-populated slot so the expensive baseline resolve (30k
    # iterations) only runs once total, the first time any candidate turns
    # out to need it - not once per close candidate.
    baseline_resolve_cache: dict = {}

    def run_one(c):
        return c, mv.mv_single_tiered(SETTINGS_TEMPLATE, baseline_config, c, baseline_screen, baseline_resolve_cache)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        pairs = list(ex.map(run_one, all_candidates))

    print(f"{'Item':<35} {'MV':>8} {'+/- noise':>10} {'iter':>7}  Verdict")
    print("-" * 90)
    results = []
    resolved_count = 0
    for c, r in pairs:
        results.append(r)
        if "excluded_reason" in r:
            print(f"{c.name:<35} {'--':>8} {'':>10} {'':>7}  excluded: {r['excluded_reason']}")
            continue
        if r.get("resolved"):
            resolved_count += 1
        verdict = "TIED (within noise)" if r["tied_within_noise"] else ("upgrade" if r["mv"] > 0 else "downgrade")
        print(f"{r['name']:<35} {r['mv']:>+8.1f} {r['noise_stdev']:>10.2f} {r['iterations']:>7}  {verdict}")

    print(f"\n{resolved_count}/{len(all_candidates)} candidates needed the 30k resolve pass "
          f"(rest were clear at 2k screening).")

    print()
    baseline_resolved = baseline_resolve_cache.get("value") or mv.valuation.evaluate(
        SETTINGS_TEMPLATE, baseline_config, mv.RESOLVE_ITERATIONS, opt.SEED)
    reference = json.load(open(REFERENCE_P3_PATH, encoding="utf-8"))
    bundle_names = [n for n in reference["recommended_full_set"] if n != "Quiver of a Thousand Feathers"]
    bundle_config = opt.resolve_name_to_config(bundle_names, candidates, owned_items)
    if bundle_config:
        bundle_result = mv.mv_bundle(SETTINGS_TEMPLATE, baseline_config, bundle_config, baseline_resolved, mv.RESOLVE_ITERATIONS)
        verdict = "TIED (within noise)" if bundle_result["tied_within_noise"] else ("upgrade" if bundle_result["mv"] > 0 else "downgrade")
        print(f"PACKAGE - full Gronnstalker T6 set (all pieces at once) @ {mv.RESOLVE_ITERATIONS} iter: "
              f"MV={bundle_result['mv']:+.1f} +/-{bundle_result['noise_stdev']:.1f}  {verdict}")

    elapsed = time.time() - start
    print(f"\nElapsed: {elapsed:.1f}s")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "mv_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline": baseline_screen, "items": results}, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
