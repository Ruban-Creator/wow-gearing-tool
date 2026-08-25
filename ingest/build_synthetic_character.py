"""Builds a character.json for a profile with no real character export yet
(Stage 6.3, Shaman) - a clearly-labeled synthetic test fixture, not a real
personal export. Seeds equipped gear from a real wowsims preset gear_sets
file (the same file build_wowsims_reference_bis.py already consumes) and
race/professions from that spec's own real presets.ts OtherDefaults - real,
sim-team-chosen values, never fabricated. Only the character name/realm
itself is a placeholder identity, deliberately unrealistic so it can never
collide with a real future WowSimsExporter export.

This is NOT a replacement for ingest/build_character.py - that stays the
real path for an actual character. A profile built against a synthetic
character must carry profile.json's "synthetic_character": true forward
into anything that reports on it (see gui/api.py, report_template.html),
so nothing downstream mistakes it for trustworthy personal advice.

Usage: python ingest/build_synthetic_character.py <name_realm> <race> <class> <spec>
    <profession1> <profession2> <gear_set_json_path> <talents_string>
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_character import load_item_db, resolve_items, sim_commit_sha  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build(name_realm: str, race: str, class_name: str, spec: str,
          profession1: str, profession2: str, gear_set_path: str, talents: str) -> dict:
    item_db = load_item_db()
    gear = json.load(open(gear_set_path, encoding="utf-8"))
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
    out_dir = os.path.join(REPO_ROOT, "data", "characters", name_realm)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "character.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(character, f, indent=2)
    print(f"Wrote {out_path}")
