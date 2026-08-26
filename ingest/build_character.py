"""Read WowSimsExporter + GearingToolCompanion SavedVariables straight off disk
(no clipboard) and build data/character.json (+ update data/acquisition_status.json's
reputation standings).

Ground truth for the shapes parsed here lives in NOTES.md ("SavedVariables
located" and the WowSimsExporter source reading) - this file doesn't invent
any field names, it mirrors what WowSimsExporter.lua / EquipmentSpec.lua /
GearingToolCompanion.lua actually write.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

# See adapters/tbc/valuation.py's own copy of this comment - the packaged
# (windowed, console-less) GUI has nowhere to attach a child console, so
# Windows pops a new visible one for this git call unless told not to.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

from slpp import slpp as lua

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_SUBMODULE = os.path.join(REPO_ROOT, "sim", "tbc-new")

sys.path.insert(0, os.path.join(REPO_ROOT, "core"))
import local_config  # noqa: E402


def find_savedvariables(addon_folder_name: str) -> list[str]:
    # WOW_ROOT used to be a hardcoded module constant here - now sourced
    # from local_config.wow_root() (configured > real autodetection > the
    # one legacy hardcoded fallback), per the user, 2026-08-26: the original
    # hardcoded path was real for the dev machine but nobody else's.
    pattern = os.path.join(local_config.wow_root(), "WTF", "Account", "*", "SavedVariables", f"{addon_folder_name}.lua")
    return glob.glob(pattern)


def parse_lua_savedvariables(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        text = f.read()
    # Files are `GLOBALNAME = { ... }`; slpp wants just the table literal.
    _, _, rhs = text.partition("=")
    return lua.decode(rhs.strip())


def sim_commit_sha() -> str:
    out = subprocess.run(
        ["git", "-C", SIM_SUBMODULE, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, creationflags=_NO_WINDOW,
    )
    return out.stdout.strip()


def load_item_db() -> dict[int, dict]:
    """Keyed by item id, covering both gear (`items`) and consumables (potions,
    elixirs, food, bandages, sappers, ...) - they're separate collections in
    db.json. Without the second, ordinary bag/bank consumables would wrongly
    show up as "unresolved" (the sim genuinely knows them, just not as gear)."""
    db_path = os.path.join(SIM_SUBMODULE, "assets", "database", "db.json")
    with open(db_path, encoding="utf-8") as f:
        db = json.load(f)
    merged = {it["id"]: it for it in db.get("items", [])}
    for it in db.get("consumables", []):
        merged.setdefault(it["id"], it)
    return merged


def find_wse_character(name_realm: str) -> tuple[dict, str] | None:
    """Returns (parsed character dict, source account dir) for the most recent
    savedCharacters entry across all WowSimsExporter SavedVariables files
    matching name_realm (e.g. "Lerynia-Thunderstrike")."""
    best = None
    best_source = None
    best_ts = -1
    for path in find_savedvariables("WowSimsExporter"):
        account = path.split(os.sep)[-3]
        wsedb = parse_lua_savedvariables(path)
        for profile in wsedb.get("profiles", {}).values():
            for entry in profile.get("savedCharacters", []):
                if entry.get("name") != name_realm:
                    continue
                ts = entry.get("timestamp", 0)
                if ts > best_ts:
                    best_ts = ts
                    best = json.loads(entry["data"])
                    best_source = account
    if best is None:
        return None
    return best, best_source


def find_gt_companion(name_realm: str) -> dict | None:
    for path in find_savedvariables("GearingToolCompanion"):
        db = parse_lua_savedvariables(path)
        if name_realm in db:
            return db[name_realm]
    return None


def update_acquisition_status(reputation: dict, arena_teams: list) -> None:
    """Merges fresh reputation standings and arena rating into
    data/acquisition_status.json - safe to overwrite, both are now read
    from confirmed, unambiguous sources: C_Reputation's `reaction` field
    for standing, GetPersonalRatedInfo's `rating` per bracket for arena
    (this client has no persistent "arena team" object at all - TBC
    Anniversary uses the modern personal-rating system, confirmed by
    testing: GetArenaTeam returned nothing despite real 2v2/3v3/5v5
    ratings existing). current_rating is the max across brackets - TBC's
    arena vendor gating is "reach X rating in ANY bracket", not tied to
    one specific bracket, a stable, long-documented game mechanic (not
    server-specific data), unlike the API-field question above which
    genuinely needed confirming."""
    path = os.path.join(REPO_ROOT, "data", "acquisition_status.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        status = json.load(f)
    if reputation:
        status.setdefault("reputation", {}).update(reputation)
    if arena_teams:
        arena = status.setdefault("arena", {})
        arena["brackets"] = arena_teams
        ratings = [t["rating"] for t in arena_teams if t.get("rating")]
        if ratings:
            arena["current_rating"] = max(ratings)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def resolve_items(raw_items: list[dict], item_db: dict[int, dict],
                   preserve_positions: bool = False) -> tuple[list[dict], list[dict]]:
    """preserve_positions=True is required for equipped items - real bug found
    and fixed 2026-08-25 testing against Rubán-Thunderstrike (a 2H-weapon
    Warrior, the first real character in this project with a genuinely empty
    equipment slot - Lerynia has all 17 filled, so this never surfaced
    before). EquipmentSpec.items is a real, fixed 17-slot positional array
    (confirmed from WowSimsExporter's own Lua source, see NOTES.md) - the
    whole rest of the pipeline (gear_config.SLOT_ORDER-indexed lookups in
    optimizer.py/run_full_sweep_mv.py) assumes `equipped["items"][i]`
    corresponds to `SLOT_ORDER[i]`. The old unconditional `continue` on an
    empty/unresolved slot silently DROPPED it instead of keeping a
    placeholder, collapsing the list and shifting every later real item up
    by one position - confirmed live: Rubán's real empty offhand (raw index
    15, a genuine `None` - he wields a 2H weapon) was dropped, which shifted
    his real ranged weapon (raw index 16, Xavian Stiletto) into the
    offhand-display position instead. Bags/bank callers correctly keep
    preserve_positions=False (default) - those aren't slot-fixed, dropping
    an empty/unresolvable entry there is correct, not a bug."""
    resolved, unresolved = [], []
    for it in raw_items or []:
        if not it or it.get("id") is None:
            if preserve_positions:
                resolved.append(None)
            continue
        db_item = item_db.get(it["id"])
        if db_item is None:
            unresolved.append(it)
            if preserve_positions:
                # Keep it in position even though we can't name it - dropping
                # it would silently treat a REAL equipped item as an empty
                # slot, corrupting every later slot's position exactly like
                # the empty-slot bug this function now avoids.
                resolved.append(it)
        else:
            resolved.append({**it, "name": db_item.get("name")})
    return resolved, unresolved


def build(name_realm: str) -> dict:
    wse = find_wse_character(name_realm)
    if wse is None:
        raise SystemExit(
            f"No WowSimsExporter export found for {name_realm!r} in any account's SavedVariables. "
            f"Run /wse export in-game once first."
        )
    char, account = wse
    item_db = load_item_db()

    equipped_raw = char.get("gear", {}).get("items", [])
    equipped, equipped_unresolved = resolve_items(equipped_raw, item_db, preserve_positions=True)

    gt = find_gt_companion(name_realm) or {}
    bags, bags_unresolved = resolve_items(gt.get("bags", []), item_db)
    bank, bank_unresolved = resolve_items(gt.get("bank", []), item_db)

    unresolved = equipped_unresolved + bags_unresolved + bank_unresolved

    update_acquisition_status(gt.get("reputation", {}), gt.get("arena", []))

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sim_commit_sha": sim_commit_sha(),
            "wse_source_account": account,
            "gt_companion_present": bool(gt),
            "gt_companion_timestamp": gt.get("timestamp"),
        },
        "character": {
            "name": char.get("name"),
            "realm": char.get("realm"),
            "race": char.get("race"),
            "class": char.get("class"),
            "level": char.get("level"),
            "spec": char.get("spec"),
            "professions": char.get("professions", []),
            "talents": char.get("talents"),
        },
        "equipped": {"items": equipped},
        "owned": {"bags": bags, "bank": bank},
        "currencies": {},
        "raid": {},
        "unresolved": unresolved,
        "history": [],
    }


def main():
    name_realm = sys.argv[1] if len(sys.argv) > 1 else "Lerynia-Thunderstrike"
    data = build(name_realm)

    out_path = os.path.join(REPO_ROOT, "data", "character.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    n_equipped = sum(1 for i in data["equipped"]["items"])
    print(f"Wrote {out_path}")
    print(f"  equipped: {n_equipped} items resolved (of 17 slots)")
    print(f"  bags: {len(data['owned']['bags'])} items")
    print(f"  bank: {len(data['owned']['bank'])} items")
    print(f"  unresolved: {len(data['unresolved'])} items")
    if data["unresolved"]:
        for it in data["unresolved"]:
            print(f"    - id={it.get('id')} (not found in sim DB)")

    status_path = os.path.join(REPO_ROOT, "data", "acquisition_status.json")
    if os.path.exists(status_path):
        with open(status_path, encoding="utf-8") as f:
            status = json.load(f)
        print(f"Updated {status_path}")
        print(f"  reputation: {status.get('reputation', {})}")
        raw_teams = status.get("arena", {}).get("raw_teams")
        if raw_teams:
            print(f"  arena raw_teams: {raw_teams}")
            print("  (confirm which field is the real gear-purchase rating, then set arena.current_rating by hand)")


if __name__ == "__main__":
    main()
