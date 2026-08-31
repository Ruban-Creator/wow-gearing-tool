# Future Tasks

Deferred backlog items, moved out of `CLAUDE.md`'s Future Scope section (2026-08-31, per the
user - "the other 3 can be moved to a future tasks file, we will deal with those tomorrow or
Wednesday") so they don't clutter the active-work doc while #13 (multi-profile-per-class report
storage) is being built. Same rule as everywhere else in this repo: real content, not a stub -
each entry below is the full context needed to pick it back up cold, not just a one-line
reminder. Numbering matches CLAUDE.md's own backlog numbering (§ Staging / Future scope).

## #7 — Three-tier funnel: 4th "confirm@5000" tier + extend to `core/optimizer.py`

Idea collection #2 from CLAUDE.md (2026-08-23). Prompted by watching Stage 5's interaction matrix
take ~15-20 minutes on Lerynia's already-narrow Phase 3 pool once the candidate-selection fix
widened it. The user's real concern: a FRESH LEVEL 70 CHARACTER STARTING IN PHASE 5 has every item
from Phases 1-5 simultaneously live as a real candidate for every slot at once - the pool this
tool would need to search is enormously bigger than "one already-decently-geared character's Phase
3 upgrade list," and it still needs to finish in a reasonable time. Rough shape, matching the
existing prefilter principle (a cheap pass may only ever prune what gets the expensive treatment,
never BE the reported number) but formalized as three explicit tiers instead of one screen/resolve
split:

1. **Pre-screen** - something cheaper than today's 1000-iteration screen, to cut an enormous raw
   pool (every phase's items at once) down to a manageable shortlist before spending even a cheap
   sim run on each one. Not yet decided whether this should be a real (very-low-iteration) sim
   call or a static EP-based prefilter using `STAT_WEIGHTS` - the ground rules already sanction EP
   as a legitimate prefilter heuristic, just never as a reported number. User's concrete proposal:
   100 iterations for this tier - real SEM math checks out (the sim's own player_stdev was ~74 at
   1000 iterations in the user's own test, so SEM ≈ 74/√100 ≈ 7.4 DPS at 100 - noisy, but only
   affects which pairs get promoted to the next tier, never a reported number, so the tradeoff is
   real but bounded).
2. **Screen** - the user's proposal: 500-1000 iterations (matches today's existing
   `SCREEN_ITERATIONS`), applied to whatever survives step 1.
3. **Finalize** - resolve only the top ~3 candidate FULL SETS (not top individual items or pairs)
   at high precision. Confirmed by the user checking the actual wowsims web UI (Hunter,
   incognito, default "Iterations" field): the sim's own real default is **25000**, not 12.5k -
   that recollection was off, caught by checking rather than assuming. If this tier ever gets
   built, 25000 is the real, verified reference point to weigh against this tool's own 30000, not
   a guessed number.

**Status: tiers 1-2 are actually built**, not just an idea anymore - `core/interaction_matrix.py`'s
`compute()` runs a real 3-pass funnel: pre-screen @100 → screen @1000 → resolve @30000, each stage
gating whether a pair gets promoted to the next. (Per CLAUDE.md's own note, `interaction_matrix.py`
itself is currently unused - Stage 5's pairwise interaction matrix was dropped from the active
pipeline 2026-08-23, replaced by the cheaper rescue_check pass. The module stays in git history.)

**Real, controlled A/B data** (10 real items, mixed magnitudes, same seed, cache cleared for a
clean timing comparison) settled the "is 30k worth it" question concretely rather than by
argument:

| iterations | time/item | verdict vs the 30k reference |
|---|---|---|
| 100 | 0.25s | unreliable - 6 of 10 disagreed, confirms pre-screen-only use |
| 1000 | 0.40s | 1 of 10 disagreed (a razor-thin +1.3 DPS real effect) |
| 5000 | 1.04s | same 1 of 10 disagreed - every clear-magnitude item (±7 to ±51 DPS) matched 30k exactly |
| 30000 | 5.33s | reference |

Conclusion: 5000 is NOT safe as the final reported number (noise-honesty is a hard rule, and it
missed exactly the case that matters - a small-but-real effect near the noise floor), but it's
strong evidence for a 4th, intermediate "confirm @5000" tier between screen and finalize, since it
agreed with 30k on every item that had a real, decision-relevant magnitude. **Not yet built.**
Earlier in the same original session, a single hand-tested wowsims comparison (30k: +1.06 DPS, 5k:
-3.50 DPS, sign flip) looked like it disproved 5k entirely - the fuller 10-item test clarifies
that scary result was itself a near-zero-effect edge case, the same class of case the 10-item
test's one disagreement also hit, not evidence that 5k is broadly unreliable.

Worth noting: this reframes the exercise back toward the core `DPS*(S)` full-set search
(`core/optimizer.py`), not just the interaction matrix specifically - "finalize the 3 best sets"
implies whole-gear-configuration finalists, which suggests this funnel principle may belong in
`optimizer.py`'s own search too, not just `interaction_matrix.py`. **Not scoped or planned** - this
is the rough shape only, for discussion once the tool needs to handle a pool this size.

## #8 — Decomposed re-sweep caching (avoid full recompute after a raid week)

Idea collection from CLAUDE.md (undated, predates 2026-08-23). Speeding up a re-sweep after a raid
week nets 1-2 new items. Rough thinking, for discussion, not a plan:

- The existing `sim_cache` (journal format, keyed by full gear-config hash) already doesn't need
  invalidating when new items arrive - a cached DPS for an old config is still a true statement
  about that config forever. The real cost isn't repeated sim calls, it's that `DPS*(P)` requires
  a joint *search* over shared-pool slots (rings/trinkets/weapons, set bonuses), and that search
  currently seems to re-run from scratch over the whole pool rather than reusing the previous
  optimal assignment.
- Possible direction: decompose the search into independent single-slot optimization plus
  explicit joint search only over the actually-coupled subgroups (ring pair, trinket pair, weapon
  pair, any tier-set combo). A new item then only requires re-solving the specific subgroup(s) it
  belongs to against the previously-known-optimal assignment for that subgroup, not a full
  15-slot re-search. This also happens to be closer to how "shared-pool slots" are already
  described in the architecture (Stage 2's Ring/Trinket/Weapon note) - may be worth building
  regardless of caching.
- A cheap per-slot swap-and-resim could serve as a *prefilter* to decide which candidates are even
  worth a real joint re-search - but per the ground rules, that can only ever be a heuristic to
  prune what gets the expensive treatment, never the source of a reported MV number itself.
- Open question the user flagged directly: the baseline `DPS*(P)` itself shifts every time P gains
  an item, so even a perfect sub-search cache still needs every remaining candidate's MV
  recomputed against the new baseline (`DPS*(P_new ∪ {i})` configs that were never tried before,
  since they include the newly-owned item). Worth discussing whether that's an acceptable cost
  (it's proportional to remaining-candidate-count, not total-pool-size) or whether it needs its
  own optimization.

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

