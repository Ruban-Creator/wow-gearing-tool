# Actions for you — updated 2026-09-06 (post #17-21 pass)

Real, current list of what's actually on YOU (a decision, an account, an in-game action). Not a
status report — see CLAUDE.md/FUTURE_TASKS.md for full technical writeups, NOTES.md for the dated
build/investigation log. This file is meant to be asked about directly ("what's left on the
todo?") and gets rewritten fresh each time it's revisited — treat it as disposable, not an
append-only log like NOTES.md.

## Open, no decision needed yet - pick one whenever you want to

- **#14 — build the real scheduled sim-update-checking agent.** `CLAUDE.md`'s "Sim update
  procedure" is a tested runbook (just re-run for real, end to end, for the v0.0.124->v0.0.130
  bump - see NOTES.md), but nothing runs it on a schedule yet. No physical dedicated machine set up
  yet - only the Dell OptiPlex 3050 Micro is on hand, the HP EliteDesk 800 G6 hasn't been bought.
- **#21 — narrowed, not fully closed.** The wowsims.com magnitude gap for Mindstorm Wristbands went
  from an unexplained 11x to a real, bounded ~1.26x (+13.77 ours vs +17.31 theirs) after ruling out
  every settings-level cause and bumping the sim 6 versions. A small residual remains - not chased
  further; re-open if it matters for a real decision.
- **TODO.md — 12 synthetic-character profiles need a fresh sweep** to pick up backlog #13's
  filename convention and get real `check_ledger_consistency.py` coverage (currently only
  light-checked via settings regeneration). Mechanical, not risky, just time-costly.
- **TODO.md — verify the "Sidegrade" (rescue_check) DPS math against a real websim test.** You
  flagged distrust of these numbers but don't have the tokens/time to verify - explicitly deferred,
  needs your own websim time, not mine.
- **SmartScreen cert decision** — accepted as unsigned for now; revisit once the installer is
  distributed more broadly than this dev machine (~$100-600/yr depending on cert type).

Nothing here is urgent or blocking anything else - genuinely just "whenever you feel like it."

## Closed since the last update

- **#17 — Feral Cat Druid's `settings_template.json` regenerated and verified for real** (was
  stale from an old sim-preset/consumables-schema update - a real sim call + fresh sweep + clean
  `check_ledger_consistency.py` confirmed it, not just a diagnosis this time).
- **#18 — Balance Druid's gem choices individually verified.** 8 real chase-bonus exceptions found
  out of 23 socketed candidates checked (Boots of Foretelling +9.6 DPS the biggest), written into
  `chase_bonus_gems.json`.
- **#19 — "Assumed Raid Buffs" report section shipped**, per your own suggestion. Reads real
  raidBuffs/debuffs/partyBuffs/player buffs straight from the settings each sweep actually used -
  never hand-typed.
- **#20 — real fix, not the partial one you rejected.** A genuine "Dual-Wield Alternative" analysis
  now answers "would dual-wield beat my current 2H" with a real sim search (best-pair greedy
  search, resolved at full precision), regardless of which one's currently equipped. Real result for
  Lerynia: DW beats her 2H by +4.6 DPS with no weaving, but loses by -453.6 DPS if she's actually
  weaving. Also caught and fixed a real latent bug in the same pass (the topology gate would have
  wrongly fired for Balance Druid's own legitimate "2H some phases" case).
- **A real, confirmed enchant-priority bug** — a curated "best" enchant was silently overriding a
  real, already-applied, different-but-real enchant in every profile's baseline DPS. You caught this
  by challenging the docstring's own quoted justification. ~11 DPS real impact for Béarforceone;
  Arms Warrior had a real 4-slot fix too.
- **Sim updated v0.0.124 -> v0.0.130** - full runbook execution (protobuf regen, all 3 binaries
  rebuilt, verified clean across all 3 weapon topologies and every real character).
- **Gem-verification's stale "Agility" labels fixed** - you caught this live ("did you really check
  agility gems on a caster???"). The underlying comparison was always correct; only the printed text
  was wrong.
- **Backlog #15 (`sources: None` DB gap)** — fully closed. 0 of 163 unique gap items unresolved.
- **CurseForge** — live: "GT Companion" by RubanCreator, https://www.curseforge.com/wow/addons/gt-companion

## Installer

Rebuilt 2026-09-06 05:56, but that predates the #17-21 pass and the sim bump - `core/*.py` and
profile data (chase_bonus_gems.json, sim submodule) have changed since. **A fresh rebuild is
pending** if you want a distributable copy carrying today's later work.
