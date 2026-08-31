"""Thin, read-only wrapper over the sim's assets/database/db.json - the
single source of truth for item stats/flags used by the optimizer. Never
invents a field; if something isn't in the DB it comes back as None/False.

The ONLY module that should ever open db.json directly (code review §2.4):
five other modules (gem_optimizer, sweep_all_loot, run_full_sweep_mv,
build_wowsims_reference_bis, ingest/build_character) each had their own
independent DB_PATH + json.load(), meaning a single sweep parsed the same
~multi-MB file into several separate in-memory copies. All five now go
through the accessors below instead.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")

_db: dict | None = None
_by_id_index: dict[int, dict] | None = None
_ids_by_name_index: dict[str, list[int]] | None = None
_gem_by_id_index: dict[int, dict] | None = None
_enchant_by_id_index: dict[int, dict] | None = None


def _load() -> dict:
    """Loads db.json once per process and builds every index this module
    offers at the same time (code review §2.4's secondary finding: the old
    per-function `hasattr(fn, "_index")` memoization worked but was
    unidiomatic - same behavior, plain module-level dicts, built once here
    instead of scattered across four separate functions)."""
    global _db, _by_id_index, _ids_by_name_index, _gem_by_id_index, _enchant_by_id_index
    if _db is not None:
        return _db
    with open(DB_PATH, encoding="utf-8") as f:
        _db = json.load(f)
    _by_id_index = {it["id"]: it for it in _db.get("items", [])}
    _ids_by_name_index = {}
    for it in _db.get("items", []):
        _ids_by_name_index.setdefault(it["name"], []).append(it["id"])
    _gem_by_id_index = {g["id"]: g for g in _db.get("gems", [])}
    _enchant_by_id_index = {e["effectId"]: e for e in _db.get("enchants", [])}
    return _db


def items() -> list[dict]:
    _load()
    return _db.get("items", [])


def gems() -> list[dict]:
    _load()
    return _db.get("gems", [])


def npcs() -> list[dict]:
    _load()
    return _db.get("npcs", [])


def zones() -> list[dict]:
    _load()
    return _db.get("zones", [])


def consumables() -> list[dict]:
    _load()
    return _db.get("consumables", [])


def by_id(item_id: int) -> dict | None:
    _load()
    return _by_id_index.get(item_id)


def ids_by_name(name: str) -> list[int]:
    _load()
    return _ids_by_name_index.get(name, [])


def gem_by_id(gem_id: int) -> dict | None:
    _load()
    return _gem_by_id_index.get(gem_id)


def enchant_by_id(effect_id: int) -> dict | None:
    """db.json's enchants collection is keyed by effectId (not itemId) -
    a display/name lookup, not proof the Go sim engine implements the
    effect (see core/verify_default_enchants.py for the real check)."""
    _load()
    return _enchant_by_id_index.get(effect_id)


# proto/common.proto GemColor enum (read directly, not guessed - color 8 is
# Prismatic, not Meta; got this wrong on a first pass before checking source).
META_GEM_COLOR = 1

# proto/common.proto Profession enum, for interpreting requiredProfession.
PROFESSION_NAMES = {
    0: "None", 1: "Alchemy", 2: "Blacksmithing", 3: "Enchanting", 4: "Engineering",
    5: "Herbalism", 6: "Inscription", 7: "Jewelcrafting", 8: "Leatherworking",
    9: "Mining", 10: "Skinning", 11: "Tailoring",
}


def required_profession_name(item: dict) -> str | None:
    prof = item.get("requiredProfession")
    if not prof:
        return None
    return PROFESSION_NAMES.get(prof, f"Unknown({prof})")


def enchant_required_profession_name(effect_id: int) -> str | None:
    """Real, found 2026-08-25 (user flagged it live): unlike every other
    enchant slot, Ring enchants in this game can only be self-applied by a
    character who personally has Enchanting - there's no "pay any enchanter
    to do it for you" option the way there is for every other slot. db.json
    already encodes this distinction for free: ordinary tradeable enchants
    (cloak/chest/weapon/etc.) carry requiredProfession=None, while ring
    enchants carry a real requiredProfession - confirmed by direct
    comparison, not assumed. Mirrors required_profession_name() above,
    applied to enchant effects instead of items."""
    enchant = enchant_by_id(effect_id)
    if not enchant:
        return None
    prof = enchant.get("requiredProfession")
    if not prof:
        return None
    return PROFESSION_NAMES.get(prof, f"Unknown({prof})")


def is_unique(item: dict) -> bool:
    return bool(item.get("unique"))


def is_meta_socket_item(item: dict) -> bool:
    """True if any of the item's gem sockets is a meta socket."""
    return META_GEM_COLOR in (item.get("gemSockets") or [])
