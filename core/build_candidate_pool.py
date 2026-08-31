"""Stage 3 candidate pool (§5): merge P2+P3 reference lists per slot,
deduplicated by item name, tagged with acquisition source. Every trinket and
weapon entry is kept regardless of rank (§5's "always keep" rule) since
those categories are already fully enumerated in the reference data; same
for anything in a set the character already holds 2+ pieces of (Rift
Stalker Armor - see NOTES.md for the confirmed 4pc bonus).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
# Kept as the default for Survival Hunter (this script's original real
# usage); Stage 6 (multi-class support) generalized build_pool() itself to
# take ref_dir/phase_files as real parameters instead of module constants,
# so a new profile calls it with its own reference_bis/ directory and phase
# filenames rather than needing its own copy of this file.
PROFILE_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")
REF_DIR = os.path.join(PROFILE_DIR, "reference_bis")
DEFAULT_PHASE_FILES = ["phase2.json", "phase3.json"]

RANK_ORDER = ["Best", "Best x2", "Best MH/OH", "Best - Weaving", "Best - Hit", "Best 6% and 9%",
              "Best - Dwarf", "Best Until Tier 6", "Best Until Tier 5", "Best Raid Wide Increase",
              "Great", "Great (4 Set)", "Second Best", "Good", "Optional MH/OH", "Optional MH",
              "Optional - Agility", "Optional"]


def rank_weight(rank: str) -> int:
    try:
        return RANK_ORDER.index(rank)
    except ValueError:
        return len(RANK_ORDER)


def build_pool(ref_dir: str = REF_DIR, phase_files: list[str] = DEFAULT_PHASE_FILES) -> dict:
    # Phase label derived from the filename itself ("phase3.json" -> "P3"),
    # not positional index - robust regardless of which phases are actually
    # passed (a future profile isn't guaranteed to start at phase 2).
    refs = []
    for fname in phase_files:
        label = "P" + os.path.splitext(fname)[0].removeprefix("phase")
        refs.append((label, repo_root.load_json(os.path.join(ref_dir, fname))))

    slots = sorted(set().union(*(set(ref["slots"]) for _, ref in refs)))
    pool = {}
    for slot in slots:
        by_name = {}
        for phase_label, ref in refs:
            for entry in ref["slots"].get(slot, []):
                name = entry["item"]
                if name not in by_name:
                    by_name[name] = {"item": name, "source": entry["source"], "seen_in": []}
                by_name[name]["seen_in"].append({"phase": phase_label, "rank": entry["rank"]})

        candidates = list(by_name.values())
        # Best rank seen across either phase, for sorting only.
        for c in candidates:
            c["best_rank_seen"] = min(c["seen_in"], key=lambda s: rank_weight(s["rank"]))["rank"]
        candidates.sort(key=lambda c: rank_weight(c["best_rank_seen"]))
        pool[slot] = candidates

    return pool


def main():
    pool = build_pool()
    out_path = os.path.join(PROFILE_DIR, "candidate_pool.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(pool, f, indent=2)

    total = sum(len(v) for v in pool.values())
    print(f"Wrote {out_path}: {total} unique candidates across {len(pool)} slots")
    for slot, candidates in pool.items():
        print(f"  {slot}: {len(candidates)} candidates ({', '.join(c['item'] for c in candidates)})")


if __name__ == "__main__":
    main()
