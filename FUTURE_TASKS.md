# Future Tasks

Deferred backlog items, moved out of `CLAUDE.md`'s Future Scope section (2026-08-31, per the
user - "the other 3 can be moved to a future tasks file, we will deal with those tomorrow or
Wednesday") so they don't clutter the active-work doc while #13 (multi-profile-per-class report
storage) is being built. Same rule as everywhere else in this repo: real content, not a stub -
each entry below is the full context needed to pick it back up cold, not just a one-line
reminder. Numbering matches CLAUDE.md's own backlog numbering (§ Staging / Future scope).

## #17 — CLOSED, 2026-09-06 - Feral Cat Druid's settings_template.json was stale, regenerated + verified

Found 2026-09-06 while auditing all 15 profiles for the enchant-fallback fix (see NOTES.md's dated
entry for the full story): regenerating her `settings_template.json` via `build_profile_settings.py`
produced a 923-line diff, dwarfing every other profile's 5-15-line enchant-only diff. Real cause,
confirmed before touching anything: her own `consumables.json` (real fields -
`battleElixirId`/`guardianElixirId`/sapper/scroll flags, matching the real historical fix already
documented for her - "Feral's own real presets.ts DefaultConsumables... flaskId->battleElixirId
+guardianElixirId swap") and her real vendored APL source had both changed since her
`settings_template.json` was last generated - it was simply never regenerated to match.

**Real fix, same day (commit `9b4aa63`)**: regenerated for real and verified - a real sim call
(2663.2 DPS, non-crashing), a fresh sweep, `check_ledger_consistency.py` clean (108/0).

**Follow-up drift found and fixed 2026-09-06 (later the same day, this session)**: the sim got
bumped v0.0.124→v0.0.130 (commit `91fd86e`) AFTER this regeneration, and nobody re-regenerated
Feral Cat Druid's settings to match - her vendored APL had picked up a real, new safety gate
(mana-cost checks against `spellId 768` = Cat Form, `sim/druid/forms.go`, guarding Engineering
trinket/potion usage so she doesn't get stuck unable to shift back into Cat Form) that her
settings file never got. Regenerated again, verified via a real sim call (2657.7 DPS) and a fresh
`check_ledger_consistency.py` pass. This is the same class of staleness as the original finding,
just recurring - worth remembering that ANY future sim bump can silently re-introduce this same gap
for any weave/APL-source-driven profile, not just a one-time fix.

## #18 — CLOSED, 2026-09-06 - Balance Druid's gem-choice verification gap, filled

Found 2026-09-06 while investigating a live Teeth of Gruul discrepancy (see NOTES.md's dated
entries). `core/gem_optimizer.py`'s `best_gems_for_item()` blanket-replaces every real socket with
the profile's primary stat gem UNLESS the item is in that profile's own `chase_bonus_gems.json` -
a real, deliberate, sim-verified policy for Survival Hunter specifically (37 real candidates
individually tested, 9 confirmed real exceptions where chasing the socket bonus wins). **Balance
Druid's own `chase_bonus_gems.json` was genuinely empty (`item_ids: []`)** - meaning none of her real
candidates had ever been individually verified this way; the "pure Spell Damage everywhere" choice
for her was an untested default, not a confirmed-correct one.

**Real fix, same day (commit `9b4aa63`)**: ran the same `core/verify_gem_choices.py` methodology
already used for Survival Hunter against Balance Druid's own real candidate pool - 23 real socketed
candidates tested, 8 confirmed real chase-bonus wins (Boots of Foretelling +9.6 DPS being the
largest), 1 tied, 14 clear pure-Spell-Damage wins. `chase_bonus_gems.json` populated with the 8
real, sim-verified exceptions. Whether this same empty-file gap exists for other profiles besides
Balance Druid was NOT checked - if a similar discrepancy surfaces for another profile, same
treatment applies.

## #19 — CLOSED, 2026-09-06 - Assumed raid buffs/party comp now surfaced directly in the rendered report

Per the user's own suggestion, 2026-09-06 (same investigation as #17/#18 - see NOTES.md): every
report currently computes DPS against a real, but SILENT, raid-composition assumption (which totems
are active, whether a Shadow Priest's mana return is modeled, etc.) baked into
`raid_buffs_overlay.json`/`_shared/raid_buffs_received.json` at settings-build time - a reader of
the report has no way to see what was assumed without reading source files. The user's own proposed
fix: add a real section to the rendered ledger showing exactly which raid buffs/party members were
assumed for that report, sourced directly from the real settings actually used (matching this
project's own "never hand-type what can be read from the real thing" convention, e.g. how the
footer's iteration-count line already reads real constants rather than hardcoded text) - not a
hand-maintained description that could drift out of sync.

Real, related context: a live, real audit of `shadowPriestDps` across all 15 profiles was done
today (Mage=1400, Priest/Warlock=0 matching wowsims' own defaults, Balance Druid/Elemental Shaman
corrected to 0 per the user's own real raid-strategy knowledge - boomkins group with 3 Warlocks + 1
Elemental Shaman, not a Shadow Priest). The user also shared real detail on other classes' typical
groups worth a fuller audit later if this feature surfaces more mismatches once built: Mage group
(1 Prot Pal + 2 Mages + 1 Shadow Priest + 1 Resto Shaman, or 3 Mages + 1 SP + 1 Resto - already
roughly matches `arcane_mage/raid_buffs_overlay.json`'s own real caster totems), melee group (1
Enhancement + 1 Warrior + 1 Feral + 1 Rogue + 1 Ret Paladin), Hunter group (ideally 1 Feral + 1
Enhancement + 3 Hunters, ideally all Beastmastery - "it really varies" per the user, sometimes 1 Arms
instead, Survival often unlucky and left in the unsupported healer group) - per the user's own
explicit policy decision, this tool should NOT chase each character's exact variable real placement,
it should assume the documented "optimal" comp and make that assumption transparent via this
feature, so a reader can judge for themselves whether it matches their real week.

**Real fix, same day (commit `9b4aa63`)**: built exactly as scoped - a new "Assumed Raid Buffs"
report section, sourced directly from the real settings file each sweep actually ran against
(`run_upgrade_sweep.py` reads it, `build_ledger_data.py` threads it through,
`report_template.html` renders it - never hand-typed). `check_ledger_consistency.py` gained a real
structural assertion for the field's pass-through and presence. (This session, 2026-09-06, later
the same day, the section was further redesigned from an inline `<details>` block into a header
stat-strip button + modal with real Wowhead tooltips on every buff/debuff chip - see NOTES.md's
dated entry.)

The fuller per-class raid-comp audit noted above (Mage/melee/Hunter group compositions) was not
done as part of this closure - only the Shadow Priest `shadowPriestDps` correction across all 15
profiles was. Re-open as a fresh, separately-scoped item if a future mismatch surfaces via this
new transparency feature.

## SmartScreen warning — revisit with a code-signing cert

Decided 2026-08-31: accept the Windows SmartScreen warning on `RGT-Setup.exe` for now (document
the "More info" -> "Run anyway" workaround, see `packaging/README.md`), rather than buy a
certificate immediately. `installer.iss` has zero code-signing configuration (confirmed via
direct grep) - a fully unsigned exe always gets SmartScreen's strongest warning, regardless of
download count. Not scoped or budgeted - a real cost decision for the user to make once the
installer is being distributed more broadly (currently pre-release, not yet published as a GitHub
Release).

**Real research done 2026-09-06 (this entry's original EV/OV framing above was WRONG, corrected
here, not just appended)**: per Microsoft's own current documentation, **EV certificates stopped
granting instant SmartScreen trust in a March 2024 policy change** - an EV-signed file now goes
through the exact same reputation-building process as any other signed file (weeks, hundreds of
clean downloads, no exact threshold). Paying EV pricing (~$300-600/yr) buys no SmartScreen
advantage over a cheaper option anymore - confirmed directly from Microsoft's own
`smartscreen-reputation` doc, not a third-party claim. What signing DOES still buy, at any
validation level: the warning shows a verified publisher name instead of "Unknown Publisher," and
the file/publisher can start accumulating reputation at all - an unsigned file never can.

**Real options, given the user is a self-employed (EPU) Austrian with an existing business
registration** - this matters because it opens Microsoft's own "Organization" identity-validation
path, which isn't available to a private individual outside the US/Canada:

1. **Azure Artifact Signing (formerly "Trusted Signing"), Microsoft's own recommended service for
   non-Store distribution** - Basic tier **$9.99/month** (~€110/yr, ~€550 over 5 years), 5,000
   signatures/month (RGT needs a handful per release). No hardware token needed - Microsoft holds
   the private key in their own FIPS 140-3 Level 3 HSM. Requires: a paid Azure subscription (not
   free/trial), a business website + monitored email on that domain, a "Business Identifier" (exact
   accepted format for an Austrian EPU without a Firmenbuch entry - Gewerbeschein number vs.
   Steuernummer vs. UID-Nummer - NOT confirmed, would need trying during actual signup), and a
   government-ID verification of the individual representative (AU10TIX, same process regardless of
   entity type). Processing: 1-20 business days. If billed with a valid Austrian UID-Nummer, Azure
   B2B billing normally reverse-charges VAT (0% charged by Microsoft, self-assessed on the
   business's own return) - not independently verified for this specific case, standard EU Azure
   practice.
2. **SSL.com's Individual Validated (IV) Code Signing Certificate** (third-party CA, doesn't
   require a registered business at all - explicitly marketed at hobbyists/open-source/students) -
   $129/yr (1-year) or ~$97/yr if prepaid as a "5-year" plan (~$484 total - really re-issued every
   458 days under the CA/Browser Forum's new March 2026 max-validity cap, not one single 5-year
   cert - confirm the actual renewal mechanic with SSL.com before prepaying). Still requires a
   FIPS-certified USB hardware token (~$30-70 one-time) OR their eSigner cloud-signing add-on
   (~$20/month per credential on top of the cert) - a hardware-key-in-some-form requirement is
   universal industry policy since June 2023, not specific to this provider or to OV vs EV.
   5-year total: ~$695 (annual renewal + token) or ~$534 (5-yr prepaid + token) - both more
   expensive than the Azure option, before EVEN accounting for eSigner's much higher ~$1,700+
   5-year total if avoiding the physical token.

**Given the user already has the business registration Option 1 needs, Azure Artifact Signing
(Basic, $9.99/mo) is the cheaper, simpler, no-hardware-token recommendation** - real numbers above,
not yet acted on. Still a real cost/effort decision for the user to make, not urgent while the
installer stays pre-release.

## #14 — Build the actual scheduled sim-update-checking agent/machine

`CLAUDE.md`'s "Sim update procedure" section is a real, already-tested RUNBOOK (every step was
actually run once, live, before being written down) - but it's still just documentation. Nothing
actually RUNS it on a schedule yet: no dedicated always-on machine, no real cron/scheduled-task
wiring, no agent actually watching `wowsims/tbc-new`'s tags daily and executing the runbook
end-to-end. Per the user (2026-08-31): plan and build this for real at some point - not scoped or
started yet, just confirmed as real, wanted infrastructure, not lost.

**Real design, attached and iterated 2026-09-06**: `ops/dedicated-agent-machine/claude-code-machine-setup.md`
- went through three real drafts the same day as understanding sharpened, kept here so the
reasoning isn't lost (all three were genuine, not wasted - see NOTES.md's 2026-09-06 entry for the
full trail):
1. Single Linux machine - wrong: it can cross-compile the sim's Windows binaries fine
   (`GOOS=windows GOARCH=amd64 go build` produces a real `.exe`) but can't RUN one to verify it
   works, since a `.exe` needs a real Windows environment to execute.
2. Two machines (a new Linux "Watcher" + the user's own existing production Windows PC as
   "Verifier") - workable, but coupled the whole pipeline to that PC's uptime, which the user
   flagged directly ("my windows production machine might not be running when a new version is
   built").
3. **Final design: ONE new, dedicated Windows machine does the entire runbook itself** (check,
   build, verify, merge, push) - the user's own real correction ("isn't it better to have the dev
   machine be Windows instead of Linux?"). No dependency on any other machine's uptime; the
   `.exe`-hardcoded paths in `adapters/tbc/adapter.py`/`simserver_client.py`/`valuation.py` need no
   code fix at all, since this machine was always going to build real Windows binaries natively.

**Real current hardware state: only the original Dell OptiPlex 3050 Micro (i5-7500T, 7th-gen) is
actually on hand** - no replacement has been bought. Windows 11 does genuinely run on this via a
well-known, routine one-time install bypass (the real tradeoff is Microsoft not formally
guaranteeing updates on unsupported hardware indefinitely, not "it won't work" - a correction to
this session's own first, overstated framing) - a real, reasonable way to start today on what's
already owned. An HP EliteDesk 800 G6 Mini (10th-gen Intel, officially Windows-11-supported, a
real ~€259 refurbished listing found and checked) is a real, verified option to consider if/when
buying new hardware instead - not a decision that's been made.
Windows install goes through Microsoft's own official download page - not Windows 11 IoT
Enterprise LTSC (checked and ruled out: not a normal individual download) and explicitly not any
third-party "debloated" ISO (unverified modified system images - a real risk for a machine holding
this repo's GitHub credentials). Debloated using only Microsoft-supported mechanisms. Missed
scheduled runs catch up automatically via Task Scheduler's own "run as soon as possible" option, so
the machine doesn't need to be on 24/7. No GUI needed anywhere in this - every real step is a CLI
tool.

Not built yet - the guide is real and detailed end to end (hardware pick through BIOS prep,
Windows install/debloat/SSH, toolchain, the one consolidated `run_sim_update.ps1` job, Task
Scheduler wiring, guardrails), but no physical machine has been set up against it yet, and the
script itself hasn't been tested against this real repo end to end - real next step whenever
picked up, not a re-design.

## #15 — CLOSED, 2026-09-06 - Investigated the widespread `sources: None` DB gap (real raid tier sets across every class)

Found 2026-08-31 while diagnosing a live bad report (see NOTES.md's dated entry for the full
story) - confirmed via a direct DB query that 200+ real item sets across every class have
`sources: None` for every single piece, including real raid tier sets (Skyshatter/Cyclone/
Thunderheart/Lightbringer/Malefic/Onslaught/Gronnstalker's/Vestments of Absolution/Bonescythe,
and more - not an exhaustive list). A real, DB-derived phase-based fallback (`PHASE_TO_TIER_ZONE_KEY`
in `core/run_upgrade_sweep.py`) already fixes the practical symptom - these items now bucket into
their correct real tier instead of "Other" - but the underlying gap (no real drop
boss/zone/npc known for any of these items) is still real and unfixed at the source.

This isn't something fixable locally - the sim's own DB is built from a real WoW client's data
files (`db2tool`/`gen_db`, see `CLAUDE.md`'s "Local setup" section), and boss loot-table data was
never part of that client-side data to begin with, so there's no local rebuild that would recover
it. Real options, per the user's own question ("is there any way we can fix the Sources?"):
- Report it upstream to `wowsims/tbc-new` as a real, verified gap (it's open source) - would need
  each item's real source individually verified (e.g. against Wowhead) before submitting, not
  bulk-guessed from general TBC knowledge.
- Maintain a small local overlay file in this repo mapping item_id -> real, individually-verified
  source data for the items this tool's own profiles actually surface - same verification bar.
- Per the user's own suggestion: fold periodic re-checking of this gap into #14's future
  sim-update agent, once that exists - each time it checks for a new wowsims release, it could
  also check whether upstream has filled in any of these previously-missing sources.

**Update, 2026-09-06: fully covered, not "not scoped" anymore.** See the two entries below (the
tier-token structural rule + the individually-verified overlay) - between them, **0 of the current
163 unique gap items remain unresolved** (all resolve to something other than "Source unclear"),
confirmed by directly re-running `describe_source_and_tier()` against every unique item id in
`check_missing_sources.py`'s current output. `check_missing_sources.py` itself will still report
255 references / 163 unique items regardless (it measures the raw DB gap, not this tool's own
coverage of it - it doesn't know about the overlay or the tier-token rule) - that's expected and
correct, not a regression to chase. The "report it upstream to wowsims" option above is still real
and not pursued; folding periodic re-checks into #14's future sim-update agent is also still real
and not started.

**Scoped down to what this tool actually surfaces (2026-08-31)**: the 200+ DB-wide figure above
counts every real item set regardless of whether this tool ever shows it (most are PvP/honor sets,
where `sources: None` is correct, not a gap). New `core/check_missing_sources.py` (pure DB/file
reads, no sim calls - safe to run any time, including while a real sweep or the game itself is
running) checks specifically each of the 15 real profiles' own `candidate_pool.json` +
`reference_bis/*.json` item lists against the DB. Real result: **255 items across all 15 profiles**
have `sources: None` - every profile is affected (7 for Retribution Paladin, the fewest; 36 for
Survival Hunter, the most - roughly proportional to candidate-pool size, not evenly spread). Most
are real raid-tier gear (matches the pattern already found: Skyshatter/Cyclone/Onslaught/
Gronnstalker's/Thunderheart/Voidheart/Malefic/etc.), a handful are real arena weapons (e.g.
Gladiator's Slicer, Merciless Gladiator's Quickblade/Maul) where `sources: None` is likely
*correct* (arena/honor purchases have no real "drop" location) rather than a gap - worth excluding
those specifically before any upstream report or overlay file, not lumping them in as "missing."
Re-run `python core/check_missing_sources.py` any time for the current, real, full per-profile
list - not reproduced item-by-item here since it's long and would drift out of date; the script is
the live source of truth.

**Started for real, 2026-09-06**: the local-overlay option above is now real, working code, not
just an idea - `profiles/tbc/_shared/source_overlay.json` (new) + a small hook in
`core/run_upgrade_sweep.py`'s `describe_source_and_tier()`, checked BEFORE the phase-bucket
fallback but only ever reached AFTER a real DB source has already come back empty - an overlay
entry can never override real DB data, only fill a gap the DB genuinely has none for (verified
directly: the DB-source check-loop returns early on any real source, so the overlay code is
structurally unreachable when real DB data exists, not just conventionally so). Per the user's own
explicit requirement: "our sourcing should always only be a fallback if no source in the wowsims
db exists."

**Major real progress, same day - a structural tier-token rule covering 111 of the 255 items.**
Started from 3 individually-verified entries (Onslaught Battle-Helm/Thunderheart Headguard/Band of
Crimson Fury), which revealed a real, general mechanism once checked against 11 different tier-set
families spanning every real raid tier: **every real TBC raid tier set is acquired via a
boss-dropped TOKEN turned in to a real vendor, never a direct drop of the finished piece** - T4
tokens (Karazhan's Prince Malchezaar for most pieces, confirmed a DIFFERENT token from
Magtheridon's Lair's own boss for at least Justicar) go to Asuur/Arodis Sunblade in Shattrath City;
T5 tokens go to Kelara/Veynna Dawnstar, also Shattrath City; T6 tokens (per the user's own real
confirmation) drop inside Black Temple/Hyjal itself, turned in to Tydormu. This is exactly why the
DB's own `sources[]` schema (only drop/crafted/rep) has nothing for any of them - the mechanism
itself doesn't fit any of those three categories.

Implemented as a real, structural rule in `core/run_upgrade_sweep.py` (`_TIER_TOKEN_DESC`/
`_SET_MIN_PHASE`), not per-item entries: any item with a real `setId` gets tiered by the MINIMUM
real phase across every piece sharing that set (several real T6 sets have pieces itemized at both
phase 3 and phase 5, but they're still one real set from one real raid) and described with its
real tier's token/vendor text. Covers **111 of the 255 real gap items** across ~30 distinct
tier-set families - verified directly against real DB items (including the phase-3/phase-5 split
case) and via `check_ledger_consistency.py` (clean on multiple real profiles). 19 of the ~30
families were individually confirmed on Wowhead before its CDN started real rate-limiting further
lookups (CloudFront 403s, not a content problem) - the rest are covered by the same
now-cross-class-confirmed mechanism, not per-item guessing. The 2 tier-set overlay entries from the
first pass (Onslaught/Thunderheart) are now redundant under this broader rule and were removed -
the general rule gives an even more specific, accurate description than the original per-item ones
did.

**Also added, per the user's own suggestion**: a real, STRUCTURAL rule for PvP gear - any item
whose real DB name contains "Gladiator's" is PvP-sourced, a 100% reliable Blizzard naming
convention across every arena season. Confirmed 6 of the 255 real gap items match this - tagged
"PvP purchase (Arena/Honor)," deliberately not claiming "Arena" specifically since a season's
Gladiator's gear becomes plain honor-purchasable once a later season replaces it (a real correction
the user caught in an earlier draft of this label).

**Real remaining scope: ~137 items** (255 minus 111 tier-token minus 6 Gladiator's minus 1
quest-reward overlay entry) - all real, standalone accessories (rings/trinkets/necks/cloaks/
weapons/misc) with no reliable structural tell, genuinely needing one-at-a-time Wowhead
verification. **Paused mid-pass by Wowhead's own rate limiting** (2026-09-06) - 43 of these were
already identified and queued (see NOTES.md's dated entry for the real list) before lookups started
returning CloudFront 403s; real next step is resuming those lookups once access clears, not a
re-design. Per the user's own suggestion, folding periodic re-checking into #14's future sim-update
agent (once built) still stands as the long-term maintenance plan (already added as a real runbook
step in CLAUDE.md's own "Sim update procedure"); reporting the schema gap upstream to
`wowsims/tbc-new` is still a real, separate, not-yet-done option. Note: `check_missing_sources.py`
itself will keep reporting all 255 regardless of this progress - it measures the DB's own raw gap,
not this tool's improved ability to describe it; that's expected, not a regression.

**Real completion pass, 2026-09-06 (second session the same day): the rest of the 43-item queue
finished.** Of the 43 items NOTES.md's first pass had identified and queued, 6 (Icon of the Silver
Crescent/29370, General's Silk Cuffs/28411, Talisman of Kalecgos/29271, Violet Signet of the
Archmage/29287, Shapeshifter's Signet/30834, Idol of the Raven Goddess/32387) were already verified
and in the overlay before this pass started, and 1 (Band of Eternity/29294) had been spotted and
confirmed during that session's own pattern-sampling but not yet formally recorded - added directly
this pass, per the user's own instruction, with no re-check needed. The remaining 36 were
individually checked against Wowhead this pass (Browser tool's `get_page_text()` against a live
page, never WebFetch, never bulk-guessed, same bar as every prior entry) - **33 added to the
overlay, 3 deliberately excluded** (see below). Real per-item source categories found: the large
majority are Badge of Justice vendor purchases from G'eras (Shattrath City, phase 1) or the two
phase-5 Isle of Quel'Danas armorsmiths (Yrma / Anwehu / Smith Hauthaa); the rest split across quest
rewards (several distinct quest chains - Fall of Magtheridon, Special Delivery to Shattrath City,
Fel Embers, Varedis Must Be Stopped, Teron Gorefiend I am..., Kael'thas and the Verdant Sphere, and
the Caverns of Time "Band of Eternity" ring-chain siblings Sage's/Champion's Covenant), 4 real
world-boss/event-boss drops from 3 distinct bosses (Doom Lord Kazzak dropping 2 of the queued
items, Doomwalker, Coren Direbrew - the last a real Brewfest holiday-event boss in Blackrock
Depths, not a raid), and 1 real PvP-honor purchase item
whose name does NOT contain "Gladiator's" (Vindicator's Dragonhide Bracers - the existing
name-based structural rule correctly does not fire for it, confirmed instead by individually
verifying it, exactly the "still needs one-at-a-time checking" case that rule was never meant to
cover).

**Real, deliberate exclusion, not an oversight**: 3 of the 36 (Elementalist Bracelets/24692,
Mask of Veiled Death/31281, Pathfinder's Band/31277) were
checked and found to be genuine random world-drop BoE items with 37-200 real, roughly-equal-odds
mob sources apiece (ordinary Outland leveling trash, not one specific boss) - forcing any one of
those sources into the overlay's `"Drop: <boss> (<zone>)"` convention would misrepresent a diffuse
drop table as a single reliable source, which is worse than leaving the item undescribed. Left out
of the overlay entirely; still genuinely `sources: None` in the DB and still bucketed by the
existing phase fallback, same as before this pass.

**Corrected, 2026-09-06 (this exact "~97 remaining" text was stale and got restated to the user in
chat before being caught and recomputed - see NOTES.md's dated entry for the real mistake and
correction): 0 items remain unresolved, not ~97.** Directly recomputed by calling
`describe_source_and_tier()` against every one of the 163 unique item ids in
`check_missing_sources.py`'s current output: all 163 resolve to something other than "Source
unclear" (111 via the tier-token rule, 6 via the Gladiator's rule, the rest via
`source_overlay.json`'s individually-verified entries). `check_missing_sources.py` will still
report 255 references / 163 unique items regardless (it measures the raw DB gap, not this tool's
coverage of it - it has no knowledge of the overlay or the structural rules) - that's expected,
not a regression to chase.

## #20 — CLOSED, 2026-09-06 - Shared-pool Weapon slot produced nonsensical MVs when real current gear is 2H but the profile's own topology is dual_wield

Found 2026-09-06, live, real user report: Lerynia (Survival Hunter, `weapon_topology: "dual_wield"`)
had genuinely re-geared in-game to a real 2H weapon (Halberd of Desolation, mainhand) with a real,
empty offhand - her `character.json` just hadn't been re-synced yet (fixed via `python cli/gear.py
sync`, unrelated one-off data-staleness issue, see NOTES.md). Once the sweep ran against her real,
current 2H-equipped state, the Weapon tier list showed EVERY 1H weapon candidate in the entire pool
- Vanilla carryover daggers included - as a `best_slot: offhand` real upgrade worth 16.5 to 80 DPS.

**Root cause, confirmed**: candidates route into the shared "mainhand"/"offhand" pool unconditionally
for a dual_wield-topology profile, regardless of what's ACTUALLY in the other slot right now. With
her real mainhand holding a 2H weapon and her real offhand genuinely empty, testing "candidate 1H
weapon in offhand" against her real baseline compares "2H mainhand + empty offhand" (baseline)
against "2H mainhand + a 1H weapon in offhand" (trial) - a gear state that isn't legal in the actual
game. Every 1H candidate looked like a huge upgrade purely because the baseline's offhand was empty.

**Correction to this entry's own earlier draft (same day)**: the first version of this writeup also
claimed the separate "2H Weapon Options" side-section had a mirror-image bug (comparing 2H candidates
against a hypothetical best-dual-wield baseline instead of her real current 2H weapon). That claim
was WRONG - caught before shipping a fix for it, by actually re-reading the code instead of trusting
the previous night's own analysis (see the new `feedback_verify_against_source_not_summary.md`
memory this exact kind of mistake prompted). `two_hand_meta`'s `no_weave_dw`/`weave_dw` are computed
by evaluating settings against `baseline_config` directly - which already reflects her REAL current
gear (2H, when that's real), never a hypothetical. The section's real, empty `two_hand` list for
Lerynia wasn't a bug at all - it correctly found no 2H candidate in her pool beats her actual current
Halberd of Desolation. Melee-weave itself doesn't require an offhand either (Raptor Strike swings
whatever's in mainhand) - `weave_dw`'s real, nonzero delta over `no_weave_dw` while genuinely
2H-equipped is a legitimate number, not evidence of a hidden dual-wield assumption.

**Real fix, implemented**: two SEPARATE candidate-building paths both needed the same gate, which is
exactly why the first attempted fix (only in `optimizer.py`'s `load_candidates()`) had ZERO visible
effect on a live resweep - nearly every real "Weapon" tier row comes from `run_upgrade_sweep.py`'s
own full-DB sweep-additions loop (every DB item not already in the curated candidate pool), which
builds its own `Candidate` objects directly, bypassing `load_candidates()` entirely. New shared
helper `optimizer.real_gear_is_two_hand_mainhand(owned_items)` (true iff her real, currently-equipped
mainhand item has `handType == HAND_TWOHAND`), called from both places - a 1H candidate destined for
the shared dual-wield pool is now excluded (`excluded_reason` in `load_candidates()`, a plain `continue`
in the sweep-additions loop) whenever this is true. Verified live: Lerynia's Weapon tier list now
shows 0 candidates (down from 92 nonsensical ones), achieved_bis correctly shows her real Halberd of
Desolation, `two_hand`/`two_hand_meta` unchanged (already correct, per the correction above).
`check_ledger_consistency.py` clean (130/0, down from 1171/0 - the flood of nonsense candidates was
itself inflating that count). Regression-checked against Test-Beastmastery-Synthetic (genuinely
dual-wielding, `real_gear_is_two_hand_mainhand()` correctly returns False, unaffected) and confirmed
by construction that every other `weapon_topology` never reaches this check at all (no profile
besides Survival/Beastmastery Hunter ever has a "weapon_dual_wield"/"weapon_dual_wield" pool key or
slot in the first place).

**Rejected by the user as incomplete, same day: "No partial fixes today WE have to compare dw to
2hand No Matter what the starting point is."** Silently excluding the nonsensical 1H candidates (the
fix above) stops the false "upgrade" numbers but never actually answers "would dual-wield beat my
current 2H weapon" when she's really 2H-equipped - exactly the mirror-image of the question the
existing "2H Weapon Options" section already answers when she's really dual-wielding. Real, complete
fix, same day: a new "Dual-Wield Alternative" analysis, gated on
`profile["weapon_topology"] == "dual_wield" and real_gear_is_two_hand_mainhand()` (the topology check
itself was a real bug caught before shipping - the original version ran for EVERY profile, which
would have incorrectly fired for Balance Druid's own real, legitimate "2H staff some phases"
alternative, whose "offhand" is an unrelated single-item pool, not a dual-wield weapon slot; not
actually triggered today since her current mainhand happens to be 1H, but a real latent bug
regardless).

Every 1H weapon candidate that would have hit the old nonsensical path (curated pool AND full-DB
sweep additions - `dw_pair_candidates`) now feeds a real, bounded, sim-based greedy search instead of
a full pairwise combinatorial one (weapon-pair interactions beyond additive stats are rare, matching
this project's own established "screen cheap, verify the winner for real" discipline): screen every
real mainhand-eligible candidate alone (offhand empty) to find the best one, then screen every real
offhand-eligible candidate against THAT fixed mainhand to find the best pairing, then resolve the
winning pair AND her real current 2H baseline at full precision - for a weave-capable profile, both
weave-on and weave-off variants, since melee weave never actually required dual-wielding to begin
with (Raptor Strike swings whatever's in mainhand, confirmed while building this).

**Real, live result for Lerynia**: best achievable pair (Blade of the Unrequited + Claw of the
Phoenix) is a genuine, if small, **+4.6 DPS upgrade over her current 2H with no melee weaving** - but
a massive **-453.6 DPS** if she's actually weaving (her 2H's much higher per-swing weapon damage
dominates once Raptor Strikes are actually landing) - a real, decisive, mechanically-sound answer,
not a tie either way. New `dual_wield_alt` field (tiered_report/ledger_data), rendered as its own
"Dual-Wield Alternative" report section (independent of the existing "2H Weapon Options" section,
which can be simultaneously empty - that only means no OTHER 2H beats her current one, a separate
real question). `check_ledger_consistency.py` gained real structural assertions for this field.
Verified clean end to end (Lerynia 132/0 including a full HTML-splice check, Test-Beastmastery-
Synthetic 150/0 with `dual_wield_alt: null` as expected for a genuinely dual-wielding character).

## #21 — CLOSED, 2026-09-06 - real, unexplained magnitude gap between this tool's own sim and wowsims.com for at least one real item (Mindstorm Wristbands, Balance Druid)

Found 2026-09-06 during the wrist-enchant investigation (see NOTES.md's dated entry for the full
trail). After fixing two real, confirmed bugs this same day (`build_owned_config()`'s enchant
priority - her real, already-applied enchant must win over a curated "BiS" one, not the reverse;
and filling in Balance Druid's real, missing wrist entry in `default_enchants.json`), our own sim
agrees with the user's real wowsims.com test on DIRECTION for swapping Crimson Bracers of Gloom ->
Mindstorm Wristbands (both enchant 369, matching exactly what the user's own websim JSON specified):
our sim says **+1.53 DPS**, wowsims.com says **+17.31 DPS** - same sign, but an ~11x magnitude gap
that has NOT been root-caused. (For reference: with our own curated default enchant on the candidate
instead of matching hers exactly, our sim actually says -7.94 DPS - a real downgrade, matching the
achieved-BiS classification the live report shows - so which of these three numbers is "the real
answer" depends entirely on which enchant policy question is being asked; #21 is specifically about
the still-unexplained gap between our +1.53 and wowsims.com's +17.31 for the SAME enchant on both
items, not about the enchant-policy question itself.)

**Update, same day - most (not all) of the gap explained.** Re-ran the exact same Crimson Bracers ->
Mindstorm Wristbands (both enchant 369) comparison with `shadowPriestDps` forced to `800` (the
user's own exact websim test value, wowsims' own generic default - vs this profile's own corrected
`0`, per the real Boomkin-raid-comp finding from earlier the same day): delta jumped from **+1.53
DPS to +11.56 DPS**. That closes most of the gap to wowsims.com's own **+17.31** (11x gap down to
~1.5x) - confirms `shadowPriestDps` materially amplifies a spell-damage/crit item's marginal value
(more mana headroom -> more casts spent capitalizing on the extra damage), not just a flat additive
raid-DPS number. This does NOT mean this profile's own `shadowPriestDps: 0` is wrong - that value
was independently confirmed correct for Balance Druid's real raid comp (3 Warlocks + 1 Elemental
Shaman, no Shadow Priest, per the user's own raid-strategy knowledge) - it means the wrist MV THIS
TOOL reports (whatever it resolves to under the correct `0`) is answering a different, correct-for-
THIS-raid question than wowsims.com's own generic-preset comparison, and the two were never
expected to match exactly once buff assumptions differ.

**Update, same day - a full field-by-field diff found more real mismatches, none of which closed the
gap (several made it slightly worse).** Diffed the user's real websim JSON (the one with the full
TypeAPL rotation, not the TypeAuto one from the very first test) against this profile's real
`settings_template.json` field by field, not just spot-checked: found real differences in
`raidBuffs.shadowProtection`, several `debuffs` (`exposeWeaknessHunterAgility`/`exposeWeaknessUptime`/
`faerieFire`/`insectSwarm`/`judgementOfLight`), `partyBuffs` (`ferociousInspiration`/totem fields),
and `player.buffs` (`blessingOfMight`/`blessingOfSalvation`/`unleashedRage`) - all real, genuine
assumption differences, but re-testing with EVERY one of them matched to the websim JSON (on top of
the already-matched `shadowPriestDps: 800`) gave **+10.59 DPS - slightly LOWER than the +11.56 from
matching shadowPriestDps alone**, not closer to wowsims.com's +17.31. Rotation itself (priorityList/
prepullActions/valueVariables) confirmed byte-identical between ours and theirs - not the cause
either. Real conclusion: none of these settings differences explain the residual gap; ruled out as a
category, not just unconfirmed.

**Update, same day - pursued the sim-version-difference theory for real, not left as a guess.**
Checked how current the pinned submodule commit actually was: **v0.0.124 (2026-08-30), 6 real
releases behind v0.0.130** - a strong, concrete lead. Followed CLAUDE.md's own "Sim update
procedure" runbook in full (see NOTES.md's dated entry for the complete real execution: risk
assessment, submodule bump, protobuf regen, binary rebuilds, stale-process cleanup, import sweep,
live sim calls across all 3 real weapon topologies, `check_ledger_consistency.py` clean for every
real character, enchant/gem re-verification for Balance Druid) - committed and pushed as its own
real, verified change, independent of this investigation.

**Re-tested the exact same comparison under v0.0.130**: Crimson Bracers -> Mindstorm Wristbands
(enchant 369 both sides, `shadowPriestDps: 800`) now gives **+13.77 DPS** (up from +11.56 under
v0.0.124) - real, meaningful movement in the right direction, closing roughly a third of the
remaining gap to wowsims.com's own +17.31 (1.5x gap down to ~1.26x). Confirms the sim-version-drift
theory was real and load-bearing, not a dead end - but a real, smaller residual gap (+13.77 vs
+17.31, ~20%) still remains even now.

**Update, 2026-09-06 (later the same day) - real root cause found: the methodology, not the sim
engine.** Triggered by the user asking "encounter duration?" - a field the field-by-field diff above
never actually checked. Found the user's own real websim JSON exports still saved in that session's
scratchpad: `user_websim_v2.json` (the one already confirmed byte-identical rotation) has
`encounter.duration: 240`, not our profile's default 180 - never checked before. More importantly,
every prior test in this investigation manually patched individual fields onto BÉARFORCEONE'S OWN
real settings/gear, one at a time - running `user_websim_v2.json` **directly, as its own complete,
self-contained settings blob** (its own real gear/talents/consumables, not patched onto ours) gives
Crimson Bracers -> Mindstorm Wristbands a real **+16.02 DPS** at its own real duration (240), and
**+19.36 DPS** at duration forced to 180 - both dramatically closer to wowsims.com's own +17.31 than
the prior best result (+13.77). Consumables checked too (per the user's own follow-up) - v2's
`potId`/`flaskId`/`foodId`/`conjuredId`/`mhImbueId` are byte-identical to
`profiles/tbc/balance_druid/consumables.json`; ruled out.

**Real, honest remaining residual**: +16.02 (ours, duration matched) vs +17.31 (wowsims.com) is a
real ~7.5% gap, still outside this run's own 2-sigma noise band (noise_stdev 0.48) - not fully
closed. But the dominant lesson is real and important: the earlier "~1.26x unexplained gap" was
mostly an artifact of computing deltas against two DIFFERENT real baselines (our character's real
gear/talents vs. the websim JSON's own separate real gear/talents), not a genuine sim-engine
calculation discrepancy - this tool's own core principle (MV depends on the FULL set P, never an
isolated swap) turned out to apply across two different real characters' P too, not just within one.
Duration=180 (+19.36) bracketed wowsims' +17.31 from above while duration=240 (+16.02) bracketed it
from below - both closer than the old mismatched-baseline comparison, so duration has a real but
modest, non-dominant effect here, not the single root cause either.

Not chased further that day - the remaining ~1.3-2 DPS gap was small enough that sim-version drift
(wowsims.com's live site deploys off `master` continuously on every merge, confirmed separately via
their own GitHub Actions "Build and Deploy" workflow - real commit `a176edf` is live on production
but not yet in any tagged release, though that specific commit - an armor-damage-reduction cap for
damage TAKEN - doesn't explain a caster's own outgoing-damage gap) or some other minor,
still-unidentified difference seemed plausible.

**Final update, 2026-09-06 (later the same day) - CLOSED for real.** The user pulled a fresh live
"Swap" comparison directly from wowsims.com's own Results panel for this exact item swap (two
screenshots with full per-spell breakdowns, real DPS 1362.43/1343.17, delta **+19.26 DPS**) and
pasted the two underlying JSON exports. Real, decisive difference from the prior best test: this
fresh export's `encounter.duration` is **180** (matching our own profile's default exactly) - the
earlier `user_websim_v2.json` capture used for the "~7.5% residual" conclusion above was apparently
a slightly different/stale settings snapshot from an earlier point in the investigation, not the one
actually underlying the live comparison being chased. Running this fresh export directly (again as
its own complete settings blob): Crimson Bracers **1414.50**, Mindstorm Wristbands **1433.69**,
delta **+19.19 DPS** (noise_stdev 0.58) - matching wowsims.com's own **+19.26** to within **0.07
DPS**, fully inside the noise band. A theory floated mid-chase (that the fresh export's
`rotation.type: "TypeAuto"` needed relabeling to `TypeAPL` before our sim would run it) was directly
tested and DISPROVEN - reverting only the `type` field back to `TypeAuto` gave an identical result;
the type label doesn't gate execution, only whether real `priorityList` content is actually present
in the export does (a genuinely bare `{"type":"TypeAuto"}` export, never opened in wowsims' own
auto-rotation UI before exporting, has nothing for our sim to run - a different, narrower gotcha than
first suspected).

**Real, closing assessment**: started as an apparently-unexplained 11x magnitude gap. Every real
cause found across the whole investigation traced back to a settings/methodology mismatch, never a
sim-engine defect: (1) `shadowPriestDps` materially amplifying a caster's spell-damage MV (a real
buff-assumption difference, not a bug), (2) sim-version drift (v0.0.124->v0.0.130, closed roughly a
third of the gap), (3) computing deltas against two DIFFERENT real character baselines instead of
one self-contained settings blob (the dominant cause - this tool's own MV-depends-on-the-full-set
principle applies across characters too, not just within one), and (4) simply using the correctly
freshly-captured settings snapshot (matching duration) instead of an earlier, slightly-stale one.
No further action needed - re-open only if a NEW, similarly-sized gap surfaces on a different item.

