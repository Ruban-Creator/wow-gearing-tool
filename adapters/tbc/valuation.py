"""Evaluate one 17-item gear config against a fixed settings background
(buffs/debuffs/consumables/encounter/talents/rotation held constant - gear
is the only variable, per the determinism ground rule). Thin over
adapter.run() (or, when USE_SIMSERVER, the persistent simserver.exe pool -
see NOTES.md, "speed up the full sweep further": wowsimcli reloads and
unmarshals the whole embedded item DB fresh on every invocation, which
dominates wall-clock time on short screening-iteration calls; simserver
loads it once and stays alive). Adds the sim cache and a stable settings
fingerprint so the cache key doesn't depend on file paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter  # noqa: E402
import simserver_client  # noqa: E402
import expose_weakness  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core"))
import sim_cache  # noqa: E402
import gear_config  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "data", "cache")

USE_SIMSERVER = False
# Was True - reverted (overnight, autonomous) after finding simserver.exe
# crashes ("process died?" RuntimeError) partway through a genuinely cold
# (no cache hits) run of ~500 sequential requests. Confirmed NOT tied to a
# specific bad item/candidate (isolated the exact failing item and it ran
# fine standalone) and NOT a concurrency bug (reproduced serially, pool
# size 1). Every previous "successful" run tonight had a warm sim_cache,
# so most evaluate() calls never actually reached simserver.exe at all -
# this is the first time it's been asked to handle sustained real load,
# and it doesn't survive it. See NOTES.md for full details. Falling back
# to the file-based adapter.run() path (fresh wowsimcli.exe per call, zero
# accumulated state) since it's the one proven reliable across this whole
# session, at the cost of losing tonight's speedup until this is properly
# root-caused - correctness and not silently truncating results matters
# more than speed here.
# The Ryzen 5 5600X this runs on is 6C/12T, and wowsimcli/simserver already
# use ALL logical threads internally per sim call ("Running N iterations on
# 12 concurrent sims" - runtime.NumCPU()). A pool size of 4 means up to
# 4x12=48-way parallelism fighting over 12 threads - measured 747ms/call
# oversubscribed vs 101ms/call at pool_size=2 with MAX_WORKERS=2 to match
# (7.4x). Keep this <= MAX_WORKERS in run_full_sweep_mv.py; there's no
# reason to hold idle simserver processes a caller can't reach. (Still
# relevant if/when simserver gets re-enabled after the crash is fixed.)
SIMSERVER_POOL_SIZE = 2

_settings_lock = threading.Lock()
_template_cache = {}


def _normalize(settings: dict) -> dict:
    """Forces the pet to Owl regardless of what's in the source file.
    Wowsims.com test exports have shown Owl/Ravager/Bat across different
    sessions - none of that was a deliberate choice, just whatever the UI
    happened to have loaded. Owl is the confirmed standing choice; every
    settings file that flows through this pipeline gets normalized to it
    so a stray future paste can't silently change the baseline again."""
    settings["player"]["hunter"]["options"]["classOptions"]["petType"] = "Owl"
    return settings


def _load_template(settings_path: str) -> dict:
    with _settings_lock:
        if settings_path not in _template_cache:
            with open(settings_path, encoding="utf-8") as f:
                _template_cache[settings_path] = _normalize(json.load(f))
        # Deep-copy via round-trip so callers can mutate freely.
        return json.loads(json.dumps(_template_cache[settings_path]))


