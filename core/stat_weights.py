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

Two real, separate sources of these numbers now (2026-09-07,
`core/stat_weight_calc.py`'s own real small-perturbation sim methodology):
`profiles/tbc/<profile>/stat_weights.json` (git-tracked, human-curated
preset - which stats this class/spec even considers relevant, plus a
reasonable static starting value) versus a real, per-CHARACTER computed
file under USER_DATA_DIR (`computed_path()`/`load_computed()`/
`save_computed()`) - the character's OWN real, empirically-measured
weights at her actual current gear.

Real bug found and fixed the same day it was introduced: an earlier
version of this recompute wrote the freshly-measured values straight back
into the git-tracked, PROFILE-level `stat_weights.json` file - two real
problems at once. (1) Self-perpetuating blind spot: once a stat's
computed weight rounds to 0.0 (e.g. a hit-capped character's real Spell
Hit weight), any caller that derives "which stats to track" from
`stat_weights.json`'s own nonzero keys would silently stop tracking that
stat forever, even though "genuinely zero right now" is exactly the
informative state worth re-checking on a future run once gear changes.
(2) Wrong scope entirely: the computed weights are a function of ONE
character's real, current gear - overwriting a shared, profile-level file
would silently corrupt the numbers for any OTHER real character sharing
that same class/spec profile. The git-tracked file now stays a stable,
never-automatically-overwritten reference for BOTH "which stats are
trackable for this class" AND a reasonable fallback value before any
character-specific computation has ever run.
"""
import json
import os

_active: dict[str, float] | None = None


def load(profile_dir: str) -> dict[str, float]:
    """Reads the git-tracked, human-curated
    profiles/tbc/<class>_<spec>/stat_weights.json - the stable reference
    for which stats this class/spec considers relevant at all, and a
    reasonable static fallback value. Never overwritten by automation -
    see this module's own docstring for the real bug that caused once."""
    path = os.path.join(profile_dir, "stat_weights.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def computed_path(user_data_dir: str, name_realm: str, profile_dir_name: str) -> str:
    """Where one real character's own empirically-computed weights for one
    profile live - USER_DATA_DIR (Production Data, per CLAUDE.md's Repo
    Layout - never repo-relative), keyed by BOTH name_realm and
    profile_dir_name since a character could plausibly be assigned a
    different profile later (see the multi-profile-per-class support in
    CLAUDE.md's Staging section) and each combination has its own real,
    independently-measured gear-state-dependent numbers."""
    char_dir = os.path.join(user_data_dir, "characters", name_realm)
    return os.path.join(char_dir, f"stat_weights_computed_{profile_dir_name}.json")


def load_computed(user_data_dir: str, name_realm: str, profile_dir_name: str) -> dict[str, float] | None:
    """None if this character/profile combination has never had a real
    computation run yet (a fresh character, or a tool that doesn't call
    core/stat_weight_calc.py) - callers fall back to the static preset in
    that case, never crash."""
    path = computed_path(user_data_dir, name_realm, profile_dir_name)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_computed(user_data_dir: str, name_realm: str, profile_dir_name: str,
                   weights: dict[str, float]) -> None:
    path = computed_path(user_data_dir, name_realm, profile_dir_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(weights, f, indent=2)


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
