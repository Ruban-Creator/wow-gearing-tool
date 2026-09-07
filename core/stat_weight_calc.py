"""Real, empirical stat-weight computation via small-perturbation sim
calls, mirroring wowsims' own real methodology
(sim/tbc-new/sim/core/statweight.go's buildStatWeightRequests/
runStatWeights) rather than trusting a hand-curated, static preset table
forever.

Real finding this module is built on (2026-09-07, checked directly against
wowsims' own source, not assumed): their gem/item EP scoring formula
(`Stats.computeEP` in ui/core/proto_utils/stats.ts) is a PURE, completely
uncapped linear dot product - `stat * weight`, summed, zero built-in
threshold/cap logic anywhere. The reason their tool "handles hit caps
perfectly" isn't a clever formula - it's that their EP WEIGHTS THEMSELVES
are (optionally) recomputed via two real sims per tracked stat (current
gear, then current gear plus a small bonus of that one stat), so a
hit-capped character's own freshly-measured Hit Rating weight comes out
near-zero automatically: the real sim naturally shows almost no DPS gain
from more Hit Rating once miss chance is already floored, no special-
casing needed. This module is our own version of that mechanism - real-
sim-based, not a hand-rolled threshold formula.

Real conventions mirrored directly from statweight.go, not reinvented:
- Symmetric +/-10 rating perturbation for most stats (matches a single
  gem's typical impact); Armor/BonusArmor/ArmorPenetration use +/-100 (10x,
  since a single point of armor matters far less); Expertise uses
  +/-(ExpertisePerQuarterPercentReduction * 2) - a real 0.5% dodge/parry
  reduction's worth of rating (sim/tbc-new/sim/core/base_stats_auto_gen.go).
- Hit Rating (both Spell and Melee) and Expertise use an ASYMMETRIC 0-to-
  +mod perturbation, not symmetric - the real, current position (mod=0) is
  the meaningful "low" baseline for these specifically, since the
  interesting local derivative is "what's my next point worth right now,"
  not an average around a hypothetically-lower value these stats don't
  usually sit near in real end-game gear.
- Computed against the character's REAL, actually-equipped gear
  (via `optimizer.build_true_owned_config()` - real gems/enchants exactly
  as socketed, no substitution) - NEVER
  `optimizer.build_owned_config()`'s idealized substitute, matching the
  same real bug already found and fixed for
  `gem_optimizer.set_active_capped_totals()` the same day (the idealized
  baseline silently understates her real current stat totals, since it
  fills empty/uncurated sockets with the profile's own default gem instead
  of what she's actually wearing).
- Only recomputes stats already tracked (nonzero) in the profile's own
  existing `stat_weights.json` - never invents a newly-tracked stat a
  human hasn't already curated as relevant for this class/spec.

Real noise propagation, per CLAUDE.md's "noise honesty" ground rule: each
computed weight carries its own real standard error (from both sims'
`player_stdev`/sqrt(iterations), linearly propagated through the same
divide-by-mod-range the weight itself uses) - returned alongside the
weight, never silently discarded, so a genuinely unreliable weight can be
flagged rather than trusted blindly.

Real cost note: `valuation.evaluate()`'s own sim_cache means a repeat call
with the SAME gear/settings/bonus-stats/iterations/seed is a cache hit -
so re-running this against unchanged gear costs near nothing after the
first time. The real cost is paid once per meaningful gear change, not on
every single report.

Usage: python core/stat_weight_calc.py [profile_dir_name] [name_realm]
  Same argument convention as verify_gem_choices.py - defaults to
  survival_hunter / the flat USER_DATA_DIR/character.json when no args
  given.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
USER_DATA_DIR = repo_root.USER_DATA_DIR
import stat_weights  # noqa: E402

import optimizer as opt  # noqa: E402

sys.path.insert(0, os.path.join(REPO_ROOT, "adapters", "tbc"))
import valuation  # noqa: E402

STATS_LEN = 42  # proto/common.proto's real Stat enum length

# Real stat indices needing the special-cased mod sizing, straight from
# sim/tbc-new/sim/core/statweight.go's buildStatWeightRequests() - see this
# module's own docstring for why each is special-cased.
_ARMOR_STATS = {23, 31, 32}  # ArmorPenetration, Armor, BonusArmor
_ASYMMETRIC_STATS = {12, 20, 24}  # SpellHitRating, MeleeHitRating, ExpertiseRating
_EXPERTISE_STAT = 24
_EXPERTISE_PER_QUARTER_PERCENT = 3.942308  # sim/tbc-new/sim/core/base_stats_auto_gen.go

_DEFAULT_MOD = 10.0
# Per-side iteration count, matching a real "resolve"-grade total (30000)
# split across the two halves the same way wowsims' own real
# buildStatWeightRequests() does ("Iterations /= 2... so RNG lines up
# perfectly") - real, measured cost on this machine: ~0.3s @ 3000 iter, so
# ~1.5s per side * 2 sides * ~8 tracked stats (Balance Druid's own real
# count) = ~24s total, comfortably inside the user's own stated 1-minute
# budget for a real, automatic pipeline stage - and a cache hit (near-zero)
# on any repeat run against unchanged gear.
ITERATIONS_PER_SIDE = 15000
# Same fixed determinism seed as the rest of this pipeline (core/optimizer.py's own SEED).
SEED = 1


def _mod_for(stat_idx: int) -> float:
    if stat_idx in _ARMOR_STATS:
        return _DEFAULT_MOD * 10
    if stat_idx == _EXPERTISE_STAT:
        return _EXPERTISE_PER_QUARTER_PERCENT * 2
    return _DEFAULT_MOD


def compute_stat_weights(settings_path: str, real_equipped_items: list,
                          tracked_stats: list[int], iterations_per_side: int,
                          seed: int) -> dict[int, tuple[float, float]]:
    """Returns {stat_idx: (weight, noise_stdev)} for each of `tracked_stats`
    - a real, empirical marginal DPS-per-point value, computed the same way
    wowsims' own real Stat Weights tool does (see this module's own
    docstring). `real_equipped_items` MUST be a clean gear config for her
    real, current equipped gear - `optimizer.build_true_owned_config()`'s
    own output, NEVER `character.json`'s raw `equipped.items` directly
    (those carry extra, non-schema fields like "name" that make bridge.exe's
    strict protojson unmarshal fail) and never `build_owned_config()`'s
    idealized substitute either."""
    results = {}
    for stat_idx in tracked_stats:
        mod = _mod_for(stat_idx)
        low_mod = 0.0 if stat_idx in _ASYMMETRIC_STATS else -mod
        high_mod = mod

        low_bonus = [0.0] * STATS_LEN
        high_bonus = [0.0] * STATS_LEN
        low_bonus[stat_idx] = low_mod
        high_bonus[stat_idx] = high_mod

        low_result = valuation.evaluate(settings_path, real_equipped_items, iterations_per_side, seed,
                                         bonus_stats_override=low_bonus)
        high_result = valuation.evaluate(settings_path, real_equipped_items, iterations_per_side, seed,
                                          bonus_stats_override=high_bonus)

        mod_range = high_mod - low_mod
        weight = (high_result["combined"] - low_result["combined"]) / mod_range
        sem_low = low_result["player_stdev"] / (iterations_per_side ** 0.5)
        sem_high = high_result["player_stdev"] / (iterations_per_side ** 0.5)
        noise = ((sem_low ** 2 + sem_high ** 2) ** 0.5) / mod_range
        results[stat_idx] = (weight, noise)
    return results


def main():
    profile_dir_name = sys.argv[1] if len(sys.argv) > 1 else "survival_hunter"
    name_realm = sys.argv[2] if len(sys.argv) > 2 else "default"
    profile_dir = os.path.join(REPO_ROOT, "profiles", "tbc", profile_dir_name)
    settings_path = os.path.join(profile_dir, "settings_template.json")

    # Real, git-tracked, STABLE reference for which stats this class/spec
    # considers relevant at all - never the (possibly already-computed,
    # possibly-zeroed) per-character file, see stat_weights.py's own
    # module docstring for the real self-perpetuating-blind-spot bug that
    # mistake caused.
    preset_weights = stat_weights.load(profile_dir)
    tracked_stats = sorted(int(k) for k, v in preset_weights.items() if v)

    char_path = (os.path.join(USER_DATA_DIR, "characters", name_realm, "character.json")
                 if name_realm != "default" else os.path.join(USER_DATA_DIR, "character.json"))
    char = repo_root.load_json(char_path)
    real_gear = opt.build_true_owned_config(char["equipped"]["items"])

    print(f"Computing real stat weights for {len(tracked_stats)} tracked stats "
          f"@ {ITERATIONS_PER_SIDE} iterations/side...")
    results = compute_stat_weights(settings_path, real_gear, tracked_stats, ITERATIONS_PER_SIDE, SEED)
    computed = dict(preset_weights)
    for stat_idx, (weight, noise) in sorted(results.items()):
        old = preset_weights.get(str(stat_idx), 0)
        flag = "  <-- NOISY (>50% of value)" if noise > abs(weight) * 0.5 else ""
        print(f"  stat {stat_idx:3d}: {old:7.3f} -> {weight:7.3f} (+/-{noise:.3f}){flag}")
        computed[str(stat_idx)] = round(weight, 4)

    stat_weights.save_computed(USER_DATA_DIR, name_realm, profile_dir_name, computed)
    print(f"\nWrote {stat_weights.computed_path(USER_DATA_DIR, name_realm, profile_dir_name)}")


if __name__ == "__main__":
    main()
