"""Builds the DATA blob embedded in the phase3_ledger.html artifact.

data/cache/tiered_report.json (run_upgrade_sweep.py's output) shapes "tiers"
as a dict-of-dicts - {tier_name: {slot_name: [item_row, ...]}} - convenient
for the text report's nested loop, but not what the artifact's JS expects:
a list of {name, slots: [{slot, items, more}]}, matching how it's actually
rendered (iterate tiers in order, iterate slots in order, show top 5 +
"N more"). "achieved_bis"/"two_hand"/"two_hand_meta" already match the JS's
expected shape as-is and pass through unchanged - "two_hand" in particular
is a flat top-N list across all tiers/zones (not grouped per tier, per the
user - a tier-grouped 2H list was mostly clutter from every zone's own weak
options), each row still carrying its own "tier" field for display context.

Run this after any run_upgrade_sweep.py sweep, before re-splicing the
artifact HTML - skipping it (or hand-rolling the transform inline again) is
exactly what broke the published ledger on 2026-08-23: the raw dict-of-dicts
got embedded directly, the JS threw partway through rendering "tiers", and
everything past "Achieved BiS" silently went blank.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import time_horizon  # noqa: E402
import stat_weights  # noqa: E402
import run_upgrade_sweep as sweep  # noqa: E402 - source of truth for the real iteration counts (see report_template.html's footer)
import ledger_diff  # noqa: E402

import repo_root  # noqa: E402
USER_DATA_DIR = repo_root.USER_DATA_DIR
TOP_N_SHOWN = 5


def build(name_realm: str, phase: str, profile_dir: str):
    """profile_dir is REQUIRED, no default - used to be "defaults to Hunter
    when omitted", the same footgun pattern found and removed from
    run_upgrade_sweep.main() 2026-08-25 (see core/character_profiles.py's
    docstring for the real bug that pattern caused there). This function's
    own blast radius was smaller (it reads an already-computed
    tiered_report - a wrong profile_dir here would misattribute metadata
    like raid_ap_contribution's enabled flag, not the DPS numbers
    themselves), but the same "resolve it via character_profiles.py, never
    guess" rule applies regardless of severity."""
    # Backlog #13 - same real, required filename component as
    # run_upgrade_sweep.py's own out_path (see core/report_storage.py's
    # docstring for the full bug this fixes).
    profile_dir_name = os.path.basename(os.path.normpath(profile_dir))
    report_path = os.path.join(USER_DATA_DIR, "characters", name_realm, "cache",
                                f"tiered_report_{profile_dir_name}_{phase}.json")
    report = repo_root.load_json(report_path)
    current_phase_num = int(phase.removeprefix("phase"))
    profile = repo_root.load_json(os.path.join(profile_dir, "profile.json"))
    raid_ap_enabled = profile["raid_ap_contribution"]["enabled"]
    weights = stat_weights.load(profile_dir)
    arp_relevant = weights.get(sweep.ARMOR_PEN_STAT_ID, 0) > 0

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

    sim_commit_sha = repo_root.sim_commit_sha()

    return {
        "baseline_dps": report["baseline_screened"],
        "sim_commit_sha": sim_commit_sha,
        "achieved_bis": report["achieved_bis"],
        "missing_enchants": report.get("missing_enchants", []),
        "missing_gems": report.get("missing_gems", []),
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
        # (see run_upgrade_sweep.py's raid_ap_contribution gate), so showing
        # a column of "n/a" for them is confusing clutter, not information.
        "raid_ap_enabled": raid_ap_enabled,
        # Real per-profile gate, same pattern as raid_ap_enabled above - the
        # Armor Penetration warning tag only means anything for a profile
        # that actually weights ArP (see run_upgrade_sweep.py's
        # item_arp_rating() comment for why it's flagged instead of trusted
        # via one-at-a-time MV alone).
        "arp_relevant": arp_relevant,
        # Real, disclosed fight-length assumption every number in this
        # report was simmed against (defaults to 180s - see
        # run_upgrade_sweep.main()'s own duration docstring) - per the user
        # (2026-08-25), which items rank best can genuinely depend on fight
        # length (their own real Teeth of Gruul finding), so this is never
        # silently omitted from the report.
        "fight_duration_seconds": report.get("fight_duration_seconds", 180),
        # Backlog #5 (CLAUDE.md Future Scope) - real, human-readable labels
        # for any loot sources this character excluded below the phase gate
        # (e.g. "Black Temple" for "raiding Hyjal but not into BT yet") -
        # empty for every character not using this setting. Self-documents
        # the report so it's never ambiguous later why an item is missing.
        "source_scope_excluded": report.get("source_scope_excluded", []),
        "screen_iterations": sweep.SCREEN_ITERATIONS,
        "confirm_iterations": sweep.CONFIRM_ITERATIONS,
        "resolve_iterations": sweep.RESOLVE_ITERATIONS,
        # Backlog #19 - real, actual raid/debuff/party/player buff
        # assumptions this exact sweep ran against, read straight from
        # run_upgrade_sweep.py's own settings file (see that function's own
        # comment) - passes through unchanged, never re-derived here.
        "assumed_buffs": report.get("assumed_buffs", {}),
        # Real, real-item consumables this exact sweep actually simmed with
        # (2026-09-06, "Used Consumables" report section) - same
        # never-hand-typed passthrough convention as assumed_buffs above.
        "used_consumables": report.get("used_consumables", {}),
        # Real OOM transparency (2026-09-06) - see run_upgrade_sweep.py's own
        # OOM_WARNING_THRESHOLD_FRACTION comment for the full motivation.
        "baseline_oom_seconds": report.get("baseline_oom_seconds", 0.0),
        "baseline_oom_fraction": report.get("baseline_oom_fraction", 0.0),
        # Backlog #20 - real "would dual-wield beat my current 2H" analysis,
        # only present when she's really 2H-equipped right now (None
        # otherwise - a genuinely dual-wielding character has no such
        # question to answer, the existing "two_hand"/"two_hand_meta"
        # fields already cover her real comparison direction).
        "dual_wield_alt": report.get("dual_wield_alt"),
    }


