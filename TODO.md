# TODO

Standing list of real, scoped work items waiting on a fresh session (not a running log like
NOTES.md, not a judgment-call review queue like QUESTIONS.md - just "pick this up next").

## Achieved-BiS Weapon row hidden whenever either weapon slot has any upgrade candidate

Found live 2026-08-26 on Lerynia's own real Phase 2 report - full root-cause writeup already in
QUESTIONS.md ("OPEN, real bug found 2026-08-26"). Short version:

- `core/run_full_sweep_mv.py:144-155` (`SLOT_DISPLAY`) maps both `mainhand` and `offhand` to one
  shared "Weapon" display bucket.
- The Achieved-BiS check (`slots_with_upgrades`) operates at the DISPLAY-slot level, so a real
  upgrade candidate on EITHER weapon slot hides the WHOLE "Weapon" row - even when the other
  weapon slot is independently maxed.
- Separate from (and not caused by) the 2H-weave comparison, which lives entirely in its own "2H
  Weapon Options" section and never feeds `slots_with_upgrades` at all.

**Not fixed - explicitly on hold per the user (2026-08-26): "wait a bit more with what you just
found."** Do not start on this until the user actively asks to pick it up again.

When it's time to build it, the user's own two suggested directions (their judgment call, not
decided yet):
1. Split mainhand/offhand into two independent Achieved-BiS rows - matches how ring1/ring2
   already render as two separate cards under one "Ring" label, real precedent already in the
   same function.
2. For weave profiles specifically, show the achieved DW pair as BiS with an explicit note
   pointing at the "2H Weapon Options" section (not duplicating its number) rather than hiding
   the row outright.

Needs a real, fresh sweep to test against before landing anything in
`run_full_sweep_mv.py`/`build_ledger_data.py`/the report template - do not edit these blind.
