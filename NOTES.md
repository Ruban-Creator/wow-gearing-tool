# Notes

Append-only log of real facts discovered while building this tool — CLI flags, schema quirks,
addon format details, anything surprising. Newest at bottom.

## 2026-08-22 — Stage 1 pre-flight research

- `wowsims/tbc-new` confirmed to exist on GitHub, fork of `wowsims/mop`, latest release
  v0.0.116 (2026-08-14). `cmd/wowsimcli` builds via `go build --tags=with_db`.
- `docs/commands.md` in tbc-new documents only `make` targets (`make host`, `make db`,
  `make wowsimtbc`, `make test`, etc.) — it does NOT document `wowsimcli`'s actual runtime
  flags. Those have to come from `wowsimcli --help` after building, per the spec's instruction.
- Makefile CLI build (Windows): `cd ./cmd/wowsimcli && GOOS=windows GOARCH=amd64 GOAMD64=v2 go
  build -o wowsimcli-windows.exe --tags=with_db -ldflags="-X 'main.Version=$(VERSION)' -s -w"`.
  No npm/vite step for the CLI — that's only in `make host`/`make wowsimtbc` (web UI).
- Local toolchain at start of Stage 1: Go — NOT installed. Node/npm — NOT installed. Python
  3.13.7 — installed. git 2.55.0 — installed.
- Installed addon: `WowSimsExporter` v3.2.4 (TOC), well past the v2.8 that added
  SavedVariables auto-save. `## SavedVariables: WSEDB` in the TOC — global var name is `WSEDB`,
  on-disk file is `WowSimsExporter.lua` under some `WTF/Account/<ACCOUNT>/SavedVariables/`.
  `autoSaveEnabled = true` by default (AceDB profile default in `SavedDataManager.lua`).
- `SavedDataManager:OnCharacterChanged` only fires an auto-save when
  `character.level == GetMaxPlayerLevel()` (`WowSimsExporter.lua` / `SavedDataManager.lua`).
  Below cap, nothing auto-saves — a manual `/wse export` is needed to seed the SavedVariables.
- `WTF/Account/` on this machine has 4 candidate dirs: `119781733#1`, `430010907#1`,
  `ELFIDELFI`, `PULLANDGO`, plus a stray top-level `SavedVariables` folder. Which one is the
  Nightelf SV Hunter's account is unresolved — first concrete ingestion task.
- Read `ExportStructures/EquipmentSpec.lua` directly: `FillFromBagItems()` iterates
  `bagId = 0, NUM_BAG_SLOTS` only. **No bank container is read.** This is confirmed from
  source, not inferred — a companion bank-export addon is required, the spec's assumption was
  correct.
- Export schema (`Character.lua`): default export (`GenerateOutput`) is
  `{version, unit, id, name, realm, race, class, level, talents, professions, spec, gear,
  glyphs}`, JSON-encoded via `LibParse:JSONEncode`. `gear.items` here is **equipped only**
  (`UpdateEquippedItems`). Bag contents come from a separate generator (`GenerateOutputBags`)
  producing a bare `{items: [...]}` — equipped and bag exports are two different button
  actions/outputs in the addon UI, not one combined export. Tool must call/merge both.
- `EquipmentSpec.items` is a 17-slot fixed array (`itemLayout` in `EquipmentSpec.lua`): head,
  neck, shoulder, back, chest, wrist, hand, waist, legs, feet, finger1, finger2, trinket1,
  trinket2, mainhand, offhand, ranged. Ammo is explicitly excluded ("Not supported as item").
- Phase 3 launches 2026-08-27 (5 days out from today). DB-coverage check for P3 items is
  expected to possibly show gaps/placeholders right now — not a bug if so.

## 2026-08-22 — Go install, submodule pin

- Installed Go 1.26.7 via `winget install --id GoLang.Go`. Installer puts it at
  `C:\Program Files\Go\bin` and updates the machine PATH — new shells pick it up automatically,
  but the git-bash tool session already open in this conversation did not; had to prepend
  `/c/Program Files/Go/bin` to PATH manually in that session.
