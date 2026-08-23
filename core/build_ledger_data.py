"""Builds the DATA blob embedded in the phase3_ledger.html artifact.

data/cache/tiered_report.json (run_full_sweep_mv.py's output) shapes "tiers"
as a dict-of-dicts - {tier_name: {slot_name: [item_row, ...]}} - convenient
for the text report's nested loop, but not what the artifact's JS expects:
a list of {name, slots: [{slot, items, more}]}, matching how it's actually
rendered (iterate tiers in order, iterate slots in order, show top 5 +
"N more"). "achieved_bis"/"two_hand"/"two_hand_meta" already match the JS's
expected shape as-is and pass through unchanged.

Run this after any run_full_sweep_mv.py sweep, before re-splicing the
artifact HTML - skipping it (or hand-rolling the transform inline again) is
exactly what broke the published ledger on 2026-08-23: the raw dict-of-dicts
got embedded directly, the JS threw partway through rendering "tiers", and
everything past "Achieved BiS" silently went blank.
"""
import json
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOP_N_SHOWN = 5


def build():
    report = json.load(open(os.path.join(REPO_ROOT, "data", "cache", "tiered_report.json"), encoding="utf-8"))

    tiers_list = []
    for tier_name, slot_dict in report["tiers"].items():
        if not slot_dict:
            continue
        slots_list = []
        for slot_name, upgrades in slot_dict.items():
            slots_list.append({
                "slot": slot_name,
                "items": upgrades[:TOP_N_SHOWN],
                "more": max(0, len(upgrades) - TOP_N_SHOWN),
            })
        tiers_list.append({"name": tier_name, "slots": slots_list})

    sim_commit_sha = subprocess.run(
        ["git", "-C", os.path.join(REPO_ROOT, "sim", "tbc-new"), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()

    return {
        "baseline_dps": report["baseline_screened"],
        "sim_commit_sha": sim_commit_sha,
        "achieved_bis": report["achieved_bis"],
        "tiers": tiers_list,
        "two_hand": report["two_hand"],
        "two_hand_meta": report["two_hand_meta"],
    }


if __name__ == "__main__":
    data = build()
    out_path = os.path.join(REPO_ROOT, "data", "cache", "ledger_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {out_path}")
    print(f"tiers: {[(t['name'], len(t['slots'])) for t in data['tiers']]}")
