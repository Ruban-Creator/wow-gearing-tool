"""Cheap, standalone pre-sweep OOM check (2026-09-06 - see run_upgrade_sweep.py's
own OOM_WARNING_THRESHOLD_FRACTION comment for the full real motivation/data).

Replicates ONLY the cheap baseline-construction-and-one-sim-call path a real
sweep already does before screening/confirming/resolving even starts
(run_upgrade_sweep.py's own profile-active-state setup +
`mv.valuation.evaluate(SETTINGS_TEMPLATE, baseline_config, SCREEN_ITERATIONS, ...)`)
- no candidate screening/resolving involved, so this is genuinely cheap
(the same "500-iteration cheap ranking pass" cost tier used everywhere else
in this pipeline) and safe to call on every Run click, not just once.

Called from gui/api.py's check_oom() BEFORE the real, multi-minute sweep
starts - if the requested duration would leave the character meaningfully
OOM, this lets the GUI offer a shorter, more realistic duration instead of
silently producing a skewed report."""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
import optimizer as opt  # noqa: E402
import gear_config as gc  # noqa: E402
import gem_optimizer  # noqa: E402
import stat_weights  # noqa: E402
import marginal_value as mv  # noqa: E402

REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR

# Duplicated from run_upgrade_sweep.py's own OOM_WARNING_THRESHOLD_FRACTION -
# a plain top-level constant is simpler to import here than restructuring
# run_upgrade_sweep.py to expose it without pulling in that whole module's
# real work (candidate loading, set-bonus parsing, etc.), which this cheap
# pre-check deliberately avoids. Keep in sync with that file's own value.
OOM_WARNING_THRESHOLD_FRACTION = 0.015
SCREEN_ITERATIONS = 500
SEED = opt.SEED
# Real, "nice" decrement step for the recommended-duration scan - finer than
# a round-number list (Béarforceone's real curve jumps from 0% at 90s to
# already 3.9% at 120s - a coarse list would overshoot to a needlessly short
# recommendation, see NOTES.md's 2026-09-06 entry for the full real curve).
DURATION_SCAN_STEP = 15
DURATION_SCAN_FLOOR = 30  # matches the duration-typo warning's own floor


def _settings_and_baseline(profile_dir: str, char_data: dict):
    """Real profile-active-state setup, same as run_upgrade_sweep.py's own
    (stat_weights/default gem+enchants/chase-bonus ids) - required before
    opt.build_owned_config() will work at all (it fails loud otherwise, by
    design, per Stage 6.0)."""
    profile = repo_root.load_json(os.path.join(profile_dir, "profile.json"))
    stat_weights.set_active(stat_weights.load(profile_dir))
    gc.set_active_default_gem(profile["primary_gem_id"])
    default_enchants_path = os.path.join(profile_dir, "default_enchants.json")
    default_enchants = repo_root.load_json(default_enchants_path) if os.path.exists(default_enchants_path) else {}
    gc.set_active_default_enchants(default_enchants)
    chase_bonus = repo_root.load_json(os.path.join(profile_dir, "chase_bonus_gems.json"))
    gem_optimizer.set_active_chase_bonus_ids(set(chase_bonus["item_ids"]))

    known_professions = {p["name"] for p in char_data["character"]["professions"]}
    baseline_config = opt.build_owned_config(char_data["equipped"]["items"], known_professions)
    settings_path = os.path.join(profile_dir, "settings_template.json")
    base_settings = repo_root.load_json(settings_path)
    return base_settings, baseline_config


def _oom_at_duration(base_settings: dict, baseline_config: list, profile_dir_name: str, duration: int) -> tuple[float, float]:
    """One cheap sim call at the given duration - returns (oom_seconds, oom_fraction)."""
    settings = copy.deepcopy(base_settings)
    settings["encounter"]["duration"] = duration
    cache_dir = os.path.join(USER_DATA_DIR, "cache")
    os.makedirs(cache_dir, exist_ok=True)
    tmp_path = os.path.join(cache_dir, f"_oom_check_{profile_dir_name}_d{duration}.json")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(settings, f)
    result = mv.valuation.evaluate(tmp_path, baseline_config, SCREEN_ITERATIONS, SEED)
    oom_seconds = result.get("oom_seconds", 0.0)
    oom_fraction = oom_seconds / duration if duration else 0.0
    return oom_seconds, oom_fraction


def check(name_realm: str, profile_dir: str, duration: int) -> dict:
    """Returns {"oom_seconds", "oom_fraction", "flagged": bool,
    "recommended_duration": int | None}. `recommended_duration` is the
    LARGEST duration (stepping down from `duration` in DURATION_SCAN_STEP
    increments, floor DURATION_SCAN_FLOOR) whose own OOM fraction clears the
    threshold - None if even the floor doesn't help (a real signal the issue
    is gear/build, not duration)."""
    char_path = os.path.join(USER_DATA_DIR, "characters", name_realm, "character.json")
    char_data = repo_root.load_json(char_path)
    profile_dir_name = os.path.basename(os.path.normpath(profile_dir))
    base_settings, baseline_config = _settings_and_baseline(profile_dir, char_data)

    oom_seconds, oom_fraction = _oom_at_duration(base_settings, baseline_config, profile_dir_name, duration)
    flagged = oom_fraction > OOM_WARNING_THRESHOLD_FRACTION
    recommended_duration = None
    if flagged:
        candidate = duration - DURATION_SCAN_STEP
        while candidate >= DURATION_SCAN_FLOOR:
            _, candidate_fraction = _oom_at_duration(base_settings, baseline_config, profile_dir_name, candidate)
            if candidate_fraction <= OOM_WARNING_THRESHOLD_FRACTION:
                recommended_duration = candidate
                break
            candidate -= DURATION_SCAN_STEP

    return {
        "oom_seconds": oom_seconds,
        "oom_fraction": oom_fraction,
        "flagged": flagged,
        "recommended_duration": recommended_duration,
    }
