"""Real-sim verification of gem_optimizer's "pure Agility everywhere" default,
broadened from the single-item spot check that originally disproved the
crude STAT_WEIGHTS-based "smart" hybrid heuristic (Ranger-General's
Chestguard: pure Agility 2701.4 beat the hybrid's 2651.6 - see NOTES.md).

That was N=1. This runs the same real-sim comparison (gem_optimizer.
verify_gem_choice: pure Agility vs the item's own socket-bonus-chased
loadout, real DPS, not a linear stat-weight guess) across every real
candidate in her actual pool that has sockets - 38 of her 71 current
candidates, more than half - to find out whether "pure Agility always
wins" actually generalizes or whether some item's socket bonus is real
enough to beat it. Screens all of them cheap first, only resolves the
close calls at high iterations - same funnel discipline as
marginal_value.mv_single_tiered.

Usage: python core/verify_gem_choices.py
"""
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import item_db as idb  # noqa: E402
import gem_optimizer as gopt  # noqa: E402
import marginal_value as mv  # noqa: E402

SETTINGS_TEMPLATE = os.path.join(REPO_ROOT, "profiles", "tbc", "canonical_settings_survival.json")
POOL_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "candidate_pool_survival.json")
SCREEN_ITERATIONS = 3000
RESOLVE_ITERATIONS = 30000
CLEAR_MARGIN_MULTIPLE = 8


def main():
    start = time.time()
    char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
    owned_items = char["equipped"]["items"]
    meta_gem_id = opt.find_owned_meta_gem(owned_items)
    baseline_config = opt.build_owned_config(owned_items)

    candidates = opt.load_candidates(POOL_PATH, owned_items)

    seen_ids = set()
    to_check = []  # (slot, candidate, item_id, item)
    for slot, cands in candidates.items():
        for c in cands:
            if c.item_id is None or c.item_id in seen_ids or c.excluded_reason:
                continue
            seen_ids.add(c.item_id)
            item = idb.by_id(c.item_id)
            if item and (item.get("gemSockets") or []):
                to_check.append((slot, c, item))

    print(f"Checking {len(to_check)} real candidates with sockets out of {len(seen_ids)} unique candidates.\n")

    results = []
    for slot, c, item in to_check:
        slot_idx = gc.SLOT_ORDER.index(slot)
        trial_config = list(baseline_config)
        trial_config[slot_idx] = c.as_entry()
        res = gopt.verify_gem_choice(item, meta_gem_id, SETTINGS_TEMPLATE, trial_config,
                                      slot_idx, SCREEN_ITERATIONS, opt.SEED)
        if not res["applicable"]:
            continue  # every socket already Red/Meta - pure Agility trivially wins, nothing to check
        res["name"] = c.name
        res["slot"] = slot
        res["item_id"] = c.item_id
        res["resolved"] = False
        results.append((trial_config, slot_idx, item, res))
        print(f"  [screen] {c.name:40s} delta={res['delta']:+7.2f}  tied={res['tied_within_noise']}")

    to_resolve = [r for r in results if abs(r[3]["delta"]) < CLEAR_MARGIN_MULTIPLE * r[3]["noise_stdev"]]
    print(f"\n[+{time.time()-start:.1f}s] Screened {len(results)}, {len(to_resolve)} close enough to resolve @ {RESOLVE_ITERATIONS}.\n")

    for trial_config, slot_idx, item, res in to_resolve:
        resolved = gopt.verify_gem_choice(item, meta_gem_id, SETTINGS_TEMPLATE, trial_config,
                                           slot_idx, RESOLVE_ITERATIONS, opt.SEED)
        res.update(resolved)
        res["resolved"] = True
        print(f"  [resolve] {res['name']:40s} delta={res['delta']:+7.2f}  tied={res['tied_within_noise']}")

    print(f"\n[+{time.time()-start:.1f}s] Done.\n")

    real_wins = [r[3] for r in results if not r[3]["tied_within_noise"] and r[3]["delta"] > 0]
    real_losses = [r[3] for r in results if not r[3]["tied_within_noise"] and r[3]["delta"] < 0]
    ties = [r[3] for r in results if r[3]["tied_within_noise"]]

    print(f"Real socket-bonus wins (chase_bonus beats pure Agility): {len(real_wins)}")
    for r in sorted(real_wins, key=lambda r: -r["delta"]):
        print(f"  {r['name']:40s} slot={r['slot']:10s} +{r['delta']:.2f} DPS "
              f"(resolved={r['resolved']}, noise={r['noise_stdev']:.2f})")

    print(f"\nTied within noise (no real difference either way): {len(ties)}")
    for r in ties:
        print(f"  {r['name']:40s} slot={r['slot']:10s} delta={r['delta']:+.2f} noise={r['noise_stdev']:.2f}")

    print(f"\nPure Agility clearly still wins: {len(real_losses)} of {len(results)} checked")

    out_path = os.path.join(REPO_ROOT, "data", "cache", "gem_choice_verification.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([r[3] for r in results], f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
