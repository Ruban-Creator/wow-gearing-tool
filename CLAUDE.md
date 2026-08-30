# Ruban's Gearing Tool (RGT)

Drives `wowsims/tbc-new` in batch to price TBC Anniversary gear upgrades by **marginal value**,
across any of the 15 real class/spec profiles it currently supports (see "Staging" below) - not
scoped to one character. Started as the user's own personal tool (originally built for a single
Survival Hunter) but is now, per the user (2026-08-30), headed toward public release through the
installer/versioning work in progress - keep that audience in mind for anything user-facing (GUI
copy, defaults, first-run behavior), not just this one dev machine's own convenience:

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
- **Before building or touching a class/spec profile, check `CLASSES.md`** — a checklist of real,
  previously-hit gotchas (gem/enchant verification methodology, weapon_topology handling,
  set_bonus.py's three Go source forms, profile_dir footguns, etc). Update it when a new class
  surfaces a new one; don't let the lesson live only in a session's own NOTES.md entry.

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

Four buckets, physically separated (2026-08-29 folder-structure rework, done ahead of a real
bundled installer — see NOTES.md's own entry for the full rationale/migration):

```
The Tool (this repo, git-tracked source):
  core/                  MV optimizer, engine-agnostic, dict-based
  adapters/tbc/          SimAdapter impl: subprocess -> wowsimcli, dict in/out
  ingest/                addon SavedVariables reader (slpp Lua parser) -> character.json
  cli/                   `gear sync`, `gear best` entry points
  gui/                   pywebview picker + report-viewer app
  packaging/             PyInstaller spec + Inno Setup installer script (installer.iss) + build docs
  addons/GearingToolCompanion/  companion addon (bank/bags/reputation/arena export) - mirrored
                                 here so a fresh machine can install it without a live WoW client;
                                 source of truth is whichever copy was most recently edited in a
                                 session (see "Addon sync" below), not automatically kept in sync

The Sim we downloaded (git submodule, pinned commit, its own history):
  sim/tbc-new/           the vendored simulator - db.bin committed inside it; wowsimcli.exe itself
                         is a local build output, not committed (see Build Output below)

The Data we have (curated, versioned, ships with the tool):
  profiles/tbc/          spec profile data (candidate pools, reference BiS, stat weights, raid
                         buffs, per-class settings) + reference/ (fixed game-mechanic tables that
                         aren't per-character, e.g. arena_rating_requirements.json)

Build Output (5th bucket, gitignored, disposable/regenerable — never committed):
  build/bin/             wowsimcli.exe, bridge.exe, simserver.exe - Go build output the Python
                         tool calls as subprocesses at runtime. Source lives in sim/tbc-new/ and
                         adapters/tbc/{bridge,simserver}/ respectively; the compiled binaries land
                         here instead of nested inside either source tree.
  build/dist/            RGT.exe - PyInstaller's final packaged output (see
                         packaging/README.md)

Production Data (generated per-user, lives OUTSIDE this repo entirely):
  %LOCALAPPDATA%\GearingTool\   character caches/reports, sim_cache.json, local_config.json - see
                                core/repo_root.py's USER_DATA_DIR. Auto-created on first run, never
                                repo-relative (an installed copy in Program Files can't write next
                                to itself). The old data/ directory is gone.
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
genuinely-generated, gitignored-upstream piece is the protobuf Go bindings. Every compiled binary
lands in `build/bin/` (the Build Output bucket, see Repo Layout above), not inside its own source
tree — `mkdir -p build/bin` once, first:
```
protoc -I=./sim/tbc-new/proto --go_opt=Mgoogle/protobuf/descriptor.proto=google.golang.org/protobuf/types/descriptorpb --go_out=./sim/tbc-new/sim/core ./sim/tbc-new/proto/*.proto
cd sim/tbc-new && go build -o ../../build/bin/wowsimcli.exe --tags=with_db ./cmd/wowsimcli/cli_main.go
cd ../adapters/tbc/bridge && go build -o ../../../build/bin/bridge.exe .
cd ../simserver && go build -o ../../../build/bin/simserver.exe --tags=with_db .
```
`--tags=with_db` is REQUIRED on `simserver.exe` too, not just `wowsimcli.exe` - real bug found
2026-08-30 during the first-ever sim version bump (v0.0.119→v0.0.124): this exact command, minus
that flag, was what this file itself documented beforehand, and rebuilding from it produced a
`simserver.exe` with a completely empty in-memory item DB (`sim/core/database_load.go`'s
DB-loading `init()` is gated behind `//go:build with_db` - omit the tag and that whole file, and
the `ItemsByID` population it does, is silently excluded from the build). Every real sim call
through `simserver.exe` then panicked with `"No item with id: <N>"` for literally any real item -
looked exactly like a sim-version DB regression at first (a whole afternoon's worth of diagnosis:
confirmed the item genuinely exists in `db.bin`/`db.json`, confirmed `database.Load()` finds it
via a standalone Go test program, before finally checking the actual build command used and
finding the missing flag). `bridge.exe` genuinely doesn't need the tag - its own job (expanding
`IndividualSimSettings`->`RaidSimRequest`) never looks up an item, confirmed by its own source
setting `player.Database = nil` unconditionally.
Also bake the sim's commit SHA into a static file (`core/repo_root.py`'s `sim_commit_sha()` falls
back to this when `git rev-parse` itself isn't available — a flat installer copy has no `.git`):
```
git -C sim/tbc-new rev-parse HEAD > build/bin/sim_commit_sha.txt
```
This is a real, required step before packaging for anyone besides this dev machine — every report/
character.json output must carry this SHA (the ground rule at the top of this file), and it's the
one piece `git rev-parse` genuinely can't produce once `.git` isn't shipped alongside the app. On
this dev machine specifically it's optional (the live git call is always tried first and always
succeeds here), but keep it current anyway so a packaged build is never a surprise.
If a future submodule bump ever does need a DB rebuild: `tools/database/generator-settings.local.json`
(untracked, not committed) is a copy of `generator-settings.json` with `BaseDir` pointed at the
local WoW install root — see NOTES.md ("Building wowsimcli: real prerequisite chain") for the
full db2tool/gen_db command and the DBCache pitfall. Afterwards, `git status` inside the
submodule and `git checkout -- .` anything that shouldn't have changed before rebuilding.

Day to day:
```
python cli/gear.py sync                                    # re-read addon export -> USER_DATA_DIR/character.json
python cli/gear.py preset <path/to/*.build.json>            # sanity-check the sim pipeline
```

## Sim update procedure (runbook for the scheduled update agent)

Written 2026-08-30 for a future scheduled Claude Code agent (per the user: a dedicated dev
machine, running a daily check against `https://github.com/wowsims/tbc-new`, rebuilding and
pushing when a new version is available) to follow with no memory of any prior session. Every
step below was actually run once, live, on this machine before being written down - not a
speculative plan. If a step here stops matching reality, trust what you observe and fix this
section, the same as any other doc in this repo.

**1. Check for a new version.** Watch the latest `v0.0.NNN` git tag on `origin` (`git -C
sim/tbc-new fetch --tags --quiet && git -C sim/tbc-new tag --sort=-v:refname | head -1`), not raw
`master` HEAD - tags are real, deliberate release cuts the wowsims team makes directly off
`master` (confirmed 2026-08-30: the then-latest tag was only 4 commits behind `master`'s own tip),
so they're a cleaner "is there something worth picking up" signal than every merged branch.
Compare against the currently pinned commit (`git -C sim/tbc-new rev-parse HEAD`, or
`repo_root.sim_version_label()` for the human-readable form). Nothing to do if they match.

**2. Assess risk before touching anything** - a real `git diff --name-only <old-tag> <new-tag>`
against the submodule, checked for:
- `proto/*.proto` changes → the protobuf Go bindings need regenerating (see step 4's protoc
  command) before anything will even build.
- `go.mod`/`go.sum` changes → new/updated Go dependencies; `go build` will fail clearly if a
  `go mod download` is needed first.
- `sim/<class>/item_sets.go` changes for any of the 15 profiled classes → `core/set_bonus.py`'s
  regex-based parser handles three known Go source forms (inline map, bare variable reference,
  function call - see `CLASSES.md`) but a fourth form is real, flagged risk there. Check
  `check_ledger_consistency.py`'s set-bonus assertions catch it if the parser silently returns
  nothing instead of erroring.
- `sim/core/buffs.go` / `sim/core/consumes.go` changes → could shift `raid_buffs_overlay.json`/
  `consumables.json` field names or semantics for any profile; a real, structural verification
  failure (not a crash) is the likely symptom, not necessarily a build error.
- Per-profile `ui/<class>/<spec>/apls/*.json` or `presets.ts` changes → **never treated as a
  problem to fix** - per this file's own ground rules, the sim's model is trusted, not
  regression-diffed. A rewritten rotation or changed EP preset is exactly what "update the sim"
  means to pick up. Just note it in the update's own summary so a human sees what changed.
- `assets/database/db.bin`/`db.json` changes → already committed inside the submodule itself, so
  bumping the submodule pulls the new DB automatically. No separate `db2tool`/`gen_db` step needed
  (see this file's own "Local setup" section for the real exception case).

**3. Bump the submodule**: `cd sim/tbc-new && git checkout <new-tag>`. This is a real, visible
change to the parent repo's own tracked submodule pointer - `git add sim/tbc-new` stages it, but
don't commit yet.

**4. Rebuild.** Regenerate protobuf bindings ONLY if step 2 found `.proto` changes (the exact
command is in "Local setup" above). Always rebuild all three binaries into `build/bin/` (same
commands as "Local setup" - **`wowsimcli.exe` AND `simserver.exe` both need `--tags=with_db`,
`bridge.exe` does not** - see that section's own real, hard-won note on why) and re-bake
`build/bin/sim_commit_sha.txt` / `sim_version_label.txt` (`git -C sim/tbc-new rev-parse HEAD` /
`git -C sim/tbc-new describe --tags --exact-match HEAD`, redirected to those files respectively).
If verification (step 6) panics with `"No item with id: <N>"` for an item you can otherwise
confirm is real (check `core.item_db.by_id()` / grep `db.bin` for its name) - don't assume the sim
version broke something, check the build tag first.

**5. Kill stale processes before verifying.** `simserver.exe` runs as a persistent pool
(`adapters/tbc/simserver_client.py`) - if old instances are still alive when you replace
`build/bin/simserver.exe`, verification would silently test the OLD binary still resident in
memory, not the new one. Check `Get-Process simserver` (PowerShell) and kill any survivors before
step 6.

**6. Verify - structural correctness, never the sim's own math.** The cache is already safe
across a version bump with no manual clearing needed: `adapters/tbc/valuation.py`'s
`_fingerprint_settings()` folds `repo_root.sim_commit_sha()` into the cache key, so every entry
under the old SHA is automatically bypassed (real bug found and fixed 2026-08-30, before this
runbook's own first real use - see NOTES.md). Run, in order:
- An import-sanity sweep of every module touching the sim (see NOTES.md's own "ALL N MODULES
  IMPORTED CLEAN" pattern for the exact list - `core/`, `adapters/tbc/`, `ingest/`, `gui/api.py`).
- A real, live sim call for at least one profile per weapon topology actually in use (confirms
  `bridge.exe`/`wowsimcli.exe`/`simserver.exe` chain runs end to end, not just imports).
- `check_ledger_consistency.py --skip-html` for all 15 profiles - fast, structural (assertion
  counts, not DPS values), catches a broken candidate pool, a set-bonus parse failure, a missing
  raid-AP field, etc. Not a full 30k-iteration production sweep for every profile - that's for a
  real upgrade decision, not a routine version-bump smoke test.
- Re-run `verify_default_enchants.py`/`verify_gem_choices.py` per profile if step 2 flagged
  `enchants.go`/DB changes - a previously-verified enchant/gem choice can legitimately stop
  verifying under new sim math without that being a bug in this tool.

**7. On any real failure**: do not commit or push a broken build. Leave the submodule bump and
rebuilt binaries in the working tree (so a human or the next agent run can pick up the diagnosis
with the state visible), and write what broke into a new dated NOTES.md entry the same way every
other real finding in this file gets recorded - specific enough that "why did this fail" doesn't
need re-deriving from scratch.

**8. On success**: commit the submodule bump (`git add sim/tbc-new`, message naming the old and
new tags) and push. `build/bin/*` itself is gitignored (Build Output, never committed - see Repo
Layout) - what a real end-user install pulls from is a separate, not-yet-built release/distribution
mechanism (see NOTES.md's "still to design" note on this), not this repo's own git history
directly. Write a NOTES.md entry: what changed upstream (the real `git diff --name-only` summary
from step 2), what was verified, and anything genuinely surprising - matching every other dated
entry in that file.

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

**Stage 6 (added 2026-08-23, Stage 6.0 done 2026-08-24): multi-class/multi-spec support** — extend
beyond Lerynia's Survival Hunter to any class/spec `wowsims/tbc-new` itself supports, starting
with Arms Warrior (Rubán-Thunderstrike) and Balance Druid (Béarforceone-Thunderstrike), for whom
real character data already exists. Full design:
`C:\Users\Matthias\.claude\plans\staged-purring-lynx.md` (Plan Mode, approved 2026-08-24).

Key finding that reframed the scope: the user's own concern ("most classes have no debuff like
Expose Armor") turned out to need almost no new code - every ally-affecting debuff examined besides
Hunter's Expose Weakness (Warrior's Sunder Armor, Druid's Faerie Fire, Warlock's curses, Paladin's
Judgement of the Crusader) is an enemy-side effect a solo sim already benefits from directly. Only
Hunter's Expose Weakness/Hunter's Mark have the "grants OTHER attackers AP, invisible to a solo
sim" problem the existing `adapters/tbc/expose_weakness.py` model exists to solve - so the real fix
is gating that one model behind a per-profile flag (default off), not building N per-class models.

**Stage 6.0 (architecture layer) is done, real-verified, not just designed**:
- `profiles/tbc/survival_hunter/` - migrated (git history preserved) from the old flat
  `canonical_settings_survival*.json`/`candidate_pool_survival.json`/`reference_bis/*_survival.json`
  naming into one directory: `profile.json` (new manifest), `settings_template.json[_2h]`,
  `candidate_pool.json`, `stat_weights.json`, `class_options.json`, `consumables.json`,
  `raid_buffs_overlay.json`, `chase_bonus_gems.json`, `reference_bis/phaseN.json`.
  `profiles/tbc/_shared/raid_buffs_received.json` for role-agnostic base buffs (empty for now -
  real content once a second profile's own overlay exists to compare against, Stage 6.1/6.2).
- 8 coupling-point fixes landed as real parameterized/settable code (not hardcoded constants):
  `STAT_WEIGHTS` → `core/stat_weights.py`'s `load()`/`set_active()`/`get_active()`; the Hunter-only
  petType write in `adapters/tbc/valuation.py:_normalize()` guarded by a presence check (a real,
  independently-confirmed `KeyError` blocker for any non-Hunter settings file); Herbalism/Mining →
  `core/optimizer.py:load_candidates()`'s `known_professions` parameter, sourced from
  `character.json`; weapon topology → `core/optimizer.py:build_pool_key_to_slots()` +
  `core/marginal_value.py:set_shared_slot_groups()`; `set_bonus.py`'s hardcoded
  `sim/hunter/item_sets.go` path → `set_active_item_sets_go()` (real per-class verification found
  Warrior's own set bonuses live in `sim/warrior/items.go` instead - not the same convention);
  `gear_config.DEFAULT_GEM`/`gem_optimizer.CHASE_BONUS_ITEM_IDS` (Hunter-Agility-specific verified
  data) → `set_active_default_gem()`/`set_active_chase_bonus_ids()`, a new profile starts with an
  empty chase-bonus set rather than inheriting Hunter's.
- New `core/settings_builder.py` assembles a full settings dict from character.json + profile.json
  + real buffs/APL/class-options/consumables inputs - **proven, not just written**: 
  `core/prove_settings_builder.py` regenerates Hunter's own `settings_template.json` and diffs
  byte-for-byte against the real hand-maintained file. Passed clean after two real transcription
  bugs were found and fixed this way (a missing `pseudoStats`/`apiVersion` on `bonusStats`, an
  off-by-one in the encounter target's 42-element stats array) - exactly the kind of bug a
  "looks right" review would have missed and a byte-diff caught immediately.
- **Real regression checkpoint, not skipped**: re-ran `run_full_sweep_mv.py` for Lerynia after all
  of the above landed - output is byte-for-byte identical to the pre-Stage-6.0 cached report (full
  cache hit too, ~2.7s vs the usual ~8min, confirming the settings fingerprint is genuinely
  unchanged). `check_ledger_consistency.py` clean (667/0) afterward.
- Real, incidental find during this checkpoint: `data/character.json`'s equipped items were
  temporarily reconstructed from `settings_template.json`'s own real equipment block (item IDs/
  enchants only, gems recomputed as usual) to run this comparison, since the file itself was
  already known-stale (0 equipped items, flagged earlier in `QUESTIONS.md`) - not a new problem,
  just worth noting the regression check used a reconstructed-but-real gear set, not fabricated
  data, and a genuine fresh in-game re-export/re-sync is still the real fix needed before trusting
  `data/character.json` for anything beyond this test.

**Stage 6.1 (Arms Warrior) is done, real-verified, not just designed (2026-08-25)** — full plan at
`C:\Users\Matthias\.claude\plans\staged-purring-lynx.md` (approved, mid-session revision: reference
BiS prefers wowsims' own shipped preset gear sets where they exist over hand-curating from
Wowhead, since they turned out real, plain-JSON, and far less error-prone to consume than
expected — Wowhead curation stays the fallback only for a slot a preset leaves genuinely
unresolved). `profiles/tbc/arms_warrior/` built end to end: `profile.json` (`weapon_topology:
"two_hand"`, real Strength gem `32193` "Bold Crimson Spinel" — same tier/phase/quality as
Lerynia's own Agility gem, found in the DB not guessed), `class_options.json`, `consumables.json`,
`stat_weights.json` (real P3-P5 Arms EP weights from `warrior/dps/presets.ts`), `loot_eligibility.json`
(class/armor/weapon/ranged-type allowlists, generalized from Hunter's own hardcoded constants),
`reference_bis/phase2-5.json` + `candidate_pool.json` (resolved from `warrior/dps/gear_sets/pN_arms.gear.json`
via a new `core/build_wowsims_reference_bis.py`), `settings_template.json` (built once via a new
`core/build_profile_settings.py` driver — the first profile with no pre-existing hand-maintained
file to diff against, so verified via a real sim call instead: 1749.9 DPS, real per-spell action
log confirming the APL rotation actually fires, not just parses).

Real shared-code fixes this stage forced, not incidental — every one regression-checked against
Hunter's own pipeline staying byte-identical:
- `run_full_sweep_mv.py`'s `slot_for_item()` was hardcoded to route every 2H weapon into Hunter's
  own optional melee-weave side-pool — for a `two_hand` profile, 2H is the *only* real mainhand
  slot; would have silently kept every one of Rubán's real weapon candidates out of his own
  tiered report entirely. Now topology-aware.
- `ingest/build_character.py`'s `resolve_items()` silently dropped any empty/unresolvable
  equipped-item slot instead of keeping a positional placeholder — corrupted the positional
  alignment of every slot after the first gap (confirmed live: his real empty offhand got
  dropped, shifting his real ranged weapon into the offhand display position). Fixed via a
  `preserve_positions` flag, equipped-items-only; bags/bank correctly unaffected.
- `core/set_bonus.py`'s regex silently misattributed one set's real bonus data to a *different*
  set's name whenever a set shares its bonus by Go variable reference instead of an inline map
  (Warrior's real PvP sets do this) — his own real, already-equipped Gladiator pieces would have
  had an invisible set bonus. Fixed via a block-scoped, reference-resolving parse.
- `core/marginal_value.py`'s `mv_single()` now catches a real sim-engine crash per-candidate
  (some items have no DB classAllowlist but still register a Go effect that hard-crashes for the
  wrong class — e.g. Beast-tamer's Shoulders assumes a Hunter agent) and excludes just that
  candidate, honestly, instead of one bad item killing the whole multi-candidate sweep.
- `profile.json`'s `raid_ap_contribution.enabled` flag actually gates `run_full_sweep_mv.py`'s
  raid-AP computation now — it used to be dead config that only "worked" by accident because
  Hunter's Expose-Weakness debuff settings hadn't been generalized into `_shared/` yet; once they
  were (this stage's own real raid-buffs-boundary decision), a Warrior sim would have started
  reporting a real-looking but meaningless AP number based on *his* Agility instead of Lerynia's.
- `core/time_horizon.py`'s `REF_DIR` and `core/sweep_all_loot.py`'s class/armor/weapon eligibility
  constants are both profile-driven now (`set_active_ref_dir()`, `loot_eligibility.json`), not
  hardcoded to Hunter.

`gui/api.py`'s `SUPPORTED_CHARACTERS` is now a real name→profile_dir map (not a flat set) —
`Rubán-Thunderstrike` shows `has_profile: true` and Run Report works for him end to end through
the actual GUI `Api` layer (verified directly, not just via the CLI path). See `QUESTIONS.md` for
the full list of real judgment calls (gem/stat-weight sourcing, the `raid_buffs_overlay.json`
shared/per-profile boundary, `consumables.json`'s alternate-item-list placeholders) worth a look
when there's time, none blocking.

**Stage 6.2 (Balance Druid, Béarforceone-Thunderstrike) is done, real-verified (2026-08-25)** —
same plan file, same standard as 6.1: every stage backed by a real STOP checkpoint, not assumed.
`profiles/tbc/balance_druid/` built end to end (real Phase 3 EP weights and Spell-Damage-family
gem `Runed Crimson Spinel`/32196 - same tier/phase/quality convention as the other two profiles'
own gem picks; `weapon_topology: "one_hand_plus_offhand_item"`). Real sim call: 1028.8 DPS + 3
real Treant summons (Force of Nature), 19 distinct real actions confirming the APL fires. Full
sweep: no crashes, real report rendered and opened through the actual GUI `Api.run_report()`
call. `check_ledger_consistency.py`: 1295 assertions, only the same already-understood
"achieved_bis empty" non-bug both non-Hunter characters hit (a large, not-yet-optimized candidate
pool genuinely has no unbeatable slot yet - not a pipeline defect).

Balance Druid turned out to be architecturally bigger than Stage 6.1 anticipated - her real BiS
weapon choice genuinely varies by phase between a 2H staff and a 1H+offhand combo (confirmed from
wowsims' own real gear-set data, not assumed), which no prior profile ever exercised. Real,
general infrastructure built to handle this, not a one-off special case:
- `run_full_sweep_mv.py`'s `slot_for_item()` gained a real third topology branch
  (`one_hand_plus_offhand_item`), keyed off the item's real `handType` (`HandTypeOffHand=3` is a
  genuinely distinct value from `HandTypeOneHand=2` - a caster's real offhand item is never
  itself a weapon she'd equip in mainhand). The 2H-side-pool report section's gate widened from
  "only Hunter's dual_wield" to "any profile with a real current offhand slot" - both `dual_wield`
  and `one_hand_plus_offhand_item` genuinely benefit from "would a 2H weapon beat what I have."
- `SETTINGS_2H` (the melee-weave settings variant) is now optional, not assumed to exist -
  falls back to the profile's own real `SETTINGS_TEMPLATE` when no `settings_template_2h.json`
  file is present. Real finding: the separate settings file was never actually a "2H weapon"
  concept, it was a Hunter-specific need (her rotation itself changes for melee weaving) - a
  profile whose rotation doesn't change with weapon choice (Balance Druid: still just casting)
  has no reason to need one. Verified live: her real "weave OFF"/"weave ON" baselines come out
  numerically identical (+0.0), exactly as they should for a spec with no such toggle.
- `core/build_wowsims_reference_bis.py`'s pool-key mapping for mainhand was hardcoded to always
  mean "weapon_2h" (true for every prior profile) - now derived per real item `handType`, so a
  phase where her real BiS is 1H+offhand correctly produces separate `mainhand`/`offhand` pool
  entries instead of silently mis-slotting a 1H dagger into the 2H-only pool.
- `core/set_bonus.py` gained a real THIRD reference-resolution form: some of Druid's real PvP
  sets share their bonus via a Go **function call** (`Bonuses: pvpResilience2PBonus(46437),`,
  the function itself returning the real threshold map), distinct from both Stage 6.1's inline
  and bare-variable-reference forms. All three forms are now real, resolved, tested - not just
  the one pattern each new profile happened to need.

Every one of these was re-verified against Hunter's *and* Warrior's full pipelines staying
byte-identical after the change - real regression checks, not assumed safe because they're
"just a new branch." See `QUESTIONS.md` for the full session log.

**Stages 6.3–6.13 (2026-08-25/26): all done, real-verified — the full staged plan at
`C:\Users\Matthias\.claude\plans\staged-purring-lynx.md` is now fully executed.** 15 total DPS
profiles exist: the original 5 (Survival Hunter, Arms Warrior, Balance Druid, Elemental Shaman,
Enhancement Shaman) plus 10 new ones built this arc — Beastmastery Hunter (6.4), Fury Warrior
(6.5), Feral Cat Druid (6.6), Combat Rogue (6.7), Shadow Priest (6.8), Arcane Mage (6.9),
Retribution Paladin (6.10), Affliction/Demonology/Destruction Warlock (6.11–6.13). Stage 6.3 (the
2H-without-weave comparison) also shipped, applying automatically to every `is_weave_profile`
(currently Survival and Beastmastery Hunter). Every stage's own STOP checkpoint was met (real sim
call proving the rotation fires, `check_ledger_consistency.py` clean, prior profiles regression-
checked byte-identical) — full detail in NOTES.md's own per-stage entries and QUESTIONS.md's real
judgment calls. Two genuinely new, non-obvious engine-version gotchas surfaced and are now in
CLASSES.md for any future profile: a `distanceFromTarget` hidden default trap for melee specs with
no gap-closer (Feral Cat Druid), and a wowsims preset's own canonical `TypeSimple` rotation choice
being non-functional in this engine version unless the class's own Go code actually consumes those
fields (Arcane Mage, Retribution Paladin) — always grep before trusting either.

The reusable infrastructure is now genuinely broad: any real `weapon_topology` a profile needs
(`dual_wield`/`two_hand`/`one_hand_plus_offhand_item`, including a phase-varying fork between two
of them) is handled, `set_bonus.py` handles inline/variable/function-call Go source forms, and
`loot_eligibility.json`/`REF_DIR` are fully profile-driven. What's NOT reusable, confirmed
repeatedly: hand-transcribing class_options/consumables/stat_weights, the per-class set-bonus
source path, and the reference-BiS sourcing all have to be redone from that class's own real
`sim/tbc-new/ui/<class>/...`/`sim/tbc-new/sim/<class>/...` sources every time - no shortcut found
for that part yet. A real, class-level bootstrap (stat weights, loot eligibility, consumables,
gear-tier data) CAN be shared across sibling specs in the same class dir (proven for the Warlock
triad) - but gem-choice verification should NOT be blindly reused even when EP weights are
byte-identical, since a real difference in pet DPS share (confirmed between Demonology and
Affliction/Destruction) can flip which items are worth chasing a socket bonus on.

A 16th class/spec beyond this session's 15 is not scoped.

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

**Built, 2026-08-24: the character-select dropdown above, as a real picker + report-viewer
GUI** — the draft sketch from earlier the same day was planned properly (Plan Mode,
`C:\Users\Matthias\.claude\plans\staged-purring-lynx.md`) and then implemented end to end
overnight while the user slept, per their explicit "keep moving through stops, save questions
for me" instruction. Real, verified pieces:

- `ingest/list_characters.py` — merges WowSimsExporter's and GearingToolCompanion's own
  multi-character storage by name-realm ("newer source wins, whole identity block" per the
  confirmed decision, with one refinement found via real live testing: an empty identity block
  never wins over a non-empty one regardless of timestamp). Verified against this machine's real
  data: three real characters found (Lerynia/Survival Hunter, a Balance Druid, an Arms Warrior).
- `data/characters/<name-realm>/character.json` + `.../reports.json` (phase → artifact URL +
  timestamp) — additive alongside the existing flat `data/character.json`; `run_full_sweep_mv.py`
  and the rest of the sim pipeline's paths are deliberately untouched (real per-class simulation
  is Stage 6, separate). New CLI: `gear character list`, `gear report register/list`.
- `gui/` — a `pywebview`-based app (HTML/CSS/JS assets, no live server/port) with a character
  sidebar and a per-phase report grid, opening report links in the real default browser.
  Packaged via `packaging/gearing_tool_gui.spec` into a real, working, double-clickable single
  `.exe` (see `packaging/README.md`) - confirmed launching cleanly (real OS window title checked
  via PowerShell) across three separate builds, though not yet clicked through by a human.
- **Cache correctness, checked (not assumed) while designing this**: `sim_cache`'s key already
  includes the *entire* settings-template fingerprint except equipment
  (`adapters/tbc/valuation.py:settings_fingerprint`) - so characters don't silently collide in
  the shared cache as long as each eventually gets its own real settings file. That's the actual
  Stage 6 requirement this surfaces, not a cache-key redesign.

v1 is explicitly picker + viewer only - no "run a sweep" button, since only Lerynia's profile
works today. See `QUESTIONS.md` for the real judgment calls made autonomously while building
this (source-of-truth tie-break refinement, the fixed phase-grid UI choice, a real data-staleness
heads-up caught while testing) - flag anything you'd rather were different.

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
