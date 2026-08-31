"""Backlog #15 (FUTURE_TASKS.md) - scopes the real, DB-wide `sources: None`
gap (found 2026-08-31, see NOTES.md's dated entry) down to specifically
which items THIS TOOL actually surfaces - every real profile's own
candidate_pool.json + reference_bis/*.json, resolved by name to a real DB
id via item_db.ids_by_name() (never guessed).

Pure DB/file reads, no sim calls - safe to run any time, including while a
real sim sweep or the game itself is running on this machine.

Usage: python core/check_missing_sources.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
import item_db as idb  # noqa: E402

REPO_ROOT = repo_root.REPO_ROOT
PROFILES_DIR = os.path.join(REPO_ROOT, "profiles", "tbc")

# Directories under profiles/tbc/ that aren't real per-spec profiles.
_NON_PROFILE_DIRS = {"_shared", "reference"}


def _real_profile_dirs() -> list[str]:
    return sorted(
        d for d in os.listdir(PROFILES_DIR)
        if d not in _NON_PROFILE_DIRS and os.path.isfile(os.path.join(PROFILES_DIR, d, "profile.json"))
    )


def _item_names_for_profile(profile_dir: str) -> set[str]:
    names = set()

    pool_path = os.path.join(PROFILES_DIR, profile_dir, "candidate_pool.json")
    if os.path.exists(pool_path):
        with open(pool_path, encoding="utf-8") as f:
            pool = json.load(f)
        for entries in pool.values():
            for e in entries:
                names.add(e["item"])

    ref_dir = os.path.join(PROFILES_DIR, profile_dir, "reference_bis")
    if os.path.isdir(ref_dir):
        for fname in os.listdir(ref_dir):
            with open(os.path.join(ref_dir, fname), encoding="utf-8") as f:
                ref = json.load(f)
            for entries in ref.get("slots", {}).values():
                for e in entries:
                    names.add(e["item"])

    return names


def main():
    grand_total_names = 0
    grand_total_missing = 0
    by_profile: dict[str, list[tuple[str, int, int | None]]] = {}

    for profile_dir in _real_profile_dirs():
        names = _item_names_for_profile(profile_dir)
        grand_total_names += len(names)
        missing = []
        for name in sorted(names):
            ids = idb.ids_by_name(name)
            if not ids:
                continue  # not found in DB at all - a different, separate problem
            item = idb.by_id(ids[0])
            if not item.get("sources"):
                missing.append((name, ids[0], item.get("phase")))
        if missing:
            by_profile[profile_dir] = missing
            grand_total_missing += len(missing)

    print(f"Checked {len(_real_profile_dirs())} real profiles, {grand_total_names} total "
          f"(profile, item-name) references (deduped per profile).\n")
    print(f"{grand_total_missing} real items across {len(by_profile)} profiles have sources:None "
          f"in the sim's own DB:\n")
    for profile_dir, missing in by_profile.items():
        print(f"{profile_dir} ({len(missing)} items):")
        for name, item_id, phase in missing:
            print(f"    {name} (id {item_id}, phase {phase})")
        print()


if __name__ == "__main__":
    main()
