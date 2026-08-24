"""Enumerate every character across WowSimsExporter's and GearingToolCompanion's
own multi-character SavedVariables storage - the "who do we even have data for"
question `build_character.py` never answers, since its whole contract
(`find_wse_character`/`find_gt_companion`) is targeted at one already-known
name_realm. Reuses `build_character`'s own SavedVariables-reading primitives
rather than reimplementing Lua parsing - see that file's own docstring on why
that parsing must not diverge from what the addons actually write.

Feeds the GUI's character picker (gui/api.py) and the `gear character list`/
`gear report list` CLI commands - never invents a character or a timestamp,
only reports what's actually on disk.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_character import find_savedvariables, parse_lua_savedvariables  # noqa: E402

# TBC Anniversary's real, fixed level cap for the whole expansion (already
# assumed throughout this codebase - every real character.json/profile is
# built at 70) - the sim pipeline can't use a sub-max-level character at
# all, so one shows up here as pointless clutter otherwise (real case:
# a level 1 alt appeared in the GUI's character list next to real raid
# characters, even after the companion addon's own /gtlist got the
# equivalent filter - that one only affects the addon's own in-game
# display/future saves, not this separate Python-side read path).
MAX_LEVEL = 70


def list_wse_characters() -> dict[str, dict]:
    """name_realm -> {"identity": {...same subset build_character.build() puts
    under "character"...}, "timestamp": int, "source_account": str}.

    Scans every savedCharacters entry in every WowSimsExporter SavedVariables
    file found (any account, any profile) - where the same name_realm shows up
    more than once (multiple accounts, or multiple profiles within one), keeps
    whichever entry has the newest timestamp, same "most recent wins" rule
    find_wse_character() already applies for a single character, just applied
    across all of them at once."""
    result: dict[str, dict] = {}
    for path in find_savedvariables("WowSimsExporter"):
        account = path.split(os.sep)[-3]
        wsedb = parse_lua_savedvariables(path)
        for profile in wsedb.get("profiles", {}).values():
            for entry in profile.get("savedCharacters", []):
                name_realm = entry.get("name")
                ts = entry.get("timestamp", 0)
                if not name_realm:
                    continue
                if name_realm in result and result[name_realm]["timestamp"] >= ts:
                    continue
                char = json.loads(entry["data"])
                result[name_realm] = {
                    "identity": {
                        "name": char.get("name"),
                        "realm": char.get("realm"),
                        "race": char.get("race"),
                        "class": char.get("class"),
                        "level": char.get("level"),
                        "spec": char.get("spec"),
                        "professions": char.get("professions", []),
                        "talents": char.get("talents"),
                    },
                    "timestamp": ts,
                    "source_account": account,
                }
    return result


def list_gtcompanion_characters() -> dict[str, dict]:
    """name_realm -> {"identity": entry["identity"], "timestamp": entry["timestamp"]}.
    GTCompanionDB is already keyed uniquely by name_realm within one file - no
    per-file merge needed, only across files if more than one WoW account on
    this machine has the addon installed (same newest-wins rule as WSE)."""
    result: dict[str, dict] = {}
    for path in find_savedvariables("GearingToolCompanion"):
        db = parse_lua_savedvariables(path)
        for name_realm, entry in db.items():
            if not isinstance(entry, dict):
                continue  # skips GTCompanionMinimapDB-shaped globals if ever matched by mistake
            ts = entry.get("timestamp", 0)
            if name_realm in result and result[name_realm]["timestamp"] >= ts:
                continue
            result[name_realm] = {
                "identity": entry.get("identity", {}),
                "timestamp": ts,
            }
    return result


def _is_empty_identity(identity: dict) -> bool:
    """A GTCompanionDB entry can exist (bags/bank/rep/arena saved) from
    before this session's identity-capture feature existed, or from before
    the player has ever triggered a save that reaches SaveIdentity() - real,
    observed live on this machine's actual SavedVariables (both real
    characters' newest GTCompanion entries currently have timestamp but no
    identity yet, since they predate the addon update and haven't logged in
    since). An empty dict isn't real data to prefer over a source that has
    some, regardless of which has the newer timestamp."""
    return not any(identity.get(k) for k in ("name", "class", "race", "level"))


def list_all_characters() -> list[dict]:
    """Merge by name_realm. Per the confirmed decision: compare each source's
    own single timestamp for that character and take that source's WHOLE
    identity block verbatim - never a deep per-field merge - EXCEPT an empty
    identity block never wins over a non-empty one regardless of timestamp
    (see _is_empty_identity). Sorted by name_realm for a stable order."""
    wse = list_wse_characters()
    gt = list_gtcompanion_characters()

    merged = []
    for name_realm in sorted(set(wse) | set(gt)):
        w = wse.get(name_realm)
        g = gt.get(name_realm)

        # Skip only when the level is DEFINITELY known and below max - a
        # character with no captured level yet is shown as usual, never
        # assumed sub-max. Checks both sources' raw identity (not yet
        # merged/picked below) so a stale sub-70 GTCompanion entry can't
        # slip through just because WSE's own data doesn't carry a level.
        known_levels = [d["identity"].get("level") for d in (w, g) if d and d["identity"].get("level")]
        if known_levels and max(known_levels) < MAX_LEVEL:
            continue
        if w and g:
            w_empty, g_empty = _is_empty_identity(w["identity"]), _is_empty_identity(g["identity"])
            if w_empty and not g_empty:
                source_used, identity = "gtcompanion", g["identity"]
            elif g_empty and not w_empty:
                source_used, identity = "wse", w["identity"]
            else:
                source_used, identity = ("wse", w["identity"]) if w["timestamp"] >= g["timestamp"] else ("gtcompanion", g["identity"])
        elif w:
            source_used, identity = "wse", w["identity"]
        else:
            source_used, identity = "gtcompanion", g["identity"]

        merged.append({
            "name_realm": name_realm,
            "source_used": source_used,
            "identity": identity,
            "wse_timestamp": w["timestamp"] if w else None,
            "gt_timestamp": g["timestamp"] if g else None,
            "has_wse": w is not None,
            "has_gtcompanion": g is not None,
        })
    return merged


if __name__ == "__main__":
    for c in list_all_characters():
        print(json.dumps(c, indent=2))
