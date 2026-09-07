"""AUDIT tool, not a production gate (rebuilt 2026-09-07, since
gem_optimizer.best_gems_for_item() now decides gem choice LIVE via a
combined crude/EP score, not a hand-curated per-profile list - see that
function's own docstring for the full design/history). This script's job
is to spot-check that live formula against real sim results, across every
real candidate in the profile's own pool that has sockets: for each one,
gem_optimizer.verify_gem_choice() real-sim-compares pure default gems
against the item's own socket-bonus-chased loadout and reports whether the
formula's own decision (best_gems_for_item(), what production actually
uses) picked the side the real sim confirms is genuinely better
(`formula_agrees_with_sim`). A `False` here is real, actionable signal - it
means the live formula got THIS item wrong, most likely because
`stat_weights.json` under/over-values some stat for this profile (the
historical Ranger-General's-Chestguard case, where linear EP scoring
undervalued Agility's real multi-stat-conversion value for Hunters, is
exactly this class of bug) - not something to hand-patch per item, since
there's no override mechanism to patch into anymore.

Screens all candidates cheap first, only resolves the close calls at high
iterations - same funnel discipline as marginal_value.mv_single_tiered.

Usage: python core/verify_gem_choices.py [profile_dir_name] [name_realm]
  Defaults to survival_hunter / the flat USER_DATA_DIR/character.json (Lerynia's
  own, original behavior) when no args given - both args must be given together
  to point at a different profile's own synthetic/real character.json, e.g.:
  python core/verify_gem_choices.py beastmastery_hunter Test-Beastmastery-Synthetic
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import item_db as idb  # noqa: E402
import gem_optimizer as gopt  # noqa: E402
import marginal_value as mv  # noqa: E402
import stat_weights  # noqa: E402
import time_horizon  # noqa: E402

PROFILE_DIR_NAME = sys.argv[1] if len(sys.argv) > 1 else "survival_hunter"
NAME_REALM = sys.argv[2] if len(sys.argv) > 2 else None
PROFILE_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", PROFILE_DIR_NAME)
SETTINGS_TEMPLATE = os.path.join(PROFILE_DIR, "settings_template.json")
POOL_PATH = os.path.join(PROFILE_DIR, "candidate_pool.json")
SCREEN_ITERATIONS = 3000
RESOLVE_ITERATIONS = 30000
CLEAR_MARGIN_MULTIPLE = 8


def main():
    start = time.time()
    # Stage 6 (multi-class support): this active-profile setup wasn't
    # needed before core/stat_weights.py + core/gear_config.py's
    # DEFAULT_GEM + gem_optimizer.CHASE_BONUS_ITEM_IDS all became
    # per-profile settable state - keeps this script runnable for Hunter.
    stat_weights.set_active(stat_weights.load(PROFILE_DIR))
    # Real, necessary as of 2026-09-07's phase-legal-gem fix (gem_optimizer.py) - gem
    # selection now needs the current phase set before it runs. Every profile's own
    # primary_gem_id/chase_bonus_gems.json is sourced from real Phase 3 data, so
    # Phase 3 is the correct, consistent choice here too.
    time_horizon.set_current_phase(3)
    profile = repo_root.load_json(os.path.join(PROFILE_DIR, "profile.json"))
    gc.set_active_default_gem(profile["primary_gem_id"])
    primary_gem = idb.gem_by_id(profile["primary_gem_id"])
    primary_gem_label = primary_gem["name"] if primary_gem else f"gem id {profile['primary_gem_id']}"
    _default_enchants_path = os.path.join(PROFILE_DIR, "default_enchants.json")
    gc.set_active_default_enchants(repo_root.load_json(_default_enchants_path)
                                    if os.path.exists(_default_enchants_path) else {})

    char_path = (os.path.join(USER_DATA_DIR, "characters", NAME_REALM, "character.json")
                 if NAME_REALM else os.path.join(USER_DATA_DIR, "character.json"))
    char = repo_root.load_json(char_path)
    owned_items = char["equipped"]["items"]
    gopt.set_active_capped_totals(owned_items)
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
        try:
            res = gopt.verify_gem_choice(item, meta_gem_id, SETTINGS_TEMPLATE, trial_config,
                                          slot_idx, SCREEN_ITERATIONS, opt.SEED)
        except (RuntimeError, OSError) as e:
            # Same real, known crash class core/marginal_value.py's mv_single()
            # already guards against (e.g. Beast-tamer's Shoulders' Go effect
            # unconditionally type-asserts a Hunter agent and panics for any
            # other class) - the item, not the process, is what's broken, so
            # simserver_client's own self-heal retry hits the identical panic
            # again. Excluded honestly, same as any other unusable candidate,
            # rather than one bad item killing this whole verification sweep.
            print(f"  [skip]   {c.name:40s} sim crashed: {e}")
            continue
        if not res["applicable"]:
            continue  # every socket already the primary color/Meta - the profile's own primary gem trivially wins, nothing to check
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
    # Real, actionable signal: a CLEAR (not tied-within-noise) real-sim
    # result the live combined-score formula (best_gems_for_item, what
    # production actually uses) got wrong. A tie doesn't count - neither
    # side is confirmed better, so disagreement there is meaningless, not
    # a bug.
    formula_wrong = [r for r in (real_wins + real_losses) if not r["formula_agrees_with_sim"]]

    print(f"Real socket-bonus wins (chase beats pure {primary_gem_label}): {len(real_wins)}")
    for r in sorted(real_wins, key=lambda r: -r["delta"]):
        flag = "  <-- FORMULA DISAGREES" if not r["formula_agrees_with_sim"] else ""
        print(f"  {r['name']:40s} slot={r['slot']:10s} +{r['delta']:.2f} DPS "
              f"(resolved={r['resolved']}, noise={r['noise_stdev']:.2f}){flag}")

    print(f"\nTied within noise (no real difference either way): {len(ties)}")
    for r in ties:
        print(f"  {r['name']:40s} slot={r['slot']:10s} delta={r['delta']:+.2f} noise={r['noise_stdev']:.2f}")

    print(f"\nPure {primary_gem_label} clearly still wins: {len(real_losses)} of {len(results)} checked")
    for r in sorted(real_losses, key=lambda r: r["delta"]):
        flag = "  <-- FORMULA DISAGREES" if not r["formula_agrees_with_sim"] else ""
        if flag:
            print(f"  {r['name']:40s} slot={r['slot']:10s} {r['delta']:+.2f} DPS{flag}")

    if formula_wrong:
        print(f"\n*** {len(formula_wrong)} item(s) where the LIVE FORMULA (best_gems_for_item) "
              f"disagrees with a real, clear sim result - worth investigating "
              f"(likely a stat_weights.json miscalibration for this profile, "
              f"see gem_optimizer.py's own module docstring on the historical "
              f"Ranger-General's-Chestguard case): ***")
        for r in formula_wrong:
            print(f"  {r['name']:40s} slot={r['slot']:10s} real_winner={r['winner']} "
                  f"delta={r['delta']:+.2f} pure_gems={r['pure_gems']} chase_gems={r['chase_bonus_gems']}")
    else:
        print(f"\nNo clear formula/real-sim disagreements found across {len(results)} checked candidates.")

    out_path = os.path.join(USER_DATA_DIR, "cache", "gem_choice_verification.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump([r[3] for r in results], f, indent=2)
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
