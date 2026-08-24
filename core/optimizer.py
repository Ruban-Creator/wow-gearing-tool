"""Stage 4 (§6): DPS*(S) via warm-started per-slot greedy sweep, with
trinkets/ranged/set-bonus handled as explicit branches since greedy search
provably misses those.

Corrected after a real miss (see NOTES.md, "Correction: the Stage 4
screening conclusion was wrong"): the greedy sweep + a too-narrow
set-bonus branch reported Rift Stalker T5 beating a full Gronnstalker T6
transition, when the full transition actually wins by ~270 DPS once
properly evaluated. Two fixes now in place:
1. `full_bundle_branch` tests an entire named reference bundle (e.g. the
   recommended full BiS set) against the greedy result directly, not just
   one set's armor pieces in isolation with everything else left at
   whatever greedy already picked.
2. `resolve` re-evaluates any close screening call at high iterations
   before it's reported as final - screening alone (2k iterations) isn't
   trustworthy for calls within a few DPS of each other.

Known simplifications, flagged rather than silently done:
- Gems: reuses her real gems for items she already owns; non-owned
  candidates get gear_config.DEFAULT_GEM (Delicate Crimson Spinel, the
  actual phase 3 gem the reference set uses - not phase 1, see the
  DEFAULT_GEM fix in gear_config.py). Meta gem slot held as-is (already her
  standard Hunter/Agility meta, Relentless Earthstorm Diamond). Full gem
  re-optimization beyond this default still isn't implemented.
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
import gem_optimizer  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "adapters", "tbc"))
import valuation  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCREEN_ITERATIONS = 2000
RESOLVE_ITERATIONS = 30000
SEED = 1
MAX_WORKERS = 4

TRINKET_SLOTS = ("trinket1", "trinket2")
RANGED_SLOT = "ranged"
GREEDY_SLOTS = [s for s in gc.SLOT_ORDER if s not in TRINKET_SLOTS and s != RANGED_SLOT]

# Rift Stalker Armor set piece item ids currently held (head/shoulder/chest/hands) -
# see NOTES.md, "Update: resolved" and item_sets.go for the confirmed 4pc bonus.
RIFT_STALKER_SET_NAME = "Rift Stalker Armor"


class Candidate:
    __slots__ = ("name", "item_id", "enchant", "gems", "excluded_reason", "variant")

    def __init__(self, name, item_id, enchant=0, gems=None, excluded_reason=None, variant=None):
        self.name = name
        self.item_id = item_id
        self.enchant = enchant
        self.gems = gems or []
        self.excluded_reason = excluded_reason
        self.variant = variant  # see gear_config.item_entry's docstring - always None for TBC today

    def as_entry(self):
        return gc.item_entry(self.item_id, self.enchant, self.gems, self.variant)


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


def find_owned_meta_gem(owned_items: list[dict]) -> int | None:
    """Her current meta gem id, found from whichever owned item has a meta
    socket - used to keep the meta gem filled on non-owned candidates that
    also have a meta socket, instead of leaving that socket empty."""
    for it in owned_items:
        if not it:
            continue
        item = idb.by_id(it["id"])
        if not item or not idb.is_meta_socket_item(item):
            continue
        for gem_id in it.get("gems") or []:
            gem = idb.gem_by_id(gem_id)
            if gem and gem.get("color") == idb.META_GEM_COLOR:
                return gem_id
    return None


def gems_for_item(item: dict, meta_gem_id: int | None) -> list[int]:
    """Real per-socket gem choice (chase the item's one all-or-nothing
    socket bonus vs. pure Agility everywhere, whichever scores higher) -
    see gem_optimizer.py. Still guarantees the meta socket never silently
    goes empty (the original bug this function was built to fix - a
    too-short gems list skipping the meta position, undervaluing e.g.
    Gronnstalker's Helmet - see NOTES.md's screening correction)."""
    return gem_optimizer.best_gems_for_item(item, meta_gem_id)


def load_candidates(pool_path: str, owned_items: list[dict]) -> dict[str, list[Candidate]]:
    """Resolves each candidate name to an id (preferring the id she already
    owns for that name, since a plain name lookup can hit multiple ids -
    see NOTES.md's "Band of Eternity" bug), applies profession gating, and
    reuses her real enchant/gems when the candidate IS what she already has
    equipped (never invents an enchant for an item she doesn't own)."""
    pool = json.load(open(pool_path, encoding="utf-8"))
    owned_by_name = {it["name"]: it for it in owned_items if it}
    meta_gem_id = find_owned_meta_gem(owned_items)

    result = {slot: [] for slot in gc.SLOT_ORDER}
    for pool_key, entries in pool.items():
        target_slots = POOL_KEY_TO_SLOTS.get(pool_key, [])
        if not target_slots:
            continue
        # Enchants attach to the SLOT via the profession UI, not to a
        # specific item - a non-owned candidate with enchant=0 was silently
        # evaluated with no enchant at all (e.g. Gronnstalker's Spaulders
        # missing the shoulder inscription), understating it by exactly
        # that enchant's value. Real bug, caught by a user's own wowsims.com
        # test disagreeing with this tool - see NOTES.md. Default to
        # whichever target slot she currently has an enchant on; for
        # rings/trinkets this naturally stays 0 since those slots never
        # carry enchants in this game.
        default_enchant = 0
        for slot in target_slots:
            slot_idx = gc.SLOT_ORDER.index(slot)
            owned_here = owned_items[slot_idx] if slot_idx < len(owned_items) else None
            if owned_here and owned_here.get("enchant"):
                default_enchant = owned_here["enchant"]
                break

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
                gems = gems_for_item(item, meta_gem_id) if item else []
                cands.append(Candidate(name, item_id, default_enchant, gems))
        for slot in target_slots:
            result[slot] = cands
    return result


def build_owned_config(equipped_items: list[dict]) -> list[dict]:
    """Optimal gems for her CURRENT gear, not her literal real (possibly
    outdated) socketed gems - matching CLAUDE.md's own MV(i) = DPS*(P∪{i})
    - DPS*(P) formula: DPS*(P) is the BEST achievable from pool P, gems
    included, not "whatever happens to be socketed right now". Real bug
    this fixes: her actual Rift Stalker Hauberk was still socketed with
    Delicate Living Ruby (phase 1) instead of the better Delicate Crimson
    Spinel (phase 3, gear_config.DEFAULT_GEM) - a free re-gem she hadn't
    done yet, which was silently understating her own baseline and
    thereby overstating every candidate's true marginal value. Applying
    the same gem_optimizer treatment here that candidates already get
    keeps the comparison fair on both sides. Enchants stay real (her
    actual current enchant, never invented)."""
    meta_gem_id = find_owned_meta_gem(equipped_items)
    config = []
    for it in equipped_items:
        if not it:
            config.append({})
            continue
        item = idb.by_id(it["id"])
        gems = gem_optimizer.best_gems_for_item(item, meta_gem_id) if item else it.get("gems")
        config.append(gc.item_entry(it["id"], it.get("enchant", 0), gems))
    return gem_optimizer.ensure_meta_requirement(config, equipped_items, meta_gem_id)


def is_unique_conflict(config: list[dict], slot_idx: int, item_id: int) -> bool:
    item = idb.by_id(item_id)
    if not item or not idb.is_unique(item):
        return False
    for i, entry in enumerate(config):
        if i != slot_idx and entry.get("id") == item_id:
            return True
    return False


# common.proto HandType enum. TwoHand(4) is already filtered out upstream
# (run_full_sweep_mv.py's slot_for_item) since it needs the melee-weave
# rotation variant, not a plain slot swap. MainHand(1) and OffHand(3) were
# NOT enforced anywhere until this was caught - a real gap, found via a
# real matched pair (Claw of Molten Fury/MainHand + Fist of Molten
# Fury/OffHand, Mount Hyjal trash, setId 719) that mv_single's "try every
# slot this item could occupy" logic would otherwise have silently tested
# in the WRONG slot for a hand-restricted weapon, producing an invalid
# config instead of a real "unequippable here" exclusion.
HAND_MAINHAND = 1
HAND_ONEHAND = 2
HAND_OFFHAND = 3
HAND_TWOHAND = 4
_SLOT_TO_HAND_RESTRICTION = {"mainhand": HAND_OFFHAND, "offhand": HAND_MAINHAND}


def is_hand_restricted_conflict(item_id: int, slot: str) -> bool:
    """True if this weapon's handType forbids it from going in `slot` -
    e.g. a MainHand-restricted weapon can't go in the offhand slot.

    Real bug caught here (not just theoretical): `hand_type ==
    _SLOT_TO_HAND_RESTRICTION.get(slot)` alone silently returned True for
    EVERY non-weapon item in EVERY non-weapon slot, since a non-weapon
    item's handType is None and _SLOT_TO_HAND_RESTRICTION.get(slot) for a
    non-weapon slot is ALSO None - `None == None` is True, so mv_single
    excluded every candidate from every armor/jewelry slot as a "hand
    conflict" (surfaced as almost the entire gear set falsely showing as
    Achieved BiS - nothing beats it - when real upgrades existed and had
    just been reported minutes earlier). This only means anything for a
    real weapon in a real weapon slot."""
    if slot not in _SLOT_TO_HAND_RESTRICTION:
        return False
    item = idb.by_id(item_id)
    if not item:
        return False
    hand_type = item.get("handType")
    if hand_type is None:
        return False
    return hand_type == _SLOT_TO_HAND_RESTRICTION[slot]


def eval_config(settings_path: str, config: list[dict]) -> dict:
    return valuation.evaluate(settings_path, config, SCREEN_ITERATIONS, SEED)


def resolve(settings_path: str, config: list[dict]) -> dict:
    """High-iteration re-evaluation (§6: 'resolve only within-error ties at
    30-50k'). Call this on any screening result before trusting it as
    final - screening alone got a real comparison wrong once already."""
    return valuation.evaluate(settings_path, config, RESOLVE_ITERATIONS, SEED)


def resolve_name_to_config(name_list: list[str], candidates: dict[str, list["Candidate"]],
                            owned_items: list[dict]) -> list[dict] | None:
    """Builds a full 17-slot config from a flat list of item names (e.g. a
    reference guide's 'recommended full set'), using the same
    owned-enchant/gems-if-owned-else-DEFAULT_GEM resolution as the rest of
    the candidate pool. Returns None if any name can't be placed - never
    silently drops an item to make a bundle 'work'."""
    by_name = {}
    for slot_cands in candidates.values():
        for c in slot_cands:
            by_name.setdefault(c.name, []).append(c)

    config = [None] * len(gc.SLOT_ORDER)
    remaining = list(name_list)
    # Fill slots that have exactly one still-unassigned name matching one of
    # their candidates first (rings/trinkets/weapons need this since two
    # slots share one pool and a name can appear twice, e.g. dual weapons).
    for slot_idx, slot in enumerate(gc.SLOT_ORDER):
        slot_names = {c.name for c in candidates.get(slot, [])}
        for name in list(remaining):
            if name in slot_names and config[slot_idx] is None:
                cand = next(c for c in candidates[slot] if c.name == name)
                config[slot_idx] = cand.as_entry()
                remaining.remove(name)
                break

    if any(c is None for c in config) or remaining:
        return None
    return config


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

    results.sort(key=lambda pr: pr[1]["combined"], reverse=True)
    top = results[:3]  # resolve the top few at high iteration - screening alone
    # already picked the wrong trinket pair once (Bloodlust Brooch over
    # Madness of the Betrayer), see NOTES.md.

    def resolve_pair(pair_res):
        pair, _ = pair_res
        a, b = pair
        trial = list(config)
        trial[t1_idx] = a.as_entry()
        trial[t2_idx] = b.as_entry()
        return pair, resolve(settings_path, trial)

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        resolved = list(ex.map(resolve_pair, top))

    best_pair, best_result = max(resolved, key=lambda pr: pr[1]["combined"])

    config[t1_idx] = best_pair[0].as_entry()
    config[t2_idx] = best_pair[1].as_entry()
    log.append({
        "slot": "trinket1+trinket2", "picked": f"{best_pair[0].name} + {best_pair[1].name}",
        f"combined_resolved_@{RESOLVE_ITERATIONS}": best_result["combined"],
        "top_3_screened": [f"{p[0].name}+{p[1].name}={r['combined']:.1f}" for p, r in top],
    })
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


def full_bundle_branch(settings_path: str, greedy_config: list[dict], candidates: dict[str, list[Candidate]],
                        bundle_name: str, name_list: list[str], owned_items: list[dict], log: list) -> list[dict]:
    """Forced branch, corrected version of set_bonus_branch: tests an ENTIRE
    named bundle (e.g. a reference guide's full recommended set) against the
    greedy result, not just one set's armor pieces with everything else left
    at whatever greedy already picked. See NOTES.md - this is exactly the
    gap that produced a wrong conclusion the first time around."""
    bundle_config = resolve_name_to_config(name_list, candidates, owned_items)
    if bundle_config is None:
        log.append({"full_bundle_branch": bundle_name, "result": "could not resolve every item to a slot - skipped"})
        return greedy_config

    bundle_screen = eval_config(settings_path, bundle_config)
    greedy_screen = eval_config(settings_path, greedy_config)
    log.append({
        "full_bundle_branch": bundle_name, "phase": "screening",
        "bundle_combined": bundle_screen["combined"], "greedy_combined": greedy_screen["combined"],
    })

    # Close at screening, or the bundle already looks better - either way,
    # don't trust screening alone; resolve both at high iterations.
    bundle_resolved = resolve(settings_path, bundle_config)
    greedy_resolved = resolve(settings_path, greedy_config)
    winner = bundle_config if bundle_resolved["combined"] > greedy_resolved["combined"] else greedy_config
    log.append({
        "full_bundle_branch": bundle_name, "phase": f"resolved @ {RESOLVE_ITERATIONS} iter",
        "bundle_combined": bundle_resolved["combined"], "greedy_combined": greedy_resolved["combined"],
        "bundle_wins": bundle_resolved["combined"] > greedy_resolved["combined"],
    })
    return winner


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
