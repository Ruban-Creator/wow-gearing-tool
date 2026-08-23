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
items across 15 slots), and Stage 4 (§6, the valuation engine actually computing `DPS*(S)` for
these candidates — `core/run_full_sweep_mv.py` + the Phase 3 Upgrade Ledger artifact; still gets
real refinements as gaps are found, e.g. the top-1-always-resolves fix and the flat top-5 2H list,
but the stage itself is built and in active use).

Next up: **Stage 5** (§7, the strategy layer) — chiefly the interaction matrix
`I(i,j) = MV(i,j) − MV(i) − MV(j)` for the top ~12 candidates (complements/substitutes as
packages), the single largest unbuilt piece of the original spec. Also still open from §8
(Outputs): `results.csv`/`winner.json` as literal files (currently substituted by
`data/cache/tiered_report.json` + the HTML ledger, not the spec'd files themselves), package
goals (ties to the interaction matrix), and the gems/enchants free-reshuffle-vs-requires-gold
split. Per-currency spend sections from §8 are moot — acquisition-cost tracking was explicitly
dropped in favor of Wowhead linking.

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
not - both are real wowsims-provided presets, see NOTES.md's hit-cap entry) etc. Not part of any
current stage — noted here so it isn't lost, but don't build toward it until the user actually
asks. Keep `core/`/`adapters/` command-line-first and UI-agnostic in the meantime so a GUI can
sit on top later without a rewrite. Until the toggle exists, keep assuming 6% (moonkin present)
per the user's stated raid comp - never silently switch to 9% without being asked.

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
