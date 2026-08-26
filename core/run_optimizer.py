import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import item_db as idb  # noqa: E402
import gem_optimizer as gopt  # noqa: E402
import stat_weights  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
PROFILE_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")
SETTINGS_TEMPLATE = os.path.join(PROFILE_DIR, "settings_template.json")
POOL_PATH = os.path.join(PROFILE_DIR, "candidate_pool.json")
REFERENCE_P3_PATH = os.path.join(PROFILE_DIR, "reference_bis", "phase3.json")


def main():
    # Stage 6 (multi-class support): required active-profile setup - see
    # verify_gem_choices.py's identical block for why. This whole file is
    # flagged elsewhere (CLAUDE.md) as the superseded design not to build
    # on further - kept runnable, not otherwise invested in.
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

    reference = json.load(open(REFERENCE_P3_PATH, encoding="utf-8"))
    # Quiver/ammo-pouch items aren't one of our 17 equip slots (they're bag
    # items) - drop them from the bundle rather than let them block
    # resolution of everything else.
    bundle_names = [n for n in reference["recommended_full_set"] if n != "Quiver of a Thousand Feathers"]
    config = opt.full_bundle_branch(
        SETTINGS_TEMPLATE, config, candidates,
        "Wowhead P3 recommended full set", bundle_names, owned_items, log,
    )

    # Final resolve at high iteration - the number reported as "final" must
    # never be a bare screening number again (see NOTES.md's correction).
    final = opt.resolve(SETTINGS_TEMPLATE, config)
    baseline_resolved = opt.resolve(SETTINGS_TEMPLATE, opt.build_owned_config(owned_items))
    elapsed = time.time() - start

    print(f"Greedy sweep: {passes} pass(es)")
    for entry in log:
        print(f"  {entry}")
    print()
    print(f"Screening baseline (current gear) @ {opt.SCREEN_ITERATIONS} iter: combined={baseline['combined']:.1f}")
    print(f"RESOLVED @ {opt.RESOLVE_ITERATIONS} iter: current gear={baseline_resolved['combined']:.1f}, "
          f"final={final['combined']:.1f} (+{final['combined'] - baseline_resolved['combined']:.1f})")
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
