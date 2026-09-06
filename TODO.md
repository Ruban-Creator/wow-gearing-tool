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

**Update, 2026-09-06 - the CODE's own math independently verified correct** (not the same as an
external wowsims.com cross-check, see below). Directly called `set_bonus.rescue_check()` by hand for
Gloves of Dexterous Manipulation (the original 2026-08-23 validating case) with real, properly-
constructed `Candidate` objects (real enchant, real chase-bonus-aware gems - matching exactly how
`run_upgrade_sweep.py`'s own sweep-additions loop builds them) - result: `mv_if_set_broken =
14.063560060973032`, matching the live report's own `rescue_mv` to full floating-point precision. A
first, sloppier attempt at this same trace (using plain unenchanted/ungemmed item entries) gave a
wildly different, wrong-signed number (-25.24) purely from that own methodology error, not a real
bug - worth recording so a future re-check doesn't repeat the same mistake and misdiagnose a real
function as broken. Confirms the formula, the real candidate resolution, and the real call site all
agree with each other - a logic/wiring bug is now ruled out.

**Still open, a genuinely different question**: whether wowsims.com's OWN live site agrees with this
same real scenario (baseline with Cowl of Defiance already swapped into head, breaking Rift Stalker
Armor's bonus, then the candidate swapped into its own slot) - an external cross-check, not a code
review. Not done - would need either the user's own manual websim test (same JSON-export
methodology already used for Teeth of Gruul/Mindstorm Wristbands) or a Claude Browser-driven
wowsims.com session reproducing the exact gear/enchants/talents/buffs by hand. Real next step
whenever picked up.

Nothing else outstanding right now - the Achieved-BiS Weapon/Ring/Trinket row bug (logged here
2026-08-26) was fixed 2026-08-28, see NOTES.md for the full writeup.