- `wowsims/tbc-new` added as git submodule at `sim/tbc-new`, pinned commit
  `3267f8dfa4a20746d4982c1522fdec1d4eb77f4c` (2026-08-19, "Add selected potion/conjured APL
  check"). This is the SHA to report in every sim output per the ground rules.

## 2026-08-22 — Building wowsimcli: real prerequisite chain

The doc's "needs the with_db build tag" undersold this — a plain `go build` fails. Full chain,
in order:

1. **protoc + protoc-gen-go**, installed via `winget install --id Google.Protobuf` (puts
   `protoc.exe` under `...\WinGet\Packages\Google.Protobuf_.../bin`) and
   `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest` (lands in `%GOPATH%\bin`,
   `C:\Users\Matthias\go\bin`). Neither is on PATH by default in an already-open shell — add both
   explicitly per session, or restart the shell.
2. Generate the proto Go bindings (repo root of the submodule):
   `protoc -I=./proto --go_opt=Mgoogle/protobuf/descriptor.proto=google.golang.org/protobuf/types/descriptorpb --go_out=./sim/core ./proto/*.proto`
   — produces `sim/core/proto/*.pb.go` (untracked, gitignored upstream, must be regenerated
   after every fresh clone).
3. Extract the item/spell/talent DB from the **local WoW client** via `tools/db2tool`:
   - The settings file `tools/database/generator-settings.json` has relative-path fields
     (`GameTablesOutDirectory: "../../assets/db_inputs/basestats"`) resolved **relative to the
     settings file's own directory** — a copy placed elsewhere breaks those paths. Put any local
     override alongside the original, e.g. `tools/database/generator-settings.local.json`
     (untracked in the submodule, not committed).
   - `BaseDir` must be the WoW **root** that contains `.build.info`, `Data/`, and the
     product subfolders (`_anniversary_`, `_retail_`, etc.) — NOT the product folder itself. On
     this machine that's `C:/Games/World of Warcraft`, with the Anniversary client at
     `_anniversary_` underneath (`Product: "wow_anniversary"` in the settings, confirmed present
     in `.build.info`).
   - Default hotfix-cache auto-scan (`<BaseDir>/**/DBCache.bin`) picks up a **stale, incompatible**
     `Cache_/ADB/enUS/DBCache.bin` at the WoW root (leftover from another install) and fails with
     `unsupported DBCache version 5 (only XFTH v9 is supported)`. Fix: pass
     `--dbcache "<BaseDir>/_anniversary_/Cache/ADB/enUS/DBCache.bin"` explicitly to pin the
     correct product's cache.
   - Working command from the submodule root:
     `go run ./tools/db2tool -s tools/database/generator-settings.local.json --output tools/database/wowsims.db --dbcache "C:/Games/World of Warcraft/_anniversary_/Cache/ADB/enUS/DBCache.bin"`
   - Result: `wowsims.db` (SQLite, ~42MB), extracted from **build 69110** (live Anniversary
     realm as of 2026-08-22). 15,588 items loaded, 28,687 spells, 579 talents.
4. Generate the runtime asset DB: `go run tools/database/gen_db/*.go -outDir=./assets -gen=db`
   → writes `assets/database/{db.bin,leftover_db.bin,db.json,leftover_db.json}`. **This repo
   embeds the item DB as a protobuf blob (`db.bin`) loaded via `go:embed` in
   `assets/database/loader.go`, not as a generated `all_items.go` Go source file** — the
   makefile's `sim/core/items/all_items.go` target is stale for this fork; ignore it, `db.bin`
   is what `--tags=with_db` actually embeds.
5. Build: `go build -o wowsimcli.exe --tags=with_db ./cmd/wowsimcli/cli_main.go`. Succeeded,
   30MB binary.

**Actual `wowsimcli --help` output** (not documented in `docs/commands.md`, which only covers
`make` targets):
```
wowsimcli [command]
  completion  Generate the autocompletion script for the specified shell
  decodelink  decode wowsims link/url
  help        Help about any command
  sim         simulate items & settings
  version     prints version information
```
```
wowsimcli sim [flags]
  --infile string    location of input file (RaidSimRequest in protojson format) (default "input.json")
  --outfile string   location of output file, defaults to stdout
  --verbose          print information during runtime
```
`wowsimcli version` printed `development` (no version string baked in — expected since we built
without the makefile's `-ldflags="-X 'main.Version=...'"`; fine for local use, but means
`version()` in the adapter should report the **submodule's pinned git SHA**, not the binary's
own version string, for the "record commit SHA" rule).

## 2026-08-22 — Resolved: the CLI's actual input contract

This was flagged as Stage 1's biggest open risk. Resolved by reading
`ui/core/components/individual_sim_ui/exporters/individual_cli_exporter.tsx`:

```ts
getData(): string {
    const raidSimJson: any = RaidSimRequest.toJson(this.simUI.sim.makeRaidSimRequest(false));
    delete raidSimJson.raid?.parties[0]?.players[0]?.database;
    return JSON.stringify(raidSimJson, null, 2);
}
```

So `input.json` for `wowsimcli sim` is **protojson for the `RaidSimRequest` message**
(`proto/api.proto`), with the per-player `database` field stripped (the web UI normally embeds
item data inline per-player for browsers running without `with_db`; the CLI doesn't need it
since it has the whole DB embedded via `db.bin`).

`RaidSimRequest` shape (`proto/api.proto`):
```
RaidSimRequest { raid: Raid, encounter: Encounter, sim_options: SimOptions, type: SimType }
Raid            { parties: [Party], num_active_parties, buffs: RaidBuffs, debuffs: Debuffs,
                  tanks, stagger_stormstrikes, target_dummies }
Party           { players: [Player], buffs: PartyBuffs }
SimOptions      { iterations, random_seed, debug, debug_first_iteration }
SimType         { SimTypeUnknown=0, SimTypeIndividual=1, SimTypeRaid=2 }
```

Separately, `proto/ui.proto` defines `IndividualSimSettings` — and it is **field-for-field the
same shape as the `.build.json` / `.gear.json` preset files already shipped in the repo**
(`raid_buffs`, `debuffs`, `party_buffs`, `player`, `encounter`, `settings: SimSettings`). Example:
`ui/hunter/dps/builds/phase_3/sv/2h_9p.build.json` is valid protojson for `IndividualSimSettings`
right now — confirmed by matching field names 1:1 against `message IndividualSimSettings` in
`proto/ui.proto`.

**No Go-side function does the `IndividualSimSettings → RaidSimRequest` expansion** — that logic
(`makeRaidSimRequest()` in `ui/core/sim.ts`) is TypeScript-only, calling `getModifiedRaidProto()`
+ `encounter.toProto()` + wrapping in `SimOptions`. Since we deliberately have no Node/npm, the
adapter has to replicate this expansion itself. It's mechanical, not guessed — every field name
below comes directly from the `.proto` sources, not memory:
- `raid.parties[0].buffs` ← `party_buffs`
- `raid.buffs` ← `raid_buffs`
- `raid.debuffs` ← `debuffs` (lives on `Raid`, not per-`Target` — confirmed from `message Raid`
  in `proto/api.proto`)
- `raid.parties[0].players[0]` ← `player` (this is where our character.json gear/talents/race
  go)
- `encounter` ← `encounter`
- `sim_options.iterations/random_seed` ← `settings.iterations` / a fixed seed we choose (per the
  determinism ground rule, not `settings.fixed_rng_seed` necessarily — need to confirm that
  field's semantics before relying on it)
- `type` ← `SimTypeIndividual` always (we're never running a real 25-body raid sim, just 1 player
  under raid-buff assumptions — see the Stage 2 Expose Weakness question below)
- the CLI-export's `delete player.database` step is required too — the DB is embedded, sending
  it duplicates/conflicts with `--tags=with_db`.

This expansion will live in a small Go bridge (using the submodule's own generated proto
package, so no enum/field table gets hand-copied into Python) rather than being reimplemented in
Python — keeps protojson handling on the Go side, keeps `core/`/Python dict-only per the
architecture rule, and the bridge is the actual adapter-boundary translator.

## 2026-08-22 — Stage 2 preview (not resolved now — Stage 2 is a separate blocker)

`ui/hunter/dps/builds/phase_3/sv/2h_9p.build.json`'s `debuffs` block includes
`"exposeWeaknessUptime": 0.9` and `"exposeWeaknessHunterAgility": 1080` as **manually-specified
individual-sim inputs**, not something the individual sim computes from the player's own agility
automatically. This is suggestive for Stage 2's Expose Weakness question but does not resolve it
— recorded here only so Stage 2 doesn't have to rediscover it from scratch. Do not treat this as
the answer; Stage 2 still has to read the actual hunter sim code per the doc's instruction.

## 2026-08-22 — SavedVariables located; current export is NOT usable yet (needs your action)

Found it: `WTF/Account/ELFIDELFI/SavedVariables/WowSimsExporter.lua` (the other candidate,
`119781733#1`, is a 124-byte stub — wrong account). Confirms the Nightelf SV Hunter is
**Lerynia-Thunderstrike**, professions Herbalism 375 / Mining 375 — matches §0.

**But the auto-saved snapshot for Lerynia (timestamp 2026-08-22 11:20:00) has `"gear":{"items":
[]}` — empty — and `"spec":"beast_mastery"`, not survival.** Auto-save fired (correctly, per the
`OnCharacterChanged` logic already noted) but caught a moment with no gear resolved and/or the
character on its other spec. This data isn't usable for ingestion as-is.

**Action needed from you**: switch to Survival spec, make sure gear is equipped (not dead/ghost/
character-select), then run `/wse export` once in-game to force a fresh save. I can't trigger
this myself. The ingestion code below is written and tested against the shape of this file
(validated against the other characters' non-empty entries in the same SavedVariables file, e.g.
Rubán's warrior gear array), so it'll pick up a corrected Lerynia export automatically on the
next `gear sync` — no code changes needed once you've re-exported.

## 2026-08-22 — Existing preset assets to reuse (bootstraps §5's reference BiS list for free)

`ui/hunter/dps/gear_sets/phase_{1..4}/{bm,sv}/*.gear.json` and
`ui/hunter/dps/builds/phase_{1..4}/{bm,sv}/*.build.json` already exist in the submodule for
every phase including **Phase 3 SV** (`2h_6p`, `2h_9p`, `dw_6p`, `dw_9p` — 2h/dual-wield ×
6pc/9pc T5 set-bonus variants). These are the sim maintainers' own reference BiS, already in the
target protojson-compatible shape (`.build.json` = `IndividualSimSettings`). Use these directly
as Stage 1's "preset SV BiS" baseline and as Stage 5's bootstrap reference list — no need to
source or transcribe a BiS list separately.

## 2026-08-22 — Correction: the DB extraction step above was unnecessary and got reverted

After building, `git status` inside the submodule showed `assets/database/db.bin` (and several
`proto/*.proto` / `*_auto_gen.go` / `*_auto_gen.ts` files) as **modified**, not untracked — the
repo already ships a **pre-built, committed** item DB (`git show HEAD:assets/database/db.bin`
existed, same byte size as my local extraction, committed 2026-08-19, three days before our
pinned commit). Running `db2tool` + `gen_db` overwrote these tracked files with a fresh
extraction from the local client instead of using what the pinned commit actually specifies —
harmless in this case (same build 69110, results were numerically identical before/after — see
below) but methodologically wrong: "record commit SHA in every output" only means something if
the code+data at that SHA is what actually ran.

**Fixed**: `git -C sim/tbc-new checkout -- .` reverted every tracked-file modification (the only
survivor is the untracked `tools/database/generator-settings.local.json`, which is fine — never
committed). Rebuilt `wowsimcli.exe` against the restored, pristine `db.bin`. Re-ran the baseline
below and got byte-for-byte the same DPS numbers, so no harm done here — but the corrected
takeaway for future sessions: **don't run `make db`/`db2tool`/`gen_db` unless
`assets/database/db.bin` is actually untracked or missing after a fresh clone.** Check
`git status` inside the submodule before assuming a "missing" build artifact needs regenerating
— it may already be committed and just not built into the binary yet (the actual gap here was
never the DB, only `sim/core/proto/*.pb.go`, which genuinely is gitignored upstream and does
need `protoc` every time).

## 2026-08-22 — Bridge built, real bug found and fixed (not worked around)

Built `adapters/tbc/bridge/` (own Go module, `replace github.com/wowsims/tbc => ../../../sim/tbc-new`).
First run against `ui/hunter/dps/builds/phase_3/sv/2h_9p.build.json` panicked inside
`core.NewCharacter`: `index out of range [26] with length 26` on `PseudoStat_PseudoStatReducedCritTakenPercent`.
Root cause, confirmed by counting: `proto/common.proto`'s `PseudoStat` enum has **27** values,
but the shipped `.build.json`'s `bonusStats.pseudoStats` array has only **26** — a stale preset
asset that predates a `PseudoStat` enum addition, at the *same* pinned commit (not a version
skew on our end). `Stat` (42 values) matches its array length fine; only `PseudoStat` is short.
Fixed by zero-padding `UnitStats.stats`/`.pseudoStats` up to `len(proto.Stat_name)` /
`len(proto.PseudoStat_name)` in the bridge before use (`padUnitStats` in `main.go`) — zero is
always the correct value for a stat the preset predates, so this can't invent a nonzero bonus,
and it's logged to stderr every time it fires so it stays visible. Applies to both
`player.bonusStats` and `player.itemSwap.prepullBonusStats`.

## 2026-08-22 — Baseline run: preset Phase 3 SV BiS (2h_9p), 10k iterations, seed 1

```
python cli/gear.py preset sim/tbc-new/ui/hunter/dps/builds/phase_3/sv/2h_9p.build.json --iterations 10000 --seed 1
```
sim commit: `3267f8dfa4a20746d4982c1522fdec1d4eb77f4c`
- **Player DPS: 1030.86 ± 44.13** (stdev; min 858.65, max 1186.16 across the 10k iterations)
- **Pet (Ravager) DPS: 317.05 ± 15.43**
- **Combined: 1347.91** — pet is ~23.5% of total damage
- **Important gotcha for Stage 4+**: the sim's own `raidMetrics.dps` / `party.dps` rollup fields
  are numerically identical to `player.dps` — they do **not** include pet damage. Confirmed by
  direct comparison, not assumed. Any MV computation that reads the raid/party-level `dps`
  rollup as "total" will silently drop ~23% of a Survival Hunter's real output. The optimizer
  must sum `player.dps + sum(pet.dps for pet in player.pets)` itself.

This preset's own bundled config does **not** match §0's assumed encounter/consumes exactly —
using it unmodified for this baseline (as the "preset SV BiS" deliverable calls for), but note
the differences for when Stage 4 builds requests from *my* actual raid setup instead of reusing
presets wholesale:
- Encounter: **180s ± 5s**, level 73 `MobTypeMechanical` target — not §0's 300s ± 60s.
- Race: `RaceOrc` (the preset is race-generic/example, not tailored to Nightelf).
- Consumables include `scrollAgi`/`scrollStr`/`petScrollAgi`/`petScrollStr` = true — §0 says
  "no scrolls will be used." Flask/elixirs: `battleElixirId`/`guardianElixirId` (dual elixirs),
  not a flask — §0 says "flask or elixirs," so this is consistent, just noting which the preset
  picked.
- Rotation: `rotation.type = "TypeSimple"` (not an APL priority list) — haven't inspected what
  "Simple" rotation parameters this preset carries beyond the type tag; worth a closer look
  before Stage 4 needs to reason about rotation choice.

Full raid/party/debuffs/consumables/encounter JSON actually used is reproducible from the
preset file itself (`ui/hunter/dps/builds/phase_3/sv/2h_9p.build.json`) — not re-pasted here
since it's just that file's content; see the file directly.

## 2026-08-22 — Companion addon note: WowSimsExporter's bag export never reaches disk

Re-reading `WowSimsExporter.lua`'s `GenerateOutputBags()`: it returns JSON for the UI's textbox
only — unlike the equipped-gear export, it is never passed to `SaveCharacterData`. So contrary
to the plan's assumption, **bag contents never auto-save to SavedVariables at all**, not even
with v3.2.4 installed — only equipped gear does. Bank was already known to be uncovered
entirely. Rather than have the user paste bag exports by hand (defeats the "no clipboard round-
trip" goal), extended the companion addon to dump both bags and bank
(`Interface/AddOns/GearingToolExporter/`, `GTExporterDB` SavedVariables, `/gtexport` slash
command, auto-saves on bank open and login). This makes it ~75 lines, over the doc's <50-line
guideline for a bank-only addon — the overage is covering a second real gap (bags), not scope
creep. Not yet exercised in-game (needs a reload/relogin to load, then a bank visit or
`/gtexport`) — `ingest/build_character.py` reads it if present and degrades to empty
bags/bank if not, so nothing breaks in the meantime.

## 2026-08-22 — Ingestion pipeline built and tested (Lerynia's own data still blocked)

`ingest/build_character.py`: parses `WowSimsExporter.lua` (via `slpp`) across every
`WTF/Account/*/SavedVariables/`, JSON-decodes the nested `data` string per matching character,
merges in `GearingToolExporter.lua`'s bags/bank if present, cross-references every item ID
against `sim/tbc-new/assets/database/db.json`, and writes `data/character.json`. Unresolved IDs
(not found in the sim DB) are kept under `unresolved`, never silently dropped, per the ground
rule.

**Validated against real data**: ran against `Rubán-Thunderstrike` (the account's warrior, who
has a populated export) — 16/17 equipped slots resolved (1 empty ranged slot, correct for a
warrior), 0 unresolved. Confirms the parser itself is correct end-to-end.

## 2026-08-22 — Cross-validated against wowsims.com; bug was mine, not the pipeline's

User ran their real gear on the live site (https://www.wowsims.com/tbc/hunter/dps/) and got
2310.14 ± 62 DPS; my own "sim my gear" one-off script gave 913.7-2518.7 depending on which
borrowed rotation I used — neither close. Root-caused by feeding the user's *exact* exported
JSON (their Export button output) straight through `bridge.exe` + `wowsimcli.exe` with zero
modification: **got 2306.76 ± 63.05 player / 483.60 ± 19.64 pet — matches their screenshot
almost exactly.** This confirms the bridge + wowsimcli toolchain (the actual Stage 1 deliverable)
is correct against an independent, real-world reference.

The bug was in my diagnostic script (`data/sim_my_gear.py`), not the pipeline: it substituted
real race/gear/talents into the stale `phase_3/sv/2h_9p.build.json` preset and left everything
else from that template, silently carrying over config that didn't match reality:
- Ammo: preset's `TimelessArrow` vs. the real `AdamantiteStinger`.
- Missing `mhImbueId`/`ohImbueId` (weapon stone imbues, correct for dual-wield) — the 2H preset
  had `explosiveId`/sapper charges instead, wrong playstyle entirely.
- Extra `partyBuffs` the preset assumed (`windfuryTotem`, `totemTwisting`) not present in the
  user's actual raid buff selection.
- Stale `apiVersion: 6` / 26-length `pseudoStats` vs. the live site's current `apiVersion: 14` /
  27-length array (consistent with the "shipped presets are stale" finding above).

**Lesson for every future request-building step**: don't fill gaps by borrowing fields from an
unrelated preset. Either use a real, verified value (from the character export or from §0's
explicit assumptions) or leave it flagged as missing — borrowing silently is exactly the kind of
thing "never invent data" is meant to catch, and it did, just after the fact instead of before.
Also confirms: WowSimsExporter's export has no consumable/ammo/imbue selection state at all
(only gear/talents/race/professions) — those always have to come from §0's stated assumptions
for any real MV request, never auto-detected.

**Update**: resolved. After a fresh in-game `/wse export` on Survival spec, `gear sync` now
produces a real, populated `character.json` — 17/17 equipped, 22 bag items, 28 bank items (once
the companion addon's `/gtexport`/bank-open was done), with unresolved items limited to
non-combat clutter (profession materials, quest items). Also fixed `load_item_db()` to check
`db.json`'s separate `consumables` collection in addition to `items` — ordinary consumables
(elixirs, food, sappers) were wrongly landing in `unresolved` before that.
