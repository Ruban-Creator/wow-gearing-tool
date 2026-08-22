"""Analytical raid-wide Expose Weakness contribution (§4 option b).

Individual sims can't see the AP that Lerynia's Expose Weakness debuff grants
to the other physical attackers in her raid - they don't exist in that sim.
Her own share is already correct in personal DPS (see NOTES.md, Stage 2).
This computes the missing raid-wide share analytically instead, so every
future MV/valuation output can report personal DPS and raid contribution as
two separate columns, per the ground rule that decided this.

Coefficient (0.25 AP per point of Agility) and mechanic details are read
directly from sim/core/debuffs.go's ExposeWeaknessAura - see NOTES.md,
Stage 2, for the source trace. Not re-derived or estimated here.
"""
from __future__ import annotations

EW_AP_PER_AGILITY = 0.25
EW_SPELL_ID = 34503


def raid_ap_contribution(agility: float, uptime_fraction: float, physical_attacker_count: int) -> float:
    """AP granted to each of the raid's other physical attackers, summed
    across all of them, from Lerynia's Expose Weakness. Does NOT include her
    own share - that's already inside personal DPS.
    """
    ap_per_attacker = agility * EW_AP_PER_AGILITY * uptime_fraction
    return ap_per_attacker * physical_attacker_count


def measured_ew_uptime(raid_sim_result: dict, target_index: int = 0) -> float:
    """Real Expose Weakness uptime (0-1) for one sim run, read from the sim's
    own encounter metrics rather than assumed. Falls back to None if the
    aura never appeared (e.g. Expose Weakness untalented in that request)."""
    duration = raid_sim_result.get("avgIterationDuration")
    if not duration:
        return None
    targets = raid_sim_result.get("encounterMetrics", {}).get("targets", [])
    if target_index >= len(targets):
        return None
    for aura in targets[target_index].get("auras", []):
        if aura.get("id", {}).get("spellId") == EW_SPELL_ID:
            return aura["uptimeSecondsAvg"] / duration
    return None
