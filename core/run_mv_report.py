"""Per-item MV report: for each real candidate, is it an upgrade over her
current gear, and by how much - the actual question (§1), not a full-set
search. Baseline P = her current equipped gear (what "this item dropped,
bid or pass" is actually asked against).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as opt  # noqa: E402
import marginal_value as mv  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_TEMPLATE = os.path.join(REPO_ROOT, "profiles", "tbc", "canonical_settings_survival.json")
POOL_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "candidate_pool_survival.json")
REFERENCE_P3_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "reference_bis", "phase3_survival.json")
ITERATIONS = 30000


def main():
    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]

    candidates = opt.load_candidates(POOL_PATH, owned_items)
    mv.set_slot_hints(candidates)

    baseline_config = opt.build_owned_config(owned_items)
    baseline_result = mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, ITERATIONS, opt.SEED)
    print(f"Baseline (current gear) @ {ITERATIONS} iter: combined={baseline_result['combined']:.1f} "
          f"(player stdev {baseline_result['player_stdev']:.2f})\n")

    # Every candidate across every slot, deduplicated by item id (a name can
    # appear in multiple slot pools, e.g. nothing here, but be safe).
    seen_ids = set()
    all_candidates = []
    for slot, cands in candidates.items():
        for c in cands:
            if c.item_id is not None and c.item_id not in seen_ids:
                seen_ids.add(c.item_id)
                all_candidates.append(c)

    print(f"{'Item':<35} {'MV':>8} {'+/- noise':>10}  Verdict")
    print("-" * 80)
    results = []
    for c in sorted(all_candidates, key=lambda c: c.name):
        r = mv.mv_single(SETTINGS_TEMPLATE, baseline_config, c, baseline_result, ITERATIONS)
        results.append(r)
        if "excluded_reason" in r:
            print(f"{c.name:<35} {'--':>8} {'':>10}  excluded: {r['excluded_reason']}")
            continue
        verdict = "TIED (within noise)" if r["tied_within_noise"] else ("upgrade" if r["mv"] > 0 else "downgrade")
        print(f"{r['name']:<35} {r['mv']:>+8.1f} {r['noise_stdev']:>10.1f}  {verdict}")

    print()
    reference = json.load(open(REFERENCE_P3_PATH, encoding="utf-8"))
    bundle_names = [n for n in reference["recommended_full_set"] if n != "Quiver of a Thousand Feathers"]
    bundle_config = opt.resolve_name_to_config(bundle_names, candidates, owned_items)
    if bundle_config:
        bundle_result = mv.mv_bundle(SETTINGS_TEMPLATE, baseline_config, bundle_config, baseline_result, ITERATIONS)
        verdict = "TIED (within noise)" if bundle_result["tied_within_noise"] else ("upgrade" if bundle_result["mv"] > 0 else "downgrade")
        print(f"PACKAGE - full Gronnstalker T6 set (all pieces at once): "
              f"MV={bundle_result['mv']:+.1f} +/-{bundle_result['noise_stdev']:.1f}  {verdict}")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "mv_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"baseline": baseline_result, "items": results}, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
