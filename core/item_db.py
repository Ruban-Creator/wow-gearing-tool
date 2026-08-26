"""Thin, read-only wrapper over the sim's assets/database/db.json - the
single source of truth for item stats/flags used by the optimizer. Never
invents a field; if something isn't in the DB it comes back as None/False.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
DB_PATH = os.path.join(REPO_ROOT, "sim", "tbc-new", "assets", "database", "db.json")

_db = None


def _load():
    global _db
    if _db is None:
        with open(DB_PATH, encoding="utf-8") as f:
            _db = json.load(f)
    return _db


def by_id(item_id: int) -> dict | None:
    db = _load()
    if not hasattr(by_id, "_index"):
        by_id._index = {it["id"]: it for it in db.get("items", [])}
    return by_id._index.get(item_id)


def ids_by_name(name: str) -> list[int]:
    db = _load()
    if not hasattr(ids_by_name, "_index"):
        idx = {}
        for it in db.get("items", []):
            idx.setdefault(it["name"], []).append(it["id"])
        ids_by_name._index = idx
    return ids_by_name._index.get(name, [])


def gem_by_id(gem_id: int) -> dict | None:
    db = _load()
    if not hasattr(gem_by_id, "_index"):
        gem_by_id._index = {g["id"]: g for g in db.get("gems", [])}
    return gem_by_id._index.get(gem_id)


def enchant_by_id(effect_id: int) -> dict | None:
    """db.json's enchants collection is keyed by effectId (not itemId) -
    a display/name lookup, not proof the Go sim engine implements the
    effect (see core/verify_default_enchants.py for the real check)."""
    db = _load()
    if not hasattr(enchant_by_id, "_index"):
        enchant_by_id._index = {e["effectId"]: e for e in db.get("enchants", [])}
    return enchant_by_id._index.get(effect_id)


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
