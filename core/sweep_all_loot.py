"""Full item-DB sweep for a Survival Hunter, Phase <= 3 only (per user: "all
loot that can drop/be bought/be crafted" during P3 is fair game, P4/P5 is
not). Replaces relying solely on Wowhead's curated BiS picks (which can
silently omit a real upgrade the guide author didn't think worth listing)
with an exhaustive filter over the sim's own item DB.

Eligibility, all from the DB's own fields - never guessed:
- classAllowlist (if present) must include Hunter (3).
- Armor pieces: armorType Leather(2) or Mail(3) only - Cloth/Plate excluded
  as a scope decision (technically equippable, never physical-DPS-competitive,
  not worth the compute), not an arbitrary data omission.
- Weapons: weaponType in {Axe, Dagger, Fist, Polearm, Sword} - TBC Hunter
  weapon proficiencies, excludes Mace/Staff/Shield/OffHand-only.
- Ranged: rangedWeaponType in {Bow, Crossbow, Gun} only.
- Jewelry/trinket/cloak: no armor-type restriction.
- quality >= 3 (Rare+) - a practical floor against vendor trash/quest greens,
  not a hidden exclusion of anything that's actually competitive.
- phase <= 3.
- must have at least one real `sources` entry (drop/crafted/quest/vendor).
"""
import json
import os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")

HUNTER_CLASS = 3
ARMOR_OK = {2, 3}  # Leather, Mail
WEAPON_OK = {1, 2, 3, 6, 9}  # Axe, Dagger, Fist, Polearm, Sword
RANGED_OK = {1, 2, 3}  # Bow, Crossbow, Gun
ITEM_TYPE_WEAPON = 13
ITEM_TYPE_RANGED = 14
NO_ARMOR_RESTRICTION_TYPES = {2, 4, 11, 12}  # Neck, Back, Finger, Trinket

MAX_PHASE = 3
MIN_QUALITY = 3
MIN_ILVL = 115  # excludes leveling-zone/world gear; heroic-dungeon tier and up
TOP_N_PER_TYPE = 15  # cheap pre-filter per §5: EP decides what's worth SIMMING, not the final answer

# Crude, disclosed stat-weight heuristic - for RANKING/PRUNING only, never
# treated as the answer. Real value always comes from the sim afterward.
STAT_WEIGHTS = {
    "0": 0.5,   # Strength
    "1": 2.0,   # Agility
    "17": 1.0,  # AttackPower
    "18": 1.0,  # RangedAttackPower
    "20": 0.8,  # MeleeHitRating
    "21": 1.2,  # MeleeCritRating
    "22": 0.8,  # MeleeHasteRating
    "23": 0.9,  # ArmorPenetration
    "24": 0.3,  # ExpertiseRating
}


def crude_score(item: dict) -> float:
    scaling = item.get("scalingOptions", {}).get("0", {})
    stats = scaling.get("stats", {})
    score = sum(STAT_WEIGHTS.get(k, 0) * v for k, v in stats.items())
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


def eligible(item: dict) -> bool:
    if item.get("phase", 99) > MAX_PHASE:
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
    if allowlist and HUNTER_CLASS not in allowlist:
        return False

    item_type = item.get("type")
    if item_type == ITEM_TYPE_WEAPON:
        return item.get("weaponType") in WEAPON_OK
    if item_type == ITEM_TYPE_RANGED:
        return item.get("rangedWeaponType") in RANGED_OK
    if item_type in NO_ARMOR_RESTRICTION_TYPES:
        return True
    # Armor slots (head/shoulder/chest/wrist/hands/waist/legs/feet)
    armor_type = item.get("armorType")
    if armor_type is None:
        # No armor type at all on an armor-slot item is unusual - could be a
        # cosmetic/off-spec item; exclude rather than guess it's fine.
        return False
    return armor_type in ARMOR_OK


def main():
    db = json.load(open(DB_PATH, encoding="utf-8"))
    items = db["items"]

    by_type = defaultdict(list)
    for it in items:
        if eligible(it):
            by_type[it.get("type")].append(it)

    total = sum(len(v) for v in by_type.values())
    print(f"Eligible (phase<=3, ilvl>={MIN_ILVL}, quality>={MIN_QUALITY}): {total}")

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

    out_path = os.path.join(REPO_ROOT, "data", "cache", "full_sweep_candidates.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(shortlisted, f, indent=2)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
