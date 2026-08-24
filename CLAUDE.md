# Gearing Tool

Local, personal tool that drives `wowsims/tbc-new` in batch to price gear upgrades for a TBC
Anniversary Survival Hunter (Nightelf, Herbalism/Mining, Phase 3) by **marginal value**:

```
MV(i) = DPS*(P ∪ {i}) − DPS*(P)
```

`DPS*(S)` is the best DPS achievable from pool `S` under all equip constraints — never a
per-slot "swap and re-sim" shortcut. That shortcut undervalues set-completing items (each piece
looks mediocre in isolation) and overvalues hit-heavy items once already capped (it never lets
the rest of the set rebalance away from now-worthless hit). Stat weights (EP) are the cheap
linear approximation of this function; this tool exists to be right where EP breaks — thresholds,
set bonuses, stacked procs, weapon-speed rotation changes. If ranking by EP alone, stop.

## Ground rules

- **Assume the latest sim's model is correct.** Don't regression-diff it or second-guess its
  math. Do record the sim's git commit SHA in every output — that's how "ranking changed because
  I got gear" is told apart from "ranking changed because the sim updated." This covers the
  sim's *model*, not its *data completeness* — DB coverage is checked and reported separately.
- **Never invent data.** Item IDs, stat lines, talent coefficients come only from the sim's DB
  and source. Drop rates and AH prices come only from the user — ask, don't estimate and carry
  forward as if measured.
- **Noise honesty.** Every result carries DPS ± error. MVs that overlap within error are tied,
  not ranked — say so. Never recommend spending a currency on a gain indistinguishable from
  noise.
- **Determinism.** Fixed seed, identical settings on every run. Gear is the only variable.
- **Sanity gate.** If the best owned set beats the preset phase BiS, that's a pipeline bug until
  proven otherwise — investigate before reporting it as a finding.
- **Work in stages, stop at checkpoints.** Don't run ahead to later stages; show results at each
  STOP and wait for review.
- **Keep `NOTES.md` current** — real CLI flags, schema quirks, addon format details, anything
  surprising. Commit to git as you go.

## Architecture

```
CORE ENGINE   (core/)       — knows nothing about classes, specs, or expansions
SPEC PROFILE  (profiles/)   — data only, e.g. profiles/tbc/survival-hunter.yaml
SIM ADAPTER   (adapters/)   — one per wowsims repo, e.g. adapters/tbc/
```

```python
class SimAdapter:
    def run(self, gear_config: dict, settings: dict) -> dict: ...      # {dps, error, damage_breakdown}
    def list_items(self, filters: dict) -> list[dict]: ...
    def slots(self) -> list[str]: ...
    def validate(self, gear_config: dict) -> list[dict]: ...           # violations
    def presets(self, spec: str) -> list[dict]: ...                    # gear sets
    def version(self) -> dict: ...                                     # {repo, commit_sha}
```

Two rules that decide whether this ports past TBC — do not violate either:

1. **Proto/generated types never cross the adapter boundary.** `core/` sees plain dicts only.
   If a generated protobuf type shows up in the optimizer, the engine has silently become
   expansion-specific.
2. **Item identity carries a `variant` field from day one.** TBC doesn't need it; WotLK's
   10/25/heroic versions of the same item do. Retrofitting identity through a cache, state file,
   and history log later is genuinely painful — do it now while it's free.

If any file under `core/` mentions a class, spec, talent, or expansion by name, that's a bug.

## Repo layout

```
sim/tbc-new/          git submodule, pinned commit — the vendored simulator
core/                  MV optimizer, engine-agnostic, dict-based
adapters/tbc/          SimAdapter impl: subprocess -> wowsimcli, dict in/out
profiles/tbc/          spec profile data (survival-hunter.yaml)
ingest/                addon SavedVariables reader (slpp Lua parser) -> character.json
addons/GearingToolCompanion/  companion addon (bank/bags/reputation/arena export) - mirrored
                               here so a fresh machine can install it without a live WoW client;
                               source of truth is whichever copy was most recently edited in a
                               session (see "Addon sync" below), not automatically kept in sync
cli/                   `gear sync`, `gear best` entry points
data/                  character.json, sim-result cache (keyed by gear-config hash), history
```

