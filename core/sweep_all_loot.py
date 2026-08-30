"""Full item-DB sweep for a given profile, Phase <= max_phase only (per user:
"all loot that can drop/be bought/be crafted" during the current phase is
fair game, later phases are not). Replaces relying solely on Wowhead's
curated BiS picks (which can silently omit a real upgrade the guide author
didn't think worth listing) with an exhaustive filter over the sim's own
item DB.

Eligibility, all from the DB's own fields plus one profile-supplied file
(loot_eligibility.json - class id, armor/weapon/ranged-weapon-type
allowlists, Stage 6.1 - previously hardcoded Hunter constants, generalized
once Arms Warrior became the second real profile to test this against):
- classAllowlist (if present) must include the profile's class_id.
- Armor pieces: armorType in the profile's armor_ok list (Hunter: Leather+
  Mail, Cloth/Plate excluded as a scope decision - technically equippable,
  never physical-DPS-competitive, not worth the compute; Warrior: Mail+Plate).
- Weapons: weaponType in the profile's weapon_ok list (real per-class TBC
  weapon proficiencies).
- Ranged: rangedWeaponType in the profile's ranged_ok list.
- Jewelry/trinket/cloak: no armor-type restriction.
- quality >= 3 (Rare+) - a practical floor against vendor trash/quest greens,
  not a hidden exclusion of anything that's actually competitive.
- phase <= max_phase.
- must have at least one real `sources` entry (drop/crafted/quest/vendor).
"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stat_weights  # noqa: E402
import set_bonus  # noqa: E402

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")

ITEM_TYPE_WEAPON = 13
ITEM_TYPE_RANGED = 14
NO_ARMOR_RESTRICTION_TYPES = {2, 4, 11, 12}  # Neck, Back, Finger, Trinket

# Per-profile eligibility (class id + armor/weapon/ranged-weapon-type
# allowlists) - same settable-active-state pattern as stat_weights.py: one
# real "active eligibility" set once at the start of a sweep, failing loud
# if a caller forgets to set it rather than silently reusing whichever
# profile's rules happened to run last.
_eligibility: dict | None = None


def set_active_eligibility(rules: dict) -> None:
    global _eligibility
    _eligibility = rules


def _eligibility_active() -> dict:
    if _eligibility is None:
        raise RuntimeError(
            "sweep_all_loot.set_active_eligibility() was never called - a pipeline entry "
            "point must load a profile's loot_eligibility.json and call it before any "
            "eligible()/run() call."
        )
    return _eligibility


# Real, confirmed bug (Stage 6.1, first non-Hunter sweep): some old items
# with no classAllowlist (armor type alone doesn't restrict which classes
# can equip Mail, e.g.) still register a per-item Go effect that
# unconditionally type-asserts the equipping agent as a specific class -
# e.g. Beast Lord Handguards/Leggings (real Hunter dungeon set, `classAllowlist:
# null` in the DB) crashed the sim outright the moment a Warrior trial tried
# to equip one: "interface conversion: *dps.DpsWarrior is not hunter.HunterAgent"
# (sim/hunter/item_sets.go). db.json has no field marking this - the DB's
# classAllowlist is about legal equip slots, not about which class's Go init
# code safely handles the item. Only confirmed against Hunter's own sets so
# far (the one other class this project actually sweeps against real data) -
# a future profile hitting the same crash for a different class's sets
# should extend this the same way, not hardcode a second one-off list.
_unsafe_set_names: set[str] = set()


def _load_unsafe_set_names(active_class_id: int) -> set[str]:
    """Real Hunter set names (from set_bonus.py's own parser, pointed at
    Hunter's real item_sets.go), only when the active profile ISN'T Hunter -
    Hunter sweeping her own sets is exactly what's supposed to happen."""
    if active_class_id == 3:  # ClassHunter
        return set()
    hunter_go = os.path.join(REPO_ROOT, "sim", "tbc-new", "sim", "hunter", "item_sets.go")
    prev_path, prev_cache = set_bonus._active_item_sets_go, set_bonus._thresholds_cache
    try:
        set_bonus.set_active_item_sets_go(hunter_go)
        return set(set_bonus.set_bonus_thresholds())
    finally:
        set_bonus._active_item_sets_go, set_bonus._thresholds_cache = prev_path, prev_cache


MAX_PHASE = 3
MIN_QUALITY = 3
MIN_ILVL = 115  # excludes leveling-zone/world gear; heroic-dungeon tier and up
TOP_N_PER_TYPE = 15  # cheap pre-filter per §5: EP decides what's worth SIMMING, not the final answer
# STAT_WEIGHTS (crude, disclosed, ranking-only heuristic) now lives in
# stat_weights.py, shared with gem_optimizer.py - one set of numbers,
# not two that could drift apart.


def crude_score(item: dict) -> float:
    scaling = item.get("scalingOptions", {}).get("0", {})
    stats = scaling.get("stats", {})
    score = sum(stat_weights.get_active().get(k, 0) * v for k, v in stats.items())
    dmg_min = scaling.get("weaponDamageMin")
    dmg_max = scaling.get("weaponDamageMax")
    speed = item.get("weaponSpeed")
    if dmg_min is not None and dmg_max is not None and speed:
        score += ((dmg_min + dmg_max) / 2 / speed) * 12  # rough DPS-equivalent weight
    return score


TYPE_TRINKET = 12
TYPE_WEAPON = 13
TYPE_RANGED = 14
# Trinkets/weapons/ranged are exempt from the ilvl floor AND (below, in
# main()) the top-N truncation: their value is often driven by an
# itemEffects proc with zero raw stats (Badge of the Swarmguard: ilvl 76,
# phase 1, no stats at all - the whole point is an on-crit AP proc), so
# both a stat-budget-correlated ilvl floor and a raw-stat crude score
# systematically miss exactly the items in these categories worth
# checking. This is what SS's own "always keep all trinkets and all
# weapons" rule was already warning about - built the sweep without it
# the first time, fixing it now rather than leaving it silently narrow.
NO_ILVL_FLOOR_TYPES = {TYPE_TRINKET, TYPE_WEAPON, TYPE_RANGED}


def is_encounter_only_legendary(item: dict) -> bool:
    """Kael'thas Sunstrider's fight-only legendary weapon pool (Netherstrand
    Longbow, Warp Slicer, Infinity Blade, etc.) - equippable only for that
    one encounter, not real persistent gear. The DB tags all 7 of them with
    sources[].drop.otherName == "Legendaries", which is exact and doesn't
    match real persistent legendaries (Warglaives, Thori'dal) - confirmed by
    checking every quality-5 item's raw source data, not guessed. Caught
    only after reporting Netherstrand Longbow as a real +131.6 upgrade -
    the user corrected it; this makes the exclusion systematic instead of a
    one-off name check."""
    for s in item.get("sources", []):
        if s.get("drop", {}).get("otherName") == "Legendaries":
            return True
    return False


def eligible(item: dict, max_phase: int = MAX_PHASE) -> bool:
    rules = _eligibility_active()
    if item.get("setName") in _unsafe_set_names:
        return False
    if item.get("phase", 99) > max_phase:
        return False
    if item.get("quality", 0) < MIN_QUALITY:
        return False
    if not item.get("sources"):
        return False
    if is_encounter_only_legendary(item):
        return False
    if item.get("type") not in NO_ILVL_FLOOR_TYPES:
        ilvl = item.get("scalingOptions", {}).get("0", {}).get("ilvl", 0)
        if ilvl < MIN_ILVL:
            return False

    allowlist = item.get("classAllowlist")
    if allowlist and rules["class_id"] not in allowlist:
        return False

    item_type = item.get("type")
    if item_type == ITEM_TYPE_WEAPON:
        return item.get("weaponType") in rules["weapon_ok"]
    if item_type == ITEM_TYPE_RANGED:
        return item.get("rangedWeaponType") in rules["ranged_ok"]
    if item_type in NO_ARMOR_RESTRICTION_TYPES:
        return True
    # Armor slots (head/shoulder/chest/wrist/hands/waist/legs/feet)
    armor_type = item.get("armorType")
    if armor_type is None:
        # No armor type at all on an armor-slot item is unusual - could be a
        # cosmetic/off-spec item; exclude rather than guess it's fine.
        return False
    return armor_type in rules["armor_ok"]


def run(max_phase: int, profile_dir: str) -> str:
    """Eligible-item universe for one phase, shared by any character running
    this profile - so the output is namespaced by (profile, phase), not by
    character. Returns the written path.

    Stage 6.1: eligibility rules (class id, armor/weapon/ranged-weapon-type
    allowlists) are now profile-driven (loot_eligibility.json), same pattern
    as stat_weights.py - real active-state wiring, not a hardcoded Hunter
    constant."""
    stat_weights.set_active(stat_weights.load(profile_dir))
    eligibility_rules = json.load(open(os.path.join(profile_dir, "loot_eligibility.json"), encoding="utf-8"))
    set_active_eligibility(eligibility_rules)
    global _unsafe_set_names
    _unsafe_set_names = _load_unsafe_set_names(eligibility_rules["class_id"])

    db = json.load(open(DB_PATH, encoding="utf-8"))
    items = db["items"]

    by_type = defaultdict(list)
    for it in items:
        if eligible(it, max_phase):
            by_type[it.get("type")].append(it)

    total = sum(len(v) for v in by_type.values())
    print(f"Eligible (phase<={max_phase}, ilvl>={MIN_ILVL}, quality>={MIN_QUALITY}): {total}")

    shortlisted = []
    for t, lst in sorted(by_type.items()):
        if t in NO_ILVL_FLOOR_TYPES:
            # No truncation either - a crude raw-stat score is exactly the
            # wrong tool for ranking proc-driven trinkets/weapons, so keep
            # all of them and let the real sim sort it out.
            print(f"  type={t}: {len(lst)} eligible -> keeping all (trinket/weapon/ranged, no score truncation)")
            shortlisted.extend(lst)
            continue
        lst.sort(key=crude_score, reverse=True)
        top = lst[:TOP_N_PER_TYPE]
        print(f"  type={t}: {len(lst)} eligible -> top {len(top)} shortlisted by crude score")
        shortlisted.extend(top)

    print(f"\nTotal shortlisted for real sim: {len(shortlisted)}")

    profile_name = os.path.basename(os.path.normpath(profile_dir))
    out_path = os.path.join(USER_DATA_DIR, "cache", f"full_sweep_candidates_{profile_name}_phase{max_phase}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(shortlisted, f, indent=2)
    print(f"Wrote {out_path}")
    return out_path


def main():
    profile_dir = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")
    run(MAX_PHASE, profile_dir)


if __name__ == "__main__":
    main()