def persist(name_realm: str, phase: str, profile_dir_name: str, data: dict) -> str:
    """Writes ledger_data_<profile>_<phase>.json - real, permanent output
    from now on (2026-09-04), not just this file's own dev-tool artifact.
    Real gap this closes: the live GUI flow (gui/api.py's _run_report_job)
    used to build the ledger_data dict only to embed it in the rendered
    HTML, never persisting it standalone - so check_ledger_consistency.py's
    own real requirement that this file already exist on disk could only
    ever be satisfied by a one-off manual write, the exact "ad-hoc snippet,
    not checked in" anti-pattern this project has already flagged elsewhere
    (see CLAUDE.md's interaction_matrix.py note). Also the real prerequisite
    for ledger_diff.py's "what changed since last sweep" comparison.

    Plain overwrite, no history/rotation file needed: ledger_diff.compute()
    always runs BEFORE this (see build_with_diff()) while the file on disk
    still holds the PRIOR sweep - "whatever's there right before this
    write" already IS "last time's sweep" by construction, so there's
    nothing to snapshot separately.
    """
    out_dir = os.path.join(USER_DATA_DIR, "characters", name_realm, "cache")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"ledger_data_{profile_dir_name}_{phase}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return out_path


def build_with_diff(name_realm: str, phase: str, profile_dir: str) -> dict:
    """The one real call site both gui/api.py and this file's own __main__
    dev tool use - build() -> compute the real diff against last sweep (MUST
    happen before persist() below overwrites the file compute() reads as
    "previous") -> embed the diff -> persist (so the on-disk file and
    whatever gets rendered into HTML stay identical, matching
    check_ledger_consistency.py's own existing check_html() equality
    assertion) -> return the same dict."""
    profile_dir_name = os.path.basename(os.path.normpath(profile_dir))
    data = build(name_realm, phase, profile_dir)
    data["diff"] = ledger_diff.compute(name_realm, phase, profile_dir_name, data)
    persist(name_realm, phase, profile_dir_name, data)
    return data


if __name__ == "__main__":
    import argparse
    import character_profiles

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="Lerynia-Thunderstrike")
    parser.add_argument("--phase", default="phase3")
    parser.add_argument("--profile", default=None,
                         help="profile_dir_name (e.g. arms_warrior) - defaults to the character's "
                              "current assignment via character_profiles.SUPPORTED_CHARACTERS, same "
                              "rule check_ledger_consistency.py already uses.")
    args = parser.parse_args()

    if args.profile:
        profile_dir = os.path.join(repo_root.REPO_ROOT, "profiles", "tbc", args.profile)
    else:
        profile_dir = character_profiles.SUPPORTED_CHARACTERS[args.character]

    data = build_with_diff(args.character, args.phase, profile_dir)
    print(f"tiers: {[(t['name'], len(t['slots'])) for t in data['tiers']]}")
    if data["diff"] is None:
        print("diff: no previous sweep to compare against (expected on a first run)")
    else:
        d = data["diff"]
        print(f"diff: {len(d['new'])} new, {len(d['moved'])} moved outside noise, "
              f"{len(d['no_longer_shown'])} no longer shown")
