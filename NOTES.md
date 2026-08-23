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

## 2026-08-22 — Stage 2: Survival mechanics, read from source (sim/hunter/talents.go, sim/core/debuffs.go)

All five requested talents are implemented, none stubbed. Her actual build (decoded from her
talents string against the field order in `proto/hunter.proto`'s `HunterTalents` message, then
verified by summing to the UI's displayed "Survival 34/61" — the sums matched exactly, 3+3+3+2+
0+0+0+2+2+0+0+3+2+2+3+0+0+5+1+0+3+0+0 = 34, confirming the positional mapping):
**Expose Weakness 3/3, Lightning Reflexes 5/5, Thrill of the Hunt 1/3, Survival Instincts 2/3,
Master Tactician 0/5 (not talented).**

- **Lightning Reflexes** (`registerLightningReflexes`, talents.go:558): flat multiplicative
  Agility, `1 + 0.03 * points`. At 5/5: +15% Agility.
- **Survival Instincts** (`registerSurvivalInstincts`, talents.go:529): flat multiplicative
  Attack Power AND Ranged Attack Power, `1 + 0.02 * points`. At 2/3: +4% AP/RAP.
- **Thrill of the Hunt** (`registerThrillOfTheHunt`, talents.go:566): on a ranged-special crit
  with a mana cost, `ProcChance = points/3`, refunds `40%` of that cast's mana cost. At 1/3:
  33% proc chance.
- **Master Tactician** (`registerMasterTactician`, talents.go:615): on ANY landed ranged hit
  (not just crit), flat 6% proc chance regardless of points, grants `2% * points` Physical Crit
  for 8s. Not on her build (0/5) so doesn't apply to her currently, but implemented correctly.
- **Expose Weakness** (`registerExposeWeakness`, talents.go:590 + `core.ExposeWeaknessAura`,
  debuffs.go:329): on a ranged crit, `ProcChance = points/3` (3/3 = 100%, guaranteed proc on
  every ranged crit). Applies a 7s debuff on the target that grants `floor(hunterAgility * 0.25)`
  bonus Attack Power AND Ranged Attack Power — stored as `target.PseudoStats.BonusAttackPower`/
  `BonusRangedAttackPower`.

### The gating question, answered with evidence

**Where the granted AP goes**: `spell_result.go:171` and `unit.go:215` — the functions computing
*any* attacker's effective (ranged) attack power against a target — read
`target.PseudoStats.BonusAttackPower`/`BonusRangedAttackPower` and add it to *that attacker's*
own AP for the purposes of their damage against this target. This is structurally raid-wide: in
a real raid sim with multiple simulated attackers, all of them would receive this bonus when
computing their damage against the debuffed boss. The mechanism is not personal-only by design.

**But**: an individual sim only ever has one player unit in the simulated raid. The mechanism
being raid-wide doesn't mean the *output* is raid-wide — there's no one else there to receive
the benefit and have it show up in the DPS number. Confirmed two ways:
1. In a debug (`--verbose`, 1 iteration) run, the Expose Weakness aura's stack count (=granted
   AP) visibly changes over the fight — 277 stacks at one point, 305 at another, tracking her
   *live* Agility as buffs/procs change it (a static input could never produce this; it would be
   a constant).
2. **Ablation test**: stripped `debuffs.exposeWeaknessUptime`/`exposeWeaknessHunterAgility`
   (the manually-editable raid-assumption fields in the UI, e.g. "1080"/"90%") out of the request
   entirely, re-ran with the same real gear/talents. The Expose Weakness aura still fires, still
   dynamically, still scaled to her live Agility (298 stacks → Agility 1192 at first proc).
   **This proves her own talented Expose Weakness (`hunter.registerExposeWeakness`) drives the
   debuff independently of, and takes priority over, the static raid-config fields** — those UI
   fields exist to model *another* hunter's Expose Weakness when the simulated character doesn't
   have the talent herself; for a character who does, they're redundant no-ops (both code paths
   register the same `Aura` identity via `GetOrRegisterAura`, and her character-construction-time
   registration wins the race, since it's evidently already active before the raid-config setup
   would apply its static uptime scheduler).

**Answer**: for Lerynia specifically (Expose Weakness 3/3), the individual sim correctly and
dynamically credits **her own share** of Expose Weakness's AP to her personal DPS — any candidate
item that changes her Agility will correctly move this contribution in an MV calculation, no
manual correction needed for that part. What the individual sim **cannot** see or report is the
AP that her raid's other 8-10 physical attackers (§0's stated comp) would *also* receive from
the same debuff, off the same live Agility — those units don't exist in an individual sim at all,
so their share is neither computed nor reported. Net effect: **every point of Agility Lerynia
gains is worth strictly more to the raid than what personal-DPS MV shows — the "underprices
Agility, in one direction" failure mode the doc names is real, just not in the way I initially
assumed** (it's not that her own EW benefit is miscounted; it's that the raid-mates' share is
invisible to this sim mode by construction).

