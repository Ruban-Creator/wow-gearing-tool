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

import functools
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
import repo_root  # noqa: E402
import sim_cache  # noqa: E402
import gear_config  # noqa: E402
import item_db  # noqa: E402
import local_config  # noqa: E402

# Real bug found 2026-08-25: the packaged GUI (a windowed, console-less
# PyInstaller build) has no console of its own, so every bridge.exe
# subprocess.run() call here (hundreds per sweep - once per real sim call)
# made Windows spawn a brand-new visible console window for the child,
# since it has nowhere else to attach one. Never affected functionality
# (stdout/stderr aren't read from bridge.exe here), just flooded the
# screen with flashing black windows during a report run - alarming for a
# real user, not just cosmetic. CREATE_NO_WINDOW tells Windows not to
# allocate one at all; harmless on non-Windows since it's never referenced
# there.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Fist weapons only, per the user: they benefit disproportionately from
# Weightstone's FLAT +14 crit rating / +12 weapon damage (a bigger relative
# gain than on a bladed weapon, whose higher base damage dilutes the same
# flat bonus) - confirmed real, sourced item id from
# sim/core/consumes.go's case 34340 ("Addy Weightstone"), matching the
# user's own in-game tooltip exactly ("Increase blunt weapon damage by 12
# and add 14 critical hit rating for 1 hour"). Every other weapon type is
# deliberately left as whatever the settings file already specifies
# (currently unset/0) - not guessed at, since the user only asked for fist
# weapons specifically.
FIST_WEAPON_TYPE = 3
FIST_WEAPON_IMBUE_ID = 34340


def _imbue_decision(items: list[dict]) -> tuple[int | None, int | None]:
    """(mainhand imbue id or None, offhand imbue id or None) - None means
    "leave whatever the settings file already has", matching
    _apply_weapon_imbues()'s original only-ever-ADDS behavior. Split out
    (code review §2.2) so this cheap part (two item_db dict lookups) can run
    BEFORE touching the settings template at all - lets evaluate() check the
    memoized fingerprint cache first and skip the template deep-copy
    entirely on a hit, which is the common case."""
    if not items:
        return (None, None)
    mh_idx, oh_idx = gear_config.SLOT_INDEX["mainhand"], gear_config.SLOT_INDEX["offhand"]
    mh = items[mh_idx] if len(items) > mh_idx else None
    oh = items[oh_idx] if len(items) > oh_idx else None
    result: list[int | None] = [None, None]
    for i, slot_item in enumerate((mh, oh)):
        if slot_item and slot_item.get("id"):
            item = item_db.by_id(slot_item["id"])
            if item and item.get("weaponType") == FIST_WEAPON_TYPE:
                result[i] = FIST_WEAPON_IMBUE_ID
    return (result[0], result[1])

REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
CACHE_DIR = os.path.join(USER_DATA_DIR, "cache")

USE_SIMSERVER = True
# Real root cause found and fixed 2026-08-24 (with the user present to
# cross-check correctness, not another blind attempt) - see NOTES.md for the
# full investigation. The "dies/hangs at exactly call #34" bug was NEVER a
# resource exhaustion in the sim engine: a live goroutine dump (Windows
# CTRL_BREAK_EVENT, intercepted via a diagnostic os/signal handler added to
# simserver/main.go) caught the stuck goroutine blocked inside Go's own
# log.Printf -> syscall.WriteFile, at sim_concurrent.go's "All %d sims
# finished successfully." line. simserver_client.py's SimServerProcess only
# ever read stdout - nothing drained stderr after the startup line, so the
# Windows anonymous pipe's small buffer filled after ~33 calls' worth of log
# lines and the child process blocked forever writing its next one. Fixed
# with a background stderr-draining thread in simserver_client.py (bounded
# 200-line tail kept for real error reporting). Verified: correctness
# (simserver vs file-based path, identical DPS to 4 decimal places, same
# seed) and stability (200 concurrent mixed-iteration calls via the real
# production pool pattern, zero errors, well past the old #34 hang point).
# The original dev machine (Ryzen 5 5600X, 6C/12T) measured wowsimcli/
# simserver already using ALL logical threads internally per sim call
# ("Running N iterations on 12 concurrent sims" - Go's runtime.NumCPU()).
# A pool size of 4 there meant up to 4x12=48-way parallelism fighting over
# 12 threads - measured 747ms/call oversubscribed vs 101ms/call at
# pool_size=2 (7.4x). Derived via local_config.sim_concurrency() (code
# review §4.4), not hardcoded to that one machine - same function
# run_upgrade_sweep.MAX_WORKERS calls, so the two stay in lockstep
# automatically instead of needing to be kept equal by hand. There's no
# reason to hold idle simserver processes a caller can't reach.
SIMSERVER_POOL_SIZE = local_config.sim_concurrency()

