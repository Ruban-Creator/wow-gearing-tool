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

## Backlog #21 - CLOSED, 2026-09-06

The residual gap this entry tracked is fully closed - see FUTURE_TASKS.md's #21 entry and NOTES.md's
dated entry for the full trail. A fresh, correctly-captured wowsims.com export (matching duration)
brought our own sim's delta for Crimson Bracers of Gloom -> Mindstorm Wristbands to +19.19 DPS
against wowsims.com's own +19.26 - a 0.07 DPS difference, fully inside noise. Nothing further to do
here.

## Align assumed raid buffs/debuffs per profile with wowsims.com's own defaults + fix unrealistic raid-comp assumptions

Raised by the user (2026-09-06) while diffing Béarforceone's real settings against her own websim
export to chase a baseline-DPS gap: our per-profile `raid_buffs_overlay.json`/`settings_template.json`
assumptions currently differ from what a user sees as the DEFAULT on wowsims.com itself (e.g. real,
confirmed differences found this session: `shadowProtection`, `judgementOfLight`, `faerieFire`,
`exposeWeaknessUptime`/`exposeWeaknessHunterAgility`, `insectSwarm`, `ferociousInspiration`,
`blessingOfMight`/`blessingOfSalvation`/`unleashedRage` were present in OUR settings but absent from
wowsims' own default/generic preset). Per the user: this is real, ongoing user-confusion risk whenever
someone tries to cross-check our numbers against wowsims.com directly (exactly what happened in this
session's own investigation) - our assumptions should be reconciled with wowsims' own defaults across
every profile, not just discovered ad hoc per investigation.

**Second, related but separate point from the user**: some of these assumed buffs/debuffs reflect an
unrealistic raid comp for the class being simmed. Real, precise attribution per the user's own
correction (don't conflate these two): **Expose Weakness** (`exposeWeaknessUptime`/
`exposeWeaknessHunterAgility`) is a **Survival Hunter's** own signature debuff; **Ferocious
Inspiration** (`partyBuffs.ferociousInspiration`) is a **Beastmastery Hunter's** own pet ability -
different specs, both currently assumed present in Balance Druid's own settings, and per the user
("usually a bm hunter will never be in group with a boomkin") that pairing doesn't match real raid comp
- matches this project's own already-established raid-comp precedent for `shadowPriestDps` (e.g.
Boomkins group with 3 Warlocks + 1 Elemental Shaman, not a Shadow Priest, per the 2026-09-06 audit
already done for that one field specifically). Real next step: a fuller per-profile audit of every
assumed buff/debuff against BOTH (a) wowsims.com's own default preset (to reduce comparison confusion)
and (b) the user's own real raid-comp knowledge (to avoid assuming a buff/debuff from a spec that
wouldn't realistically be grouped with this one) - not done yet, flagged here for a dedicated pass.

## Baseline-honesty plan: FULLY COMPLETE, all 4 stages (2026-09-07)

Plan file: `staged-purring-lynx.md` ("Baseline gear honesty + phase-legal gems"). All done and
regression-tested (see NOTES.md's 2026-09-06/07 entries for the full trail): Stage 1 (two-config
split, phase-legal gems, Missing Enchants rework, `best_four_of_five()` reconciliation), the
separately-discovered pet-DPS double-counting bug, Stage 2 (enchant-coverage completion - 2 real
gains, Demonology/Destruction Warlock chest enchants; the rest of the sparse profiles confirmed
genuinely blocked on dead preset enchant IDs or ring-slot presets that don't exist, not a tooling
gap - see "Ring-enchant coverage gap" below), Stage 3 (new Missing Gems feature, mirrors Missing
Enchants, real-verified in-browser against 3 real profiles), and Stage 4 (`CLAUDE.md`'s MV-formula
now names phase-legality as an equip constraint + the two-config rule spelled out; the stale
"Dropped from §8" line corrected; `CLASSES.md` gained the phase-aware-gem convention + the
unique/profession-gated chase-bonus trap as new real gotchas).

A real, major SECOND-ORDER finding surfaced while closing out the plan's own open question (should
`chase_bonus_gems.json` be re-verified under phase-legal gems?): yes, and 11 of 15 profiles' files
were WRONG - several existing "socket-bonus wins" were verified against an illegally-selectable gem
(unique/profession-gated) that this session's own earlier fix now correctly excludes, so the real
comparison flips to a loss once restricted to legally-obtainable gems. 6 profiles' entire
chase-bonus lists emptied out (survival_hunter, affliction_warlock, beastmastery_hunter,
destruction_warlock, fury_warrior, demonology_warlock - every one of their real DPS reports has been
recommending an item's socket bonus that was never actually worth chasing); 2 previously-empty files
gained real new wins (arms_warrior, enhancement_shaman); balance_druid/arcane_mage/combat_rogue got
a mix of real removals and real new finds. Full per-profile before/after table in NOTES.md's
2026-09-07 entry. All 15 profiles re-swept, ledger-rebuilt, and `check_ledger_consistency.py --skip-
html` clean afterward.

## Ring-enchant coverage gap - CLOSED, 2026-09-07

Real correction found before starting: 2 of the originally-flagged 8 profiles (Shadow Priest,
Elemental Shaman) already had real, verified ring coverage - only 6 genuinely lacked it (Balance
Druid, Enhancement Shaman, all 3 Warlocks, Arcane Mage). Real, DB-sourced fix, not hand-researched
from Wowhead as originally planned - TBC's own sim DB (`sim/tbc-new/assets/database/db.json`)
directly confirmed 4 real Enchanting-only ring enchants (`requiredProfession: 3`) that no wowsims
preset itemizes but the sim engine DOES implement. All 6 profiles re-verified via the same
isolate-and-verify methodology as `verify_default_enchants.py` (sim decides, never a stat-weight
guess) - 5 casters picked "Enchant Ring - Spellpower" (+8.98 to +14.48 DPS), the 1 melee profile
(Enhancement Shaman) correctly picked "Enchant Ring - Stats" instead (+8.45 DPS). See NOTES.md's
2026-09-07 entry for the full per-profile table and the real candidate ids. The offhand/ranged
"gap" mentioned in this entry's original wording was never a real actionable one - a caster's real
offhand item and wand/ranged slot have no enchant in actual TBC, so their absence from
`default_enchants.json` is correct, not a coverage hole.

## Fresh-install "Run Report" doesn't start - REAL ROOT CAUSE FOUND AND FIXED (2026-09-07), not yet confirmed on a second machine

Reported live by the user (2026-09-06): installed the latest `RGT-Setup.exe` on a DIFFERENT machine
(not this dev machine) and clicked "Run Report" - the sweep never actually starts, and `simserver.exe`
(the persistent sim-worker process `adapters/tbc/simserver_client.py` is supposed to spawn) never shows
up in the process list at all. Not investigated or fixed yet - explicitly deferred by the user ("this
does not have to be fixed now but has to be kept in todos"). Real, plausible starting points for
whoever picks this up: check whether `build/bin/simserver.exe` actually landed in the fresh install's
payload (packaging/installer.iss's own `[Files]` list should include it via `..\build\bin\*`), whether
the fresh machine is missing some real runtime dependency the dev machine already has installed, or
whether `simserver_client.py`'s own spawn logic silently swallows a real startup failure without
surfacing it to the GUI. **Update, same day - reproduced on THIS dev machine too**: renaming an existing character's real
production-data folder (`%LOCALAPPDATA%\GearingTool\characters\<name-realm>\`, e.g. to
`Béarforceone-Thunderstrike_`) to simulate a genuine first-run/no-prior-data state reproduces the same
symptom here - real, useful, deliberately-induced repro, not something that needed the second machine
after all. Points toward something in the "character has never been run before" code path (first-ever
sweep for a character, or `simserver.exe`'s own startup/pool-init logic reacting badly to a missing
directory it expects) rather than a fresh-install/packaging gap specifically - worth checking
`adapters/tbc/simserver_client.py`'s spawn logic and whatever directory-creation assumptions exist
around a character's first real run, not just installer payload completeness. Still not investigated
further per the user's explicit "not now" - real next step whenever picked up: reproduce again with the
renamed-folder trick and get the actual stderr/exception, not just "it doesn't start."

**Update, same day - one real cause ruled out.** Ran a real, full CLI sweep (`python cli/gear.py best
"Béarforceone-Thunderstrike" phase1`) immediately after the user renamed her real folder to simulate a
missing/first-run state - the CLI path handled a genuinely-missing character folder fine, created a
fresh one, and completed the whole sweep with no error. This means the underlying sweep pipeline itself
(`core/run_upgrade_sweep.py`, `cli/gear.py`) does NOT choke on a missing character folder - the real bug
is more likely specific to the GUI's own path (`gui/api.py`'s `_run_report_job()`/background-job
handling, or `adapters/tbc/simserver_client.py`'s persistent process-pool startup specifically), not the
core sweep logic shared by both. Narrows where to look, doesn't fix it.

**Update, same day - real, more specific repro detail from the user**: even with every real directory
present (folders alone recreated), the bug still occurs - it only starts working once the real
`character.json` file itself is copied back in. Points specifically at something in the pipeline that
depends on `character.json` already existing (not just the containing folder) before `simserver.exe`/
the GUI's report job will actually start - worth checking `gui/api.py`'s pre-flight checks (does it
silently no-op or hang if `character.json` is missing, rather than surfacing a real error?) and
whether `adapters/tbc/simserver_client.py`'s own spawn is gated behind a successful character-data read
that fails quietly.

**Update, 2026-09-07 - real root cause found and fixed, reproduced directly (not guessed).**
`gui/api.py`'s `check_oom()` (runs synchronously, called by `app.js`'s Run Report click handler
BEFORE `run_report()` itself) called `oom_check.check()` with no error handling at all -
`oom_check.check()` reads `character.json` directly with no fallback, so a genuinely missing file
(exactly the folder-rename repro's own end state) raised an uncaught `FileNotFoundError` that
became a rejected JS promise with no try/catch on the click handler - `run_report()` (the only code
path that actually knows how to build/sync a missing `character.json`) was never reached at all.
Confirmed by directly deleting a real synthetic profile's `character.json` and calling
`Api().check_oom()` - crashed before the fix, returned a clean "not flagged" result after. Fixed:
`check_oom()` now catches any failure and falls back to "nothing flagged," since the OOM pre-check
is a pure nicety that should never be able to block Run Report from starting. See NOTES.md's
2026-09-07 entry for the full trail. **Left open, not closed**: this explains and fixes the exact
symptom already reproduced on THIS machine, but the ORIGINAL report was from a different machine
entirely - if that machine has some other, separate cause too (e.g. a real packaging/payload gap),
this fix wouldn't catch it. Close this entry only after a real test confirms Run Report now works
on a genuinely fresh install elsewhere.

## GearingToolCompanion addon: "All Characters"/main window text overlap - CLOSED, 2026-09-06

Flagged with a real screenshot, real root cause found (both windows centered at the exact same
screen position, none of the 3 real places that show either one hid the other first - see NOTES.md's
dated entry for the full trail), fixed (a missing `Hide()` call at all 3 toggle sites), and
**live-confirmed working by the user in-game**. Shipped as v1.0.3 - `CHANGELOG.md`/`.toc` bumped,
`packaging/build_addon_zip.py` re-run, live install re-synced.
