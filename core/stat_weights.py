"""Crude, disclosed stat-weight heuristic - for RANKING/PRUNING and gem-
choice tradeoffs only, never treated as the final answer (real value
always comes from the sim afterward, per CLAUDE.md's core mandate). One
shared copy so sweep_all_loot.py's candidate pre-filter and
gem_optimizer.py's per-socket gem choice can't drift into two different
numbers for the same stats.
"""
STAT_WEIGHTS = {
    "0": 0.5,   # Strength
    "1": 2.0,   # Agility
    "17": 1.0,  # AttackPower
    "18": 1.0,  # RangedAttackPower
    "20": 0.8,  # MeleeHitRating
    "21": 1.2,  # MeleeCritRating
    "22": 0.8,  # MeleeHasteRating
    "23": 0.9,  # ArmorPenetration
    "24": 0.3,  # ExpertiseRating
}