_settings_lock = threading.Lock()
_template_cache = {}


def _normalize(settings: dict) -> dict:
    """Forces the pet to Owl regardless of what's in the source file.
    Wowsims.com test exports have shown Owl/Ravager/Bat across different
    sessions - none of that was a deliberate choice, just whatever the UI
    happened to have loaded. Owl is the confirmed standing choice; every
    Hunter settings file that flows through this pipeline gets normalized
    to it so a stray future paste can't silently change the baseline again.

    Guarded by presence of a "hunter" block (added for Stage 6, multi-class
    support): every other class's settings file has no player.hunter key at
    all, and this used to write it unconditionally - a guaranteed KeyError
    on the very first non-Hunter settings file, confirmed by direct testing
    before this guard existed."""
    if settings["player"].get("hunter"):
        settings["player"]["hunter"]["options"]["classOptions"]["petType"] = "Owl"
    return settings


def _load_template(settings_path: str) -> dict:
    with _settings_lock:
        if settings_path not in _template_cache:
            with open(settings_path, encoding="utf-8") as f:
                _template_cache[settings_path] = _normalize(json.load(f))
        # Deep-copy via round-trip so callers can mutate freely.
        return json.loads(json.dumps(_template_cache[settings_path]))


def _fingerprint_settings(settings: dict) -> str:
    """Hash of everything in the settings dict EXCEPT player.equipment.items
    - the fixed background gear runs must hold constant. Takes the dict
    directly (not a file) so callers that mutate settings first (e.g.
    evaluate()'s per-config weapon imbue selection) get a fingerprint that
    actually reflects what's about to run, not the un-mutated file.

    Real bug found and fixed 2026-08-30, before ever actually updating the
    sim for the first time: this hash never accounted for which sim BINARY
    ran the request. Swapping wowsimcli.exe/bridge.exe/simserver.exe for a
    new sim version, with the exact same gear+settings, would have silently
    served a stale DPS number computed under the OLD sim's math - the cache
    key had no way to know anything changed. Folding the sim's own commit
    SHA into the hashed content means a sim update invalidates every cache
    entry automatically; no caller needs to change since every real caller
    (marginal_value.py, run_upgrade_sweep.py, interaction_matrix.py, ...)
    already reaches this one fingerprinting function, never sim_cache.key()
    directly."""
    template = json.loads(json.dumps(settings))  # deep copy, don't mutate caller's dict
    template["player"]["equipment"] = None
    canonical = json.dumps(template, sort_keys=True, separators=(",", ":"))
    payload = canonical + "|" + repo_root.sim_commit_sha()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@functools.lru_cache(maxsize=256)
def settings_fingerprint(settings_path: str) -> str:
    """Hash of everything in the file-loaded template EXCEPT
    player.equipment.items. Used as part of the cache key so two different
    backgrounds never collide. Reflects only the settings FILE - callers
    whose effective settings differ from the file (e.g. evaluate()'s
    per-config weapon imbue mutation) must fingerprint their own mutated
    dict via _fingerprint_for()/_fingerprint_settings() instead, or the
    cache key would miss that dimension.

    Memoized (code review §2.2) - a pure function of settings_path alone
    (repo_root.sim_commit_sha() can't change mid-process), so a repeat call
    skips the template deep-copy + canonical json.dumps + sha256 entirely."""
    return _fingerprint_settings(_load_template(settings_path))


