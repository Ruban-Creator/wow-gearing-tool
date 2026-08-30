"""Real, sim-verified sanity pass over a profile's default_enchants.json -
never trust a raw wowsims preset's "enchant" field blindly. Real, confirmed
finding (2026-08-25): Balance Druid's and Enhancement Shaman's own real p3
gear_sets files carry several enchant ids that either do NOTHING when
applied (delta ~0 - not a real, sim-recognized effect in this DB build) or
make things WORSE (a real negative delta - the id doesn't mean what the
slot position implies). Warrior's and Elemental's ids happened to all
resolve real names via db.json's own enchants collection, but that
collection is a display lookup, not proof the Go sim engine implements the
effect - every profile gets the same real verification here regardless of
whether its ids "looked" trustworthy.

Rejects (drops from the file) any entry whose real, isolated sim delta
isn't clearly positive (using CLEAR_THRESHOLD DPS, not raw >0, to not keep
a value that's really just screening noise) - a dropped slot simply has no
default enchant afterward (the same honest "no verified data" state as
before this feature existed), not a wrong one kept because it came from a
real source file.

Usage: python core/verify_default_enchants.py <profile_dir> <name_realm>
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import stat_weights  # noqa: E402
import gem_optimizer  # noqa: E402
import set_bonus  # noqa: E402
import time_horizon  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "tbc"))
import valuation  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
CLEAR_THRESHOLD = 1.0  # DPS - below this, treat as noise/no real effect, not a genuine gain
ITERATIONS = 3000


def verify(profile_dir: str, name_realm: str) -> dict[str, int]:
    profile = json.load(open(os.path.join(profile_dir, "profile.json"), encoding="utf-8"))
    stat_weights.set_active(stat_weights.load(profile_dir))
    time_horizon.set_active_ref_dir(os.path.join(profile_dir, "reference_bis"))
    gc.set_active_default_gem(profile["primary_gem_id"])
    # Real default-enchants active state now required by build_owned_config()
    # too (see gear_config.py) - empty here on purpose: this script is what
    # DECIDES the real values, each slot under test is independently
    # stripped and isolated regardless of what other slots resolve to, so
    # an empty starting point doesn't bias the result.
    gc.set_active_default_enchants({})
    chase_bonus = json.load(open(os.path.join(profile_dir, "chase_bonus_gems.json"), encoding="utf-8"))
    gem_optimizer.set_active_chase_bonus_ids(set(chase_bonus["item_ids"]))
    set_bonus.set_active_item_sets_go(os.path.join(REPO_ROOT, "sim", "tbc-new", profile["set_bonus_go_source"]))

    character = json.load(open(os.path.join(USER_DATA_DIR, "characters", name_realm, "character.json"),
                                encoding="utf-8"))
    known_professions = {p["name"] for p in character["character"]["professions"]}
    baseline_config = opt.build_owned_config(character["equipped"]["items"], known_professions)
    settings_path = os.path.join(profile_dir, "settings_template.json")

    enchants_path = os.path.join(profile_dir, "default_enchants.json")
    candidates = json.load(open(enchants_path, encoding="utf-8"))

    # Real methodology fix, found live (2026-08-25): comparing a candidate
    # enchant against the character's own REAL current baseline is only a
    # fair test when that slot's real current enchant is 0 - if she already
    # has this exact same enchant equipped, "apply it" trivially shows
    # delta=0 (nothing changed, not "doesn't work") and got misread as a
    # broken id on the first pass. Real fix: strip THIS SLOT's own enchant
    # to 0 first (holding everything else - all other slots' real gear -
    # constant), so both the "0 enchant" reference point and the candidate
    # test are measured from the same, real, enchant-neutral starting
    # point - the same "hold everything else constant, isolate the one
    # real variable" principle set_bonus.isolate_bonus_value() already
    # uses for set bonuses.
    verified = {}
    for slot, enchant_id in candidates.items():
        idx = gc.SLOT_ORDER.index(slot)
        stripped = list(baseline_config)
        stripped[idx] = dict(stripped[idx]) if stripped[idx] else {}
        stripped[idx].pop("enchant", None)
        zero_result = valuation.evaluate(settings_path, stripped, ITERATIONS, opt.SEED)

        trial = list(stripped)
        trial[idx] = dict(trial[idx])
        trial[idx]["enchant"] = enchant_id
        result = valuation.evaluate(settings_path, trial, ITERATIONS, opt.SEED)
        delta = result["combined"] - zero_result["combined"]
        status = "KEEP" if delta >= CLEAR_THRESHOLD else "DROP"
        print(f"{slot:10} enchant={enchant_id:6} delta vs no-enchant={delta:+7.2f}  {status}")
        if delta >= CLEAR_THRESHOLD:
            verified[slot] = enchant_id

    with open(enchants_path, "w", encoding="utf-8") as f:
        json.dump(verified, f, indent=2)
    dropped = set(candidates) - set(verified)
    print(f"\nWrote {enchants_path}: {len(verified)} verified, {len(dropped)} dropped ({sorted(dropped)}).")
    return verified


if __name__ == "__main__":
    profile_dir, name_realm = sys.argv[1], sys.argv[2]
    verify(profile_dir, name_realm)
