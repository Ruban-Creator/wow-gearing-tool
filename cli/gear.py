"""`gear sync` / `gear best` / `gear preset` / `gear character list` / `gear report register|list`."""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

# core/ is always this file's own sibling directory - see
# ingest/build_character.py's own comment on why this lookup (not REPO_ROOT
# itself) is what's safe to compute directly here.
_REPO_ROOT_GUESS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT_GUESS, "core"))
import repo_root  # noqa: E402

REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
sys.path.insert(0, os.path.join(REPO_ROOT, "ingest"))
sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))

import build_character  # noqa: E402
import list_characters  # noqa: E402
import adapter  # noqa: E402
import character_profiles  # noqa: E402
import report_storage  # noqa: E402


def character_dir(name_realm: str) -> str:
    path = os.path.join(USER_DATA_DIR, "characters", name_realm)
    os.makedirs(path, exist_ok=True)
    return path


def cmd_sync(args):
    data = build_character.build(args.character)
    out_path = os.path.join(USER_DATA_DIR, "character.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Additive: the legacy flat file above stays the one run_upgrade_sweep.py
    # actually reads (unchanged), this is the per-character copy the GUI/
    # multi-character CLI commands read instead - see CLAUDE.md's plan for
    # why the sim pipeline's own paths intentionally aren't touched here.
    per_char_path = os.path.join(character_dir(args.character), "character.json")
    with open(per_char_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Synced {args.character} -> {out_path}")
    print(f"  also wrote {per_char_path}")
    print(f"  equipped: {len(data['equipped']['items'])} items resolved (of 17 slots)")
    print(f"  bags: {len(data['owned']['bags'])} items, bank: {len(data['owned']['bank'])} items")
    print(f"  unresolved: {len(data['unresolved'])} items")
    if not data["equipped"]["items"]:
        print("  WARNING: equipped is empty - re-export in-game (/wse export) while geared.")


def cmd_best(args):
    """Real pipeline now (was a Stage-1 stub) - both blockers it was waiting
    on are long resolved: Stage 2's Expose Weakness raid-vs-personal
    question (now the "Debuff" column, per-attacker) and a real gear
    export. Thin wrapper - run_upgrade_sweep.main(name_realm, phase) reads
    USER_DATA_DIR/characters/<name_realm>/character.json and writes
    USER_DATA_DIR/characters/<name_realm>/cache/tiered_report_<phase>.json.

    profile_dir is resolved explicitly via character_profiles.py, never left
    to run_upgrade_sweep.main()'s own default - a real bug, found 2026-08-25:
    that default silently points at Survival Hunter's profile (its
    historical single-character value), so this command previously swept
    any non-Hunter character's real gear against Hunter's whole profile
    (candidate pool, enchants, stat weights, settings) without erroring.
    See core/character_profiles.py's own docstring for how this was caught."""
    phase = _normalize_phase(args.phase)
    import run_upgrade_sweep
    import character_profiles
    if args.character not in character_profiles.SUPPORTED_CHARACTERS:
        print(f"'{args.character}' has no known profile yet - supported: "
              f"{', '.join(character_profiles.SUPPORTED_CHARACTERS)}")
        return
    profile_dir = character_profiles.SUPPORTED_CHARACTERS[args.character]
    run_upgrade_sweep.main(args.character, phase, profile_dir=profile_dir, duration=args.duration)


def cmd_character_list(args):
    chars = list_characters.list_all_characters()
    if not chars:
        print("No characters found in any WowSimsExporter or GearingToolCompanion SavedVariables.")
        return
    for c in chars:
        # Names can carry real non-ASCII characters (accents etc, confirmed
        # live on this machine) - this terminal's stdout is not reliably
        # UTF-8 (see the memory note on Windows console encoding), so encode
        # defensively rather than let a print crash the whole listing.
        label = c["name_realm"].encode(sys.stdout.encoding or "ascii", errors="replace").decode(sys.stdout.encoding or "ascii")
        id_ = c["identity"]
        class_race = f"{id_.get('race', '?')} {id_.get('class', '?')}" if id_ else "(no identity captured yet)"
        print(f"{label:30s} source={c['source_used']:11s} {class_race}")
        print(f"    wse_timestamp={c['wse_timestamp']}  gt_timestamp={c['gt_timestamp']}")


def _normalize_phase(raw: str) -> str:
    if re.fullmatch(r"\d+", raw):
        return f"phase{raw}"
    if re.fullmatch(r"(?i)phase\d+", raw):
        return raw.lower()
    raise SystemExit(f"Unrecognized phase {raw!r} - expected e.g. '3' or 'phase3'.")


def _resolve_profile_dir_name(character: str, explicit: str | None) -> str:
    """Backlog #13 - reports.json is now nested under profile_dir_name (see
    report_storage.py's own docstring for the real bug this fixes: a
    character reassigned to a different sim profile used to silently
    overwrite her prior spec's report). --profile lets a caller register/
    list a report for a profile OTHER than the character's current
    assignment (e.g. registering a Fury report while she's currently
    assigned Arms); defaults to her current assignment, same "resolve via
    character_profiles.py, never guess" rule as cmd_best."""
    if explicit:
        return explicit
    profile_dir = character_profiles.SUPPORTED_CHARACTERS.get(character)
    if profile_dir is None:
        raise SystemExit(f"'{character}' has no known profile yet - pass --profile explicitly, "
                          f"or assign one first (supported: {', '.join(character_profiles.SUPPORTED_CHARACTERS)})")
    return os.path.basename(os.path.normpath(profile_dir))


def cmd_report_register(args):
    phase = _normalize_phase(args.phase)
    profile_dir_name = _resolve_profile_dir_name(args.character, args.profile)
    reports = report_storage.load_reports(args.character)
    profile_reports = reports.setdefault(profile_dir_name, {})

    old = profile_reports.get(phase)
    entry = {
        "artifact_url": args.url,
        "generated_at": args.generated_at or datetime.now(timezone.utc).isoformat(),
    }
    if args.notes:
        entry["notes"] = args.notes
    profile_reports[phase] = entry

    report_storage.save_reports(args.character, reports)

    if old:
        print(f"Replaced {args.character}/{profile_dir_name}/{phase}'s report URL:")
        print(f"  old: {old['artifact_url']}")
        print(f"  new: {entry['artifact_url']}")
    else:
        print(f"Registered {args.character}/{profile_dir_name}/{phase} -> {entry['artifact_url']}")


def cmd_report_list(args):
    profile_dir_name = _resolve_profile_dir_name(args.character, args.profile)
    reports = report_storage.load_reports(args.character)
    profile_reports = reports.get(profile_dir_name, {})
    if not profile_reports:
        print(f"No reports registered yet for {args.character}/{profile_dir_name}.")
        return
    for phase in sorted(profile_reports):
        r = profile_reports[phase]
        print(f"{phase}: {r['artifact_url']}  (generated {r['generated_at']})")
        if r.get("notes"):
            print(f"    notes: {r['notes']}")


def cmd_preset(args):
    v = adapter.version()
    result = adapter.run(args.build_json, iterations=args.iterations, seed=args.seed)
    dps = adapter.player_and_pet_dps(result)
    total_pet = sum(p["avg"] for p in dps["pets"])
    print(f"sim commit: {v['commit_sha']}")
    print(f"iterations={args.iterations} seed={args.seed}")
    print(f"player DPS: {dps['player']['avg']:.1f} (stdev {dps['player']['stdev']:.2f})")
    for p in dps["pets"]:
        print(f"pet {p['name']} DPS: {p['avg']:.1f} (stdev {p['stdev']:.2f})")
    print(f"combined (player+pets): {dps['player']['avg'] + total_pet:.1f}")


def main():
    parser = argparse.ArgumentParser(prog="gear")
    sub = parser.add_subparsers(required=True)

    p_sync = sub.add_parser("sync", help="re-read addon export, write USER_DATA_DIR/character.json")
    p_sync.add_argument("character", nargs="?", default="Lerynia-Thunderstrike")
    p_sync.set_defaults(func=cmd_sync)

    p_best = sub.add_parser("best", help="full MV sweep against the owned pool - writes USER_DATA_DIR/characters/<character>/cache/tiered_report_<phase>.json")
    p_best.add_argument("character", nargs="?", default="Lerynia-Thunderstrike")
    p_best.add_argument("phase", nargs="?", default="phase3")
    p_best.add_argument("--duration", type=int, default=None,
                         help="fight length override in seconds (default: profile's own settings_template.json value, currently 180s)")
    p_best.set_defaults(func=cmd_best)

    p_preset = sub.add_parser("preset", help="run a shipped .build.json preset through the sim")
    p_preset.add_argument("build_json")
    p_preset.add_argument("--iterations", type=int, default=10000)
    p_preset.add_argument("--seed", type=int, default=1)
    p_preset.set_defaults(func=cmd_preset)

    p_character = sub.add_parser("character", help="multi-character listing")
    character_sub = p_character.add_subparsers(required=True)
    p_character_list = character_sub.add_parser("list", help="list every character found across WSE + GearingToolCompanion")
    p_character_list.set_defaults(func=cmd_character_list)

    p_report = sub.add_parser("report", help="track published report/artifact links per character+phase")
    report_sub = p_report.add_subparsers(required=True)
    p_report_register = report_sub.add_parser("register", help="record a published report URL for a character+phase")
    p_report_register.add_argument("character")
    p_report_register.add_argument("phase")
    p_report_register.add_argument("url")
    p_report_register.add_argument("--notes")
    p_report_register.add_argument("--generated-at")
    p_report_register.add_argument("--profile", default=None,
                                    help="profile_dir_name (e.g. fury_warrior) - defaults to the "
                                         "character's current assignment")
    p_report_register.set_defaults(func=cmd_report_register)
    p_report_list = report_sub.add_parser("list", help="list registered report URLs for a character")
    p_report_list.add_argument("character")
    p_report_list.add_argument("--profile", default=None,
                                help="profile_dir_name (e.g. fury_warrior) - defaults to the "
                                     "character's current assignment")
    p_report_list.set_defaults(func=cmd_report_list)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
