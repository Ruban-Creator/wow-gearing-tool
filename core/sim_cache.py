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


def _load() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(cache: dict):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    # threading.Lock only guards this process - if another process (a
    # second pipeline run, a stray test script, antivirus/OneDrive
    # scanning the just-written file) has CACHE_PATH momentarily open,
    # Windows os.replace raises PermissionError instead of just blocking.
    # A few short retries ride out that transient window instead of
    # crashing a run that's otherwise perfectly fine.
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
        return _load().get(cache_key)


def put(cache_key: str, value: dict):
    with _lock:
        cache = _load()
        cache[cache_key] = value
        _save(cache)
