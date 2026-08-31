"""Merge a non-canonical gear variant's unique items into an existing
candidate_pool.json, WITHOUT touching reference_bis/phaseN.json (which stays
the canonical "Best"/Achieved-BiS reference). Reuses
build_wowsims_reference_bis.py's own resolve_gear_set()/_pool_key_for()/
_real_source() so item resolution and pool-key routing never diverges from
the canonical builder.

Real motivating case (2026-08-31): Feral Cat Druid's P1 only ever built the
'bis' gear variant into the pool - wowsims also ships a more-attainable
'realistic' tier at P1 whose own unique items were never represented
anywhere, per the user's explicit request to add it back in.

Usage: python core/add_gear_variant_to_pool.py <profile_dir> <gear_sets_dir> <spec_label> <phase> <rank_label> <file.gear.json>
Example:
  python core/add_gear_variant_to_pool.py profiles/tbc/feral_cat_druid \
      sim/tbc-new/ui/druid/feralcat/gear_sets "Feral Cat" phase1 Realistic p1_realistic_6p.gear.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_wowsims_reference_bis as refbis  # noqa: E402


def merge(profile_dir: str, gear_sets_dir: str, spec_label: str, phase: str,
          rank_label: str, filename: str) -> None:
    profile = json.load(open(os.path.join(profile_dir, "profile.json"), encoding="utf-8"))
    weapon_topology = profile["weapon_topology"]

    resolved = refbis.resolve_gear_set(os.path.join(gear_sets_dir, filename))

    pool_path = os.path.join(profile_dir, "candidate_pool.json")
    pool = json.load(open(pool_path, encoding="utf-8"))

    added, already_present = [], []
    phase_label = phase.replace("phase", "P")
    for slot, entry in resolved.items():
        pool_key = refbis._pool_key_for(slot, entry, weapon_topology)
        if pool_key is None:
            continue
        bucket = pool.setdefault(pool_key, [])
        existing = next((rec for rec in bucket if rec["item"] == entry["item"]), None)
        phase_entry = {"phase": phase_label, "rank": rank_label}
        if existing:
            if phase_entry not in existing["seen_in"]:
                existing["seen_in"].append(phase_entry)
                already_present.append(entry["item"])
        else:
            bucket.append({
                "item": entry["item"],
                "source": refbis._real_source(entry["db_item"], phase, spec_label),
                "seen_in": [phase_entry],
                "best_rank_seen": rank_label,
            })
            added.append(entry["item"])

    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)

    print(f"Added {len(added)} new candidate(s): {added}")
    print(f"Already tracked (just tagged {phase_label}/{rank_label}): {already_present}")
    print(f"Wrote {pool_path}")


if __name__ == "__main__":
    merge(*sys.argv[1:7])
