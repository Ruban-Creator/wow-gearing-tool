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

## Verify "Sidegrade" (rescue_check) MV correctness against a real websim test

2026-09-06: while investigating a stale-data confusion on Lerynia's survival_hunter_phase2 report
(her `character.json` hadn't been re-synced since 2026-08-31 and still showed her old dual-wield
setup - fixed via a fresh `python cli/gear.py sync`, see NOTES.md), the user flagged the report's
6 "Sidegrade" notes (Shoulderpads of the Stranger/Ranger-General's Chestguard/3x Hands items, each
claiming a real +2.9 to +16.2 DPS gain "once Rift Stalker Armor's bonus is already broken by
swapping in Cowl of Defiance") as suspect: "i don't even think most of these sidegrades are dps
increases - we lack the tokens now to verify with the websim."

Two separate things were found/fixed today, neither of which is this concern:
- The referenced "Cowl of Defiance" (the `via_item` each note names) was genuinely invisible
  anywhere else in the report - not one of its own slot's top-5 displayed candidates - making the
  claim unverifiable at a glance. Fixed: `set_bonus.rescue_check()` now returns `via_item_id`,
  threaded through `run_upgrade_sweep.py`'s `rescue_via_item_id`/`rescue_via_item` row fields, and
  `report_template.html` now renders it as a real, clickable Wowhead link next to the note.
- This does NOT touch the actual `mv_if_set_broken` math itself (`set_bonus.rescue_check()`,
  core/set_bonus.py) - that's a real, live sim call (two 30k-iteration `valuation.evaluate()`
  calls, not an estimate), but has never been independently cross-checked against a manual websim
  test the way the Teeth of Gruul/Mindstorm Wristbands bugs were today.

Real next step: pick at least one of these 6 real Sidegrade candidates (e.g. Gauntlets of the
Dragonslayer, the smallest claimed gain at +4.7, or Gloves of Dexterous Manipulation, the original
2026-08-23 validating case per that function's own docstring) and manually reproduce
`rescue_check()`'s exact scenario in wowsims.com by hand (baseline with Cowl of Defiance already
swapped into head, breaking Rift Stalker Armor's bonus, then swap the candidate into its own slot)
- same JSON-diff methodology already used for Teeth of Gruul/Mindstorm Wristbands. Not done today -
explicitly deferred per the user ("we lack the tokens now").

Nothing else outstanding right now - the Achieved-BiS Weapon/Ring/Trinket row bug (logged here
2026-08-26) was fixed 2026-08-28, see NOTES.md for the full writeup.
