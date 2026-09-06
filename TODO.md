# TODO

Standing list of real, scoped work items waiting on a fresh session (not a running log like
NOTES.md, not a judgment-call review queue like QUESTIONS.md - just "pick this up next").

## Fresh sweeps needed for 11 synthetic-character profiles (regression verification)

2026-09-06: today's enchant-fallback fix (`core/optimizer.py`'s `build_owned_config()`, see
NOTES.md) was verified for real via `check_ledger_consistency.py` for the 3 real-character
profiles (Béarforceone/Rubán/Lerynia), but the 12 synthetic-character profiles' cached
`tiered_report_*.json` files all predate backlog #13's profile-suffixed filename convention, so
`check_ledger_consistency.py` can't run against them without a fresh sweep first (`FATAL: ...not
found - run core/run_upgrade_sweep.py first`). Confirmed instead via the lighter-weight check that
`build_profile_settings.py` regenerates a valid, sane `settings_template.json` for 11 of them
(Beastmastery Hunter is a known, pre-existing exception - hand-built `TypeSimple` rotation, same as
Survival Hunter) - real enchants were confirmed restored for
affliction/demonology/destruction_warlock, enhancement_shaman, shadow_priest.

Real next step: run a fresh `run_upgrade_sweep.py` sweep for each of the 12 synthetic characters
(bringing their cache up to the current filename convention as a side effect) and confirm
`check_ledger_consistency.py` passes clean, the same real verification standard already applied to
the 3 real characters. Not done today - a real, mechanical, time-costly (12 sweeps) but low-risk
task, not requiring further judgment calls.

Nothing else outstanding right now - the Achieved-BiS Weapon/Ring/Trinket row bug (logged here
2026-08-26) was fixed 2026-08-28, see NOTES.md for the full writeup. The "Sidegrade" MV-correctness
question (tracked here earlier today) is now closed for real - see NOTES.md's dated entry: the
user's own real websim comparison found a genuine design bug (the check never verified the enabling
swap was itself worth making), fixed in `set_bonus.rescue_check()`.
