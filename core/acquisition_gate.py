"""Some real MV upgrades aren't actually obtainable yet - reputation-gated
quest/vendor rewards below the required standing, or rating-gated arena
gear above her current rating. The sim has no concept of any of this (it
prices an item once you have it, not whether you can get it), so nothing
upstream catches it. Caught first from a real report: Band of the Eternal
Champion (Exalted The Scale of the Sands) was blocking "Ring" from showing
as Achieved BiS even though she isn't exalted yet - see NOTES.md.

Detection is text-pattern based against the same `source` string already
shown in the report (not a new data source) - the DB doesn't structurally
encode "Exalted" for every item (Band of the Eternal Champion has no
`sources` field at all; the info only exists in Wowhead's curated text),
and it has NO arena rating data whatsoever, so a fixed field lookup
wouldn't cover the cases that actually matter. Never invents a threshold:
unknown reputation standing or unknown rating requirement both default to
"gate not satisfied" (conservative - don't claim a fake upgrade is
available) with an explicit note asking the user to confirm, rather than
silently assuming either the favorable or unfavorable case.
"""
from __future__ import annotations

import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
# rating_requirements is a fixed, character-independent game-mechanic table
# (not per-character state) - lives with the tool's own curated reference
# data, versioned in git, never in Production Data. Everything else here
# (reputation standings, current arena rating) is real per-character state
# and lives under USER_DATA_DIR/characters/<name_realm>/ instead - see
# ingest/build_character.py's update_acquisition_status().
RATING_REQUIREMENTS_PATH = os.path.join(REPO_ROOT, "profiles", "tbc", "reference", "arena_rating_requirements.json")

REPUTATION_TIERS = [
    "Hated", "Hostile", "Unfriendly", "Neutral", "Friendly", "Honored", "Revered", "Exalted",
]
_REP_PATTERN = re.compile(r"\b(" + "|".join(REPUTATION_TIERS) + r")\s+(.+)$")


def load_status(name_realm: str) -> dict:
    """Merges this character's own per-character acquisition state (real
    reputation/arena data, Production Data) with the shared, versioned
    arena.rating_requirements table (Data We Have) into the same in-memory
    shape gate_for_item() always expected, so that function needs no
    changes for the split."""
    status_path = os.path.join(USER_DATA_DIR, "characters", name_realm, "acquisition_status.json")
    if os.path.exists(status_path):
        with open(status_path, encoding="utf-8") as f:
            status = json.load(f)
    else:
        status = {"reputation": {}, "arena": {}}
    status.setdefault("arena", {})
    if os.path.exists(RATING_REQUIREMENTS_PATH):
        with open(RATING_REQUIREMENTS_PATH, encoding="utf-8") as f:
            status["arena"]["rating_requirements"] = json.load(f)
    return status


def gate_for_item(source_text: str, slot_label: str, status: dict) -> dict | None:
    """Returns None if the item isn't gated at all. Otherwise a dict with
    satisfied (True/False), and a human-readable note - always present,
    never a silently-blank column, matching how the rest of the report
    already treats "we don't have this number" (raid AP, screening-only)."""
    if not source_text:
        return None

    m = _REP_PATTERN.search(source_text)
    if m:
        required_tier, faction = m.group(1), m.group(2).strip()
        current = (status.get("reputation") or {}).get(faction)
        if current is None:
            return {
                "kind": "reputation", "satisfied": False,
                "note": f"Requires {required_tier} with {faction} - your standing isn't recorded yet. "
                        f"Login and run /gtexport to save it (GearingToolCompanion reads reputation "
                        f"automatically and this file updates on the next gear sync).",
            }
        try:
            satisfied = REPUTATION_TIERS.index(current) >= REPUTATION_TIERS.index(required_tier)
        except ValueError:
            satisfied = False
        if satisfied:
            return {"kind": "reputation", "satisfied": True,
                    "note": f"Requires {required_tier} with {faction} - you're {current}."}
        return {"kind": "reputation", "satisfied": False,
                "note": f"Requires {required_tier} with {faction} - you're currently {current}."}

    if "Arena" in source_text:
        arena = status.get("arena") or {}
        required = (arena.get("rating_requirements") or {}).get(slot_label)
        current = arena.get("current_rating")
        if required is None:
            return {"kind": "arena", "satisfied": False,
                    "note": "Arena vendor gear is rating-gated, but the required rating for this "
                            "slot isn't recorded - confirm before assuming it's obtainable."}
        if current is None:
            return {"kind": "arena", "satisfied": False,
                    "note": f"Requires {required} rating - your current rating isn't recorded yet. "
                            f"Login and run /gtexport to save it."}
        satisfied = current >= required
        return {"kind": "arena", "satisfied": satisfied,
                "note": f"Requires {required} rating - you're at {current}."}

    return None
