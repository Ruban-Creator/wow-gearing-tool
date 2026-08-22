"""`gear sync` / `gear best` - see CLAUDE.md and NOTES.md for why `best` is a
stub right now: it needs (a) a fresh in-game export (current one has an empty
gear array) and (b) Stage 2's Survival-mechanics blocker resolved before it's
allowed to talk about my own gear's DPS at all, per the ground rules.
"""
import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "ingest"))
sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))

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
    print("`gear best` is deferred: Stage 2 (Survival mechanics / Expose Weakness raid-vs-")
    print("personal question) has to be resolved before this tool emits any DPS number tied")
    print("to your own gear - see CLAUDE.md ground rules. Use `gear sync` for now, and")
    print("`gear preset <build.json>` to sanity-check the sim pipeline against the shipped")
    print("reference presets in the meantime.")


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

    p_best = sub.add_parser("best", help="deferred - see CLAUDE.md")
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
