import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import item_db as idb  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_TEMPLATE = os.path.join(REPO_ROOT, "data", "cache", "user_export_2.json")
POOL_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "candidate_pool_survival.json")


def main():
    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]

    candidates = opt.load_candidates(POOL_PATH, owned_items)

    print("Excluded candidates (profession gating or unresolved):")
    any_excluded = False
    for slot, cands in candidates.items():
        for c in cands:
            if c.excluded_reason:
                any_excluded = True
                print(f"  {slot}: {c.name} - {c.excluded_reason}")
    if not any_excluded:
        print("  (none)")
    print()

    config = opt.build_owned_config(owned_items)
    start = time.time()
    log = []

    baseline = opt.eval_config(SETTINGS_TEMPLATE, config)
    print(f"Warm start (current gear) @ {opt.SCREEN_ITERATIONS} iter: combined={baseline['combined']:.1f}")
    print()

    config, passes = opt.greedy_sweep(SETTINGS_TEMPLATE, config, candidates, log)
    config = opt.trinket_pairs(SETTINGS_TEMPLATE, config, candidates["trinket1"], log)
    config = opt.ranged_exhaustive(SETTINGS_TEMPLATE, config, candidates["ranged"], log)
    config = opt.set_bonus_branch(
        SETTINGS_TEMPLATE, config, candidates,
        "Gronnstalker's Armor", ["head", "shoulder", "chest", "hands"], log,
    )

    final = opt.eval_config(SETTINGS_TEMPLATE, config)
    elapsed = time.time() - start

    print(f"Greedy sweep: {passes} pass(es)")
    for entry in log:
        print(f"  {entry}")
    print()
    print(f"Screening result @ {opt.SCREEN_ITERATIONS} iter: combined={final['combined']:.1f} "
          f"(vs warm start {baseline['combined']:.1f}, +{final['combined'] - baseline['combined']:.1f})")
    print(f"Elapsed: {elapsed:.1f}s")
    print()

    print("Final screened set:")
    for slot, entry in zip(gc.SLOT_ORDER, config):
        item = idb.by_id(entry.get("id")) if entry.get("id") else None
        name = item["name"] if item else "(empty)"
        owned_name = owned_items[gc.SLOT_ORDER.index(slot)].get("name") if owned_items[gc.SLOT_ORDER.index(slot)] else "(empty)"
        marker = "" if name == owned_name else "  <-- CHANGED"
        print(f"  {slot:<10} {name}{marker}")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "optimizer_screening_result.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"config": config, "final": final, "baseline": baseline, "log": log}, f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