## Addon sync

`addons/GearingToolCompanion/` is a plain copy, not a symlink — WoW loads addons from
`<WoW install>/Interface/AddOns/GearingToolCompanion/`, which lives outside this repo entirely
and varies per machine. After any session that edits the live addon (usually the case, since
addon changes need real in-game testing to verify), copy the edited files back into this repo
and commit before ending the session:

```
cp "<WoW install>/Interface/AddOns/GearingToolCompanion/GearingToolCompanion.lua" addons/GearingToolCompanion/
cp "<WoW install>/Interface/AddOns/GearingToolCompanion/GearingToolCompanion.toc" addons/GearingToolCompanion/
```

To install on another machine: copy `addons/GearingToolCompanion/` into that machine's
`Interface/AddOns/` directory.

## Stack

Python 3.13 for everything except the simulator itself (Go, vendored via submodule, built to
`wowsimcli`). No Node/npm — only the CLI binary is needed, not the web UI.

The adapter's translation step (`IndividualSimSettings` protojson → `RaidSimRequest` protojson,
the CLI's actual input) is a small Go program (`adapters/tbc/bridge/`) rather than a Python
reimplementation — it imports the submodule's own generated proto package via a `replace`
directive, so field names/enums are never hand-copied. See NOTES.md, "Resolved: the CLI's
actual input contract," for why this exists and how it was derived.

## Local setup (this machine)

Prerequisites installed this session: Go 1.26 (`winget install --id GoLang.Go`), protoc + 
protoc-gen-go (`winget install --id Google.Protobuf` + `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest`),
Python `slpp` (`pip install -r requirements.txt`). None of these are on a fresh shell's PATH
automatically in this git-bash environment — see NOTES.md for the exact PATH prepends needed.

One-time build (from repo root). `assets/database/db.bin` (the item DB) is already **committed**
in the submodule — do NOT run `db2tool`/`gen_db`/`make db` unless `git status` inside
`sim/tbc-new` shows it's actually missing or you've bumped to a commit that changed it. The only
genuinely-generated, gitignored-upstream piece is the protobuf Go bindings:
```
protoc -I=./sim/tbc-new/proto --go_opt=Mgoogle/protobuf/descriptor.proto=google.golang.org/protobuf/types/descriptorpb --go_out=./sim/tbc-new/sim/core ./sim/tbc-new/proto/*.proto
cd sim/tbc-new && go build -o wowsimcli.exe --tags=with_db ./cmd/wowsimcli/cli_main.go
cd ../../adapters/tbc/bridge && go build -o bridge.exe .
```
If a future submodule bump ever does need a DB rebuild: `tools/database/generator-settings.local.json`
(untracked, not committed) is a copy of `generator-settings.json` with `BaseDir` pointed at the
local WoW install root — see NOTES.md ("Building wowsimcli: real prerequisite chain") for the
full db2tool/gen_db command and the DBCache pitfall. Afterwards, `git status` inside the
submodule and `git checkout -- .` anything that shouldn't have changed before rebuilding.

Day to day:
```
python cli/gear.py sync                                    # re-read addon export -> data/character.json
python cli/gear.py preset <path/to/*.build.json>            # sanity-check the sim pipeline
```

## Stage 2 decision: Expose Weakness raid contribution (analytical)

Individual sims can't see the AP Lerynia's Expose Weakness grants to her raid's other physical
attackers (they don't exist in that sim) — her own share is already correct in personal DPS
(dynamic, tied to her live Agility — see NOTES.md). Decided: compute the raid-wide share
analytically (`adapters/tbc/expose_weakness.py`) rather than switching to raid sims. Every
future MV/valuation output must report **personal DPS and raid AP contribution as two separate
columns** — never collapse them into one number, and never silently drop the raid column.

## Staging

See the user's full spec for §0–§9. Done: Stage 1 (adapter + ingestion), Stage 2 (Survival
mechanics blocker), Stage 3 (candidate pool: `profiles/tbc/candidate_pool_survival.json`, 79
items across 15 slots), Stage 4 (§6, the valuation engine actually computing `DPS*(S)` for these
candidates — `core/run_full_sweep_mv.py` + the Phase 3 Upgrade Ledger artifact; still gets real
refinements as gaps are found, e.g. the top-1-always-resolves fix and the flat top-5 2H list, but
the stage itself is built and in active use), and Stage 5 (§7, the interaction matrix —
`core/interaction_matrix.py`, `I(i,j) = MV(i,j) − MV(i) − MV(j)` for the top 3 real-upgrade
candidates per slot plus any candidate carrying nonzero Hit/Expertise Rating; real joint two-item
sims, not estimates; a pair is only a "package" if it's a genuinely high-interaction pair — no
rollup into named bundles beyond that, per the user).

