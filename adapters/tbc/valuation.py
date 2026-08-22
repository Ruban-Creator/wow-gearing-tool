"""Evaluate one 17-item gear config against a fixed settings background
(buffs/debuffs/consumables/encounter/talents/rotation held constant - gear
is the only variable, per the determinism ground rule). Thin over
adapter.run(); adds the sim cache and a stable settings fingerprint so the
cache key doesn't depend on file paths.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adapter  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "core"))
import sim_cache  # noqa: E402
import gear_config  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE_DIR = os.path.join(REPO_ROOT, "data", "cache")

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
    }
    sim_cache.put(cache_key, out)
    return out
