"""One-time builder: reference_bis/phaseN.json + candidate_pool.json from
wowsims' own shipped preset gear sets, preferred over hand-curating from
Wowhead per the user's explicit decision (2026-08-25) - a real, sim-team-
authored source is faster and less error-prone to consume than expected
(plain JSON item-id arrays, not TypeScript builder calls), Wowhead curation
is the fallback only for a slot a wowsims preset leaves genuinely
unresolved (not the 2H-topology empty-offhand case, which is real and
correct, not a gap).

Usage: python core/build_wowsims_reference_bis.py <profile_dir> <gear_sets_dir> <spec_label> <phase>:<file.gear.json> [...]
Example:
  python core/build_wowsims_reference_bis.py profiles/tbc/arms_warrior \
      sim/tbc-new/ui/warrior/dps/gear_sets "Arms" phase2:p2_arms.gear.json phase3:p3_arms.gear.json \
      phase4:p4_arms.gear.json phase5:p5_arms.gear.json
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import item_db as idb  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SLOT_ORDER = ["head", "neck", "shoulder", "back", "chest", "wrist", "hands", "waist",
              "legs", "feet", "ring1", "ring2", "trinket1", "trinket2",
              "mainhand", "offhand", "ranged"]

# Real HandType enum values (proto/common.proto) - Stage 6.2 finding: a
# fixed "mainhand always means weapon_2h" mapping (Stage 6.1's original
# version) is WRONG for a profile whose real BiS weapon choice varies by
# phase between a 2H weapon and a 1H+offhand combo (Balance Druid: staff in
# some phases, dagger+offhand item in others, confirmed from the real gear
# set data itself) - the pool key has to be derived per-item from its real
# handType, not assumed fixed per slot.
HAND_TYPE_TWO_HAND = 4
HAND_TYPE_OFF_HAND = 3

# Pool-key mapping for non-weapon slots mirrors optimizer.py's real
# POOL_KEY_TO_SLOTS - "ring"/"trinket" share one pool each (either real
# slot), everything else is 1:1. mainhand/offhand are handled separately
# below (real per-item handType, not a fixed slot->key mapping).
POOL_KEY_FOR_SLOT = {
    "head": "head", "neck": "neck", "shoulder": "shoulder", "back": "back", "chest": "chest",
    "wrist": "wrist", "hands": "hands", "waist": "waist", "legs": "legs", "feet": "feet",
    "ring1": "ring", "ring2": "ring", "trinket1": "trinket", "trinket2": "trinket",
    "ranged": "ranged",
}


def _weapon_pool_key(slot: str, hand_type: int | None) -> str | None:
    """mainhand/offhand only - real per-item routing, not a fixed mapping.
    A 2H item in mainhand goes to the "weapon_2h" side-pool (matches
    run_full_sweep_mv.py's own slot_for_item() routing for any topology
    that isn't strictly "two_hand"); a real 1H mainhand or a real distinct
    offhand item (HandTypeOffHand - never itself a weapon a caster would
    dual-wield) goes to its own single-item pool key. offhand for a 2H
    phase never reaches here (the raw gear-set slot is genuinely empty)."""
    if slot == "mainhand":
        return "weapon_2h" if hand_type == HAND_TYPE_TWO_HAND else "mainhand"
    if slot == "offhand":
        return "offhand"
    return None


def resolve_gear_set(path: str) -> dict[str, dict]:
    """slot -> {"item": name, "id": int, "hand_type": int|None} for each
    real (non-empty) slot."""
    data = json.load(open(path, encoding="utf-8"))
    result = {}
    for slot, it in zip(SLOT_ORDER, data["items"]):
        if not it or "id" not in it:
            continue
        item = idb.by_id(it["id"])
        if item is None:
            print(f"WARNING: {path} slot {slot} id={it['id']} not found in item DB - skipped, "
                  f"needs a real Wowhead fallback entry for this slot/phase.")
            continue
        result[slot] = {"item": item["name"], "id": it["id"], "hand_type": item.get("handType")}
    return result


def _pool_key_for(slot: str, entry: dict) -> str | None:
    if slot in ("mainhand", "offhand"):
        return _weapon_pool_key(slot, entry["hand_type"])
    return POOL_KEY_FOR_SLOT.get(slot)


def build(profile_dir: str, gear_sets_dir: str, spec_label: str, phase_files: dict[str, str]) -> None:
    ref_dir = os.path.join(profile_dir, "reference_bis")
    os.makedirs(ref_dir, exist_ok=True)

    # phase -> slot -> {"item", "id", "hand_type"}, kept around to build candidate_pool.json's union afterward.
    per_phase = {}
    for phase, filename in phase_files.items():
        resolved = resolve_gear_set(os.path.join(gear_sets_dir, filename))
        per_phase[phase] = resolved

        slots_out = {}
        for slot, entry in resolved.items():
            pool_key = _pool_key_for(slot, entry)
            if pool_key is None:
                continue
            slots_out.setdefault(pool_key, []).append({
                "item": entry["item"],
                "rank": "Best",
                "source": f"wowsims {phase.replace('phase', 'Phase ')} {spec_label} preset",
            })
        out_path = os.path.join(ref_dir, f"{phase}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"slots": slots_out}, f, indent=2)
        print(f"Wrote {out_path} ({sum(len(v) for v in slots_out.values())} entries)")

    # candidate_pool.json: union across phases, tracking seen_in per the
    # existing schema (Hunter's own file) - every wowsims-sourced entry is
    # uniformly "Best" (one recommended pick per slot per phase, no
    # Wowhead-style rank spread to track), so best_rank_seen is always "Best".
    pool: dict[str, dict[str, dict]] = {}  # pool_key -> item_name -> {"source", "seen_in": [...]}
    for phase, resolved in per_phase.items():
        for slot, entry in resolved.items():
            pool_key = _pool_key_for(slot, entry)
            if pool_key is None:
                continue
            bucket = pool.setdefault(pool_key, {})
            rec = bucket.setdefault(entry["item"], {
                "source": f"wowsims {phase.replace('phase', 'Phase ')} {spec_label} preset",
                "seen_in": [],
            })
            rec["seen_in"].append({"phase": phase.replace("phase", "P"), "rank": "Best"})

    pool_out = {}
    for pool_key, items in pool.items():
        pool_out[pool_key] = [
            {"item": name, "source": rec["source"], "seen_in": rec["seen_in"], "best_rank_seen": "Best"}
            for name, rec in items.items()
        ]
    pool_path = os.path.join(profile_dir, "candidate_pool.json")
    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool_out, f, indent=2)
    total = sum(len(v) for v in pool_out.values())
    print(f"Wrote {pool_path} ({total} unique candidates across {len(pool_out)} pool keys)")


if __name__ == "__main__":
    profile_dir, gear_sets_dir, spec_label = sys.argv[1], sys.argv[2], sys.argv[3]
    phase_files = {}
    for arg in sys.argv[4:]:
        phase, filename = arg.split(":", 1)
        phase_files[phase] = filename
    build(profile_dir, gear_sets_dir, spec_label, phase_files)