Still open from §8 (Outputs): `results.csv`/`winner.json` as literal files (currently substituted
by `data/cache/tiered_report.json` + the HTML ledger, not the spec'd files themselves). Package
goals are effectively covered by Stage 5's interaction matrix now that it's built.

**Stage 7 (new, added 2026-08-23, PRIORITY — confirmed by the user, not just idea-collection
anymore): decompose the re-sweep so a weekly gear change doesn't force a full recompute.**
Directly motivated by watching this session's Stage 5 sweep take 15-20+ minutes live, and the
realization that this isn't a one-off cost - it's what would happen EVERY WEEK after a raid, every
single time any gear changes. Root cause, confirmed by tracing the actual caching mechanism:
`sim_cache.json`'s key is a hash of the FULL 17-slot gear config being evaluated, not per-candidate
- so every trial config (baseline-with-one-slot-swapped) embeds the ENTIRE baseline, meaning a
single changed slot (say Legs) changes the hash of literally every OTHER candidate's trial config
too, even ones with zero real relationship to Legs. The cache isn't wrong, it's just far more
conservative than necessary: most candidates' true MV doesn't actually depend on unrelated slots'
specific contents, but the current architecture can't tell the difference between "genuinely
coupled, must recompute" and "hash technically changed, but the real number provably didn't."

This is the same problem already sketched under "Idea collection" below (decompose into
independent single-slot evaluation + explicit joint search only over ACTUALLY-coupled subgroups -
rings, trinkets, weapons, tier-set slots), now confirmed as a real, lived cost rather than a
theoretical one, and made worse by Stage 5's interaction matrix (pairs multiply the same problem
across two slots, and which slots even count as "active set slots" can shift week to week as she
moves between set bonuses). Not yet scoped in detail - the open question from that idea-collection
note still applies (the baseline `DPS*(P)` itself shifts every time P gains an item, so no caching
scheme fully eliminates recompute proportional to remaining-candidate-count) - but this is now a
real near-term priority to design properly, not a someday idea.

**Dropped from §8, per the user (2026-08-23) — gold-based decisions are explicitly not something
this tool should factor in.** This kills two §8 items outright, not just "not yet": per-currency
spend sections (already moot once acquisition-cost tracking was dropped for Wowhead linking
instead), and the gems/enchants free-reshuffle-vs-requires-gold split (the two-number split's only
purpose was surfacing which portion of an item's value needs gold spent to realize - once gold
isn't a factor the tool should weigh at all, that distinction has no use). Every report number
should keep assuming the fully-optimal gem/enchant loadout, same as it already does, with no
"free vs. gold-gated" breakdown.

**Stage 6 (new, added 2026-08-23): multi-class/multi-spec support** — extend beyond Lerynia's
Survival Hunter to any class/spec `wowsims/tbc-new` itself supports. Per the user, this is a big
piece of work but explicitly does **not** need to be done before Phase 3 launches — it can proceed
in parallel with or after Stage 5, not gating it. The architecture's two day-one rules (proto types
never cross the adapter boundary; item identity carries `variant`) were already written to make
this possible without a rewrite, and the "no class/spec/talent/expansion names in `core/`" rule
means `core/` itself shouldn't need changes. The real work is elsewhere and not yet scoped in
detail - known coupling points found so far that will need to become profile-driven instead of
hardcoded, from working on `adapters/tbc/` and `core/run_full_sweep_mv.py` this session: the
Survival-specific melee-weave APL switch and its own settings variant, `STAT_WEIGHTS`, the
Herbalism/Mining profession filter, `SLOT_ORDER`/weapon-type assumptions, and the Expose-Weakness
raid-AP analytical model (§ above) being Survival Hunter-specific by construction. Not started -
noted here so it isn't lost, and to be scoped properly (probably its own sub-stages) when work on
it actually begins.

