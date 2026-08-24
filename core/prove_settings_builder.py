"""Stage 6.0's real regression check for settings_builder.py: regenerate
Survival Hunter's settings_template.json from its own real component pieces
and diff against the hand-maintained file it was migrated from - if this
doesn't come out byte-identical, the builder has a real bug, not a design
flaw to hand-wave past.

Character (race/equipment/talents/professions) is extracted from the
EXISTING settings_template.json itself, not data/characters/Lerynia-
Thunderstrike/character.json - that file's WSE export currently has 0
equipped items (a real, already-flagged, unrelated data-staleness issue,
not a settings_builder bug - see QUESTIONS.md). Testing the builder's own
correctness shouldn't depend on that being fixed first.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import settings_builder  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_DIR = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")


def main():
    original = json.load(open(os.path.join(PROFILE_DIR, "settings_template.json"), encoding="utf-8"))
    profile = json.load(open(os.path.join(PROFILE_DIR, "profile.json"), encoding="utf-8"))
    class_options = json.load(open(os.path.join(PROFILE_DIR, "class_options.json"), encoding="utf-8"))
    consumables = json.load(open(os.path.join(PROFILE_DIR, "consumables.json"), encoding="utf-8"))
    overlay = json.load(open(os.path.join(PROFILE_DIR, "raid_buffs_overlay.json"), encoding="utf-8"))
    shared = json.load(open(os.path.join(REPO_ROOT, "profiles", "tbc", "_shared", "raid_buffs_received.json"),
                             encoding="utf-8"))
    raid_buffs_received = {
        "raidBuffs": {**shared["raidBuffs"], **overlay["raidBuffs"]},
        "debuffs": {**shared["debuffs"], **overlay["debuffs"]},
        "partyBuffs": {**shared["partyBuffs"], **overlay["partyBuffs"]},
        "playerBuffs": {**shared["playerBuffs"], **overlay["playerBuffs"]},
    }

    # Character input extracted from the real, known-good settings_template.json
    # itself - race as a bare string (settings_builder re-adds the "Race" prefix),
    # class similarly. Talents/professions/equipment already in the right shape.
    p = original["player"]
    character = {
        "race": p["race"].removeprefix("Race"),
        "equipment": p["equipment"],
        "talents": p["talentsString"],
        "professions": [{"name": p["profession1"]}, {"name": p["profession2"]}],
    }

    rebuilt = settings_builder.build_settings(
        character, profile, raid_buffs_received,
        rotation=p["rotation"], class_options=class_options, consumables=consumables,
    )

    original_canon = json.dumps(original, sort_keys=True, separators=(",", ":"))
    rebuilt_canon = json.dumps(rebuilt, sort_keys=True, separators=(",", ":"))

    if original_canon == rebuilt_canon:
        print("MATCH - settings_builder.build_settings() reproduces settings_template.json byte-identically.")
        return 0

    print("MISMATCH - real diff, not hand-waved:")
    orig_flat = json.loads(original_canon)
    rebuilt_flat = json.loads(rebuilt_canon)

    def diff(a, b, path=""):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(set(a) | set(b)):
                diff(a.get(k), b.get(k), f"{path}.{k}")
        elif a != b:
            print(f"  {path}: original={a!r}  rebuilt={b!r}")

    diff(orig_flat, rebuilt_flat)
    return 1


if __name__ == "__main__":
    sys.exit(main())
