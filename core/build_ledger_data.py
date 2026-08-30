"""Builds the DATA blob embedded in the phase3_ledger.html artifact.

data/cache/tiered_report.json (run_full_sweep_mv.py's output) shapes "tiers"
as a dict-of-dicts - {tier_name: {slot_name: [item_row, ...]}} - convenient
for the text report's nested loop, but not what the artifact's JS expects:
a list of {name, slots: [{slot, items, more}]}, matching how it's actually
rendered (iterate tiers in order, iterate slots in order, show top 5 +
"N more"). "achieved_bis"/"two_hand"/"two_hand_meta" already match the JS's
expected shape as-is and pass through unchanged - "two_hand" in particular
is a flat top-N list across all tiers/zones (not grouped per tier, per the
user - a tier-grouped 2H list was mostly clutter from every zone's own weak
options), each row still carrying its own "tier" field for display context.

Run this after any run_full_sweep_mv.py sweep, before re-splicing the
artifact HTML - skipping it (or hand-rolling the transform inline again) is
exactly what broke the published ledger on 2026-08-23: the raw dict-of-dicts
got embedded directly, the JS threw partway through rendering "tiers", and
everything past "Achieved BiS" silently went blank.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time_horizon  # noqa: E402
import stat_weights  # noqa: E402
import run_full_sweep_mv as sweep_mv  # noqa: E402 - source of truth for the real iteration counts (see report_template.html's footer)

# See adapters/tbc/valuation.py's own copy of this comment - the packaged
# (windowed, console-less) GUI has nowhere to attach a child console, so
# Windows pops a new visible one for this git call unless told not to.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
TOP_N_SHOWN = 5


def build(name_realm: str, phase: str, profile_dir: str):
    """profile_dir is REQUIRED, no default - used to be "defaults to Hunter
    when omitted", the same footgun pattern found and removed from
    run_full_sweep_mv.main() 2026-08-25 (see core/character_profiles.py's
    docstring for the real bug that pattern caused there). This function's
    own blast radius was smaller (it reads an already-computed
    tiered_report - a wrong profile_dir here would misattribute metadata
    like raid_ap_contribution's enabled flag, not the DPS numbers
    themselves), but the same "resolve it via character_profiles.py, never
    guess" rule applies regardless of severity."""
    report_path = os.path.join(USER_DATA_DIR, "characters", name_realm, "cache", f"tiered_report_{phase}.json")
    report = json.load(open(report_path, encoding="utf-8"))
    current_phase_num = int(phase.removeprefix("phase"))
    profile = json.load(open(os.path.join(profile_dir, "profile.json"), encoding="utf-8"))
    raid_ap_enabled = profile["raid_ap_contribution"]["enabled"]
    weights = stat_weights.load(profile_dir)
    arp_relevant = weights.get(sweep_mv.ARMOR_PEN_STAT_ID, 0) > 0

    tiers_list = []
    for tier_name, slot_dict in report["tiers"].items():
        if not slot_dict:
            continue
        slots_list = []
        for slot_name, upgrades in slot_dict.items():
            slots_list.append({
                "slot": slot_name,
                "items": upgrades[:TOP_N_SHOWN],
                "more": max(0, len(upgrades) - TOP_N_SHOWN),
            })
        tiers_list.append({"name": tier_name, "slots": slots_list})

    sim_commit_sha = subprocess.run(
        ["git", "-C", os.path.join(REPO_ROOT, "sim", "tbc-new"), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, creationflags=_NO_WINDOW).stdout.strip()

    return {
        "baseline_dps": report["baseline_screened"],
        "sim_commit_sha": sim_commit_sha,
        "achieved_bis": report["achieved_bis"],
        "missing_enchants": report.get("missing_enchants", []),
        "tiers": tiers_list,
        "two_hand": report["two_hand"],
        "two_hand_meta": report["two_hand_meta"],
        "interactions": report.get("interactions", []),
        # Drives the template's own phase/iteration-count text (Achieved BiS
        # subtitle, footer) so neither has to hardcode a phase number or an
        # iteration constant that could silently drift from the real ones -
        # see NOTES.md/CLAUDE.md on why a stale phase number in rendered text
        # is a real correctness bug, not cosmetic.
        "current_phase": current_phase_num,
        "final_phase_num": time_horizon.FINAL_PHASE,
        # Real per-profile gate (Stage 2's Expose Weakness model, Survival
        # Hunter-only) - the "Debuff (AP/ea)" column/legend only means
        # anything for a profile that actually has this mechanic; every
        # other class's raid_ap_per_attacker is always null by construction
        # (see run_full_sweep_mv.py's raid_ap_contribution gate), so showing
        # a column of "n/a" for them is confusing clutter, not information.
        "raid_ap_enabled": raid_ap_enabled,
        # Real per-profile gate, same pattern as raid_ap_enabled above - the
        # Armor Penetration warning tag only means anything for a profile
        # that actually weights ArP (see run_full_sweep_mv.py's
        # item_arp_rating() comment for why it's flagged instead of trusted
        # via one-at-a-time MV alone).
        "arp_relevant": arp_relevant,
        # Real, disclosed fight-length assumption every number in this
        # report was simmed against (defaults to 180s - see
        # run_full_sweep_mv.main()'s own duration docstring) - per the user
        # (2026-08-25), which items rank best can genuinely depend on fight
        # length (their own real Teeth of Gruul finding), so this is never
        # silently omitted from the report.
        "fight_duration_seconds": report.get("fight_duration_seconds", 180),
        "screen_iterations": sweep_mv.SCREEN_ITERATIONS,
        "confirm_iterations": sweep_mv.CONFIRM_ITERATIONS,
        "resolve_iterations": sweep_mv.RESOLVE_ITERATIONS,
    }


if __name__ == "__main__":
    name_realm, phase = "Lerynia-Thunderstrike", "phase3"
    data = build(name_realm, phase)
    out_dir = os.path.join(USER_DATA_DIR, "characters", name_realm, "cache")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"ledger_data_{phase}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"Wrote {out_path}")
    print(f"tiers: {[(t['name'], len(t['slots'])) for t in data['tiers']]}")