@functools.lru_cache(maxsize=256)
def _fingerprint_for(settings_path: str, mh_imbue: int | None, oh_imbue: int | None,
                      bonus_key: tuple[float, ...] | None) -> str:
    """Memoized fingerprint for evaluate()'s actual mutated settings (weapon
    imbues + optional bonus-stats override) - code review §2.2. The real
    input space is tiny (one settings file x 3 imbue states x a handful of
    real bonus_stats_override vectors), but without memoizing, EVERY
    evaluate() call - including pure cache hits, where this was the entire
    remaining cost - paid a full template deep-copy + canonical dump +
    hash. On a repeat key, lru_cache returns the memoized string without
    re-executing any of this."""
    settings = _load_template(settings_path)
    consumables = settings["player"]["consumables"]
    if mh_imbue is not None:
        consumables["mhImbueId"] = mh_imbue
    if oh_imbue is not None:
        consumables["ohImbueId"] = oh_imbue
    if bonus_key is not None:
        settings["player"]["bonusStats"]["stats"] = list(bonus_key)
    return _fingerprint_settings(settings)


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
            check=True, creationflags=_NO_WINDOW,
        )
        with open(out_path, encoding="utf-8") as f:
            return json.load(f)
    finally:
        for p in (in_path, out_path):
            try:
                os.remove(p)
            except OSError:
                pass


def evaluate(settings_path: str, items: list[dict], iterations: int, seed: int,
             bonus_stats_override: list[float] | None = None) -> dict:
    """Returns {"player_dps": ..., "player_stdev": ..., "pets": [...],
    "combined": ...}. Cached by (gear hash, settings fingerprint,
    iterations, seed) - never sims the same config twice.

    bonus_stats_override, when given, replaces player.bonusStats.stats
    outright (42-element vector, same indexing as gem/item stats) - used
    by set_bonus.isolate_bonus_value() to hold total character stats
    constant while swapping which real items count toward a set, so a
    delta reflects ONLY the set bonus's own behavioral effect (a proc, a
    spell mod) and not any raw stat difference from the swap itself."""
    gear_hash = gear_config.config_hash(items)
    # Code review §2.2: the imbue decision (cheap - two item_db dict
    # lookups) is computed BEFORE touching the settings template at all, so
    # the memoized _fingerprint_for() can be checked - and the cache
    # consulted - without ever deep-copying/re-serializing the (up to
    # ~75KB) template. Previously this happened on EVERY call, including
    # pure cache hits, where it was the entire remaining cost.
    mh_imbue, oh_imbue = _imbue_decision(items)
    bonus_key = tuple(bonus_stats_override) if bonus_stats_override is not None else None
    fp = _fingerprint_for(settings_path, mh_imbue, oh_imbue, bonus_key)
    cache_key = sim_cache.key(gear_hash, fp, iterations, seed)

    cached = sim_cache.get(cache_key)
    if cached is not None:
        return cached

    # Only reached on an actual cache MISS - build the real mutated
    # settings dict for the sim call itself.
    settings = _load_template(settings_path)
    if mh_imbue is not None:
        settings["player"]["consumables"]["mhImbueId"] = mh_imbue
    if oh_imbue is not None:
        settings["player"]["consumables"]["ohImbueId"] = oh_imbue
    if bonus_stats_override is not None:
        settings["player"]["bonusStats"]["stats"] = bonus_stats_override
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
        # Real, already-computed by the sim, never surfaced until the OOM
        # transparency feature (2026-09-06) - see adapter.player_seconds_oom()'s
        # own docstring for the real motivating bug this closes.
        "oom_seconds": adapter.player_seconds_oom(result),
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
