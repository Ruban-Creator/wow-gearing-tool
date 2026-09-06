# TODO

Standing list of real, scoped work items waiting on a fresh session (not a running log like
NOTES.md, not a judgment-call review queue like QUESTIONS.md - just "pick this up next").

## Fresh sweeps for all 12 synthetic-character profiles — CLOSED, 2026-09-06

The real next step this entry called for is done: a fresh `run_upgrade_sweep.py` sweep ran for
every one of the 12 synthetic characters (Beastmastery Hunter and Feral Cat Druid earlier the same
day, the remaining 10 - affliction/demonology/destruction_warlock, arcane_mage, combat_rogue,
elemental_shaman, enhancement_shaman, fury_warrior, retribution_paladin, shadow_priest - via a
background batch), each rebuilt into the current profile-suffixed filename convention
(`tiered_report_<profile>_phase3.json`/`ledger_data_<profile>_phase3.json`, backlog #13). Every one
of the 10 needed its `ledger_data_*` rebuilt afterward via `core/build_ledger_data.py --character
<name> --phase phase3` (the sweep itself only produces `tiered_report_*`) - done for all 10.
`check_ledger_consistency.py --skip-html` confirmed clean for all 12 (45-327 assertions each
depending on candidate-pool size, 0 failures/0 warnings across the board) - the same real
verification standard already applied to the 3 real-character profiles.

Nothing else outstanding right now - the Achieved-BiS Weapon/Ring/Trinket row bug (logged here
2026-08-26) was fixed 2026-08-28, see NOTES.md for the full writeup. The "Sidegrade" MV-correctness
question (tracked here earlier today) is now closed for real - see NOTES.md's dated entry: the
user's own real websim comparison found a genuine design bug (the check never verified the enabling
swap was itself worth making), fixed in `set_bonus.rescue_check()`.
