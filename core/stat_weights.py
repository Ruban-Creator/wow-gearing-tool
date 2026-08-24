"""Crude, disclosed stat-weight heuristic - for RANKING/PRUNING and gem-
choice tradeoffs only, never treated as the final answer (real value
always comes from the sim afterward, per CLAUDE.md's core mandate).

Per-profile since Stage 6 (multi-class support) - Hunter's Agility-heavy
weights are meaningless for a caster. Loaded once per pipeline run via
`set_active()` (matching the existing `marginal_value._SLOT_HINT` pattern:
one real "current profile" set at startup, read by many functions,
avoiding threading a weights dict through every call signature in
gem_optimizer.py/set_bonus.py/sweep_all_loot.py) rather than a module-level
constant - `get_active()` raises if nothing was ever set, so a
forgotten set_active() call fails loud instead of silently reusing
whatever profile happened to run last.
"""
import json
import os

_active: dict[str, float] | None = None


def load(profile_dir: str) -> dict[str, float]:
    """Reads profiles/tbc/<class>_<spec>/stat_weights.json."""
    path = os.path.join(profile_dir, "stat_weights.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def set_active(weights: dict[str, float]) -> None:
    global _active
    _active = weights


def get_active() -> dict[str, float]:
    if _active is None:
        raise RuntimeError(
            "stat_weights.set_active() was never called - a pipeline entry point "
            "must load a profile's stat_weights.json and call set_active() before "
            "any gem/set-bonus scoring code runs."
        )
    return _active
