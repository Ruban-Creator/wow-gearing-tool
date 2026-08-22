"""Stage 4 (§6): DPS*(S) via warm-started per-slot greedy sweep, with
trinkets/ranged/set-bonus handled as explicit branches since greedy search
provably misses those. Screening-only (2k iterations) - resolving close
ties at 30-50k is a separate, later pass per the doc's own STOP point.

Known simplifications, flagged rather than silently done:
- Gems held constant at her existing default (Delicate Living Ruby, see
  gear_config.DEFAULT_GEM) for candidate items she doesn't currently own.
  Meta gem slot is held as-is (already her standard Hunter/Agility meta,
  Relentless Earthstorm Diamond - confirmed from her actual gear, not
  re-derived). Full gem re-optimization is not implemented this pass.
- Ranged weapon is exhaustive over the candidate pool but does NOT
  re-verify/retune the rotation per weapon speed (the doc explicitly warns
  this matters for Steady Shot weaving) - every ranged candidate is
  evaluated under the same fixed rotation as the settings template.
Both are reported explicitly in the run summary, not hidden.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402
import gear_config as gc  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "tbc"))
import valuation  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_ITERATIONS = 2000
SEED = 1
MAX_WORKERS = 4

TRINKET_SLOTS = ("trinket1", "trinket2")
RANGED_SLOT = "ranged"
GREEDY_SLOTS = [s for s in gc.SLOT_ORDER if s not in TRINKET_SLOTS and s != RANGED_SLOT]

# Rift Stalker Armor set piece item ids currently held (head/shoulder/chest/hands) -
# see NOTES.md, "Update: resolved" and item_sets.go for the confirmed 4pc bonus.
RIFT_STALKER_SET_NAME = "Rift Stalker Armor"


class Candidate:
    __slots__ = ("name", "item_id", "enchant", "gems", "excluded_reason")

    def __init__(self, name, item_id, enchant=0, gems=None, excluded_reason=None):
        self.name = name
        self.item_id = item_id
        self.enchant = enchant
        self.gems = gems or []
        self.excluded_reason = excluded_reason

    def as_entry(self):
        return gc.item_entry(self.item_id, self.enchant, self.gems)


# Reference-list slot keys -> the 17 equipped-array slot names that draw
# from them. Rings and trinkets share one pool each across two slots;
# mainhand/offhand share the dual-wield pool (she's confirmed dual-wielding
# in her real, validated export - two-handed is not explored this pass).
POOL_KEY_TO_SLOTS = {
    "head": ["head"], "neck": ["neck"], "shoulder": ["shoulder"], "back": ["back"],
    "chest": ["chest"], "wrist": ["wrist"], "hands": ["hands"], "waist": ["waist"],
    "legs": ["legs"], "feet": ["feet"], "ring": ["ring1", "ring2"],
    "trinket": ["trinket1", "trinket2"], "weapon_dual_wield": ["mainhand", "offhand"],
    "ranged": ["ranged"],
}


def load_candidates(pool_path: str, owned_items: list[dict]) -> dict[str, list[Candidate]]:
    """Resolves each candidate name to an id (preferring the id she already
    owns for that name, since a plain name lookup can hit multiple ids -
    see NOTES.md's "Band of Eternity" bug), applies profession gating, and
    reuses her real enchant/gems when the candidate IS what she already has
    equipped (never invents an enchant for an item she doesn't own)."""
    pool = json.load(open(pool_path, encoding="utf-8"))
    owned_by_name = {it["name"]: it for it in owned_items if it}

    result = {slot: [] for slot in gc.SLOT_ORDER}
    for pool_key, entries in pool.items():
        target_slots = POOL_KEY_TO_SLOTS.get(pool_key, [])
        if not target_slots:
            continue
        cands = []
        for entry in entries:
            name = entry["item"]
            owned = owned_by_name.get(name)
            ids = idb.ids_by_name(name)
            if not ids:
                cands.append(Candidate(name, None, excluded_reason="not found in sim DB"))
                continue
            item_id = owned["id"] if owned else ids[0]
            item = idb.by_id(item_id)
            req_prof = idb.required_profession_name(item) if item else None
            # Only Herbalism/Mining known professions for this character (character.json).
            if req_prof and req_prof not in ("Herbalism", "Mining"):
                cands.append(Candidate(name, item_id, excluded_reason=f"requires {req_prof}"))
                continue
            if owned:
                cands.append(Candidate(name, item_id, owned.get("enchant", 0), owned.get("gems")))
            else:
                gems = [gc.DEFAULT_GEM] * len([s for s in (item.get("gemSockets") or []) if s != idb.META_GEM_COLOR]) if item else []
                cands.append(Candidate(name, item_id, 0, gems))
        for slot in target_slots:
            result[slot] = cands
    return result


def build_owned_config(equipped_items: list[dict]) -> list[dict]:
    return [gc.item_entry(it["id"], it.get("enchant", 0), it.get("gems")) if it else {} for it in equipped_items]


def is_unique_conflict(config: list[dict], slot_idx: int, item_id: int) -> bool:
    item = idb.by_id(item_id)
    if not item or not idb.is_unique(item):
        return False
    for i, entry in enumerate(config):
        if i != slot_idx and entry.get("id") == item_id:
            return True
    return False


def eval_config(settings_path: str, config: list[dict]) -> dict:
    return valuation.evaluate(settings_path, config, SCREEN_ITERATIONS, SEED)


def greedy_sweep(settings_path: str, config: list[dict], candidates: dict[str, list[Candidate]], log: list):
    changed = True
    passes = 0
    while changed and passes < 6:
        changed = False
        passes += 1
        for slot in GREEDY_SLOTS:
            slot_idx = gc.SLOT_ORDER.index(slot)
            options = [c for c in candidates.get(slot, []) if c.excluded_reason is None]
            if not options:
                continue

            def try_option(cand):
                if is_unique_conflict(config, slot_idx, cand.item_id):
                    return cand, None
                trial = list(config)
                trial[slot_idx] = cand.as_entry()
                return cand, eval_config(settings_path, trial)

            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
                results = list(ex.map(try_option, options))

            current_result = eval_config(settings_path, config)
            best_cand, best_result = None, current_result
            for cand, res in results:
                if res is not None and res["combined"] > best_result["combined"]:
                    best_cand, best_result = cand, res

            if best_cand is not None and best_result["combined"] > current_result["combined"] + 0.01:
                config[slot_idx] = best_cand.as_entry()
                changed = True
                log.append({
                    "pass": passes, "slot": slot, "picked": best_cand.name,
                    "combined": best_result["combined"],
                    "gain_over_previous_best_in_pass": best_result["combined"] - current_result["combined"],
                })
    return config, passes


def trinket_pairs(settings_path: str, config: list[dict], candidates: list[Candidate], log: list):
    options = [c for c in candidates if c.excluded_reason is None]
    t1_idx, t2_idx = gc.SLOT_ORDER.index("trinket1"), gc.SLOT_ORDER.index("trinket2")
    pairs = []
    for i, a in enumerate(options):
        for b in options[i:]:
            if a.item_id == b.item_id:
                item = idb.by_id(a.item_id)
                if item and idb.is_unique(item):
                    continue  # can't equip the same unique trinket twice
            pairs.append((a, b))

    def try_pair(pair):
        a, b = pair
        trial = list(config)
        trial[t1_idx] = a.as_entry()
        trial[t2_idx] = b.as_entry()
        return pair, eval_config(settings_path, trial)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(try_pair, pairs))

    best_pair, best_result = None, None
    for pair, res in results:
        if best_result is None or res["combined"] > best_result["combined"]:
            best_pair, best_result = pair, res

    config[t1_idx] = best_pair[0].as_entry()
    config[t2_idx] = best_pair[1].as_entry()
    log.append({"slot": "trinket1+trinket2", "picked": f"{best_pair[0].name} + {best_pair[1].name}", "combined": best_result["combined"]})
    return config


def set_bonus_branch(settings_path: str, greedy_config: list[dict], candidates: dict[str, list[Candidate]],
                      set_name: str, set_slots: list[str], log: list) -> list[dict]:
    """Forced branch (§6 point 3): greedy per-slot sweep will never break an
    already-held 4pc bonus for one mediocre-in-isolation piece of a
    competing set, which is correct - but that also means it can never see
    whether swapping the WHOLE set would win once the competing set's own
    2pc/4pc bonus kicks in. Forces the full swap and compares against the
    greedy result directly, rather than assuming greedy already covers it."""
    trial = list(greedy_config)
    swapped_names = []
    for slot in set_slots:
        slot_idx = gc.SLOT_ORDER.index(slot)
        target = next((c for c in candidates.get(slot, [])
                        if c.excluded_reason is None and _in_set(c.item_id, set_name)), None)
        if target is None:
            log.append({"set_bonus_branch": set_name, "result": f"no candidate found for slot {slot} - skipped"})
            return greedy_config
        trial[slot_idx] = target.as_entry()
        swapped_names.append(target.name)

    forced_result = eval_config(settings_path, trial)
    greedy_result = eval_config(settings_path, greedy_config)
    log.append({
        "set_bonus_branch": set_name,
        "forced_full_set": swapped_names,
        "forced_combined": forced_result["combined"],
        "greedy_combined": greedy_result["combined"],
        "forced_wins": forced_result["combined"] > greedy_result["combined"],
    })
    return trial if forced_result["combined"] > greedy_result["combined"] else greedy_config


def _in_set(item_id: int, set_name: str) -> bool:
    item = idb.by_id(item_id)
    return bool(item and item.get("setName") == set_name)


def ranged_exhaustive(settings_path: str, config: list[dict], candidates: list[Candidate], log: list):
    options = [c for c in candidates if c.excluded_reason is None]
    r_idx = gc.SLOT_ORDER.index("ranged")

    def try_option(cand):
        trial = list(config)
        trial[r_idx] = cand.as_entry()
        return cand, eval_config(settings_path, trial)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        results = list(ex.map(try_option, options))

    best_cand, best_result = None, None
    for cand, res in results:
        if best_result is None or res["combined"] > best_result["combined"]:
            best_cand, best_result = cand, res

    config[r_idx] = best_cand.as_entry()
    log.append({"slot": "ranged (exhaustive, rotation NOT re-tuned per weapon speed)", "picked": best_cand.name, "combined": best_result["combined"]})
    return config
