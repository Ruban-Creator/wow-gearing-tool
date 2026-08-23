"""`gear sync` / `gear best` / `gear preset`."""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "ingest"))
sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))
sys.path.insert(0, os.path.join(REPO_ROOT, "core"))

import build_character  # noqa: E402
import adapter  # noqa: E402


def cmd_sync(args):
    data = build_character.build(args.character)
    out_path = os.path.join(REPO_ROOT, "data", "character.json")
    import json
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    print(f"Synced {args.character} -> {out_path}")
    print(f"  equipped: {len(data['equipped']['items'])} items resolved (of 17 slots)")
    print(f"  bags: {len(data['owned']['bags'])} items, bank: {len(data['owned']['bank'])} items")
    print(f"  unresolved: {len(data['unresolved'])} items")
    if not data["equipped"]["items"]:
        print("  WARNING: equipped is empty - re-export in-game (/wse export) while geared.")


def cmd_best(args):
    """Real pipeline now (was a Stage-1 stub) - both blockers it was waiting
    on are long resolved: Stage 2's Expose Weakness raid-vs-personal
    question (now the "Debuff" column, per-attacker) and a real gear
    export. Thin wrapper - run_full_sweep_mv.main() takes no arguments,
    it reads data/character.json and the candidate pool from their fixed
    repo-relative paths and writes data/cache/tiered_report.json."""
    import run_full_sweep_mv
    run_full_sweep_mv.main()


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

    p_sync = sub.add_parser("sync", help="re-read addon export, write data/character.json")
    p_sync.add_argument("character", nargs="?", default="Lerynia-Thunderstrike")
    p_sync.set_defaults(func=cmd_sync)

    p_best = sub.add_parser("best", help="full MV sweep against the owned pool - writes data/cache/tiered_report.json")
    p_best.set_defaults(func=cmd_best)

    p_preset = sub.add_parser("preset", help="run a shipped .build.json preset through the sim")
    p_preset.add_argument("build_json")
    p_preset.add_argument("--iterations", type=int, default=10000)
    p_preset.add_argument("--seed", type=int, default=1)
    p_preset.set_defaults(func=cmd_preset)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
