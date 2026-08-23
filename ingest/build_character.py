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

from slpp import slpp as lua

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WOW_ROOT = r"C:\Games\World of Warcraft\_anniversary_"
SIM_SUBMODULE = os.path.join(REPO_ROOT, "sim", "tbc-new")


def find_savedvariables(addon_folder_name: str) -> list[str]:
    pattern = os.path.join(WOW_ROOT, "WTF", "Account", "*", "SavedVariables", f"{addon_folder_name}.lua")
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
        capture_output=True, text=True, check=True,
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
    """Merges fresh reputation standings into data/acquisition_status.json -
    safe to overwrite, GetFactionInfo's standing is unambiguous. Arena
    rating is NOT auto-applied to current_rating: GetArenaTeam's exact
    field for "the personal rating that gates a gear purchase" isn't
    confirmed against this client build (see the addon's own comment) -
    the raw per-team dump is stored under raw_teams for a human to check
    once, rather than the pipeline silently trusting a guessed field."""
    path = os.path.join(REPO_ROOT, "data", "acquisition_status.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        status = json.load(f)
    if reputation:
        status.setdefault("reputation", {}).update(reputation)
    if arena_teams:
        status.setdefault("arena", {})["raw_teams"] = arena_teams
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)


def resolve_items(raw_items: list[dict], item_db: dict[int, dict]) -> tuple[list[dict], list[dict]]:
    resolved, unresolved = [], []
    for it in raw_items or []:
        if not it or it.get("id") is None:
            continue
        db_item = item_db.get(it["id"])
        if db_item is None:
            unresolved.append(it)
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
    equipped, equipped_unresolved = resolve_items(equipped_raw, item_db)

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