### Path forward — needs your call, per §4's own fork

The doc offers two options once this is established: (a) run valuations against the raid sim
with your real comp, or (b) compute Expose Weakness's raid-wide value analytically and report
personal DPS and raid contribution as two separate columns everywhere. I now have everything
needed to build the analytical version: the coefficient is exactly `0.25` AP per point of
Agility (from `SetStacks(sim, int32(agilityFunc()*0.25))` — read directly from source, not
estimated), granted identically to melee and ranged AP; uptime is close to 100% given the 3/3
talent (100% proc chance per ranged crit, refreshing a 7s duration against a hunter who's
casting ranged specials constantly) but should be measured from actual sim output per candidate
gear set rather than assumed; and the physical-attacker count comes from §0's stated raid comp
(8-10).

**Decision: option (b), analytical.** Built `adapters/tbc/expose_weakness.py`:
- `measured_ew_uptime(raid_sim_result)` — real uptime read from the sim's own
  `encounterMetrics.targets[0].auras` (spell 34503's `uptimeSecondsAvg`) divided by
  `avgIterationDuration`, not assumed. Validated against the earlier ablation run: **97.25%**
  measured uptime (matches the log-based manual estimate).
- `raid_ap_contribution(agility, uptime_fraction, physical_attacker_count)` — total AP granted
  to the raid's *other* physical attackers (not Lerynia's own share, which is already inside
  personal DPS). At her buffed Agility (1220, from the wowsims.com stats panel) and 9 attackers
  (midpoint of §0's 8-10): **2669.6 total AP, ~296.6 AP each.**

Deliberately stops at AP, not DPS — converting further to a DPS-equivalent needs each raid-mate's
own AP-to-damage ratio (class, weapon speed, hit/crit), which isn't knowable generically. Future
MV/valuation output should report this as its own column (raid AP contribution) alongside
personal DPS, per the ground rule, not collapse it into a single number.

## 2026-08-22 — Stage 4: valuation engine built, screening pass run

Built: `core/item_db.py` (DB lookups: unique flag, requiredProfession, gem sockets/colors -
`GemColorMeta = 1` confirmed from `proto/common.proto`, not 8 as first guessed - color 8 is
Prismatic), `core/gear_config.py` (17-slot config + hash for caching), `core/sim_cache.py`
(persisted, keyed by gear hash + settings fingerprint + iterations/seed - never sims the same
config twice), `adapters/tbc/valuation.py` (evaluates one config against a fixed settings
background - her real, wowsims.com-validated `user_export_2.json` export, gear is the only
variable), `core/optimizer.py` (warm-started per-slot greedy sweep + trinket-pair exhaustive +
ranged exhaustive + explicit set-bonus forced-branch), `core/run_optimizer.py` (orchestrator).

**Real concurrency bug found and fixed while building this**: `adapters/tbc/adapter.py`'s
`run()` used fixed shared filenames (`_last_request.json`/`_last_result.json`) for its
bridge/wowsimcli intermediate files. The optimizer runs many evaluations in parallel threads
(each candidate in a slot sweep is independent) - concurrent calls collided on the same files
and wowsimcli failed outright. Fixed to use a unique per-call temp filename (uuid token),
cleaned up in a `finally` block.

**Profession gating confirmed real and enforced**: `requiredProfession` is a genuine DB field
(distinct from `sources[].crafted.profession`, which only describes who can *craft* an item, not
who can *wear* it - e.g. Belt of Deep Shadow is Leatherworking-crafted but has no equip
requirement, and she wears it despite not having Leatherworking). Surestrike Goggles v2.0
(`requiredProfession: Engineering`) and Primalstrike Vest (`requiredProfession: Leatherworking`)
excluded correctly - she only has Herbalism/Mining.

**Screening result (2000 iterations, seed 1)**: current gear (warm start) = 2681.9 combined
(player+pet). Greedy sweep + trinket pair + ranged exhaustive converged on: offhand -> Netherbane
(dual Netherbane over Netherbane/Blade of the Unrequited), waist -> Don Alejandro's Money Belt,
legs -> Bow-stitched Leggings, feet -> Shadowmaster's Boots, ring1 -> Band of the Eternal
Champion, trinkets -> Dragonspine Trophy + Bloodlust Brooch, ranged -> Bristleblitz Striker.
**Combined: 2758.8 (+76.9, ~2.9%).**

**Set-bonus forced branch, the concrete payoff of this whole architecture (§1's core claim)**:
forced a full swap to all 4 Gronnstalker's Armor T6 pieces (head/shoulder/chest/hands - Wowhead
ranks every one of these individually as "Best," ahead of her current Rift Stalker T5 pieces).
Forced-branch result: **2722.2, actually *worse* than keeping Rift Stalker's 4pc (2758.8) by
36.7 combined DPS.** A per-slot EP ranking would have recommended every one of these four swaps
individually - exactly the failure mode the doc opens with. Not fully explained yet (Gronnstalker
4pc is +10% Steady Shot damage vs. Rift Stalker 4pc's +5% Steady Shot crit, so the raw numbers
alone wouldn't predict this - the actual per-piece stat itemization on this specific gear must be
carrying real weight here too), but it's a direct sim comparison, not an EP heuristic, so I'm not
second-guessing the result itself.

**Noise caveat, explicit per the doc's own two-tier process**: these are 2000-iteration
screening numbers only. Per-slot deltas in the sweep range from 0.8 (feet) to 17.8 (ring1)
combined DPS - the smaller ones are within or near the screening noise floor (~1.4-2 DPS
standard error at this iteration count) and need the 30-50k resolve pass before being trusted.
**Stopping here per the doc's explicit STOP before that high-iteration run.**

**Known simplifications, disclosed not hidden**:
- Gems held constant: her existing gems reused for owned items; new/candidate items get a
  default of `Delicate Living Ruby` (the same gem she already uses in nearly every socket
  herself, not an invented EP-based choice) in every non-meta socket. Meta gem slot untouched -
  she already has Relentless Earthstorm Diamond (the standard Hunter/Agility meta), confirmed
  from her real gear, not re-derived. Full gem re-optimization isn't implemented this pass.
- Ranged weapon is exhaustive over candidates but does NOT re-verify/retune the rotation per
  weapon speed, which the doc explicitly flags as mattering for Steady Shot weaving - every
  ranged candidate ran under the same fixed rotation as the settings template.
- Two-handed weapon path not explored - stuck with confirmed dual-wield (her real, validated
  wowsims.com export uses two 1H weapons).

## 2026-08-23 — Tiered leaderboard output; fixed a real resolve-budget mistake

User asked for output grouped by acquisition tier (T6/T5/T4/Heroics/Vanilla carryover/Crafted/
Reputation), each showing its next-5-best upgrades - matches how loot priority actually gets
planned (T6 needs raid clears + competition + RNG; crafted/heroic you can just go get).

**Also caught, mid-run**: the first full-sweep attempt (566 candidates) was taking far too long.
User's diagnosis was right - `mv_single_tiered`'s "resolve anything within 8x the screening
noise" rule, fine for a ~70-item curated pool, doesn't scale to a much larger uncurated one: most
random raid drops don't beat an already-decent-itemized character, so hundreds of them cluster
near zero and ALL of them were triggering the expensive 30k resolve pass. Killed the run.

**Fixed** (`run_full_sweep_mv.py`, rewritten): screen every candidate once at 1,000 iterations
(cheap), group by tier, take each tier's top 8 by screening MV, and ONLY resolve those at 30k -
a little slack over "top 5" in case resolving nudges the order near the cutoff. Everything
outside a tier's leaderboard stays at screening precision and is reported honestly as such
("screened only" flag) rather than silently presented with resolved-looking confidence.

Tier zone IDs pulled from the DB's own `zones` collection (queried every non-raid zone actually
referenced by a phase<=3 item drop) and `ui/core/player.tsx`'s `RAID_IDS` map - not guessed from
memory. Found two real content categories this way: 13 TBC heroic dungeons, and 12 vanilla
zones (Ahn'Qiraj, Blackwing Lair, Molten Core, etc.) that still drop obtainable, phase<=3-tagged
items - confirms Badge of the Swarmguard's Ahn'Qiraj source lines up with a real "Vanilla
carryover" bucket, not a one-off.

## 2026-08-23 — Full item-DB sweep, replacing "curated guide = the pool"

User caught a real scope gap: the candidate pool was built entirely from Wowhead's curated BiS
picks (Stage 3's bootstrap), which §5 always meant as a ranking heuristic for what to sim first,
never a hard exclusion - but that's exactly what it had become, since nothing outside the guide
ever entered the pool. An item the guide author judged not worth listing (off-meta, niche, or
itemized for another spec but incidentally good here) was invisible no matter how good it
actually was for this character.

**Fix**: `core/sweep_all_loot.py` sweeps the sim's own item DB directly instead of depending on
the guide's curation - eligibility by the DB's own fields only (classAllowlist includes Hunter
if present; armorType Leather/Mail for armor slots; weaponType in Axe/Dagger/Fist/Polearm/Sword
for one-handers, matching real TBC Hunter weapon proficiencies; rangedWeaponType in Bow/
Crossbow/Gun; `phase <= 3` per the user's explicit "everything obtainable in P3 - drop, bought,
or crafted - not P4/P5" scope; quality >= Rare; has a real `sources` entry). `core/
run_full_sweep_mv.py` merges the sweep with the existing curated pool (union, nothing already
found is lost) and runs the same MV pipeline over it.

**A crude stat-weight score is used to pre-filter armor slots down to a top-15 shortlist per
slot** before the real sim runs on them (1426 eligible items down to a tractable count) - this
is exactly what §5 always intended EP to be used for ("decide what's worth simming first"), not
a hard exclusion either.

**Caught before running the expensive sim, from the user naming a specific example (Badge of the
Swarmguard)**: the same TOP_N truncation, and an ilvl >= 115 floor meant to exclude leveling-zone
junk, were BOTH being applied uniformly to trinkets and weapons too. Checked Badge of the
Swarmguard directly: phase 1 (passes), quality 4/Epic (passes), but **ilvl 76** (fails the floor)
and **zero raw stats in its base scalingOptions** - its entire value is an on-crit AP proc via
itemEffects, which the crude score can't see at all, so it would've scored ~0 and been truncated
even without the ilvl floor. Same failure mode §5 already named explicitly ("always keep all
trinkets and all weapons... never a hard exclusion") - built the sweep without applying that rule
the first time, fixed by exempting trinkets/weapons/ranged from both the ilvl floor and the
top-N truncation entirely; armor slots keep both, since armor value is overwhelmingly raw-stat-
budget-driven and doesn't have this problem the way procs do.

**2H weapons remain excluded from this sweep, deliberately, for a real reason** (per the user):
evaluating a 2H candidate fairly needs the rotation itself switched to melee weave
(`meleeWeave:true`, confirmed present in the 2h_9p preset's `specRotationJson`, absent from
dw_9p's - see the Stage 1 preset-diffing entry above) wherever the boss allows it - not just a
worse number under the dual-wield settings, a wrong one, since the character would stay parked
at range instead of weaving into melee. That branching isn't built yet; `slot_for_item()` returns
`None` for `HandType.TwoHand` rather than silently reporting a number that tested the wrong
playstyle. Next step if 2H ever needs checking: build a second settings variant with
`meleeWeave:true` and route 2H candidates through it specifically.

## 2026-08-23 — Real bug: non-owned candidates got enchant=0, not their real enchant

User pushed on the shoulders-alone discrepancy again after the canonical-settings fix didn't
close it (Gronnstalker's Spaulders standalone MV still read -14.8 in the tool, near-zero on
wowsims.com). Isolated it by calling `adapter.run()` directly on a hand-built pair of settings
files (bypassing the optimizer entirely) and got -1.0 - matching the user's observed result, not
the tool's. That meant the bug was specifically in how `optimizer.load_candidates` builds
candidates, not in the settings background.

**Root cause, confirmed by inspection**: every non-owned candidate got `enchant=0` hardcoded,
regardless of the item's actual owned-slot equivalent. Enchants attach to the *slot* via the
profession UI, not to a specific item - a real player would obviously enchant a new shoulder
piece with the same Greater Inscription of Vengeance she already uses. Evaluating Gronnstalker's
Spaulders with **no shoulder enchant at all** understated it by roughly the enchant's own value,
enough to flip "roughly even" into "clear downgrade." This wasn't shoulders-specific - it applied
to every non-owned candidate in every slot with an enchant (weapons, boots, bracers, cloak,
chest, legs, etc.), silently deflating most of the 79-item MV table.

**Fixed**: `load_candidates` now defaults a non-owned candidate's enchant to whatever she
currently has enchanted on that same slot, computed once per pool key from `owned_items`. Rings
and trinkets correctly stay at 0 (no enchant slot exists for them in this game) - not a bug,
just nothing to inherit.

**Re-ran the optimizer after the fix - the shift is large, not marginal**: current gear
(unchanged, 2656.0) -> full bundle **2999.7 (+343.7)**, more than double the previous +148.2.
The full bundle branch's screening phase alone jumped 2809->3001. Greedy search now finds 3 of
the 4 Gronnstalker pieces (head/shoulder/chest all pass its normal per-slot sweep, hands +38 in
one step) on its own, without needing the forced branch to discover them - each piece no longer
looks artificially worse than it is, so the local-optimum trap that made greedy avoid the set in
the first place is largely gone. This is now much closer to the user's own wowsims.com full-BiS
result (3030.9) - the remaining ~30 DPS gap is the still-disclosed, still-unfixed per-socket gem
simplification (uniform DEFAULT_GEM vs her specific socket-bonus-chasing choices), not a new bug.

**Lesson, stated plainly**: two significant optimizer bugs in a row (missing meta gem, then
missing enchants) were both "non-owned candidate gets a worse default than reality" - systematic
understatement of anything not currently equipped. Worth treating any future "candidate looks
worse than expected" signal as a prompt to check what implicit default it's silently getting,
not just re-running at higher iterations.

## 2026-08-23 — Canonical settings locked in, background drift fixed

The background settings I'd been using (`data/cache/user_export_2.json`) turned out to be just
one snapshot among several inconsistent test sessions - diffed all three exports the user had
sent and found real drift: Windfury Totem, Mana Spring/Wrath of Air Totem, Braided Eternium
Chain, Curse of Elements, Blessing of Salvation, and weapon imbues were each present in some
sessions and absent in others, none of it deliberate (confirmed by the shoulders test: swapping
shoulders alone gave -14.5 under one background and -0.17 - matching the user's own -1.19 result
- under another; same gear swap, different answer, purely from which background happened to be
loaded). Pet type alone had been Owl/Ravager/Bat across three different sessions.

**User's confirmed standing assumptions**:
- Pet: Owl, always - now force-normalized in `valuation.py`'s `_load_template` regardless of
  what's in any source file, so a future pasted test export can't silently change this again.
- Totem-twisting Enhancement Shaman assumed: Windfury Totem (Regular) + Grace of Air Totem +
  `totemTwisting: true`. NOT Mana Spring/Wrath of Air Totem - those aren't part of the twist.
- Braided Eternium Chain: NOT assumed (was stray session state, not a real standing item).
- Curse of Elements and Blessing of Salvation: assumed present.
- Weapon imbues: NOT assumed - the imbue id used in earlier exports (29453) is Fist Weapon-only
  per the user, and her actual weapons (axes/swords) don't qualify. Omitted entirely rather than
  substituting a "correct" sword/axe stone she didn't ask for.

Built `profiles/tbc/canonical_settings_survival.json` - a version-controlled (not gitignored
scratch) canonical background reflecting all of the above, replacing the ad hoc
`data/cache/user_export_2.json` as `SETTINGS_TEMPLATE` in both `run_optimizer.py` and
`run_mv_report.py`. Re-ran the optimizer against it: conclusion unchanged (Gronnstalker bundle
still wins, now +148.2 vs current gear's corrected 2656.0, was +150.6 under the old background) -
the fix mattered for close-to-noise individual swaps like shoulders, not for the headline result.

## 2026-08-23 — Refocus: per-item MV, not just DPS*(pool)

User's reminder: the actual goal is "is this item an upgrade, and how much" (§1's core
question), not chasing decimal precision on one full-set number. Built `core/marginal_value.py`
+ `core/run_mv_report.py`: computes `MV(i) = DPS*(P u {i}) - DPS*(P)` per candidate against her
CURRENT gear (not an already-optimized set - that's the actual baseline "this item dropped, bid
or pass" gets asked against), reporting every candidate's delta with a noise bound.

**Real bug caught before trusting the first run**: initial noise threshold used the sim's raw
`player_stdev` (~62.5 DPS - the spread across *individual simulated fights*) as the tied-vs-not
cutoff. That's not the uncertainty on a 30,000-iteration *average* - conflating the two made
almost every real, verified difference read as "tied within noise." Fixed:
`standard_error = player_stdev / sqrt(iterations)`, and the delta's combined error is
`sqrt(SEM_a^2 + SEM_b^2)` for the two independent runs being compared. At 30k iterations this
gives a real noise floor of ~0.5 DPS, not ~62.5.

**With the fix, individual results are exactly the §1 failure-mode demonstration the tool exists
for**: every single Gronnstalker T6 piece is a *downgrade* alone (Helmet -29.4, Spaulders -14.5,
Chestguard -13.2, Gloves -10.1 - each one breaks her held Rift Stalker 4pc for a mediocre-in-
isolation trade), while the full 4-piece package together is **+150.6, a clear upgrade** (see
the "Correction" entry above for how that number was arrived at correctly). A per-slot EP
ranking would recommend against every one of these four items individually and therefore never
reach the package - this is the concrete, numeric version of "these three pieces are worth more
together than separately" from §7.

Other real upgrades found (MV vs current gear, single-item swaps, 30k iter): Dragonspine Trophy
+23.7, Band of the Eternal Champion +19.0, Don Alejandro's Money Belt +19.1, Bristleblitz
Striker +14.9, Bow-stitched Leggings +9.0, Madness of the Betrayer +5.8, Shadowmaster's Boots
+5.9. Real downgrades among reference-list "Great"/"Best Until T5" items that looked
individually plausible: every Beast Lord piece (T4, -43 to -70), most non-set alternatives.

## 2026-08-22 — Correction: the Stage 4 screening conclusion was wrong

User verified on wowsims.com directly and got numbers that flatly contradicted my "Rift Stalker
beats Gronnstalker" screening finding. Chased it through several dead ends (a stripped-down
rotation export missing `prepullActions`/`groups` - confirmed real, reproduced it exactly by
deleting those fields from a known-good settings file, DPS crashed 2681.9->1160.4 because the
character never moves into melee range without the prepull group - but that turned out to be a
red herring for THIS discrepancy, not the cause) before finding the real issue.

**Re-ran three configs at 30,000 iterations against her real, complete settings background**
(full rotation intact, only `equipment.items` varied):
- Current gear: 2681.9 combined
- My optimizer's screened set: 2759.2 combined
- **Full reference BiS (Gronnstalker 4pc + Insidious Bands + Madness of the Betrayer + dual
  Blade of Infamy): 3030.9 combined** - beats my optimizer's own recommendation by 271.7, far
  outside noise at this iteration count (SEM well under 1 DPS at n=30000).

**Root causes of the wrong conclusion, all in the optimizer, not the simulator:**
1. `set_bonus_branch` only forced the 4 armor pieces, holding wrist/trinkets/weapons at
   whatever the greedy sweep had already picked (Vambraces of Ending, Dragonspine+Bloodlust
   Brooch, dual Netherbane) instead of testing the full recommended bundle (Insidious Bands,
   Madness of the Betrayer, dual Blade of Infamy) together. Too narrow a branch - the same
   isolation error the whole tool exists to catch, just applied one level too shallow.
2. The trinket-pair search picked Bloodlust Brooch over Madness of the Betrayer at 2000
   *screening* iterations and that call was reported as final instead of being flagged for the
   30-50k resolve pass the doc explicitly calls for on close ties.
3. Non-owned candidates (Insidious Bands etc.) got the generic placeholder gem
   (`gear_config.DEFAULT_GEM`, Delicate Living Ruby) instead of the better Phase 3 equivalent
   (Delicate Crimson Spinel, id 32194, +10 vs +8 Agility) the reference set actually uses -
   handicapping those candidates for real, not just cosmetically.

**Fixed, all three**:
1. `gear_config.DEFAULT_GEM` changed from Delicate Living Ruby (24028, phase 1) to Delicate
   Crimson Spinel (32194, phase 3) - the actual gem the reference set uses.
2. `optimizer.full_bundle_branch` replaces the old `set_bonus_branch`: resolves an entire named
   bundle of item names (e.g. a reference guide's full recommended set) to a complete config via
   `resolve_name_to_config`, and compares it against the greedy result at both screening AND a
   30k-iteration resolve pass before picking a winner.
3. `optimizer.trinket_pairs` now resolves its top-3 screened pairs at 30k iterations before
   picking a winner, instead of trusting the 2k screening ranking directly.

**A second real bug found while wiring in the fix**: the original candidate gem-filling logic
built a gems list *shorter* than the item's socket count whenever a socket was Meta - it skipped
the meta position instead of filling it, so any non-owned candidate with a meta socket (e.g.
Gronnstalker's Helmet, same 2-socket yellow+meta layout as her current Rift Stalker Helm) got
evaluated with **no meta gem socketed at all**. Fixed: `gems_for_item` now builds the list
position-for-position against `gemSockets`, filling the meta position with her own currently-
socketed meta gem (found via `find_owned_meta_gem` - Relentless Earthstorm Diamond, the standard
choice, not re-derived) instead of leaving it empty.

**Re-ran the full optimizer after both fixes**: full bundle branch now correctly wins -
**2832.5 combined @ 30k iterations (+150.6 vs current gear's 2681.9)**, chosen over the greedy
sweep's 2776.8. Still short of the 3030.9 the user's exact manual gear+gems produced on
wowsims.com - the remaining ~198 DPS gap is the disclosed, still-unfixed simplification: generic
candidates get uniform `DEFAULT_GEM` in every non-meta socket, not the specific per-socket gem
choices (e.g. Jagged Seaspray Emerald in two of the chestpiece's sockets, chasing a socket bonus)
the real reference set uses. Directionally this only makes the true gap *bigger*, never flips
which set wins, so the corrected conclusion (full Gronnstalker bundle beats current gear and
beats the narrower greedy result) is solid even with generic gems - but the absolute DPS number
is a conservative underestimate until per-socket gem optimization is implemented. Not doing that
this pass; flagging it as the next known gap rather than leaving it undisclosed.

## 2026-08-22 — Raid progression (from user)

SSC/TK: full weekly clears already, ongoing. BT/MH: expected to start full weekly clears from
Week 1 or Week 2 of Phase 3 (launches 2026-08-27). **Why this matters**: it means essentially
the entire P2+P3 Survival reference list becomes realistically accessible on a weekly cadence
very early in the phase, not a slow multi-month grind - relevant for Stage 5's time-horizon
bucketing (`lasts the expansion` / `lasts this phase` / `replaced soon`) later. Doesn't change
anything about Stage 4 (the valuation engine doesn't need cost/progression data, only gear
configs) - only matters once cost/spend recommendations (§5 acquisition cost tags, §7) come up.

## 2026-08-22 — Stage 3 bug: name->id resolution silently picked the wrong item

User spotted it from a screenshot: my gap analysis said "Band of Eternity" wasn't on the Phase 2
reference list at all, but Wowhead's own table clearly shows it there (rank "Optional"). Root
cause: `core/gap_analysis.py`'s original `resolve_reference_ids` built `{name: id}` from the sim
DB via a plain dict comprehension - but **"Band of Eternity" is 12 distinct item IDs in the DB**
(29294-29308, itemization/random-suffix variants sharing one display name), and the comprehension
silently kept whichever came last, which wasn't her actual ring's id (29298). The match check
compared ids, so it missed a name that was genuinely present. Nothing in the unresolved-list
reporting caught this either, since "some id resolved" ≠ "the *right* id resolved" - a name with
duplicate ids never triggers the unresolved path.

**Fixed**: match candidates against owned gear **by name**, not resolved id (`gap_analysis.py`).
`resolve_reference_ids` now returns `ids` (plural, a list) per candidate for reference/display,
but the actual owned-vs-candidate comparison is `candidate["item"] == owned_name`, which is
unambiguous regardless of how many ids share that name. Re-ran: `ring1` moved from "NOT ON P2
LIST" to correctly "was P2 Optional" - shifting it from the "real, longstanding gap" bucket into
"expected P2->P3 progression." Corrected counts: 2 real gaps (trinket2, offhand), 4 expected-
progression slots (waist, legs, ring1, ranged) - was previously reported as 3/3.

**Lesson**: any future `{name: id}` lookup against this DB needs to assume names aren't unique,
not just for rings - check for collisions before trusting a plain dict comprehension.

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

**Second cross-check, different config** (Owl pet, TimelessArrow ammo, no scrolls, Curse of
Elements/Wrath of Air/Mana Spring added, Windfury dropped to Regular): user's wowsims.com result
2244.48 ± 62 player, Owl 440.01. Feeding their exact export through the pipeline unmodified:
**2242.24 ± 62.36 player, Owl 439.35** — matches again, well inside Monte Carlo noise. Two
independent configurations now confirm the bridge/wowsimcli chain reproduces wowsims.com exactly.

**Update**: resolved. After a fresh in-game `/wse export` on Survival spec, `gear sync` now
produces a real, populated `character.json` — 17/17 equipped, 22 bag items, 28 bank items (once
the companion addon's `/gtexport`/bank-open was done), with unresolved items limited to
non-combat clutter (profession materials, quest items). Also fixed `load_item_db()` to check
`db.json`'s separate `consumables` collection in addition to `items` — ordinary consumables
(elixirs, food, sappers) were wrongly landing in `unresolved` before that.

**Full-sweep tiered-report fixes (three real bugs, all corrected before reporting results)**:
1. Curated-item tier/source lookup was keyed by item *name* (`db_by_name = {it["name"]: it ...}`)
   in `run_full_sweep_mv.py` — same collision class as the earlier "Band of Eternity" bug.
   Miscategorized Gronnstalker's Leggings/Gloves and blanked Scaled Greaves of the Marksman /
   Tsunami Talisman's source text. Fixed to look up by `c.item_id` via `idb.by_id()` instead.
2. Netherstrand Longbow was reported as a real +131.6 T5 upgrade; the user caught it — it's one
   of 7 items in Kael'thas Sunstrider's fight-only legendary pool (Warp Slicer, Infinity Blade,
   Staff of Disintegration, Phaseshift Bulwark, Devastation, Cosmic Infuser, Netherstrand
   Longbow), tagged `sources[].drop.otherName == "Legendaries"` in the DB — not real persistent
   gear. Real legendaries (Warglaives, Thori'dal) don't carry that tag. Added
   `is_encounter_only_legendary()` to `sweep_all_loot.py`'s `eligible()` filter.
3. Gronnstalker's Armor set (setId 669: Leggings/Gloves/Helmet/Chestguard/Spaulders/Bracers/
   Belt/Boots, ids 31001-31006 + 34443/34549/34570) has **no `sources` field at all** in
   db.json — the DB simply doesn't carry drop data for this set on this server, so tier lookup
   fell back to "Other" even though Wowhead's own curated text correctly says "Drop: The
   Illidari Council (Black Temple)" / "Drop: Azgalor (Hyjal Summit)". Added `tier_from_text()`
   to `run_full_sweep_mv.py`: when the DB gives no tier and curated text exists, match the
   tier's own zone names as substrings of that text instead of leaving it stuck in "Other".

**simserver.exe (persistent sim process) built and integrated.** `wowsimcli` reloads and
unmarshals the whole embedded item DB (~2.3MB protobuf) fresh on every invocation — dominates
wall-clock time on short (1000-iteration) screening calls, which is most of what a full sweep
spends. `adapters/tbc/simserver/main.go` is a persistent version: loads the DB once
(`sim.RegisterAll()`), then serves one `RaidSimRequest` protojson line in / one `RaidSimResult`
protojson line out per request over stdin/stdout, calling the exact same
`core.RunRaidSimConcurrentAsync` path `cmd/wowsimcli/cmd/basic_sim.go` uses. **Must be built with
`go build -o simserver.exe --tags=with_db .`** — the first build omitted the tag and failed at
runtime ("No item with id: 30141") since the embedded DB isn't active without it.
`adapters/tbc/simserver_client.py` provides `SimServerPool` (N persistent processes, checked
out/in like a connection pool — one process is strictly serial, concurrency comes from pool
size, not from pipelining a single process). `adapters/tbc/valuation.py`'s `evaluate()` now
calls `bridge.exe` directly (still fast, unchanged) to build the `RaidSimRequest`, then routes
it through `simserver_client.get_pool()` instead of spawning `wowsimcli.exe` fresh
(`USE_SIMSERVER = True` flag, file-based path kept as a fallback). Verified byte-identical
player DPS between both paths on a fresh (uncached) seed; ~30% faster per call end-to-end
(240ms vs 340ms warm, serial, including the bridge.exe step) — less than the previously-quoted
isolated 2.15x since that number excluded bridge.exe's fixed cost, but a confirmed real win, and
it stacks with the `MAX_WORKERS=4` thread pool the sweep already uses.

**Per-slot leaderboards, owned-item exclusion, set-bonus rescue, and a real
oversubscription bug found while building all three (session continued).**
- Tiered report now breaks down top-5 by *equipment slot within each tier*
  (Head/Trinket/Weapon/etc.), not one blended top-5 per tier - per the
  user's correction that a tier's leaderboard was hiding real per-slot
  upgrades behind bigger numbers from other slots. Empty (tier, slot)
  combos just don't print (T4 legitimately has almost nothing for this
  character - that's expected, not a bug).
- Items she already owns (equipped + bags + bank, `data/character.json`'s
  `owned.bags`/`owned.bank`) are excluded from every acquisition tier - not
  something to go acquire. First attempt pruned them out of the whole
  `candidates` pool, which also silently broke set-bonus math (a banked
  piece needs to stay visible to `set_bonus.py` to be credited toward a set
  combo) - the user caught this ("we don't want to filter out our gear
  entirely"). Fixed: owned items stay in `candidates`, filtered only at the
  final per-row report-building step.
- Set-bonus rescue: before this, an item that's a downgrade alone but part
  of a set whose combined MV is a real upgrade was just dropped like any
  other downgrade - exactly the EP-blind-spot §1 exists to catch. Now
  `set_bonus.set_progression()` runs once per distinct `setName` found in
  the pool; any item whose own screened MV is NOT already a clear upgrade
  gets an explicit info note if the set eventually becomes worth it. First
  version attached the note to every member of a flagged set regardless of
  the item's own verdict - so a genuinely-good standalone piece
  (Gronnstalker's Leggings, +10.4 alone) got a false "downgrade alone"
  label. Fixed: the note only prints when the item's own resolved/screened
  mv isn't already a clear upgrade.
- **Real oversubscription bug, found while investigating a 9-minute run**:
  `SIMSERVER_POOL_SIZE=4` + `MAX_WORKERS=4` means up to 4 simserver
  processes x 12 internal goroutines each (`runtime.NumCPU()` on this
  6C/12T Ryzen 5 5600X) = 48-way parallelism fighting over 12 threads.
  Measured: 747ms/call at (4,4) vs 101ms/call at (2,2) - **7.4x slower from
  oversubscription alone**, not the sim being slow. Fixed both to 2 (must
  stay matched - no reason to hold idle simserver processes a caller can't
  reach). If this ever moves to different hardware, retune both to roughly
  match `logical_threads / 12` (rounded up, min 1).
- Reintroduced the "skip resolving what screening already made obvious"
  rule (`marginal_value.CLEAR_MARGIN_MULTIPLE`, already used by
  `mv_single_tiered` for the curated-71-item report) into the leaderboard
  resolve step here too - only items still within 8x screening-noise of
  zero get the 30k pass; a screened +35.7 with tight noise doesn't need it,
  resolving can only sharpen a number that was never in question. Cut the
  leaderboard resolve count from ~300+ to 124 on this pool.
- **`sim_cache.py`'s `_save()` isn't safe against a second process touching
  the same cache file** - `threading.Lock()` only guards one process; a
  concurrent second Python process (a stray test script, in this session's
  case) hitting the same `data/cache/sim_cache.json` caused a genuine
  `PermissionError: [WinError 5]` on `os.replace` under Windows. Hardened
  with a short retry/backoff (5 attempts, 50-200ms) rather than crashing a
  perfectly fine run over someone else's transient file lock - but the
  real lesson is **don't run manual test scripts against the same repo
  while a real pipeline run is in flight**, they share the cache file.
- GPU acceleration was asked about and ruled out: the sim is a branchy,
  stateful per-iteration simulation (ability priority, proc rolls, buff
  timers) - the worst case for GPU SIMT execution (warp divergence), and
  `wowsimcli`'s engine has no GPU path to begin with. The real lever on
  this hardware is core count (Monte Carlo iterations parallelize cleanly
  across cores); RAM/storage/GPU upgrades wouldn't move this workload.
