# Future Tasks

Deferred backlog items, moved out of `CLAUDE.md`'s Future Scope section (2026-08-31, per the
user - "the other 3 can be moved to a future tasks file, we will deal with those tomorrow or
Wednesday") so they don't clutter the active-work doc while #13 (multi-profile-per-class report
storage) is being built. Same rule as everywhere else in this repo: real content, not a stub -
each entry below is the full context needed to pick it back up cold, not just a one-line
reminder. Numbering matches CLAUDE.md's own backlog numbering (§ Staging / Future scope).

## #8 — Decomposed re-sweep caching (avoid full recompute after a raid week)

**Investigated in full, 2026-09-01, working autonomously overnight per the user's own standing
authorization ("plan both #7 and #8, build what works well, document what doesn't"). Conclusion:
the original framing no longer matches the current architecture, the real root cause is understood
and documented (matches CLAUDE.md's own prior "Stage 7" note), and a safe fix is NOT something to
build unsupervised overnight - real correctness risk to a component every report depends on. Not
implemented. Real findings below, so this can be picked up as a scoped decision rather than
re-derived from scratch.**

**Finding 1 - the original "joint search over shared-pool slots" premise is stale.** Re-read
`core/run_upgrade_sweep.py`/`core/optimizer.py` directly: `baseline_config` (the pool `P` in
`DPS*(P)`) is built by `opt.build_owned_config()` straight from the character's own currently
EQUIPPED items (gems/enchants optimized in place, per-slot) - there is no combinatorial search
happening to determine it, not today. `optimizer.py`'s own joint-slot search functions
(`trinket_pairs()`, `greedy_sweep()`, `set_bonus_branch()`, `full_bundle_branch()`) are real but
confirmed unused anywhere in the active pipeline (same "real code, no call site" status as
`interaction_matrix.py` - see #7's own resolution in CLAUDE.md). And backlog #16 (done
2026-09-01) already solved the actual "shared-pool slot" coupling problem a totally different way -
independent per-real-slot MV results, not a joint search - so this part of #8's original idea is
now moot, not just unbuilt. This also folds in the leftover tail of #7's own original idea
("extend the funnel to `optimizer.py`'s search") - there's no live `DPS*(S)` combinatorial search
anywhere in the active pipeline to extend a funnel into.

**Finding 2 - the real, remaining cost is `sim_cache`'s key granularity, matching CLAUDE.md's own
"Stage 7" note exactly.** The cache key is a hash of the FULL gear config (all ~17 slots), not
per-candidate. Every candidate's trial config = `baseline_config` with exactly one slot swapped, so
it embeds the entire baseline. The moment ANY slot in `baseline_config` changes (a real raid-week
gear change), literally every OTHER candidate's trial-config hash changes too, even candidates with
zero real relationship to the changed slot - so a re-sweep after gaining 1-2 items is close to a
100% cache miss on the next full sweep, not a targeted one. This is a genuine, measured cost
(15-20+ min full sweeps), confirmed real, not hypothetical.

**Why this isn't safe to fix unsupervised tonight.** The sim computes DPS from the FULL character
state - every slot contributes to the total stat pool (crit/hit/AP/haste/etc.), which can in
principle shift APL rotation choices and threshold effects for ANY candidate, not just ones in the
changed slot. A cache scheme that reuses a candidate's old cached MV across an unrelated baseline
change is only safe if that candidate's true MV is provably independent of the changed slot - and
that's a real, per-class, per-rotation claim (does Warrior's Rage economy near a haste breakpoint
actually not care about a new Ring's Agility? does Shaman's mana math not care about a new Trinket's
MP5?) that would need real verification per profile, not an assumption. This project's own ground
rules exist for exactly this failure mode: "never invent data," "noise honesty," "Sanity gate."
Shipping an unreviewed, unverified partial-cache-invalidation scheme into a component every
report's DPS numbers depend on, overnight, with no one awake to catch a subtle bug, is the kind of
risk this project has consistently avoided elsewhere (see e.g. how carefully backlog #16's real
collision risk was hunted down before, not after, shipping). Real, honest correctness risk beats a
faster sweep.

**Real alternative worth the user's consideration, NOT built tonight (different deliverable than
#8 originally asked for, so flagging rather than building unilaterally):** the actual underlying
motivation - "I got 1-2 items this week, what changed?" - doesn't strictly need a faster sweep at
all. `core/report_storage.py` (backlog #13) already keeps the PRIOR sweep's `reports.json` entry
per profile/phase; a "diff since last report" view (compare the new ledger's MVs per item_id
against the previous `ledger_data_<profile>_<phase>.json` for the same character/profile/phase,
surface what's new/changed) would serve the real want with zero cache-correctness risk, since it's
a pure display-layer comparison over two already-fully-computed, already-trusted ledgers - not a
shortcut inside the computation itself. Genuinely buildable in a future session if the user wants
it; not started.

**If the user wants the actual sweep-speed problem solved instead of routed around:** the honest
next step is proving real per-class independence bounds (which stat/slot changes a given profile's
own APL genuinely never branches on) before any cache-key change, one profile at a time - real,
substantial verification work, not a quick fix. Worth a real discussion before scoping further, per
this idea's own original "for discussion, not a plan" framing.

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

