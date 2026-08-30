"""Merges mv_report.json + candidate_pool + P3 reference source info +
character.json into one JSON structure for the loot ledger artifact.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR

mv = json.load(open(os.path.join(USER_DATA_DIR, "cache", "mv_report.json"), encoding="utf-8"))
pool = json.load(open(os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter", "candidate_pool.json"), encoding="utf-8"))
p3 = json.load(open(os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter", "reference_bis", "phase3.json"), encoding="utf-8"))
char = json.load(open(os.path.join(USER_DATA_DIR, "character.json"), encoding="utf-8"))

mv_by_name = {it["name"]: it for it in mv["items"]}

# item name -> source text, pulled from the P3 reference (has boss/instance).
source_by_name = {}
for slot, entries in p3["slots"].items():
    for e in entries:
        source_by_name.setdefault(e["item"], e["source"])

SLOT_ORDER = ["head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist",
              "legs", "feet", "ring", "trinket", "weapon_dual_wield", "ranged"]
SLOT_LABELS = {
    "head": "Head", "neck": "Neck", "shoulder": "Shoulder", "back": "Back",
    "chest": "Chest", "wrist": "Wrist", "hands": "Hands", "waist": "Waist",
    "legs": "Legs", "feet": "Feet", "ring": "Rings", "trinket": "Trinkets",
    "weapon_dual_wield": "Weapons", "ranged": "Ranged",
}

owned_names = {it["name"] for it in char["equipped"]["items"] if it}

out = {"baseline": mv["baseline"]["combined"], "slots": []}
for pool_key in SLOT_ORDER:
    entries = pool.get(pool_key, [])
    items = []
    for e in entries:
        name = e["item"]
        m = mv_by_name.get(name)
        if m is None:
            continue
        row = {
            "name": name,
            "source": source_by_name.get(name, e.get("source", "")),
            "owned": name in owned_names,
            "seen_in": [s["phase"] for s in e.get("seen_in", [])],
        }
        if "excluded_reason" in m:
            row["excluded"] = m["excluded_reason"]
        else:
            row["mv"] = round(m["mv"], 1)
            row["noise"] = round(m["noise_stdev"], 2)
            row["tied"] = m["tied_within_noise"]
            row["iterations"] = m["iterations"]
        items.append(row)
    items.sort(key=lambda r: r.get("mv", -9999), reverse=True)
    out["slots"].append({"key": pool_key, "label": SLOT_LABELS[pool_key], "items": items})

out["package"] = {
    "name": "Gronnstalker's Armor (4pc)",
    "pieces": ["Gronnstalker's Helmet", "Gronnstalker's Spaulders", "Gronnstalker's Chestguard", "Gronnstalker's Gloves"],
    "mv": 343.7,
    "note": "Each piece alone reads as a modest upgrade or a wash now (enchant/gem defaults fixed) - "
            "the set bonus is what makes the full swap this large, not any single piece.",
}

out_path = os.path.join(USER_DATA_DIR, "cache", "loot_ledger_data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print("wrote", out_path)
print("slots:", [(s["key"], len(s["items"])) for s in out["slots"]])
