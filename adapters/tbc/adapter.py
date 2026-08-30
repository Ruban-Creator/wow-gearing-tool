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
import sys
import uuid

# core/ is always this file's own great-grandparent's child (adapters/tbc/
# -> repo root -> core/) - true whether running from source or from inside
# a frozen PyInstaller build's extraction dir. Delegated to repo_root.py
# rather than computed naively here so this module shares the same single
# REPO_ROOT/USER_DATA_DIR resolution as everything else - see that module's
# own docstring for why a naive __file__-based guess is real risk.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core"))
import repo_root  # noqa: E402

REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
SIM_DIR = os.path.join(REPO_ROOT, "sim", "tbc-new")
# Build Output (the 5th bucket, 2026-08-29 folder-structure rework) - these
# two are compiled from the Go sources under adapters/tbc/bridge/ and
# sim/tbc-new/ respectively, but the compiled binaries themselves live in
# one predictable place (build/bin/) rather than nested inside either
# source tree, so an installer/build script never has to hunt for them.
BRIDGE_EXE = os.path.join(REPO_ROOT, "build", "bin", "bridge.exe")
WOWSIMCLI_EXE = os.path.join(REPO_ROOT, "build", "bin", "wowsimcli.exe")
CACHE_DIR = os.path.join(USER_DATA_DIR, "cache")

# See valuation.py's own copy of this comment - the packaged (windowed,
# console-less) GUI has nowhere to attach a child console, so Windows pops
# a new visible one for every subprocess call here unless told not to.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def version() -> dict:
    return {"repo": "wowsims/tbc-new", "commit_sha": repo_root.sim_commit_sha()}


def run(individual_sim_settings_path: str, iterations: int, seed: int) -> dict:
    """Runs one IndividualSimSettings-shaped JSON file (protojson - e.g. one of
    the repo's own .build.json presets) through bridge.exe + wowsimcli.exe.
    Returns the parsed RaidSimResult dict. Raises RuntimeError with the sim's
    own error message on failure (never swallows it). Uses a unique-per-call
    temp filename pair so concurrent calls (the optimizer runs many in
    parallel threads) never collide on the same file - a fixed shared
    filename here caused real race-condition failures under threading."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    token = uuid.uuid4().hex[:12]
    req_path = os.path.join(CACHE_DIR, f"_req_{token}.json")
    result_path = os.path.join(CACHE_DIR, f"_res_{token}.json")

    try:
        subprocess.run(
            [BRIDGE_EXE, "-in", individual_sim_settings_path, "-out", req_path,
             "-iterations", str(iterations), "-seed", str(seed)],
            check=True, creationflags=_NO_WINDOW,
        )
        subprocess.run(
            [WOWSIMCLI_EXE, "sim", "--infile", req_path, "--outfile", result_path],
            check=True, cwd=SIM_DIR, creationflags=_NO_WINDOW,
        )

        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
    finally:
        for p in (req_path, result_path):
            try:
                os.remove(p)
            except OSError:
                pass

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
