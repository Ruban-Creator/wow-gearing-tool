"""Real per-slot BiS enchant IDs for a profile, sourced from wowsims' own
preset gear set - the same real source build_wowsims_reference_bis.py's
reference-BiS already comes from, just extracting a field that builder
already parses (resolve_gear_set()'s "enchant" key) but never wrote out.

Not phase-aware, matching primary_gem_id's own real precedent: one real
value per profile, sourced from whichever phase file is passed in (use the
same phase already used for that profile's stat_weights.json/primary_gem_id
- currently phase3 for every existing profile). Enchants are far less
phase-sensitive than gear in TBC; a real phase-aware version can be built
later if a real case shows this mattering.

Usage: python core/build_default_enchants.py <profile_dir> <gear_set_path>
Example:
  python core/build_default_enchants.py profiles/tbc/arms_warrior \
      sim/tbc-new/ui/warrior/dps/gear_sets/p3_arms.gear.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_wowsims_reference_bis as ref_bis  # noqa: E402


def build(profile_dir: str, gear_set_path: str) -> dict[str, int]:
    resolved = ref_bis.resolve_gear_set(gear_set_path)
    return {slot: entry["enchant"] for slot, entry in resolved.items() if entry.get("enchant")}


if __name__ == "__main__":
    profile_dir, gear_set_path = sys.argv[1], sys.argv[2]
    enchants = build(profile_dir, gear_set_path)
    out_path = os.path.join(profile_dir, "default_enchants.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(enchants, f, indent=2)
    print(f"Wrote {out_path} ({len(enchants)} enchanted slots) from {gear_set_path}")
