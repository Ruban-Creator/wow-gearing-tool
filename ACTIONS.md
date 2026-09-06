# Actions for you — updated 2026-09-06 (backlog #17-21 pass)

**#17, #18, #19, #20 all closed this pass** (see NOTES.md/FUTURE_TASKS.md for full writeups):
Feral Cat Druid regenerated+verified, Balance Druid's gem choices individually verified (8 real
chase-bonus exceptions found), a real "Assumed Raid Buffs" transparency section shipped, and #20 got
a real fix (not the partial exclusion first attempted) - a genuine "Dual-Wield Alternative" analysis
that answers "would DW beat my current 2H" with a real sim search, regardless of which one's
currently equipped. #21 (the wowsims.com magnitude gap) is in progress - found we're 6 real releases
behind (v0.0.124 vs v0.0.130) and are mid-way through the sim-update runbook to close that gap for
real, not just document it further.


Real, current list of what's actually on YOU (a decision, an account, an in-game action). Not a
status report — see CLAUDE.md/FUTURE_TASKS.md for full technical writeups, NOTES.md for the dated
build/investigation log. This file is meant to be asked about directly ("what's left on the
todo?") and gets rewritten fresh each time it's revisited — treat it as disposable, not an
append-only log like NOTES.md.

## Open, no decision needed yet - pick one whenever you want to

- **#14 — build the real scheduled sim-update-checking agent.** `CLAUDE.md`'s "Sim update
  procedure" is a tested runbook, but nothing runs it on a schedule yet. Real question when you
  want to pick this up: what machine/mechanism actually runs it (this dev machine on a schedule?
  something else?). No physical dedicated machine set up yet - only the Dell OptiPlex 3050 Micro
  is on hand, the HP EliteDesk 800 G6 hasn't been bought.
- **#17 — Feral Cat Druid's `settings_template.json` is stale** (real cause understood: her
  `consumables.json`/APL source changed since it was last generated, never regenerated to match) -
  the actual regeneration + verification hasn't been done, just diagnosed and reverted twice now.
- **#18 — Balance Druid's gem choices were never individually verified** the way Survival Hunter's
  were (37 candidates tested, 9 confirmed exceptions) - her `chase_bonus_gems.json` is empty, so
  the blanket "replace every socket with Spell Damage" policy is an untested default for her.
- **#19 — surface the assumed raid buffs directly in the report** (your own suggestion) - not
  built yet.
- **#20 — new today: the Weapon tier list produces nonsensical numbers when a weave-capable
  character (Survival/Beastmastery Hunter) is genuinely 2H-equipped in real life but the profile's
  topology assumes dual-wield.** Real architecture gap, not a quick fix - see FUTURE_TASKS.md for
  the full writeup. Until fixed: eyeball the Achieved-BiS Weapon entry against what she's actually
  wearing before trusting the Weapon tier list underneath it, for either Hunter profile.
- **#21 — new today: a real, only-partly-explained magnitude gap between this tool's own sim and
  wowsims.com** for at least one item (Mindstorm Wristbands, Balance Druid) - same direction, but
  our +11.56 DPS vs their +17.31 even with buffs matched. Real next step on file: a full
  field-by-field settings diff, not spot-checks.
- **TODO.md — verify the "Sidegrade" (rescue_check) DPS math against a real websim test.** You
  flagged today that you don't trust most of these numbers, but don't currently have the
  tokens/time to verify - explicitly deferred, not fixed. The one thing that WAS fixed today: the
  note's referenced "via" item is now a real clickable link instead of an invisible name.
- **SmartScreen cert decision** — accepted as unsigned for now; revisit once the installer is
  distributed more broadly than this dev machine (a real cost decision, ~$100-600/yr depending on
  cert type — see `FUTURE_TASKS.md`).

Nothing here is urgent or blocking anything else - genuinely just "whenever you feel like it."

## Closed since the last update

- **Backlog #15 (`sources: None` DB gap) — fully closed 2026-09-06.** All 163 unique items in the
  current gap list resolve via structural rules (tier-token vendor mechanism, Gladiator's PvP
  naming rule) or the individually-verified `source_overlay.json` overlay. 0 remain unresolved.
- **A real, confirmed enchant-priority bug — fixed 2026-09-06.** A curated "best" enchant was
  silently overriding a REAL, already-applied, different-but-real enchant in every profile's
  baseline DPS computation (not just filling genuinely-unenchanted slots, which was the only thing
  the original 2026-08-25 decision actually justified - you caught this precisely by challenging
  the docstring's own quoted justification). Real, measured impact: ~11 DPS for Béarforceone alone.
  Re-verified across all 15 profiles; Arms Warrior (Rubán) had a real, legitimate 4-slot diff from
  this, now fixed too.
- **The Mindstorm Wristbands / Teeth of Gruul discrepancies — investigated to the real, honest end
  of what's explainable today**, not fully closed (see #21 above) but no longer a mystery: sign
  agrees with wowsims.com now, only a partial, unexplained magnitude gap remains.
- **CurseForge** — live: "GT Companion" by RubanCreator, https://www.curseforge.com/wow/addons/gt-companion

## Installer

Rebuilt fresh, 2026-09-06 05:56 - `packaging/output/RGT-Setup.exe` now bundles today's real fixes
(enchant-priority fix, sidegrade link, the corrected Balance Druid/Arms Warrior profile data).
`build/dist/RGT.exe` (the GUI itself) did NOT need rebuilding - it reads `core/*.py` as live
sibling files from the checkout rather than bundling them in, per `packaging/README.md`. Nothing
pending here right now.
