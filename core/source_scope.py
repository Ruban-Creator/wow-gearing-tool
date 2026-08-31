"""Backlog #5 (CLAUDE.md Future Scope) - lets a user narrow the candidate pool
below the Phase selector, to the specific real loot sources they currently
have access to (e.g. "Phase 3, but not Black Temple yet" - Hyjal Summit and
Black Temple are both real Phase 3 content, but BT access in real TBC
progression requires clearing/attuning through Hyjal first, so the Phase
selector alone can't express that).

Every real item source in the sim's own DB is exactly one of three types -
`drop` (a real zoneId, resolvable via item_db.zones()), `crafted` (a real
profession id, resolvable via item_db.PROFESSION_NAMES), `rep` (a
repFactionId/factionId with NO real name table anywhere in this DB - see
`available_sources()`'s own docstring for why Reputation stays one bucket,
not per-faction). No other source type exists in this DB's data model - an
item with no `sources` at all is already excluded upstream by
sweep_all_loot.eligible(), never reaches this module.

Wire format: a source is a short string key - "zone:<zoneId>",
"craft:<professionId>", or the single literal "rep" - so the GUI's JS side
only ever ships plain string arrays across the pywebview bridge, never
nested objects.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402


def source_keys(item: dict) -> list[str]:
    """Every real key implied by this item's own `sources` list - an item
    can have more than one genuine acquisition path (e.g. drops off two
    different bosses/zones), and it should stay in scope if ANY of them
    is still available (see is_in_scope())."""
    keys = []
    for s in item.get("sources", []) or []:
        if "drop" in s:
            zid = s["drop"].get("zoneId")
            if zid is not None:
                keys.append(f"zone:{zid}")
        elif "crafted" in s:
            prof = s["crafted"].get("profession")
            if prof is not None:
                keys.append(f"craft:{prof}")
        elif "rep" in s:
            keys.append("rep")
    return keys


def is_in_scope(item: dict, excluded_keys: set[str]) -> bool:
    """True unless EVERY one of this item's real source keys is excluded -
    an item with one drop location the user has access to stays available
    even if it also drops somewhere they've excluded. An item with no
    resolvable source keys (shouldn't happen post-eligible(), which already
    requires a non-empty `sources` list) defaults to in scope - never
    silently drop something this module can't actually classify."""
    if not excluded_keys:
        return True
    keys = source_keys(item)
    if not keys:
        return True
    return any(k not in excluded_keys for k in keys)


def available_sources(items: list[dict], zone_by_id: dict[int, str]) -> dict:
    """Scans an already phase-filtered item list and returns only the real
    (key, label) pairs actually present at that phase, grouped for the GUI's
    checklist: {"zones": [...], "crafts": [...], "rep": [...]}, each entry
    {"key": ..., "label": ...}, sorted by label. A category is omitted
    entirely if nothing at this phase uses it (e.g. no "rep" key at all if
    no rep-sourced item exists in the given item list).

    Reputation is deliberately kept as ONE bucket ("Reputation rewards"),
    not broken out per real faction - db.json carries raw repFactionId/
    factionId numbers but no faction-name table anywhere (confirmed, not
    assumed - checked every top-level key in db.json). Per this project's
    "never invent data" rule, resolving those ids to real names (e.g. "The
    Sha'tar") would mean hand-maintaining a table sourced from outside the
    sim's own DB - decided against, per the user, 2026-08-31."""
    zone_keys: dict[str, str] = {}
    craft_keys: dict[str, str] = {}
    has_rep = False
    for item in items:
        for s in item.get("sources", []) or []:
            if "drop" in s:
                zid = s["drop"].get("zoneId")
                if zid is None:
                    continue
                zone_keys[f"zone:{zid}"] = zone_by_id.get(zid, f"Zone {zid}")
            elif "crafted" in s:
                prof = s["crafted"].get("profession")
                if prof is None:
                    continue
                craft_keys[f"craft:{prof}"] = idb.PROFESSION_NAMES.get(prof, f"Unknown({prof})")
            elif "rep" in s:
                has_rep = True

    def _sorted(d: dict[str, str]) -> list[dict]:
        return [{"key": k, "label": v} for k, v in sorted(d.items(), key=lambda kv: kv[1])]

    result = {"zones": _sorted(zone_keys), "crafts": _sorted(craft_keys)}
    if has_rep:
        result["rep"] = [{"key": "rep", "label": "Reputation rewards"}]
    else:
        result["rep"] = []
    return result
