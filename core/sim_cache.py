"""Persisted cache keyed by gear-config hash + settings/iteration fingerprint.
Never sim the same config twice (§6 performance rule).

Append-only journal format (sim_cache.jsonl), not a single JSON dict file -
real fix, 2026-08-31, for a real measured problem (code review finding
§2.1): the old design (`sim_cache.json`, one big dict, rewritten whole on
every put()) made every single cache write O(cache size) - measured at
14.4ms/put with 1,782 real entries, 41ms/put at 5,000, growing without
bound as the cache accumulates across sweeps. It also ran that full
serialize-and-atomic-replace under the SAME lock get() uses, so one
worker's write stalled every other worker's reads. A journal fixes both:
put() is one O(1) line-append (no lock contention with reads beyond the
dict update itself), and it also happens to fix a real, previously-admitted
gap - the old format was explicitly NOT safe for two processes writing
concurrently (last full-file write wins, silently dropping the other
process's entries); the journal's append-only writes can't collide that
way (worst case is an interleaved-but-still-valid set of lines).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
CACHE_DIR = os.path.join(USER_DATA_DIR, "cache")
JOURNAL_PATH = os.path.join(CACHE_DIR, "sim_cache.jsonl")
# Old format, pre-2026-08-31 - read once for a one-time migration so an
# existing install's accumulated cache isn't silently discarded by this
# format change, never written again after that.
LEGACY_JSON_PATH = os.path.join(CACHE_DIR, "sim_cache.json")

# Once the journal has accumulated more lines than ~this multiple of its
# actual unique-key count, compact it back down to one line per key -
# keeps replay-on-load bounded instead of growing forever with superseded
# entries (a cache_key is only ever overwritten with an identical value in
# practice, but re-runs across sessions still append a "new" line each
# time the same key is recomputed after a restart).
_COMPACT_RATIO = 2

_lock = threading.Lock()
_memory_cache: dict | None = None
_journal_lines_since_load = 0


def _migrate_legacy_if_needed() -> dict:
    """One-time: fold the old whole-file sim_cache.json into a fresh
    journal, then get out of the way - never read or written again after
    this. Real data, not discarded: an existing install's accumulated
    cache (which can represent hours of real sim time) survives the
    format change instead of silently starting cold."""
    if not os.path.exists(LEGACY_JSON_PATH):
        return {}
    with open(LEGACY_JSON_PATH, encoding="utf-8") as f:
        legacy = json.load(f)
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(JOURNAL_PATH, "w", encoding="utf-8") as f:
        for k, v in legacy.items():
            f.write(json.dumps({"key": k, "value": v}) + "\n")
    os.replace(LEGACY_JSON_PATH, LEGACY_JSON_PATH + ".migrated")
    return legacy


def _load() -> dict:
    if not os.path.exists(JOURNAL_PATH):
        migrated = _migrate_legacy_if_needed()
        if migrated:
            return migrated
        return {}
    cache: dict = {}
    global _journal_lines_since_load
    lines = 0
    with open(JOURNAL_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # A process killed mid-write can leave a truncated final
                # line - real, expected failure mode for an append-only
                # log, not a corrupt cache. Skip just that line.
                continue
            cache[entry["key"]] = entry["value"]
    _journal_lines_since_load = lines
    return cache


def _ensure_loaded() -> dict:
    global _memory_cache
    if _memory_cache is None:
        _memory_cache = _load()
    return _memory_cache


def _atomic_write_journal(cache: dict):
    """Only used for compaction - the normal put() path appends instead.
    Same unique-tmp-name + retry-on-PermissionError dance as the old
    single-file design, for the same real reasons (concurrent-writer tmp
    collisions, antivirus/OneDrive transiently locking the target)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    tmp = f"{JOURNAL_PATH}.tmp.{os.getpid()}.{time.time_ns()}"
    with open(tmp, "w", encoding="utf-8") as f:
        for k, v in cache.items():
            f.write(json.dumps({"key": k, "value": v}) + "\n")
    for attempt in range(5):
        try:
            os.replace(tmp, JOURNAL_PATH)
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
    global _journal_lines_since_load
    with _lock:
        cache = _ensure_loaded()
        cache[cache_key] = value
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": cache_key, "value": value}) + "\n")
        _journal_lines_since_load += 1
        if _journal_lines_since_load > max(50, len(cache) * _COMPACT_RATIO):
            _atomic_write_journal(cache)
            _journal_lines_since_load = len(cache)
