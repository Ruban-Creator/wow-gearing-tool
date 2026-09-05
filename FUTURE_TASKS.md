# Future Tasks

Deferred backlog items, moved out of `CLAUDE.md`'s Future Scope section (2026-08-31, per the
user - "the other 3 can be moved to a future tasks file, we will deal with those tomorrow or
Wednesday") so they don't clutter the active-work doc while #13 (multi-profile-per-class report
storage) is being built. Same rule as everywhere else in this repo: real content, not a stub -
each entry below is the full context needed to pick it back up cold, not just a one-line
reminder. Numbering matches CLAUDE.md's own backlog numbering (§ Staging / Future scope).

## SmartScreen warning — revisit with a code-signing cert

Decided 2026-08-31: accept the Windows SmartScreen warning on `RGT-Setup.exe` for now (document
the "More info" -> "Run anyway" workaround, see `packaging/README.md`), rather than buy a
certificate immediately. `installer.iss` has zero code-signing configuration (confirmed via
direct grep) - a fully unsigned exe always gets SmartScreen's strongest warning, regardless of
download count. Real reminder, revisit once this ships more broadly:

- A standard cert (~$100-400/yr, e.g. DigiCert/Sectigo/SSL.com) removes the "Unknown Publisher"
  text but SmartScreen still needs weeks/months of real download reputation before the warning
  itself goes away.
- An EV cert (~$300-600/yr, usually a hardware token + business identity verification) is the
  only option that clears the warning immediately, from the very first download.

Not scoped or budgeted - a real cost decision for the user to make once the installer is being
distributed more broadly (currently pre-release, not yet published as a GitHub Release).

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

## #15 — Investigate the widespread `sources: None` DB gap (real raid tier sets across every class)

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

Not scoped or started - real, confirmed, worth doing at some point, not urgent (the practical
tier-bucketing symptom is already fixed).

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

