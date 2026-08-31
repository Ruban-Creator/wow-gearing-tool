"""Builds a character.json for a profile with no real character export yet
(Stage 6.3, Shaman) - a clearly-labeled synthetic test fixture, not a real
personal export. Seeds equipped gear from a real wowsims preset gear_sets
file (the same file build_wowsims_reference_bis.py already consumes) and
race/professions from that spec's own real presets.ts OtherDefaults - real,
sim-team-chosen values, never fabricated. Only the character name/realm
itself is a placeholder identity, deliberately unrealistic so it can never
collide with a real future WowSimsExporter export.

This is NOT a replacement for ingest/build_character.py - that stays the
real path for an actual character. The fixture is trusted by NAME alone
(character_profiles._SYNTHETIC_CHARACTERS / is_synthetic_character()) - a
profile.json-level "synthetic_character" flag used to exist for this too,
but was removed 2026-08-31 after it turned out to be the root cause of a
real bug (a real player assigned to a profile that still had the flag hit
a FileNotFoundError, since gui/api.py checked the PROFILE's flag instead of
the CHARACTER's own identity to decide whether to sync). Never add that
flag back to a profile.json - the fixture name itself is already the
correct, permanent signal.

Usage: python ingest/build_synthetic_character.py <name_realm> <race> <class> <spec>
    <profession1> <profession2> <gear_set_json_path> <talents_string>
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_character import REPO_ROOT, USER_DATA_DIR, load_item_db, resolve_items, sim_commit_sha  # noqa: E402
import repo_root  # noqa: E402 - core/ already on sys.path via build_character's own bootstrap above


def build(name_realm: str, race: str, class_name: str, spec: str,
          profession1: str, profession2: str, gear_set_path: str, talents: str) -> dict:
    item_db = load_item_db()
    gear = repo_root.load_json(gear_set_path)
    equipped, unresolved = resolve_items(gear["items"], item_db, preserve_positions=True)
    if unresolved:
        print(f"WARNING: {len(unresolved)} item(s) in {gear_set_path} not found in item DB: "
              f"{[it.get('id') for it in unresolved]}")

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sim_commit_sha": sim_commit_sha(),
            "synthetic": True,
            "synthetic_source": os.path.relpath(gear_set_path, REPO_ROOT).replace("\\", "/"),
            "synthetic_note": "No real character export exists for this profile yet - "
                               "equipped gear/race/professions are real wowsims preset "
                               "defaults, not a real personal export. Never trust this "
                               "report as real personal upgrade advice.",
        },
        "character": {
            "name": name_realm.split("-")[0],
            "realm": name_realm.split("-", 1)[1] if "-" in name_realm else None,
            "race": race,
            "class": class_name,
            "level": 70,
            "spec": spec,
            "professions": [{"name": profession1}, {"name": profession2}],
            "talents": talents,
        },
        "equipped": {"items": equipped},
        "owned": {"bags": [], "bank": []},
        "currencies": {},
        "raid": {},
    }


if __name__ == "__main__":
    (name_realm, race, class_name, spec, profession1, profession2,
     gear_set_path, talents) = sys.argv[1:9]
    character = build(name_realm, race, class_name, spec, profession1, profession2,
                       gear_set_path, talents)
    out_dir = os.path.join(USER_DATA_DIR, "characters", name_realm)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "character.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(character, f, indent=2)
    print(f"Wrote {out_path}")
