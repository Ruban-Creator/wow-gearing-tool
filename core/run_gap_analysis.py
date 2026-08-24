import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gap_analysis as ga  # noqa: E402

char = json.load(open(os.path.join(REPO_ROOT, "data", "character.json"), encoding="utf-8"))
ref_p3 = json.load(open(
    os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter", "reference_bis", "phase3.json"),
    encoding="utf-8",
))
ref_p2 = json.load(open(
    os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter", "reference_bis", "phase2.json"),
    encoding="utf-8",
))
db = json.load(open(
    os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json"),
    encoding="utf-8",
))
name_to_ids = {}
for it in db.get("items", []):
    name_to_ids.setdefault(it["name"], []).append(it["id"])

ref_p3 = ga.resolve_reference_ids(ref_p3, name_to_ids)
ref_p2 = ga.resolve_reference_ids(ref_p2, name_to_ids)
for label, ref in [("P3", ref_p3), ("P2", ref_p2)]:
    if ref["unresolved"]:
        print(f"UNRESOLVED {label} reference items (not found in sim DB by exact name):")
        for name in ref["unresolved"]:
            print(f"  - {name}")
        print()

results_p3 = ga.per_slot_gap(char["equipped"]["items"], ref_p3)
results_p2 = ga.per_slot_gap(char["equipped"]["items"], ref_p2)

print(f"{'Slot':<10} {'Owned':<32} {'P3 status':<40} {'P2 status':<20}")
print("-" * 105)
gap_both = []
gap_p3_only = []
for r3, r2 in zip(results_p3, results_p2):
    if r3["is_best"]:
        p3_status = "BEST"
    elif r3["matches_reference_rank"]:
        p3_status = f"{r3['matches_reference_rank']} (best={r3['best_reference_item']})"
    else:
        p3_status = f"NOT ON LIST (best={r3['best_reference_item']})"

    if r2["is_best"]:
        p2_status = "was P2 BEST"
    elif r2["matches_reference_rank"]:
        p2_status = f"was P2 {r2['matches_reference_rank']}"
    else:
        p2_status = "not P2 either"
        if not r3["on_reference_list_at_all"]:
            gap_both.append(r3["position"])

    if not r3["on_reference_list_at_all"] and r2["on_reference_list_at_all"]:
        gap_p3_only.append(r3["position"])

    owned = r3["owned_name"] or "(empty)"
    print(f"{r3['position']:<10} {owned:<32} {p3_status:<40} {p2_status:<20}")

print()
print(f"Off the P3 list AND was already sub-P2 (real, longstanding gaps, {len(gap_both)}): {', '.join(gap_both) or 'none'}")
print(f"Off the P3 list but WAS on-list for P2 (expected progression, now needs the P3 upgrade, {len(gap_p3_only)}): {', '.join(gap_p3_only) or 'none'}")