def settings_fingerprint(settings_path: str) -> str:
    """Hash of everything in the template EXCEPT player.equipment.items -
    the fixed background gear runs must hold constant. Used as part of the
    cache key so two different backgrounds never collide."""
    template = _load_template(settings_path)
    template["player"]["equipment"] = None
    canonical = json.dumps(template, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def _build_raid_sim_request(settings: dict, iterations: int, seed: int) -> dict:
    """Runs the bridge (IndividualSimSettings -> RaidSimRequest expansion)
    on the given settings dict. Kept as a real subprocess call to bridge.exe
    - it's fast (no DB to load) and already proven correct; only the
    wowsimcli step benefits enough from persistence to be worth pooling."""
    token = uuid.uuid4().hex[:8]
    in_path = os.path.join(CACHE_DIR, f"_vb_in_{token}.json")
    out_path = os.path.join(CACHE_DIR, f"_vb_out_{token}.json")
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(in_path, "w", encoding="utf-8") as f:
        json.dump(settings, f)
    try:
        subprocess.run(
            [adapter.BRIDGE_EXE, "-in", in_path, "-out", out_path,
             "-iterations", str(iterations), "-seed", str(seed)],
            check=True,
        )
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


def evaluate(settings_path: str, items: list[dict], iterations: int, seed: int) -> dict:
    """Returns {"player_dps": ..., "player_stdev": ..., "pets": [...],
    "combined": ...}. Cached by (gear hash, settings fingerprint,
    iterations, seed) - never sims the same config twice."""
    gear_hash = gear_config.config_hash(items)
    fp = settings_fingerprint(settings_path)
    cache_key = sim_cache.key(gear_hash, fp, iterations, seed)

    cached = sim_cache.get(cache_key)
    if cached is not None:
        return cached

    settings = _load_template(settings_path)
    settings["player"]["equipment"] = {"items": items}

    if USE_SIMSERVER:
        raid_sim_request = _build_raid_sim_request(settings, iterations, seed)
        pool = simserver_client.get_pool(SIMSERVER_POOL_SIZE)
        result = pool.run(raid_sim_request)
        if result.get("error"):
            raise RuntimeError(f"sim error: {result['error'].get('message', '')[:2000]}")
    else:
        token = uuid.uuid4().hex[:8]
        tmp_settings = os.path.join(CACHE_DIR, f"_opt_settings_{token}.json")
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(tmp_settings, "w", encoding="utf-8") as f:
            json.dump(settings, f)
        try:
            result = adapter.run(tmp_settings, iterations=iterations, seed=seed)
        finally:
            try:
                os.remove(tmp_settings)
            except OSError:
                pass

    dps = adapter.player_and_pet_dps(result)
    total_pet = sum(p["avg"] for p in dps["pets"])
    out = {
        "player_dps": dps["player"]["avg"],
        "player_stdev": dps["player"]["stdev"],
        "pets": dps["pets"],
        "combined": dps["player"]["avg"] + total_pet,
        # Real per-iteration measurement from this exact run, not assumed -
        # see NOTES.md's "ComputeStats wired in" entry. None if the aura
        # never appeared (e.g. Expose Weakness untalented in this settings
        # background).
        "ew_uptime": expose_weakness.measured_ew_uptime(result),
    }
    sim_cache.put(cache_key, out)
    return out


def get_agility(settings_path: str, items: list[dict]) -> float | None:
    """Final (fully-buffed) Agility for one gear config via the ComputeStats
    RPC (see NOTES.md - RaidSimResult itself carries no stat breakdown).
    Deterministic given gear/buffs/talents/encounter (no Monte Carlo
    iterations involved), so cached under fixed iterations=0/seed=0 keys -
    a real, distinct cache namespace within the same sim_cache store, not a
    claim that this ran at "0 iterations"."""
    gear_hash = gear_config.config_hash(items)
    fp = settings_fingerprint(settings_path)
    cache_key = sim_cache.key(gear_hash, fp, 0, 0)

    cached = sim_cache.get(cache_key)
    if cached is not None:
        return cached.get("agility")

    settings = _load_template(settings_path)
    settings["player"]["equipment"] = {"items": items}
    raid_sim_request = _build_raid_sim_request(settings, 1, 1)  # iterations/seed unused by ComputeStats
    compute_stats_request = {"raid": raid_sim_request["raid"], "encounter": raid_sim_request["encounter"]}

    # This is the raid-AP-contribution column - an addition on top of the
    # core DPS numbers, not something that should ever take down a whole
    # multi-hour run. simserver.exe (the only path to ComputeStats - see
    # NOTES.md, wowsimcli's CLI has no stats subcommand) has a known,
    # not-yet-root-caused crash under sustained load; SimServerPool
    # self-heals a single dead process, but if that still fails, degrade
    # to None (reported as "n/a" downstream) rather than propagate and
    # crash the caller. Not cached as a failure - a later call for the
    # same config gets a fresh attempt, not a permanently poisoned result.
    try:
        pool = simserver_client.get_pool(SIMSERVER_POOL_SIZE)
        result = pool.run(compute_stats_request)
        if result.get("errorResult"):
            raise RuntimeError(f"computeStats error: {result['errorResult'][:2000]}")
        player = result["raidStats"]["parties"][0]["players"][0]
        agility = player["finalStats"]["stats"][1]  # StatAgility = 1, common.proto
    except (RuntimeError, KeyError, IndexError) as e:
        print(f"valuation.get_agility: degraded to None ({e})", file=sys.stderr)
        return None

    sim_cache.put(cache_key, {"agility": agility})
    return agility
