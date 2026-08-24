"""Persisted cache keyed by gear-config hash + settings/iteration fingerprint.
Never sim the same config twice (§6 performance rule).
"""
from __future__ import annotations

import json
import os
import threading
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_PATH = os.path.join(REPO_ROOT, "data", "cache", "sim_cache.json")

_lock = threading.Lock()
_memory_cache: dict | None = None
# Real, measured cost (2026-08-24): with ~1782 entries (~450KB) on disk,
# _load()'s full-file json.load() was only ~5-20ms - not today's dominant
# per-call cost, but a real, unnecessary re-read on EVERY get() (even cache
# HITS), including from run_full_sweep_mv.py's ThreadPoolExecutor workers,
# which all share this same process/module (safe to keep one shared
# in-memory copy - see MAX_WORKERS's threading.Lock, unchanged below). Will
# matter more as the cache keeps growing across sweeps. Loaded once lazily
# per PROCESS, not per call; still write-through to disk on every put() (same
# crash-safety and cross-process visibility as before - a concurrently
# running second process's own new writes just won't be visible to THIS
# process's in-memory copy until it restarts, which only costs a missed
# cache-hit opportunity, never a wrong answer).


def _load() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _ensure_loaded() -> dict:
    global _memory_cache
    if _memory_cache is None:
        _memory_cache = _load()
    return _memory_cache


def _save(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    # Unique per-call tmp name (pid + high-res timestamp) - real incident
    # (2026-08-23): a fixed ".tmp" name meant two concurrent processes (a
    # background sweep + a stray diagnostic script) both wrote to the SAME
    # tmp path; whichever process's os.replace() ran second found the file
    # already gone (renamed away by the first), crashing with
    # FileNotFoundError. threading.Lock only guards this process, never
    # protected against that - a unique tmp name per write removes the
    # collision entirely instead of retrying around it.
    tmp = f"{CACHE_PATH}.tmp.{os.getpid()}.{time.time_ns()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    # If another process (antivirus/OneDrive scanning the just-written
    # file) has CACHE_PATH momentarily open, Windows os.replace raises
    # PermissionError instead of just blocking. A few short retries ride
    # out that transient window instead of crashing a run that's
    # otherwise perfectly fine.
    for attempt in range(5):
        try:
            os.replace(tmp, CACHE_PATH)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def key(gear_hash: str, settings_fingerprint: str, iterations: int, seed: int) -> str:
    return f"{gear_hash}:{settings_fingerprint}:{iterations}:{seed}"


def get(cache_key: str) -> dict | None:
    with _lock:
        return _ensure_loaded().get(cache_key)


def put(cache_key: str, value: dict):
    with _lock:
        cache = _ensure_loaded()
        cache[cache_key] = value
        _save(cache)
