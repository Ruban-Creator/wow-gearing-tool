"""SimAdapter for wowsims/tbc-new. Subprocess wrapper only - dict in, dict out.
No proto types cross this module's public functions (see CLAUDE.md's adapter
boundary rule). Internally: bridge.exe expands an IndividualSimSettings-shaped
JSON into a RaidSimRequest (see NOTES.md, "Resolved: the CLI's actual input
contract"), then wowsimcli.exe runs it.
"""
from __future__ import annotations

import json
import os
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SIM_DIR = os.path.join(REPO_ROOT, "sim", "tbc-new")
BRIDGE_EXE = os.path.join(REPO_ROOT, "adapters", "tbc", "bridge", "bridge.exe")
WOWSIMCLI_EXE = os.path.join(SIM_DIR, "wowsimcli.exe")
CACHE_DIR = os.path.join(REPO_ROOT, "data", "cache")


def version() -> dict:
    out = subprocess.run(
        ["git", "-C", SIM_DIR, "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    )
    return {"repo": "wowsims/tbc-new", "commit_sha": out.stdout.strip()}


def run(individual_sim_settings_path: str, iterations: int, seed: int) -> dict:
    """Runs one IndividualSimSettings-shaped JSON file (protojson - e.g. one of
    the repo's own .build.json presets) through bridge.exe + wowsimcli.exe.
    Returns the parsed RaidSimResult dict. Raises RuntimeError with the sim's
    own error message on failure (never swallows it)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    req_path = os.path.join(CACHE_DIR, "_last_request.json")
    result_path = os.path.join(CACHE_DIR, "_last_result.json")

    subprocess.run(
        [BRIDGE_EXE, "-in", individual_sim_settings_path, "-out", req_path,
         "-iterations", str(iterations), "-seed", str(seed)],
        check=True,
    )
    subprocess.run(
        [WOWSIMCLI_EXE, "sim", "--infile", req_path, "--outfile", result_path],
        check=True, cwd=SIM_DIR,
    )

    with open(result_path, encoding="utf-8") as f:
        result = json.load(f)

    if result.get("error"):
        raise RuntimeError(f"sim error: {result['error'].get('message', '')[:2000]}")

    return result


def player_and_pet_dps(result: dict) -> dict:
    """Extracts the player's own dps and each pet's dps separately. The sim's
    raid/party-level 'dps' rollup mirrors the player's dps field exactly and
    does NOT include pet damage - confirmed empirically (see NOTES.md, "pet
    vs player damage split"). Callers that want total combined DPS must sum
    player + pets themselves; this function does not do that summing so the
    two stay visibly separate per the noise-honesty ground rule."""
    player = result["raidMetrics"]["parties"][0]["players"][0]
    pets = [
        {"name": p.get("name"), "avg": p["dps"]["avg"], "stdev": p["dps"].get("stdev", 0)}
        for p in player.get("pets", [])
    ]
    return {
        "player": {"avg": player["dps"]["avg"], "stdev": player["dps"].get("stdev", 0)},
        "pets": pets,
    }
