"""Real, noise-aware "what changed since your last sweep" comparison.

Real gap this closes (2026-09-04): after backlog #8's investigation found no
safe way to speed up a re-sweep itself (see FUTURE_TASKS.md), the actual
underlying want - "I got 1-2 items this week, what's different?" - doesn't
need the sweep to be faster, it needs the ALREADY-COMPUTED output compared
against last time. This module does that comparison, over two already-
trusted, already-fully-resolved ledger_data snapshots - no new sim calls,
so zero cache-correctness risk (see NOTES.md's 2026-09-04 entry for the full
design trail).

Deliberately does NOT try to tell apart WHY an item is no longer shown
(already equipped now / excluded by a source-scope change / still a real
candidate but pushed out of the top-LEADERBOARD_SIZE list by something else)
- only the top run_upgrade_sweep.LEADERBOARD_SIZE items per (tier, slot) are
ever persisted to ledger_data, so the full screened pool needed to
distinguish those cases isn't available here. Labeled honestly as "no
longer shown" rather than claiming false precision - flag if this ambiguity
turns out to matter enough to persist the full pool for.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402

USER_DATA_DIR = repo_root.USER_DATA_DIR


def _current_path(name_realm: str, phase: str, profile_dir_name: str) -> str:
    """The file that, at the moment compute() is called, still holds the
    PRIOR sweep's data - build_ledger_data.persist() hasn't overwritten it
    yet (compute() must run before persist() in build_with_diff(), see that
    function's own docstring). No separate ".previous.json" history file is
    needed - "whatever's on disk right before this sweep's own write" IS
    last time's sweep, by construction, so there's nothing to rotate."""
    return os.path.join(USER_DATA_DIR, "characters", name_realm, "cache",
                         f"ledger_data_{profile_dir_name}_{phase}.json")


def _index(ledger: dict) -> dict:
    """(item_id, best_slot) -> item row, across every tier/slot - matches
    backlog #16's own real-slot keying convention throughout this codebase
    (run_upgrade_sweep.py's confirmed_by_key/resolved_by_key, etc.)."""
    idx = {}
    for tier in ledger.get("tiers", []):
        for slot in tier.get("slots", []):
            for it in slot.get("items", []):
                key = (it["item_id"], it.get("best_slot") or slot["slot"])
                idx[key] = it
    return idx


def compute(name_realm: str, phase: str, profile_dir_name: str, current: dict) -> dict | None:
    """Returns None if there's no previous sweep for this exact (character,
    profile, phase) to compare against - the first-ever sweep, or one from
    before this feature existed. A legitimate, expected state, not an error;
    callers should render nothing (no empty "0 changes" section) in that case.
    """
    prev_path = _current_path(name_realm, phase, profile_dir_name)
    if not os.path.exists(prev_path):
        return None
    previous = repo_root.load_json(prev_path)

    old_idx = _index(previous)
    new_idx = _index(current)

    new_candidates = []
    moved = []
    no_longer_shown = []

    for key, it in new_idx.items():
        old_it = old_idx.get(key)
        if old_it is None:
            new_candidates.append(it)
            continue
        old_mv, new_mv = old_it.get("mv"), it.get("mv")
        if old_mv is None or new_mv is None:
            continue
        delta = new_mv - old_mv
        # Same "~95% confidence, not tied" rule used everywhere else in this
        # codebase (marginal_value.py/run_upgrade_sweep.py/gem_optimizer.py/
        # set_bonus.py's own `abs(delta) < 2 * noise` tied_within_noise check)
        # - reused here rather than inventing a new threshold for this one
        # comparison. Two INDEPENDENT sim results being compared, so their
        # noise combines as sqrt(a^2 + b^2), same as marginal_value.delta_noise().
        combined_noise = ((old_it.get("noise_stdev") or 0) ** 2
                           + (it.get("noise_stdev") or 0) ** 2) ** 0.5
        if abs(delta) >= 2 * combined_noise:
            moved.append({**it, "old_mv": old_mv, "delta": delta})

    for key, old_it in old_idx.items():
        if key not in new_idx:
            no_longer_shown.append(old_it)

    return {
        "new": new_candidates,
        "moved": moved,
        "no_longer_shown": no_longer_shown,
    }