## Future scope (deferred to final implementation, not now)

User wants a GUI eventually: run a sim on demand, a phase toggle to switch reference/candidate
data between phases, a character-select dropdown (this tool should support simming more than one
character, not just Lerynia), a hit-target toggle (6% assuming a moonkin present vs 9% assuming
not - both are real wowsims-provided presets, see NOTES.md's hit-cap entry), and a raid/zone scope
filter (2026-08-23) - let the user directly limit which raids get scanned for upgrade candidates
at all, not just which phase. Real motivating case: a fresh level 70 starting in Phase 5 wouldn't
actually be raiding Sunwell Plateau day one even though it's technically "in phase" - without a
way to say "I can currently get into Karazhan and Gruul's, not SWP," the candidate pool search
space balloons with content that isn't really accessible yet, which is also a more practical fix
for that scaling problem than pure compute optimization (see the three-tier funnel idea above -
this filter shrinks the actual problem instead of just computing the huge version faster), and a
real progress indicator (2026-08-23) - a big sweep can genuinely run 15-20+ minutes (watched this
happen live this session once the candidate pool got wider), and a user watching a GUI needs
actual feedback (candidates screened so far / total, current phase: screening vs resolving), not
a blank wait wondering if it's stuck. Means the underlying pipeline needs to expose a real
progress signal (e.g. a callback or periodic status write), not just print-to-stdout text - worth
designing in from the start rather than bolting on later, per the same "keep core/adapters
UI-agnostic so a GUI can sit on top without a rewrite" principle already governing this section.
Also a resolve-iterations setting (2026-08-23) - per the user, expose the final resolve pass's
iteration count as a real GUI setting rather than a hardcoded constant, since the right value is
a genuine speed/precision tradeoff a user might want to tune (see the funnel idea below for the
actual measured numbers behind this).
etc. Not part of any current stage — noted here so it isn't lost, but don't build toward it until the
user actually asks. Keep `core/`/`adapters/` command-line-first and UI-agnostic in the meantime so
a GUI can sit on top later without a rewrite. Until the toggle exists, keep assuming 6% (moonkin
present) per the user's stated raid comp - never silently switch to 9% without being asked.

**Draft sketch (2026-08-24, requested by the user while driving — discuss and refine before
building, not a committed plan): the character-select dropdown above, concretely, now that the
addon side of multi-character support actually exists** (`addons/GearingToolCompanion`'s
`GTCompanionDB`/`/gtlist`, added this session — see NOTES.md). Rough shape:

- **Character listing**: `GTCompanionDB` is already keyed per character (name-realm) with a
  timestamp and identity (class/race/faction/level/professions). WowSimsExporter separately
  keeps its own multi-character `savedCharacters` list (own timestamp, own data) - confirmed by
  reading `ingest/build_character.py`'s `find_wse_character()`. Neither is read as a *list*
  today - `build_character.py` only ever targets one hardcoded/passed `name_realm`. A GUI's
  character picker needs a new listing function (`ingest/list_characters.py`?) that enumerates
  both sources, merges by name-realm, and surfaces per-character: identity, and each source's own
  last-saved timestamp (so "GTCompanion data is 3 days stale, re-save in game" is visible before
  running anything stale).
- **Per-character data, not one flat file**: `data/character.json` is a single file today,
  overwritten per run - fine for one character, actively wrong for several (whoever ran last
  silently becomes "the" character). Needs to become `data/characters/<name-realm>/character.json`
  (and similarly for that character's own cache/report state) before a character picker means
  anything real.
- **Cache correctness, checked (not assumed) this session**: `sim_cache`'s key is
  `gear_hash:settings_fingerprint:iterations:seed`
  (`core/sim_cache.py:key`), and `settings_fingerprint` hashes the *entire* settings template
  except equipment (`adapters/tbc/valuation.py:settings_fingerprint`) - so it already includes
  race/class/talents/consumables, meaning two different characters do NOT silently collide in the
  shared cache as long as each gets their OWN real settings file. The actual requirement this
  surfaces isn't a cache-key redesign - it's that `SETTINGS_TEMPLATE` needs to stop being one
  hardcoded file (`profiles/tbc/canonical_settings_survival.json`, Lerynia's own) and become
  per-character (or per class/spec/race), matching the Stage 6 profile-driven work already
  planned above. A single shared `sim_cache.json` across all characters is otherwise fine to keep
  - correctness comes from the fingerprint, not from separating the cache files.
- **Report link**: once a character's sweep/valuation is published (per today's ledger-artifact
  pattern), track that URL per (character, phase) - e.g.
  `data/characters/<name-realm>/reports.json` mapping phase → artifact URL + generated-at
  timestamp - so the GUI's picker can show "view last report" without re-running anything, and
  "stale, re-run?" once gear/phase has moved on since that URL was generated.

Genuinely open, not resolved: whether GTCompanion or WowSimsExporter is the source of truth when
both have data for the same character (favor whichever has the newer timestamp? always prefer
one?); whether the report-link tracking file becomes part of what `check_ledger_consistency.py`
validates once it exists. Sketched only because the user asked for something to plan during a
15-minute gap - needs real discussion before any of it gets built.

Tool rename to something including the user's gamertag "Ruban" (e.g. RubanAutoSim) is also
planned, as a final rework once the product is otherwise done — not yet, folder path and
internal naming stay as-is until then. Fold in a general file-naming clarity pass at the same
time (e.g. `core/run_full_sweep_mv.py` — "mv" = Marginal Value, the tool's core metric, but the
name doesn't read as self-explanatory to someone new to the repo) — per the user, file names
should be clear on their own, not just to someone who already knows the codebase.

Publishing `addons/GearingToolCompanion/` to CurseForge is planned as one of the final steps too
— account + project via console.curseforge.com, tagged for the Anniversary client flavor
specifically (not retail/normal Classic), a declared license, and either manual zip uploads per
release or a `.pkgmeta` file driving their GitHub-based packager off this repo directly. Not yet —
the addon is still actively changing session to session.

An optional self-hosted rebuild of the HTML ledger is also planned, to be scoped later - the
claude.ai Artifact platform's CSP blocks loading Wowhead's real tooltip-preview script (only
Google Fonts is allowed through), but that CSP doesn't exist on a plain HTML file served from
somewhere we control (an external webserver, or the user's Synology NAS) - Wowhead's script is
explicitly designed for third-party embedding, so a self-hosted build could get full, authentic
in-game-style tooltips on hover, not just the click-through links the Artifact version has. Not
built - needs its own plan (build/deploy process, whether to keep the Artifact version as the
convenient default alongside it, etc.) once the rest of the tool is otherwise done.

**Version 2 / a separate future feature build (explicitly not this build)**: a Google Sheets
export function for the results.csv/winner.json outputs from §8 - per the user, this would be
nice but isn't part of the current build; noted here only so the idea isn't lost, not scoped or
planned yet.

**Idea collection, not decided — discuss before building**: speeding up a re-sweep after a raid
week nets 1-2 new items. Rough thinking, for discussion, not a plan:

- The existing `sim_cache.json` (keyed by full gear-config hash, per the architecture above)
  already doesn't need invalidating when new items arrive — a cached DPS for an old config is
  still a true statement about that config forever. The real cost isn't repeated sim calls, it's
  that `DPS*(P)` requires a joint *search* over shared-pool slots (rings/trinkets/weapons, set
  bonuses), and that search currently seems to re-run from scratch over the whole pool rather
  than reusing the previous optimal assignment.
- Possible direction: decompose the search into independent single-slot optimization plus
  explicit joint search only over the actually-coupled subgroups (ring pair, trinket pair,
  weapon pair, any tier-set combo). A new item then only requires re-solving the specific
  subgroup(s) it belongs to against the previously-known-optimal assignment for that subgroup,
  not a full 15-slot re-search. This also happens to be closer to how "shared-pool slots" are
  already described in the architecture (Stage 2's Ring/Trinket/Weapon note) — may be worth
  building regardless of caching.
- A cheap per-slot swap-and-resim could serve as a *prefilter* to decide which candidates are
  even worth a real joint re-search — but per the ground rules at the top of this file, that can
  only ever be a heuristic to prune what gets the expensive treatment, never the source of a
  reported MV number itself.
- Open question the user flagged directly: the baseline `DPS*(P)` itself shifts every time P
  gains an item, so even a perfect sub-search cache still needs every remaining candidate's MV
  recomputed against the new baseline (`DPS*(P_new ∪ {i})` configs that were never tried before,
  since they include the newly-owned item). Worth discussing whether that's an acceptable cost
  (it's proportional to remaining-candidate-count, not total-pool-size) or whether it needs its
  own optimization.

**Idea collection #2, not decided — a three-tier funnel for scaling to a much bigger pool**
(2026-08-23). Prompted by watching Stage 5's interaction matrix take ~15-20 minutes on Lerynia's
already-narrow Phase 3 pool once the candidate-selection fix (below) widened it. The user's real
concern: a FRESH LEVEL 70 CHARACTER STARTING IN PHASE 5 has every item from Phases 1-5
simultaneously live as a real candidate for every slot at once - the pool this tool would need to
search is enormously bigger than "one already-decently-geared character's Phase 3 upgrade list,"
and it still needs to finish in a reasonable time. Rough shape, matching the existing prefilter
principle above (a cheap pass may only ever prune what gets the expensive treatment, never BE the
reported number) but formalized as three explicit tiers instead of one screen/resolve split:

1. **Pre-screen** - something cheaper than today's 1000-iteration screen, to cut an enormous raw
   pool (every phase's items at once) down to a manageable shortlist before spending even a cheap
   sim run on each one. Not yet decided whether this should be a real (very-low-iteration) sim
   call or a static EP-based prefilter using `STAT_WEIGHTS` - the ground rules already sanction
   EP as a legitimate prefilter heuristic, just never as a reported number. User's concrete
   proposal (2026-08-23): 100 iterations for this tier - real SEM math checks out (the sim's own
   player_stdev was ~74 at 1000 iterations in the user's own test, so SEM ≈ 74/√100 ≈ 7.4 DPS at
   100 - noisy, but only affects which pairs get promoted to the next tier, never a reported
   number, so the tradeoff is real but bounded).
2. **Screen** - the user's proposal: 500-1000 iterations (matches today's existing
   `SCREEN_ITERATIONS`), applied to whatever survives step 1.
3. **Finalize** - resolve only the top ~3 candidate FULL SETS (not top individual items or
   pairs) at high precision - the user left the exact iteration count open ("12.5k baseline from
   sim or your 30k, up to you"). Confirmed by the user checking the actual wowsims web UI
   (Hunter, incognito, default "Iterations" field): the sim's own real default is **25000**, not
   12.5k - that recollection was off, caught by checking rather than assuming. If this tier ever
   gets built, 25000 is the real, verified reference point to weigh against this tool's own 30000,
   not a guessed number.

**Status (2026-08-23): tiers 1-2 are actually built**, not just an idea anymore -
`core/interaction_matrix.py`'s `compute()` now runs a real 3-pass funnel: pre-screen @100 →
screen @1000 → resolve @30000, each stage gating whether a pair gets promoted to the next.

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
strong evidence for a 4th, intermediate "confirm @5000" tier between screen and finalize, since
it agreed with 30k on every item that had a real, decision-relevant magnitude. Not yet built.
Earlier in this same session, a single hand-tested wowsims comparison (30k: +1.06 DPS, 5k: -3.50
DPS, sign flip) looked like it disproved 5k entirely - the fuller 10-item test clarifies that
scary result was itself a near-zero-effect edge case, the same class of case the 10-item test's
one disagreement also hit, not evidence that 5k is broadly unreliable.

Worth noting: this reframes the exercise back toward the core `DPS*(S)` full-set search (Stage
4), not just Stage 5's pairwise interaction matrix specifically - "finalize the 3 best sets"
implies whole-gear-configuration finalists, which suggests this funnel principle may belong in
`core/optimizer.py`'s own search too, not just `interaction_matrix.py`. Not scoped or planned -
this is the rough shape only, for discussion once the tool needs to handle a pool this size (not
yet - today's actual character is a single, already-geared Phase 3 Survival Hunter).
