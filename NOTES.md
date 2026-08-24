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

## 2026-08-23 (overnight, autonomous) — Root cause found: raid AP contribution column still isn't wired in anywhere

Checked CLAUDE.md's own Stage 2 ground rule against the actual pipeline: "every future MV/
valuation output must report personal DPS and raid AP contribution as two separate columns —
never collapse them into one number, and never silently drop the raid column." Grepped the whole
codebase for any real (non-doc) use of `adapters/tbc/expose_weakness.py` - **zero hits**. It's
never been called from `valuation.py`, `marginal_value.py`, `optimizer.py`, or
`run_full_sweep_mv.py`. Every MV number this session (including tonight's tiered sweep report)
has been reporting personal DPS only, silently missing the raid column the ground rule requires.
Not a new problem introduced tonight - this gap has existed since Stage 4 began and was never
caught because nothing was checking for it.

**Why it was never wired in - traced to a real, structural blocker, not an oversight**:
`expose_weakness.raid_ap_contribution(agility, uptime_fraction, physical_attacker_count)` needs
her live buffed Agility per gear config. `measured_ew_uptime()` already works fine - it reads
`encounterMetrics.targets[0].auras`, which IS part of the regular `RaidSimResult` this pipeline
already gets back from every sim call. But **Agility is not available anywhere in `RaidSimResult`
at all** - confirmed directly from `proto/api.proto`: `RaidSimResult` (line 384) only has
`raid_metrics` (dps numbers), `encounter_metrics` (aura uptimes/procs), `logs`, timing, and
`error`. The per-player stat breakdown (`PlayerStats.final_stats`, a `UnitStats` with an
Agility entry) lives on `ComputeStatsResult` (line 511) - **a completely separate RPC**
(`ComputeStats`, not `RaidSim`) that neither `bridge.exe`, `simserver.exe`, nor `wowsimcli`'s
`sim` subcommand this pipeline uses ever calls.

Physical-attacker-count itself is NOT the blocker (already real, already used once - 9, midpoint
of §0's stated 8-10 raid comp, per the Stage 2 entry above) - the blocker is purely that this
pipeline has no code path that ever asks the sim for a config's Agility.

**Three real options to close this, none attempted tonight - this is a design call, not a bug
fix, and touches the Go bridge/simserver boundary where mistakes are hard to self-verify without
the user's wowsims.com cross-check**:
1. Add `ComputeStats` RPC support to `bridge.exe` + `simserver.exe` (mirrors how `RaidSim` support
   was added - real but bounded Go work, probably ~1-2 hours). Cleanest, most correct: gets
   Agility the same way the sim itself computes it, no reimplementation risk.
2. Reimplement Agility computation in Python from the gear config directly (base race Agility +
   item stats + talents + buffs). Rejected as the default choice: talent/buff percentage
   multipliers and stacking order would need to exactly replicate the sim's own math, which is
   precisely what CLAUDE.md's "assume the latest sim's model is correct, don't second-guess or
   reimplement it" rule warns against - a silent drift here would be very hard to notice.
   Suggest 1 over this for the audit trail.
   `debug_first_iteration` (`sim/tbc-new/proto/api.proto` line 133) turns on logging into the
   `logs` string field of the normal RaidSimResult - worth a quick check whether the sim's debug
   log conventionally prints a stat summary at combat start, which would give a fourth path with
   no new RPC needed. Not checked yet.

Flagging this as open rather than picking an approach and building it, per the "genuinely
ambiguous, needs the user's call" carve-out - option 1 is my lean, but it's the user's call
whether the Go-side work is worth it now vs. deferring the raid-column ground rule (with this
now explicitly documented as a known, disclosed gap rather than a silent one) until it matters
for an actual decision.

## 2026-08-23 (overnight, autonomous) — ComputeStats wired into simserver.exe, verified correct

Continuing last cycle's finding (raid AP contribution column needs a config's Agility, which
`RaidSimResult` never carries). Ruled out the debug-log-parsing shortcut definitively this cycle
first: grepped `sim/core/*.go` for where debug logging prints stats - only `pet.go` logs a pet's
stats (`pet.Log(sim, "Pet stats: %s", pet.GetStats().FlatString())`); nothing logs the player's
own stats anywhere, so there's no free text-log path to Agility. Also confirmed `wowsimcli`'s CLI
(`cmd/wowsimcli/cmd/`) has no `stats`/`compute-stats` subcommand at all - `ComputeStats` is
genuinely unreachable from anything this pipeline currently calls.

**Checked `core.ComputeStats`'s actual implementation** (`sim/core/api.go:12`) - much simpler than
`RunRaidSimConcurrentAsync`: a single synchronous function, `ComputeStats(csr *proto.ComputeStatsRequest) *proto.ComputeStatsResult`,
no async/channel handling needed. `ComputeStatsRequest{raid, encounter}` is a strict subset of the
fields already in every `RaidSimRequest` this pipeline builds via `bridge.exe` - no new Go-side
request construction needed, just `{"raid": req["raid"], "encounter": req["encounter"]}` in Python.
This narrowed my own "needs the user's call" flag from last cycle down to a single clearly-correct
approach (log-parsing and Python reimplementation both ruled out/rejected), low complexity, and
directly implements an already-mandated CLAUDE.md ground rule rather than new scope - built it.

**`adapters/tbc/simserver/main.go`**: added `isRaidSimRequest()` (peeks for a `simOptions` key -
present on every `RaidSimRequest`, absent on every `ComputeStatsRequest` - to route each stdin
line without a wire-format change) and `runComputeStats()` (calls `core.ComputeStats` directly).
Purely additive - `runOne`/the existing RaidSim path is untouched, zero regression risk to the
DPS pipeline. Needed `google.golang.org/protobuf/proto.Message` for the shared return type, but
had to alias it (`protoiface`) since the generated types package is already imported as `proto`.

**Verified two ways**: (1) re-ran a normal 1000-iteration DPS eval through `valuation.py` after
rebuilding - combined 2656.6, matching the existing baseline range, confirming the RaidSim path
has zero regression. (2) Sent a `ComputeStatsRequest` built from her current real gear
(`canonical_settings_survival.json` + `character.json`'s equipped items) - got **final
(fully-buffed) Agility 1195**, `stats[1]` per `StatAgility = 1` in `common.proto`. This is very
close to the independently-recorded **"298 stacks → Agility 1192 at first proc"** from the Stage 2
ablation debug run earlier this session (same real gear, different measurement method entirely -
aura stack count vs. direct ComputeStats query) - two independent methods landing within 3 Agility
of each other is real cross-validation, not just a plausible-looking number.

**Not done yet, deliberately left for the next firing**: this only proves the plumbing is correct
and reachable - it is NOT yet wired into `valuation.py`/`marginal_value.py`/`run_full_sweep_mv.py`
as an actual reported column. Next concrete step: add a Python helper (probably in
`adapters/tbc/valuation.py` or a new small module) that calls this ComputeStats path, feeds the
result plus `measured_ew_uptime()` (from the same RaidSimResult a normal MV eval already produces)
and `physical_attacker_count=9` (§0's stated 8-10 raid comp, midpoint - already used once, see the
Stage 2 entry above, not a new number) into `expose_weakness.raid_ap_contribution()`, and add the
result as an explicit second column on `mv_single`'s/`mv_bundle`'s output dicts, threading it
through to the tiered report's print/JSON output per CLAUDE.md's Stage 2 ground rule.

## 2026-08-23 (overnight, autonomous) — raid AP contribution wired end-to-end; found and worked around a real simserver.exe crash

Continued from the previous cycle's ComputeStats verification. Added `valuation.get_agility()`
(builds a `ComputeStatsRequest` from the same `raid`/`encounter` fields already built for a
normal sim call, cached under a fixed iterations=0/seed=0 key since it's deterministic - no
Monte Carlo involved) and wired it into `marginal_value.mv_single()` via a new optional
`baseline_agility` parameter (default `None` - existing callers unaffected). When supplied, the
result dict gets a `raid_ap_contribution` field: `expose_weakness.raid_ap_contribution()` on the
winning trial's Agility/measured EW uptime, minus the same for baseline, using
`PHYSICAL_ATTACKER_COUNT = 9` (§0's stated 8-10, midpoint - already used once, not re-derived).
`run_full_sweep_mv.py` computes `baseline_agility` once and only passes it into the resolve pass
(not the 500-candidate screen pass - the extra ComputeStats call isn't worth paying for items
that never make a leaderboard). The tiered report now prints "DPS" and "raid AP" as genuinely
separate columns per CLAUDE.md's Stage 2 rule, with an explicit "n/a" (not a blank/dropped
column) for screened-only items that never got resolved.

**A real, serious bug found while verifying this at production scale**: after clearing
`sim_cache.json` (necessary - ~2400 of 2515 entries predated the `ew_uptime` field this cycle's
`evaluate()` change added, so every cached hit was silently returning `ew_uptime: None` and
`raid_ap_contribution` was coming back `None` for every single item), the full pipeline appeared
to hang for 10-16 minutes with near-zero CPU. Spent a long time chasing this as a concurrency bug
in the new ComputeStats integration - ruled that out completely (a 71-candidate curated pool and
even a 500-candidate full run at both screening and 30k resolve iterations worked fine, serial
AND concurrent, repeatedly). Root cause, found by finally adding per-item progress printing
(`python -u`, unbuffered - the fully-buffered runs gave zero visibility into where it actually
was): **`simserver.exe` crashes with "process died?" partway through a long run of real
(non-cached) requests** - reproduced it directly (crashed around request #65 in one run), then
immediately re-ran the *exact same* request in isolation and it worked fine, proving it's not
tied to a specific bad item. Every previous "successful" run tonight had a warm cache, so most
`evaluate()` calls never actually reached the persistent process at all - this is the first time
it's been asked to handle sustained real load, and it doesn't survive it. Root cause (memory
leak? some accumulating state in `core.RunRaidSimConcurrentAsync`/`core.ComputeStats` that the
original one-shot-per-process `wowsimcli` CLI never exercised?) is **not yet found** - flagging
for real investigation, not guessing at a Go-level fix blind at 6am unsupervised.

**Two-part mitigation, both real fixes not just band-aids**:
1. `valuation.py`: `USE_SIMSERVER` flipped back to `False`. The file-based `adapter.run()` path
   (fresh `wowsimcli.exe` per call, zero accumulated state) is what this whole session was
   validated against for hours before simserver existed - proven reliable, just slower. DPS
   correctness matters more than tonight's speedup until the crash is root-caused.
2. `get_agility()` **cannot** fall back the same way - `ComputeStats` has no CLI/file-based path
   at all (confirmed last cycle: `wowsimcli`'s CLI has no stats subcommand). So instead:
   `SimServerPool.run()` is now self-healing - on a `RuntimeError` from a dead process, it
   spawns a replacement and retries once before giving up (standard connection-pool pattern: a
   pool must assume its resources can die, not just build one and trust it forever - the old
   code left a dead process in rotation forever, failing every future request through it).
   `get_agility()` itself also degrades gracefully: any failure returns `None` (reported as
   "n/a raid AP" downstream, never crashes the caller) and is NOT cached as a permanent failure,
   so a later call for the same config gets a fresh attempt.

**Verified correct end-to-end**: full cold run (both DPS and Agility caches empty), 500
screened + 124 resolved candidates, zero errors, zero degraded-to-None entries needed (the
self-heal never even had to fire, or fired silently and succeeded - either way the run was
clean). 560.2s total (fully cold both caches - future runs stay cheap via the sim cache, same
as always; this number reflects a worst case, not steady-state). Raid AP contribution values
are real, sane, and already surfacing exactly the kind of divergence this feature exists to
catch - e.g. Boneweave Girdle: +8.4 personal DPS but **-26 raid AP** (lower Agility despite the
DPS gain from other stats); Gronnstalker's Helmet: -16.8 DPS alone but **+13 raid AP** (on top
of the existing set-bonus rescue note) - genuinely different verdicts depending which column
you're optimizing for, never collapsed into one number.

**Open, for a future session with more attention available**: re-enable `USE_SIMSERVER` only
after the crash is actually root-caused (not just papered over by the pool's self-heal, which
helps `get_agility()` survive it but doesn't explain WHY it's dying) - would restore tonight's
speedup for the main DPS path too. Real next steps: stress-test simserver.exe standalone (no
Python) with a long loop of varied requests to reproduce without any pipeline complexity;
compare memory usage over the run's lifetime for a leak; check if `core.RunRaidSimConcurrentAsync`
or `core.ComputeStats` have known one-shot-process assumptions baked in (global state that's
supposed to reset at process exit).

## 2026-08-23 (overnight, autonomous) — simserver.exe crash investigation, continued

Stress-tested simserver.exe standalone (bypassing the whole pipeline) to narrow down last
cycle's crash. First attempt (naive slot-cycling through all 17 slots regardless of item type)
hung indefinitely - traced precisely (per-request logging) to placing **a ranged weapon
(Vengeful Gladiator's Rifle) into the offhand slot**. Confirmed this is an artifact of the test
script, not a real risk: the real pipeline's `marginal_value._SLOT_HINT` mechanism (populated by
`set_slot_hints()` from the same candidate-building logic `run_full_sweep_mv.py` actually uses)
only ever tries an item in slots matching its real type - ran the full 71-item curated pool
through the real `mv.mv_single()` path (proper slot hints, `raid_ap_contribution` included) and
it completed cleanly, 0.6s, no hang. Still a real Go-engine bug worth knowing about (equipping a
ranged weapon in a melee slot apparently causes an infinite loop rather than a clean validation
error) but not one the pipeline can ever trigger through its own candidate-building path.

**Directly stress-tested `get_agility()` (the only code path still using simserver.exe now that
`USE_SIMSERVER=False`) at full production scale**: all 500 real sweep+curated candidates, each
in its own real (slot-hint-correct) trial config, one `get_agility()` call each - **500/500
succeeded, 0 degraded, 25.0s total, no crash, no hang**. This is strong, direct evidence the
current production configuration is solid: the DPS path never touches simserver.exe at all
(file-based, proven reliable all session), and the one remaining simserver-dependent path
(`get_agility`/ComputeStats) is now independently verified robust at real scale, with self-heal
and graceful-None-degradation as a backstop even if some other combination of conditions still
trips it.

**Narrows the original crash hypothesis**: since `ComputeStats` (simple, synchronous, no Monte
Carlo iterations at all) survives 500 real calls in a row with zero issues, but the earlier
crash happened specifically during a long run of `evaluate()`-via-simserver calls (heavy
`RunRaidSimConcurrentAsync`, up to 12 concurrent goroutines per call, repeated hundreds of times,
iteration counts up to 30000) - the likely culprit is something specific to sustained heavy
`RunRaidSimConcurrentAsync` usage within one long-lived process (goroutine/channel accumulation,
a leak somewhere in the iteration-loop machinery), not a general "any repeated request" issue.
This is now a much more specific, testable hypothesis for whoever picks this up next: stress-test
`RunRaidSimConcurrentAsync` alone (not mixed with ComputeStats) at full iteration counts (30000,
matching the resolve pass) for several hundred real requests in a row, the same way
`get_agility()` was just verified - if THAT reproduces the crash cleanly, the bug is confirmed
isolated to the RaidSim path specifically, and `USE_SIMSERVER` could potentially be re-enabled
for `get_agility()`-style light calls while staying off for the heavy DPS path, or the actual Go
fix can be targeted precisely instead of guessed at.

No code changes this cycle - the current committed state (`USE_SIMSERVER=False`, self-healing
pool, graceful `get_agility()` degradation) was already correct; this cycle's work confirms and
sharpens that finding rather than changing it.

## 2026-08-23 (overnight, autonomous) — simserver.exe hang: precisely characterized, not yet fixed

Continued the crash/hang investigation with a targeted hypothesis: `simserver.exe`'s `runOne()`
hardcodes the SAME `requestId` string ("simserver") for every single `RunRaidSimConcurrentAsync`
call. That function registers the id in a process-lifetime map (`simsignals.RegisterWithId`) and
only removes it via a `defer`'d `UnregisterId` once its internal goroutine returns - safe for
`wowsimcli sim` (which hardcodes `"cmd-raid-sim"` the same way, in `basic_sim.go:50` - but that
process only ever calls this once before exiting, so it never matters), unsafe for a persistent
process making hundreds of calls with a reused id.

**Fixed this real bug regardless of whether it's the hang's cause**: `simserver/main.go` now
generates a genuinely unique requestId per call (`nextRequestId()`, an atomic counter). Verified
both code paths still work correctly after rebuild (`get_agility` -> Agility 1195, `evaluate`
file-based path -> combined 2655.4, matching known-good baselines).

**This did NOT fix the hang** - re-ran the exact same stress test (real candidates, valid slot
hints, 1000-iteration RaidSim calls) and it hung again. But precisely re-localizing it this time
produced a much stronger finding: it hangs at **exactly request #34**, every time, and - critically
- **completely independent of which candidates are involved**. Confirmed by skipping the first 30
candidates entirely (so request #34 became a totally different item, a Back-slot cloak instead of
the original neck item) - still hung at #34. This rules out anything item-specific and points
directly at a **fixed-capacity resource exhaustion inside the Go sim engine itself** - something
with a hard limit around 33 uses gets exhausted on the 34th call to `RunRaidSimConcurrentAsync`
within one process's lifetime. Not yet identified which resource (worker pool? channel buffer?
something GOMAXPROCS-sized, given `runtime.NumCPU()`=12 and this is close-ish to 3x that?) -
would need actual Go-level debugging (goroutine dump via SIGQUIT, or reading `runSimConcurrent`'s
internals directly for anything sized/counted around 32-34) to pin down further, not something to
guess at blind.

**Practical implication - this is a *tighter* threshold than previously known** (earlier
estimates ranged 25-65 depending on call mix). `USE_SIMSERVER` should stay `False` for the DPS
path until this is root-caused - a real production run easily exceeds 34 RaidSim calls. The
`get_agility`/ComputeStats path remains unaffected (verified separately at 500/500 calls with
zero issues - `ComputeStats` never goes through `RunRaidSimConcurrentAsync` at all, consistent
with the resource being specific to that function).

## 2026-08-23 — Acquisition gating (reputation/arena rating) + addon rename to GearingToolCompanion

User caught a real bug from the ledger: Ring wasn't showing as Achieved BiS even though it should
be - Band of the Eternal Champion (a real +18.3 DPS upgrade) requires Exalted with The Scale of
the Sands, which she isn't yet. The sim has no concept of acquisition gating at all (prices an
item once you have it, not whether you can currently get it) - nothing upstream would ever catch
this. Generalized to also cover arena rating gates per the user's own correction (Vengeful
Gladiator's Rifle - Arena Points doesn't mean rating-unlocked; user confirmed Anniversary ruleset
values: Weapons need 1700, Shoulders need 2000).

**`core/acquisition_gate.py`**: text-pattern detection against the same `source` string already
shown in the report - not a new data source. The DB doesn't structurally encode "Exalted" for
every item (Band of the Eternal Champion has no `sources` field at all - the info only exists in
Wowhead's curated text) and has zero arena rating data, so a DB-field-only approach would miss
exactly the cases that matter. Compares against `data/acquisition_status.json` (new, user-
maintained, not addon-synced by default logic - reputation section IS now auto-updated by
`gear sync`, see below). Unknown standing/rating always defaults to "gate not satisfied" -
conservative, disclosed, never silently assumes the favorable case.

Gated items still show normally in their tier (never hidden), tagged `[LOCKED]` in the console /
a red "locked" badge + explicit note in the HTML ledger. They no longer count as "beats current
gear" for Achieved BiS purposes. Caught two previously-unflagged gates in the same pass:
Ashtongue Talisman of Swiftness (Exalted Ashtongue Deathsworn) and Vengeful Gladiator's Rifle
(1700 rating, Ranged).

**Addon renamed `GearingToolExporter` -> `GearingToolCompanion`** (its scope outgrew "bank
export" - now also reads reputation and arena data). Old addon folder deleted from
`Interface/AddOns/` (WoW install, not this repo - the addon has never lived in git, it has to sit
in the client's AddOns folder to load; `addons/BankExporter/` in this repo is just an empty
placeholder, always has been). `GTExporterDB` -> `GTCompanionDB` SavedVariables global,
`ingest/build_character.py` updated to match (`find_gt_companion`, `gt_companion_present`/
`gt_companion_timestamp` meta keys).

New Lua: `DumpReputation()` (walks `GetNumFactions()`, expanding collapsed headers, standing IDs
mapped to names - Hated..Exalted) auto-merges into `data/acquisition_status.json`'s `reputation`
dict on every `gear sync`. `DumpArena()` (`GetArenaTeam(1..3)`) is NOT auto-trusted -
**GetArenaTeam's exact field for "the personal rating that gates a gear purchase" isn't confirmed
against this TBC Anniversary client build**, so raw per-team data is dumped to
`acquisition_status.json`'s `arena.raw_teams` for a human to check once; `arena.current_rating`
stays manual until that's confirmed. **Needs the user to relogin/reload UI in-game once** before
`gear sync` will pick up the renamed addon's SavedVariables file at all (same pattern as every
previous addon change this session) - not yet exercised with real reputation/arena data.

**Also recorded** (not built): user wants the eventual GUI to include a character-select
dropdown (multi-character support, not just Lerynia) - added to CLAUDE.md's existing "Future
scope" note. Tool rename to something including "Ruban" (e.g. RubanAutoSim) is planned as a
final rework once the product is otherwise done - explicitly NOT now; folder path and internal
naming stay as-is until then, per the user's own words.

## 2026-08-23 — GearingToolCompanion: minimap button UX, a real font-template bug, auto-save on rep/arena change

Added a minimap button + small status panel to the addon (left-click: save now, right-click: show
bag/bank/reputation/arena counts + last-saved time) so the addon is usable without knowing
`/gtexport` exists. Found and fixed through live in-game testing with the user:

- **Real bug** (via BugGrabber): `CreateFontString(nil, "OVERLAY", "GameFontHeader")` errored -
  "GameFontHeader" isn't a valid font template on this TBC Anniversary client build. Worse than
  cosmetic: the error aborted the rest of the file's top-level execution from that line onward,
  which is *why* the button initially had no working click/hover at all - `SetScript("OnClick", ...)`
  and `OnEnter`/`OnLeave` were registered later in the file and never ran. Fixed by reusing
  "GameFontNormalLarge" (already proven working elsewhere in the same file) instead of guessing
  another template name blind.
- Icon: started as `INV_Misc_Gear_01` (a very commonly reused "options" icon among other addons -
  hard to tell apart in a crowded minimap-button-collector popout), then a bow (thematically
  fitting, confirmed correctly detected by the user's MinimapButtonButton addon), then a custom
  dark badge with a bold gold "R" (user's idea, no external texture file needed - just a
  ColorTexture + FontString) - more legible at icon size and distinctive.
- Save confirmation: a plain `print()` is easy to miss (scrolls away, chat window may not be
  visible). Added `Announce()` - prints AND posts to `UIErrorsFrame` (the same floating on-screen
  text Blizzard uses for "You are out of range") for every user-*triggered* save (slash command,
  minimap click, status panel button). Passive/automatic saves (login, bag update) stay chat-only.
- Auto-save triggers extended: bank already saved on `BANKFRAME_OPENED` (a real technical
  requirement - bank container APIs return invalid data unless the bank frame is open).
  Reputation/arena have no such restriction (`GetFactionInfo`/`GetArenaTeam` are always
  queryable), so rather than tie their auto-save to "did the user open that UI tab" (a weak
  proxy - reputation changes constantly without ever opening the reputation pane), hooked the
  real data-change events instead: `UPDATE_FACTION` and `ARENA_TEAM_UPDATE`/
  `ARENA_TEAM_ROSTER_UPDATE`, throttled to 1/sec same as the existing bag-update handler.

Known unresolved: the minimap button's left-click doesn't reliably fire once wrapped inside
MinimapButtonButton's popout (right-click/tooltip work fine there, confirming collection itself
works) - suspected MBB click-forwarding quirk with hand-rolled buttons, not something fixable
from this side without MBB's own source. `/gtexport` and the status panel's own "Save Now"
button both work regardless and are the reliable fallbacks.

## 2026-08-23 — Real fix: this client uses modern reputation/arena APIs, not the classic globals

The status panel showed "Reputation: 0 factions tracked, Arena teams: 0" despite the character
genuinely having reputation and three real arena bracket ratings (screenshot: 2v2 1484, 3v3 1494,
5v5 1585, "This Week" games/rank columns). Not an offseason/no-data issue as first guessed -
verified against WoW's actual API docs (warcraft.wiki.gg) rather than guessing twice:

- **Arena**: `GetArenaTeam(1..3)` returned nothing because **this client has no persistent
  "arena team" object at all** - TBC Anniversary uses the modern per-bracket PERSONAL rating
  system instead (`GetPersonalRatedInfo(index)`, bracket 1=2v2/2=3v3/3=5v5 - confirmed field
  order: `rating, seasonBest, weeklyBest, seasonPlayed, seasonWon, weeklyPlayed, weeklyWon, cap`).
  The "38616"/"32793"/"36377" numbers in the user's PvP pane screenshot are ladder rank, not team
  IDs, per the user - consistent with there being no team object to have an ID.
- **Reputation**: `GetNumFactions()`/`GetFactionInfo()` were deprecated as of patch 11.0 in favor
  of the `C_Reputation` namespace (`C_Reputation.GetNumFactions()`,
  `C_Reputation.GetFactionDataByIndex(i)` returning a table with `name`/`isHeader`/`isCollapsed`/
  `reaction` fields - `reaction` replaces the old `standingID`). The old globals didn't error,
  just silently returned 0 - a much sneakier failure mode than a thrown error would have been.

Fixed both in `GearingToolCompanion.lua` using the modern APIs, with a fallback to the old
globals in case this ever runs on an actually older client. Since arena rating is now read from
a confirmed, unambiguous field (not a guessed one), `ingest/build_character.py` now
auto-populates `acquisition_status.json`'s `arena.current_rating` as the max across brackets
(TBC's "reach X rating in ANY bracket" vendor-gating rule is a stable, well-documented game
mechanic - not per-server data, safe to encode directly, unlike the API-field question that
genuinely needed the confirm-before-trusting treatment it got last time).

**Lesson for next time a WoW API call silently returns empty/zero instead of erroring**: don't
assume "no data" - Classic/Anniversary realms run on a modern, shared client codebase, and
Blizzard has been deprecating classic-era globals in favor of C_-namespaced APIs project-wide
(patch 11.0 reputation being one instance) - check whether the "old" API even still works on
this specific client build before trusting a zero/empty result at face value.

## 2026-08-23 — Reputation still 0 after the C_Reputation fix: a real, documented lazy-load quirk

Arena rating confirmed working after the previous fix (screenshot: "Arena teams: 3"). Reputation
still showed 0 despite the user's Reputation tab clearly showing many real standings. Verified
via search rather than guessing again: **`C_Reputation.GetNumFactions()` can return 0 until the
reputation panel has actually been shown at least once this session** - a known Blizzard API
quirk (the backing list isn't populated until the panel itself initializes it), separate from
the patch-11.0 API rename fixed last time. `UPDATE_FACTION` (a real standing change) doesn't
help here since the panel may simply never have been opened yet.

Fixed by hooking `ReputationFrame`'s `OnShow` to re-run `SaveReputationAndArena()` - exactly
what the user originally suggested days ago ("autofire when the tab is opened"), which was
wrongly deprioritized at the time in favor of pure data-change events on the assumption
reputation was always freely readable. `ReputationFrame` may not exist yet at addon-load time
(it belongs to a separately, lazily-loaded Blizzard UI addon) - hooked both immediately (in case
it's already loaded) and again on `ADDON_LOADED` (in case it loads later, the first time the tab
is opened).

Also swapped the minimap button's click mapping per user feedback - left-click now shows the
status panel (the more discoverable, "look at it" action), right-click does the quick silent
save. The reverse felt unintuitive.

## 2026-08-23 — Reputation still 0, real root cause: `C_Reputation` doesn't exist on this client, and `hasRep` was misread

The `OnShow` fix above didn't help either. Added temporary debug prints to `DumpReputation()` to
stop guessing and just see what each API actually returns. The debug output was decisive:
`C_Reputation` is **not present at all** on this client build (contrary to the previous entry's
assumption) - it always falls through to the pre-11.0 `GetNumFactions`/`GetFactionInfo` globals,
and those return real, correct data: `GetNumFactions() = 43`.

Despite that, the counting loop still produced 0 real factions. The debug dump of row 2 showed
why: `name=Darnassus isHeader=false isCollapsed=false hasRep=false standingId=7`. `standingId=7`
is real (Revered) data, but `hasRep=false` on a completely normal, non-header faction. The
counting condition was `not isHeader and hasRep and name` - it required `hasRep` to be true,
but **`hasRep` is not "this row has valid reputation data"** at all; it only flags whether a
*header* row itself additionally carries its own account-wide reputation bar (rare - most
headers don't). It's false/nil on every ordinary leaf faction by design, which is exactly why
all 43 real factions were silently skipped despite the count being right the whole time.

Fixed by keying the count off `not isHeader and name and standingId` instead - `standingId`
being present is what actually means "this is a real, trackable faction row." Removed all the
temporary debug prints and the stale "matches the modern C_Reputation namespace" comment (this
client genuinely doesn't have it) now that the real cause is confirmed and fixed, rather than
inferred a third time.

**Lesson**: don't trust an unfamiliar API return value's *name* to mean what it sounds like -
`GetFactionInfo`'s field order/semantics needed a live raw dump to actually pin down, not the
assumption a plausibly-named boolean does the obvious thing.

## 2026-08-23 — Gem baseline fix: real-socketed gems for owned gear + meta gem requirement enforced

Investigated a user-flagged edge case: Gloves of Dexterous Manipulation (Kara) + Ranger-General's
Chestguard (SSC) are commonly cited P2 SV BiS but weren't showing as upgrades. Two real,
compounding pipeline bugs found along the way (not the original question, but more consequential
for every MV number the tool produces):

1. `build_owned_config()` (baseline) was using her *literal currently-socketed* gems while
   candidates always got the optimal default gem. Confirmed her actual gem in Rift Stalker
   Hauberk was still Delicate Living Ruby (phase 1, Agi 8) instead of Delicate Crimson Spinel
   (phase 3 default, Agi 10) - a real, un-re-gemmed socket she hadn't noticed. This silently
   understated `DPS*(P)` (her baseline) and correspondingly overstated every single candidate's
   MV, since MV = DPS*(P∪{i}) − DPS*(P). Fixed: baseline now fills the same optimal gem logic as
   candidates (`core/gem_optimizer.py::best_gems_for_item`, wired into `optimizer.py`).

2. Tried a "smarter" gem choice that color-matches an item's sockets to unlock its socket bonus
   (hybrid AP/RAP/Crit gems) whenever `STAT_WEIGHTS` said the bonus + hybrid beat pure Agility.
   User was skeptical ("i don't think its the socket bonus"). Direct sim A/B/C test at 30k
   iterations against Ranger-General's Chestguard proved the heuristic actively harmful: pure
   Agility scored 2701.4, her real (partly outdated) gems scored 2656.0, the "smart" hybrid
   choice scored **2651.6 - worse than even her suboptimal real gems**. Root cause: Agility is a
   Hunter multi-stat-conversion stat (→RAP/Crit/Armor) that a flat linear `STAT_WEIGHTS` entry
   can't capture, so it's systematically undervalued relative to flat AP/RAP stacking. Reverted
   to pure Agility (`DEFAULT_GEM`) in every socket; kept the color-matching/socket-bonus
   infrastructure in `gem_optimizer.py` as real DB-grounded groundwork, unwired until a version
   of it is actually verified per-candidate against the sim rather than a crude weight table -
   this is CLAUDE.md's own "never shortcut to EP-only ranking" rule, just newly discovered to
   also apply to gem choice, not only item choice.

3. Pure-Agility-everywhere silently breaks her real meta gem: user caught it directly ("you are
   deactivating my meta gem"). Confirmed via `sim/tbc-new/sim/core/item_effects.go` that the sim
   does **not** model or check meta gem activation requirements at all -
   `ApplyMetaGemCriticalDamageEffect` applies the 3% crit-damage bonus unconditionally, no
   color-count check anywhere - so the sim's own reported DPS wouldn't reflect an invalid
   real-world gem setup. Web research on her actual meta gem (Relentless Earthstorm Diamond,
   id 32409) gave three conflicting answers across sources; correctly did not trust any blind and
   asked the user to check her own in-game tooltip instead. Confirmed requirement (her
   screenshot): "Requires at least 2 Red Gems / at least 2 Yellow Gems / at least 2 Blue Gems",
   counted across her whole gear. No hunter-relevant (AP/RAP/Crit/Hit) pure Blue gem exists in
   this DB at all - every quality-4 Blue gem is Stamina/Spirit/Intellect - so satisfying the
   requirement always costs real stat value; a Green gem (Blue+Yellow hybrid) satisfies both
   missing colors from one socket, making 2 Green gems the minimum-sacrifice fix (vs 3+ sockets
   for any pure-color combination). Implemented `gem_optimizer.py::ensure_meta_requirement()` -
   swaps the fewest pure-Agility sockets to the best Green gem needed to satisfy any shortfall,
   no-op for any other meta gem or if already satisfied. Verified: swaps exactly 2 sockets
   (Head + Shoulder → Sundered Chrysoprase), final valid baseline = 2685.5 (between the invalid
   2701.4 meta-broken number and her real un-re-gemmed 2656.0).

**Net effect**: the tool's own baseline DPS number changes (goes up, since re-gemming Rift
Stalker Hauberk is a free, real improvement she hadn't done yet), and every MV in the pool
shifts down correspondingly to compensate - this is the pipeline getting *more* correct, not the
sim's model changing, so it doesn't violate the "assume the sim's model is correct" rule; it's a
data-completeness/methodology fix on this tool's side of the boundary.

## 2026-08-23 — Bank-clearing bug, second real cause: bag -1's slot COUNT is static, only item links go nil

The first bank-loss fix (`if C_Container.GetContainerNumSlots(-1) == 0 then return end`) didn't
actually fix it - user reported "The Save Button still clears the Bank" again. Root cause:
`GetContainerNumSlots(-1)` returns the real, purchased slot count (e.g. 24) **whether or not the
bank frame is open** - only the per-slot `GetContainerItemLink` calls go nil while closed. So the
guard's condition (`== 0`) never actually triggered on a closed bank, `DumpContainers` proceeded
to scan every slot, got nil links back, and happily saved an all-empty bank over the last good
snapshot - exactly the reported symptom, just via a subtly wrong precondition check.

Fixed properly this time by tracking real open/closed state via events instead of inferring it
from container data at all: a module-level `bankIsOpen` flag, set `true` on `BANKFRAME_OPENED`
(already handled) and `false` on the newly-registered `BANKFRAME_CLOSED`. `SaveBank()` now gates
on that flag. This is the standard, reliable pattern other bank addons use - inferring "is the
bank open" from any container-API side effect is fragile precisely because slot *counts* and
slot *contents* are populated on different lifecycles that aren't obvious until tested live.

## 2026-08-23 — Real hit cap numbers (Wowhead-sourced), and she's currently well over it

User pushed back on the joint-search proposal for hit-rating threshold crossings with real
context: "we gain 3% hit as survival from talents." Rather than guess at TBC hit mechanics from
memory, fetched Wowhead's own Hunter stat priority guide directly (in-browser, since the static
fetch only returns the JS shell): **base hit cap is 142 rating (9%) vs a raid boss with no
hit-affecting buffs; with Improved Faerie Fire (Balance Druid talent) it drops to 95 rating
(6%); 15.77 rating = 1% hit.** Her `canonical_settings_survival.json` already assumes Improved
Faerie Fire (`"faerieFire": "TristateEffectImproved"`), so her real target is 95/6%, not 142/9% -
confirmed via the wowsims.com live site too, which only ships a 6%-hit Survival preset (no 9%
variant), consistent with "always assume a moonkin" being the standard community assumption for
this spec, not an arbitrary choice.

Cross-checked her stated "3% from talents" against the sim's own `ComputeStats` RPC (not hand
math): her gear alone gives 104 hit rating (`finalStats.stats[20]`, ≈6.6%), and
`pseudoStats[24]` (`PseudoStatRangedHitPercent`) reports her actual computed hit chance as
**9.595%** - matching 6.6% (gear) + ~3% (talent) almost exactly, confirming her number is real
and the sim already applies it correctly (talent-derived hit doesn't even show up as "rating" at
all, it's a separate PseudoStat channel - `sim/hunter/talents.go`'s
`hunter.AddStat(stats.PhysicalHitPercent, ...)` for Surefooted confirms this mechanism is real
and modeled).

**Net finding: she's over-capped by ~3.6 percentage points right now (~57 rating of pure
waste)**, spread across 5 gear pieces (Rift Stalker Mantle/Hauberk/Gauntlets, Belt of Deep
Shadow, Arcanite Steam-Pistol). Per the user's own framing, this isn't a "mistake" - it's just
what P2 BiS itemization gives you; P3 gear naturally itemizes differently. Checked whether this
needed a new analysis pass: it didn't - the already-completed full sweep's existing per-item MV
numbers for these exact 5 slots already correctly account for the wasted hit, since the real sim
computes actual miss-chance-driven damage rather than a crude heuristic. All 5 slots already had
real, sim-verified upgrades in the existing report (Shoulder +8.2, Chest package +25.2, Hands
+8.1, Waist +13.4, Weapon +9.7) - nothing new needed computing.

Added a GUI future-scope note (not built) for a 6%/9% hit-target toggle, since wowsims itself
ships both as presets for other specs - see CLAUDE.md.

## 2026-08-23 — Melee weave: real mechanism traced, real +333 DPS finding, boss-dependent

User: "we still need to implement the 2 handed features since meleeweaving can lead to a big dps
gain." Investigated properly before building anything, since `slot_for_item()` had deliberately
excluded 2H weapons with a note that evaluating them under the DW rotation "would be a wrong
number, not just worse" - the melee-weave rotation itself was never built.

**How the sim actually consumes rotation config, traced from source rather than assumed**:
grepped the entire vendored sim for consumers of `SpecRotationJson` (the `TypeSimple` knob that
supposedly carries `meleeWeave:true`/`false`) - found **zero Go backend consumers**, only the
raw proto definition. The web UI must pre-compile `TypeSimple` + `specRotationJson` into a full
`TypeAPL`-equivalent script client-side at save/export time; the backend just executes whatever's
in `rotation.priorityList`/`groups`/`valueVariables` verbatim, regardless of what `rotation.type`
claims. Confirmed: our own `canonical_settings_survival.json` already contains this fully
compiled APL, and it ALREADY has weave-conditional branches built into the same script used for
non-weave play - every relevant action is gated on one boolean:
`{"variableRef":{"name":"Melee weave"}}`, currently `{"const":{"val":"false"}}}`. The real,
correct switch is flipping that one constant, not touching `specRotationJson` at all (which
nothing reads).

Created `profiles/tbc/canonical_settings_survival_2h.json` = the DW settings with only that one
constant flipped to `"true"`. Verified this is a real mechanic and not a bug via the raw damage
breakdown (`raidMetrics`, not just the aggregate DPS number) on a test 2H config (Twinblade of
the Phoenix, offhand emptied): ranged auto shot (`OtherActionShoot`) fires at its completely
normal, unthrottled rate; the offhand attack action correctly shows **zero casts** (proof the
slot is genuinely empty, not silently still swinging); and the mainhand melee auto-attack channel
- which sits at exactly zero casts for a normal kiting hunter, since distance-from-target never
drops into melee range - picks up real, substantial additional damage from the periodic
weave-in windows. This is genuinely free damage from filling otherwise-wasted GCD gaps, not a
double-count artifact.

**Tested on her actual current DW gear, zero item changes**: +333 DPS combined just from
flipping the rotation (2685.9 -> 3018.8, ~12.4%) - larger than every single item MV found this
entire session, combined. This raised an immediate question: should this become the new default
baseline for everything? User's answer: **"we do plan to weave on bosses that allow for it but
not all do."** So there is no single correct baseline - it's genuinely boss-dependent, unlike
every other setting in this tool (buffs/debuffs/talents are raid-wide constants). Decided: keep
`canonical_settings_survival_2h.json` as a separate, explicitly-labeled variant rather than
replacing the default - matches the same "two separate, never-silently-collapsed numbers"
principle already established for Player/Raid columns.

**Real, DB-confirmed correctness gap found along the way**: `handType` was only ever checked for
the `TwoHand` exclusion. `MainHand`-only (1) and `OffHand`-only (3) restrictions were never
enforced anywhere - `mv_single`'s "try every slot this item could occupy" logic for
`weapon_dual_wield` items could have silently tested a hand-restricted weapon in the wrong slot.
Found via a real example the user raised: Mount Hyjal TRASH drop (`sources[].drop.otherName ==
"Trash"`, zone 3606) "The Fists of Fury" (setId 719) - **Claw of Molten Fury** (id 32946,
`handType:1`/MainHand-only) + **Fist of Molten Fury** (id 32945, `handType:3`/OffHand-only), a
deliberately matched pair. Fixed with `optimizer.is_hand_restricted_conflict()`, wired into
`mv_single` alongside the existing unique-item conflict check.

Tested the real pair itself: **-49.9 DPS without weave, -39.4 DPS even with weave on**, vs her
current Netherbane/Blade of the Unrequited - a real downgrade either way, weave narrows the gap
but doesn't flip the sign. Checked for a "Weightstone" consumable (the user's hypothesis was
"upgrade IF we use weightstones on both") to see if that could close the remaining gap: **this
sim's DB has no Weightstone-equivalent modeled at all** - nothing matching in the `enchants`
table, and the settings schema (`apiVersion 14`) has no weapon-applied-consumable field at all
(the old `mhImbueId`/`ohImbueId` fields mentioned in an earlier NOTES entry belong to a stale,
different schema version, not this one). Reported the raw comparison as real and correct, and
explicitly flagged that Weightstone's real effect is outside what this sim can currently answer -
not silently assumed to be zero, not guessed at a value either.

## 2026-08-23 — Correction: Weightstone IS modeled, just not where I looked

Above entry was wrong. Only checked `db.json`'s `items`/`enchants`/`consumables` tables (all
empty for "weightstone") and concluded it wasn't modeled at all. User's own tooltip screenshot
("Adamantite Weightstone... Increase blunt weapon damage by 12 and add 14 critical hit rating
for 1 hour") prompted grepping the actual Go source instead of trusting a DB-table absence:
`sim/core/consumes.go`'s `case 34340: // Addy Weightstone` matches the tooltip exactly
(`MeleeCritRating +14`, `BaseDamageMin/Max +12` on the imbued hand). The mechanism is
`ConsumesSpec.mhImbue_id`/`ohImbue_id` (proto fields 10/11, JSON `mhImbueId`/`ohImbueId`) - real,
current fields our settings files simply never populated (the earlier "stale mhImbueId/ohImbueId,
different schema" note was about an unrelated bug in a diagnostic script, not evidence the fields
don't exist now). Also found 29453 ("Addy Sharpstone", same effect, bladed-weapon-gated) in the
same switch. **Lesson**: absence from a DB export table doesn't mean absence from the sim's
model - the Go source is the actual ground truth, the DB tables are just what got exported into
JSON for item/gem lookups.

User's scope: only Fist weapons get auto-imbued (Weightstone), not bladed weapons too - "they
have a bigger benefit due to flat crit" (a flat +14 rating / +12 damage bonus is a bigger
relative gain on a fist weapon's typically smaller stat/damage budget than on a bladed weapon's
larger one). Implemented in `adapters/tbc/valuation.py`: `_apply_weapon_imbues()` checks
mainhand/offhand's `weaponType` and sets `mhImbueId`/`ohImbueId` to 34340 only when it's
`WeaponTypeFist` (3); every other weapon type is left exactly as the settings file specifies
(currently unset). Wired in before cache-key fingerprinting (not after), since two configs that
trigger different imbue outcomes must not collide on the same cache key -
`_fingerprint_settings()` now takes the mutated dict directly rather than re-reading the file, so
the fingerprint always reflects what's actually about to run.

Real final number for the Molten Fury pair (superseding both earlier estimates - the first
had no imbue on either side, the second wrongly gave the *baseline* bladed weapons a Sharpstone
imbue the user never asked for): **-30.7 DPS vs current gear, no weave** - through the
now-corrected, automatic pipeline. Still a real downgrade. Checked the cache blast radius before
committing: non-fist configs produce a byte-identical fingerprint to before this change (no
mutation happens for them), so the existing cache stays valid for the vast majority of entries -
only fist-weapon candidates (Blackhand Doomsaw, Darkspear, the Molten Fury pair, ~40 items total
across the pool) get a genuinely different fingerprint and correctly recompute.

## 2026-08-23 — Real regression: hand-restriction check silently zeroed every non-weapon slot

User caught it immediately from the published artifact: "it seems we now didn't run p3 items at
all? no upgrades?" Achieved BiS had grown from its real 3 slots (Neck/Back/Ring) to nearly every
slot in the game (Head/Shoulder/Chest/Wrist/Hands/Waist/Legs/Feet/Ring/Trinket/Ranged) - as if
her current gear now beat the entire Phase 3 pool everywhere, minutes after a run that correctly
showed dozens of real upgrades in those exact slots. Root cause: `is_hand_restricted_conflict()`
(added a few entries above, for the Molten Fury pair fix) computed
`hand_type == _SLOT_TO_HAND_RESTRICTION.get(slot)` with no None-guard. A non-weapon item's
`handType` is `None`; `_SLOT_TO_HAND_RESTRICTION.get(slot)` for any non-weapon slot (head, chest,
trinket1, etc.) is ALSO `None` (key not in the dict). `None == None` is `True` in Python, so
every single non-weapon candidate in every non-weapon slot was silently treated as a hand
conflict and excluded from `mv_single`'s trial loop - `best` stayed `None`, and every candidate
came back `{"excluded_reason": "unique conflict in every candidate slot"}` instead of a real MV.

Confirmed directly: `mv_single()` on Cursed Vision of Sargeras (real +13.3 DPS Head upgrade,
reported minutes earlier) returned the exclusion instead of a number. Fixed by returning `False`
immediately when the slot isn't a real weapon slot (`mainhand`/`offhand`) or the item has no
`handType` at all - the check only ever means something for an actual weapon in a weapon slot.
Cache itself was never corrupted (the exclusion happened before any sim call, so no bad values
were ever written) - a rerun after the fix reproduced the exact known-good numbers immediately.

**Lesson**: a boolean comparison against two independently-computed "not applicable here" values
(`None`/absent) is a real Python footgun - `x == y` doesn't distinguish "both real values happen
to match" from "neither value applies at all." Should have guarded on "is this even a scenario
where the check applies" first, not trusted equality to naturally handle the null case.

## 2026-08-23 — "Raid AP" renamed to "Debuff", reported per-attacker not a fixed-total

User's reasoning, from looking at the published ledger: the old column multiplied the Expose
Weakness AP delta by `PHYSICAL_ATTACKER_COUNT` (a fixed assumed 9, from §0's stated raid comp
midpoint) into one pre-baked total. That's the wrong shape for how this number actually gets
used - a real raid's physical-attacker count varies week to week, and baking in one assumed
count makes the number harder to argue to a raid lead/loot council and impossible to use for "at
what attacker count does this become worth it" reasoning. Changed `mv_single()` to call
`expose_weakness.raid_ap_contribution(..., count=1)` and report the PER-attacker delta instead -
multiply by your raid's actual count for a total, which is now the reader's job, not this tool's
assumption. `PHYSICAL_ATTACKER_COUNT` itself is kept in `marginal_value.py` only as a documented
reference constant, no longer driving the reported number.

Also renamed the column from "Raid" to "Debuff" - a more literal, accurate name (it's reporting
how strong Lerynia's OWN Expose Weakness debuff is, not some already-aggregated raid total) that
reads less ambiguously than "Raid," which could be misread as already being a raid-wide sum.

## 2026-08-23 — Real bug: set-progression piece count meant "swaps performed," not real total

User's own tooltip screenshot showed Rift Stalker Armor's real bonuses (2pc: pet healed for 15%
of damage dealt; 4pc: Steady Shot +5% crit) and asked why the tool's own "1pc..5pc" progression
showed no visible jump anywhere. Confirmed both bonuses ARE modeled in the sim
(`sim/hunter/item_sets.go`, setId 652) - not a coverage gap. Real cause: she already owns 4 of
the 5 Rift Stalker pieces (Helm/Mantle/Hauberk/Gauntlets), so the 4pc bonus is already active in
her baseline. `set_progression()`'s `pieces_held` was `count` - the loop index, i.e. "how many
pool candidates have been swapped in so far" - not the real total set-piece count in the
resulting config. Those only match when baseline starts at 0 pieces of the set (true for
Gronnstalker's Armor, which she owns none of - hence its progression showed a real, clean 1-5
climb with a visible 4pc jump). For Rift Stalker, every one of the first 4 reported "swaps" was
actually replacing an already-owned Rift Stalker piece with a *different* Rift Stalker candidate
in the same slot - real total stayed at 4 throughout, so the actual 0->4 transition (and the
bonus activating) had already happened before the reported range even starts. Only the 5th step
(Leggings, the one slot she's missing) was a genuine count change to 5 - correctly showing -16.0,
since no 5pc bonus exists (confirmed by her tooltip) and Leggings just has worse raw stats than
her current Void Reaver Greaves.

Fixed with `set_bonus.count_set_pieces_in_config()` - scans the actual trial config for real
`setName` matches instead of trusting the loop counter. Piece counts can now legitimately repeat
in the printed steps (e.g. "4pc" four times before "5pc") - added the swapped item's name to each
step so repeated counts stay unambiguous. **Lesson**: never assume a loop counter tracks the real
domain quantity it's named after - it only does when the starting state is known-zero, which
wasn't checked here and silently wasn't true for a set she's already deep into.

## 2026-08-23 — Isolated, stat-neutral set-bonus values via a bonusStats correction

Replaced the flat 1pc..5pc progression display entirely, per the user's follow-up: most piece
counts carry no bonus at all, and even at a real threshold the reported delta mixed the bonus's
own effect with the raw stat difference of whichever piece happened to cross it. User's own
suggested method: "we can manipulate stats for this test so baseline character stats stay the
same but set bonus activates or deactivates."

Implementation (`core/set_bonus.py`): `item_stat_vector(item_id, gems)` pulls the real 42-element
stat vector (item's own `scalingOptions` stats + its socketed gems' stats, same indexing as
`bonusStats.stats` and a gem's own `stats` array - confirmed all three use the identical 42-slot
layout). `isolate_bonus_value(set_name, threshold, ...)` builds two configs that differ by exactly
one real piece count (threshold-1 vs threshold - pieces removed from an already-owned set or added
from pool candidates as needed to reach each), and applies a `bonusStats` correction to each so
total character stats match TRUE baseline throughout - the delta between the two configs is then
purely the bonus's own behavioral effect (a proc, a spell mod), not a stat difference.
`valuation.evaluate()` gained a `bonus_stats_override` parameter for this, mutated before
fingerprinting (same pattern as the fist-weapon-imbue fix) so it gets a distinct cache key, never
colliding with a normal run.

Real bonus thresholds come from `set_bonus_thresholds()`, which parses them directly out of
`sim/hunter/item_sets.go`'s own `Bonuses: map[int32]core.ApplySetBonus{2: func(...){...}, 4:
func(...){...}}` per set - never guessed, and generalizes automatically to every hunter tier set
in the file (checked: Cryptstalker [2,4,6,8], Beast Lord [2,4], Demon Stalker [2,4], Rift Stalker
[2,4], Gronnstalker's [2,4] - matches the real in-game tooltip for Rift Stalker exactly).

Real isolated results from the first full run: **Gronnstalker's Armor** 2pc +0.0 (tied - not a
damage effect), 4pc +70.3 (real). **Rift Stalker Armor** 2pc +51.1, 4pc +85.2. **Beast Lord
Armor** 2pc tied, 4pc +73.4. The Rift Stalker 2pc value (pet healed for 15% of damage dealt) is
larger than a pure heal effect would suggest at first glance - plausible explanation is sustained
pet DPS uptime (a pet that doesn't die/go quiet from unhealed damage keeps dealing damage longer
across a full fight), not re-derived or second-guessed further - the sim's own model is trusted
per the ground rules, this is just noted as an interesting result worth being aware of.

## 2026-08-23 — Acquisition cost dropped; Wowhead item/recipe linking added instead

Started building a per-item acquisition cost feature (§7's cost tables) - checked the sim's DB
directly first and confirmed it has NO cost data at all (only `rep`/`drop`/`crafted` source
*types*, no prices anywhere). Only 4 real-upgrade items in the current report are even non-drop
(Vengeful Gladiator's Rifle - 1500 Arena Points; Ashtongue Talisman of Swiftness - 23g 5s 25c;
Band of the Eternal Champion - no cost, pure quest reward; Bindings of Lightning Reflexes -
Leatherworking, 5 real reagents pulled from Wowhead). User cancelled this mid-build and asked to
skip acquisition cost entirely in favor of Wowhead linking instead - simpler, more broadly
useful, and needs zero manual research per item since every report row already carries a real
`item_id`.

Implemented: every item name in the artifact links to `wowhead.com/tbc/item=<id>`. For crafted
items specifically, also added a small 🔨 link to the real crafting recipe page
(`wowhead.com/tbc/spell=<spellId>`) - found that `sources[].crafted.spellId` was already sitting
in the DB, just discarded by `describe_source_and_tier()` (only the profession name was kept).
Now threaded through as `craft_spell_id` on every report row.

## 2026-08-23 — Time-horizon flags: "lasts until Phase N" / "alternative for Phase N"

Replaces the original spec's coarse three-bucket label with a precise phase number, per the
user, and drops the cost-paired "scarce currency + replaced soon = don't spend" logic since
acquisition cost tracking was dropped in favor of Wowhead linking. Fetched real Phase 4
(Zul'Aman) and Phase 5 (Sunwell Plateau - confirmed the final phase of TBC by the guide's own
text) Survival Hunter BiS guides from Wowhead, same author/format/structure as the existing
Phase 3 list - `profiles/tbc/reference_bis/phase{4,5}_survival.json`. Explicitly treated as
truth for now, not simmed ourselves - the user's own framing: a later build sims these phases
directly and finds the real best set per phase; this is a disclosed stand-in until then.

`core/time_horizon.py` matches by item NAME against each list's flattened item set (same
exact-match convention `run_full_sweep_mv.py` already uses for `curated_source_text`), finds the
highest phase the name still appears in at all, and separately checks whether its rank AT THAT
PHASE actually reads "Best..." vs "Optional"/"Alternative"/"Good"/"Great". User's follow-up catch:
being listed in a future phase's guide doesn't mean still recommended - Gronnstalker's Helmet is
real BiS through Phase 4 but drops to "Optional" once Coif of Alleria takes over in Phase 5, so
the tag reads "alternative for P5" instead of implying it's still the top pick. A name that
doesn't match anywhere fails safe to "lasts until Phase 3" rather than asserting longevity.

## 2026-08-23 — Reworked again: "BiS until Phase N", not "lasts/alternative for"

The version above was still wrong per the user, in a more fundamental way than a labeling tweak.
Two real corrections:

1. Cursed Vision of Sargeras showed "[lasts P5]" because it's technically LISTED in the Phase 5
   guide - but only as "Best Previous Phase Option," an explicit leftover the guide itself says
   isn't really recommended anymore. Being listed at all was never the useful signal; staying the
   genuine top pick is. It's Phase 4's "Best Personal" (a real top-tier choice for one gearing
   route) but stops being BiS once Phase 5's real options exist - should read "BiS until P4".
2. Thalassian Wildercloak, owned since Phase 2, staying the guide's actual top pick all the way
   through Phase 4 is a real, non-obvious finding worth surfacing clearly - "BiS until P4" (gets
   replaced once Phase 5 starts). Conversely, an item that was only ever a stepping-stone
   alternative (never the guide's real top pick, even now - e.g. Rift Stalker Hauberk, kept
   around only until the real Tier 6 piece drops) doesn't need a tag at all. Per the user: "its
   not important to know that tier 5 is an alternative to tier 6 we understand that without a
   tag" - showing a tag for every non-BiS item was noise, not signal.

`lasts_until_phase()` (function name kept, return shape changed) now returns `bis_until_phase`
(None when the item was never confirmed a genuine top pick anywhere - no tag shown for these at
all) instead of the old `lasts_until_phase`/`is_best` pair. Walks phase 3 -> 4 -> 5, stopping at
the first rank that doesn't read as an actual top pick - excludes any rank containing "Until"
("Best Until Tier X" - a within-phase stepping stone), "Previous" ("Best Previous Phase Option" -
an explicit leftover), "Alternative", or "Second" (both mean "a named runner-up next to a plain
Best in the same slot"). Plain "Best" and route-qualified variants that ARE genuine top picks for
a legitimate gearing choice ("Best Personal", "Best 6%"/"Best 9%", "Best x2", "Best Overall",
"Best Raid Wide Increase") all still count. Absence from Phase 3's own table is treated as
unknown rather than disqualifying (that list is already known to have real completeness gaps -
items our own sim finds as real upgrades that the guide's table just doesn't happen to rank);
absence from Phase 4 or 5's table is treated as "no longer relevant" and stops the walk, since
those lists are comprehensive per-slot rankings, not curated highlights.

## 2026-08-23 — Best-4-of-5 tier combo finder; WoW-quality colors; phase-toggle-ready

Two more real pieces added to the same session's work:

**`set_bonus.best_four_of_five()`**: per the user, BiS guides almost always recommend 4 of a tier
set's 5 armor pieces (occasionally all 5, rare; occasionally fewer, when bonuses are weak) - which
slot should stay non-tier is determined by comparing REAL sim numbers across all five
leave-one-slot-out combinations plus the full 5pc, not assumed from guide convention or a fixed
add-order. Caught a real bug while verifying it against Rift Stalker Armor: when the "excluded"
slot happened to be one she already owned the tier piece for (Hands - Rift Stalker Gauntlets), the
first version just left it in place instead of testing a genuine non-tier alternative, silently
making that combo a no-op duplicate of the full 5pc test. Fixed by swapping in the best real
non-tier candidate for that slot (crude STAT_WEIGHTS prefilter) when needed - changed the real
answer: excluding Hands (2709.2) beats excluding Legs (2687.6), which the broken version couldn't
even see as an option. Wired into the main report, printing the best combo + excluded slot + real
cost of going full 5pc for every relevant set.

**WoW item-quality colors for the BiS-until tag**, worked out with the user over several rounds:
green (BiS for the current phase only), blue (one more phase), purple (reaches the final phase),
orange (reaches the final phase AND the item's own real DB `phase` is <= 2 - genuinely spans
nearly the whole expansion, not just "permanent from now on"). Purple and orange are layered, not
parallel alternatives - orange is the rarer subset of purple's condition, matching WoW's own
epic-then-legendary escalation. Real example that resolved the design: Dragonspine Trophy (real
Phase 1 Gruul's Lair drop, never replaced) reads orange; Gronnstalker's Spaulders (a Phase 3/T6
piece that also happens to never get replaced) reads purple - both "permanent from here on," but
only one has been relevant since near the start.

**Generalized away from a hardcoded "current phase = 3" assumption**: per the user, this tool
should work correctly whenever it's actually run in the future, not just during Phase 3 - a
character could start using it from Phase 1. `time_horizon.py` now has named `CURRENT_PHASE`/
`FINAL_PHASE` constants instead of scattered `3`/`4`/`5` literals, and `_load_phase_item_ranks()`
scans phase 1..FINAL_PHASE instead of a fixed `(3,4,5)` tuple - picks up the already-existing
`phase2_survival.json` for free, and would pick up a future phase1 file with zero code changes.
Not a full phase-toggle (that's still a separate, later GUI feature per CLAUDE.md), just keeping
the seam from being buried under a hardcoded assumption that would need finding and unpicking
later.

## 2026-08-23 — Screened #1 now always gets the real resolve

User caught this from the report itself: Beast-tamer's Shoulders was ranked #1 for Shoulder but
still printed "(screened only)" - correct under the old rule (its margin over noise already
cleared `CLEAR_MARGIN_MULTIPLE`, so resolving couldn't flip the verdict) but wrong to show as the
headline number, since the cheap 1k-iteration screen is noisier than the real 30k resolve. Per the
user - "if a screened item ends up on top we should really sim that" - `run_full_sweep_mv.py` now
always resolves the #1-ranked item within each `(tier, slot)` group regardless of margin, both in
the main leaderboard and the 2H section (per-tier top, not just the single global #1, since that's
what's actually displayed as "top of this tier"). Verified against a real sweep run: Beast-tamer's
Shoulders' Shoulder group went from 1/5 to 2/5 resolved, with the same #1 ranking (resolving only
tightens the number, doesn't change who's on top - as expected, since the margin check already
guaranteed that).


## 2026-08-23 - Published ledger went blank below "Achieved BiS"; missing build script found and fixed

Republishing the artifact after the fix above broke it: everything past "Achieved BiS" rendered
empty. Root cause - `tiered_report.json`'s "tiers" field is a dict-of-dicts
(`{tier_name: {slot_name: [item_row, ...]}}`, convenient for the text report's nested loop) but
the artifact's JS expects a list (`[{name, slots: [{slot, items, more}]}]`, matching how it
actually iterates and renders). Some earlier session clearly did this transform before embedding
the DATA blob, but only as an inline one-off - never saved anywhere in the repo - so this
session's republish skipped it and spliced the raw dict straight in, which threw a JS exception
partway through rendering.

Fixed properly this time: `core/build_ledger_data.py` does the dict-of-dicts -> list-of-tiers
transform as a real, reusable script (also folds in the sim commit SHA via a live `git rev-parse`
in the submodule, rather than a value hand-copied into the DATA blob each time). Writes
`data/cache/ledger_data.json`, which then gets spliced into the artifact's `const DATA = ...;`
line. Lesson: any one-off transform between a data file and the artifact needs to be a checked-in
script, not an ad-hoc snippet in that turn's Bash call - otherwise the next session has no way to
know it was ever needed.

## 2026-08-23 - Stage 5 (§7): interaction matrix built, real set-bonus artifact caught and labeled

I(i,j) = MV(i,j) - MV(i) - MV(j), computed for real via a genuine joint two-item
sim (core/interaction_matrix.py) - nothing else in this tool evaluates two-item
swaps together. Candidate pool per the user: top 3 real-upgrade candidates per
slot, plus any candidate beyond the top 3 carrying nonzero Hit or Expertise
Rating (stat indices 20/24, confirmed via core/stat_weights.py) - the exact
items whose true value depends on a cap threshold elsewhere in the set, which
is the whole reason this stage exists. Same-slot pairs are skipped UNLESS the
slot is a paired group (ring1/ring2, trinket1/trinket2, mainhand/offhand DW) -
those pairs are real, wearable, and often the most interesting to test.

First real run surfaced something worth recording carefully: 47 of the 50 real
(non-tied) interactions found were not real item synergy at all, but a set-bonus
accounting artifact. She currently sits at Rift Stalker Armor's 4pc breakpoint
(4/5 pieces: Head/Shoulder/Chest/Hands). Swapping any ONE of those slots alone
drops her to 3pc, losing the 4pc bonus - that cost is correctly baked into that
item's own solo MV. Swapping TWO of those slots at once still only drops her to
2pc - the 4pc bonus is lost exactly once either way, not twice - so naively
summing two solo MVs double-counts a cost the joint config only pays once,
producing a phantom "+30 DPS complement" for almost any two candidates that
touch her current 4pc slots, regardless of whether the items have anything real
to do with each other. A second, related case: Rift Stalker Leggings (a slot
she doesn't currently fill with this set) ADDS a piece while another candidate
REMOVES one - together the count nets back to 4, "restoring" a bonus that was
never really in danger from the pair as a unit.

Per the user ("maybe on set items we add a value with 2pc or 4pc"), rather than
filtering these out, each interaction row now carries a set_notes list labeling
the real mechanism using the sim's own actual thresholds (never guessed -
set_bonus.set_bonus_thresholds() reads them from item_sets.go). Two distinct
cases, both correctly detected:
- "lost by either item alone, not lost again together" (the double-counting
  case above)
- "one item's swap alone would lose it, but the other backfills the displaced
  piece" (the Rift Stalker Leggings case)

Both use set-piece BUCKETS (how many thresholds cleared: e.g. for [2,4], a
piece count of 3 and 2 are the SAME bucket, both "only the 2pc tier") rather
than a naive per-threshold >=/< comparison - the first version of this used the
naive comparison and it never fired, because dropping from 4 to 3 and 4 to 2
both read as "no longer >=4," so the "did together cross the SAME way as
alone" signal was structurally unreachable. Verified against real data after
the fix: all 47 set-bonus-driven pairs now carry a note; the 3 genuinely novel
pairs (all trinket substitutes, see below) correctly carry none.

The 3 real findings that survived: Dragonspine Trophy, Tsunami Talisman, and
Madness of the Betrayer are pairwise SUBSTITUTES, not complements to combine.
Verified by hand: Tsunami Talisman is a real downgrade in trinket1 (-5.8 DPS
vs. her current Bloodlust Brooch) and only a real upgrade in trinket2 (+8.6) -
the same slot Dragonspine Trophy also wants (+24.1 there vs only +9.0 in
trinket1). Wearing both forces one into its worse slot, so together (+16.7)
undershoots what summing their solo MVs would suggest (+32.7). A "substitute"
finding is a caution against pairing them, not a recommendation - the ledger's
legend/copy was tightened after this read ambiguously in an early draft.

Also fixed while verifying against a real run: a Windows console encoding
crash - the note text originally used a Unicode arrow character (U+2192),
which isn't in cp1252 (the default Windows console codepage) and crashed
print(). Replaced with ASCII "->" - the same class of bug could hit any
future non-ASCII character added to printed report text on this machine.

A follow-up conversation with the user surfaced two more real problems with
this stage, both fixed the same session:

1. **A real testing bug on my (Claude's) side, not the tool's**: the user
   asked whether Attumen the Huntsman's "Gloves of Dexterous Manipulation"
   (id 28506, real Karazhan epic - 35 Agi/42 AP/42 RAP) should be an upgrade
   once a T6 shoulder swap already breaks Rift Stalker Armor's 4pc bonus. My
   first manual check said no (-32.2 alone, still a small downgrade even
   after the shoulder swap) - wrong, because I built the test candidate with
   enchant=0 instead of her real current hands enchant (id 2564, copied from
   `character.json`). The actual sweep pipeline always copies the current
   slot's enchant onto non-owned candidates (see run_full_sweep_mv.py's
   `default_enchant` logic) - my manual verification script didn't, and that
   alone was worth ~16.5 DPS. With the enchant applied correctly: gloves
   alone = -15.7 (not -32.2), and paired with a T6 shoulder swap, the gloves
   are a REAL +13.4 to +13.9 DPS upgrade (noise ~0.5) - the user's original
   intuition was correct.

   This also surfaced a real STRUCTURAL gap in the interaction matrix, not
   yet fixed: candidate selection only pulls from the tiered report's
   already-filtered "real upgrade" list (top 3 per slot by mv, mv>0 or has a
   set_note). An item like Attumen's Gloves - a real downgrade ALONE purely
   because it breaks a set bonus, but a real upgrade once paired with
   another set-breaking swap - never enters the candidate pool at all, so
   the matrix can never discover this class of finding on its own; it can
   only confirm/deny a specific pairing someone already suspects. Flagged to
   the user, not yet resolved - would mean including "solo downgrade,
   explained by a set-bonus break" items in the pool too, which meaningfully
   grows the pair count beyond the current ~50.

2. **A real, confirmed labeling problem, not just presentation**: calling a
   set-bonus-artifact row "COMPLEMENT" (with a large positive number) reads
   as "pursue this pairing," which is actively wrong for these rows - the
   honest takeaway for e.g. Gronnstalker's Spaulders + Beast Lord Handguards
   is "Beast Lord Handguards is just a bad item, full stop; pairing it with
   Spaulders doesn't change that." Fixed: rows with a set_notes entry now
   get a neutral "artifact" kind instead of complement/substitute, and sort
   AFTER the genuinely novel rows (previously all 50 rows sorted purely by
   |interaction|, which buried the 3 real trinket findings under 47 near-
   identical ~+30 artifact rows at the top of the list).

## 2026-08-23 - Tried an EP cutoff for the interaction matrix pool, reverted - structural conflict

After confirming the active-set-slot full-pool rule was producing a genuinely large
search space (122 candidates -> 7558 pairs, measured, not estimated), tried adding a
crude STAT_WEIGHTS-based EP cutoff for non-set, non-Hit/Expertise candidates in those
slots (keep only if within 70% of the slot's best EP). This is the same prefilter
pattern already used elsewhere in this codebase (sweep_all_loot.py's own candidate
filter, gem_optimizer.py's gem choice) and explicitly sanctioned by the ground rules
as a legitimate prefilter heuristic.

Real verification (comparing against a real external EP reference the user pulled up,
and cross-checking every active-set-slot item's crude score directly) caught something
the ground rules already warned about, seen concretely instead of abstractly this time:
Attumen's "Gloves of Dexterous Manipulation" - id 28506, the exact, already-validated
rescue this whole pool-gap fix exists to catch (+13-14 DPS once paired with a T6
shoulder swap that breaks the same set bonus) - scored crude_ep=154 against a cutoff of
165 (70% of Hands' best, 236). The EP filter would have excluded it.

This isn't a threshold-tuning problem (moving 0.7 to some other fraction). It's a
structural conflict: a "rescue" is by definition an item that looks unremarkable or bad
by any solo-item metric (crude EP, real solo sim MV, doesn't matter which) - that's
what makes it invisible to a naive report in the first place. Any prefilter that scores
candidates by "how good does this look alone" will, by construction, exclude exactly
the items the mechanism is supposed to find. Reverted the EP cutoff entirely.

The correct lever for pool size, confirmed by this investigation: real pair-level
screening (the pre-screen@100 -> screen@1000 -> resolve@30000 funnel), which tests the
actual joint effect instead of a solo proxy, is the only sound way to shrink the search
space for these specific slots. The pre-screen tier's own cost across thousands of real
pairs (measured: ~5946 pairs, roughly 12 minutes just for the cheapest tier) is the
honest, necessary cost of doing this analysis correctly for a genuinely deep,
well-itemized raid tier - not a bug to engineer away with a shortcut.

Also generalized active_set_slot_labels() the same session: was hardcoded to the
classic 5 tier-armor slots (head/shoulder/chest/hands/legs); per the user, Phase 5 has
real sets on boots/belt/wrist too, so hardcoding to 5 slots would silently miss an
active set bonus anywhere else. Now checks every single-occupancy slot dynamically.

## 2026-08-24 - best_four_of_five's Rift Stalker Armor pick cross-validated against Wowhead

The user questioned why the tool picks "leave hands non-tier" (4pc: head/shoulder/
chest/legs) for Rift Stalker Armor, having seen the WoWSims web UI's own PRESET gear
list use only 2pc (head/shoulder tier, chest/hands/legs all non-tier - the chest slot
there is Ranger-General's Chestguard, not a Rift Stalker piece, easy to misread at a
glance). Verified directly: real 30k-resolved DPS for the actual leave-one-out options
(all via `set_bonus.best_four_of_five`'s own `all_options` field) -

- leave hands non-tier (the tool's pick): 2709.1
- leave shoulder non-tier: 2706.8 (close second)
- leave legs non-tier: 2688.0
- full 5pc: 2672.1
- leave chest non-tier: 2645.9 (worst)
- 3pc (both hands AND legs non-tier, matching the wowsims preset): 2695.85 - real,
  computed on demand (not part of best_four_of_five's normal leave-ONE-out search,
  which only ever compares 4-of-5 combos against the full 5, never 3-of-5 or fewer)

The 3pc preset combo is real but ~13.3 DPS worse than the tool's 4pc pick - matches
what the user found hand-testing "chest and gloves" themselves, AND matches Wowhead's
separately-written guide (which recommends keeping Legs as tier and using a non-tier
glove instead - the exact same combo, reached independently). The wowsims preset
turned out to be a generic, non-optimized default, not a competing recommendation -
good real-world validation that best_four_of_five's search is trustworthy.

Real, not-yet-resolved gap flagged by the user in the same conversation: gem choice
for `best_non_set_alt`'s picks is decided per-item independently (crude EP score
only), with no awareness of whether the resulting sockets across the WHOLE build
jointly satisfy the meta gem's color requirement - "I struggle to activate my meta
gem with useful gem bonuses when going for that." The sim itself correctly reflects
whatever the real activation state ends up being (a real mechanic, not something our
Python code approximates), but a smarter, JOINTLY-optimized gem choice across the
whole build could plausibly push the winning combo's DPS even higher than what's
currently found. Not investigated yet - next real step if this becomes a priority is
confirming whether the meta gem is actually active in the current winning ("leave
hands non-tier") combo before deciding whether joint gem optimization is worth
building.

## 2026-08-24 - Overnight: 4-week gearing progression + runtime optimization pass

Two standing overnight tasks, run autonomously while the user slept (explicit
instruction: keep going until told to stop or the 9:00 window closes).

**4-week gearing progression** (`E:\Claude\Temp\Gearing-Tool\weekly_progression.py`,
not committed - a scratch driver, not a permanent core/ tool yet): simulates a fresh
level-70's gearing path starting from a deliberately WORSE baseline - the item list
from a pasted wowsims "Pre-Raid BiS" reference build (17 items only; race/professions/
talents stay Lerynia's real Nightelf/Herbalism-Mining identity throughout, per the
user's explicit choice). Each week: swap `data/character.json`'s `equipped.items` to
that week's gear, run the real unmodified `core/run_full_sweep_mv.py`, find the single
highest real (non-tied) MV upgrade across the whole tiered report (rescue_mv when
flagged, else mv - same selection rule the ledger itself uses), "acquire" it with its
real enchant/gems via `opt.load_candidates()`, repeat. **Safety**: `character.json` is
backed up once at the very start and restored in a `finally` block no matter what -
verified this actually fires correctly on a real early failure (see below), so a crash
mid-run doesn't leave her real file in a modified state.

Real bug caught before the real run: the pasted reference build's raw items (id/
enchant/gems only) don't carry the `"name"` field real `character.json` entries always
have - `optimizer.load_candidates()` indexes owned items by name and crashed with
`KeyError: 'name'` on the very first week. Fixed by resolving each id's name via
`item_db.by_id()` before writing week-0 gear (and again for each week's newly-acquired
item, same reason).

**Runtime optimization pass** - investigated the standing `project-bridge-exe-overhead`
memory's claim (fresh `bridge.exe` spawn costing ~0.3s/call) directly rather than
trusting it, since a good chunk of tonight's time budget was explicitly for this.
**The claim was wrong** - real instrumented breakdown of `valuation.evaluate()`
(config_hash / load_template / apply_imbues / fingerprint / sim_cache.get / build_
raid_sim_request / pool.run / player_and_pet_dps, timed separately):
- `bridge.exe` itself: ~0.022s/call in isolation (8 calls, tight variance) - cheap,
  not the bottleneck. Memory file corrected in place rather than left stale.
- `_load_template()`'s per-call deep copy (JSON round-trip, not `copy.deepcopy` -
  actually FASTER for this dict: 0.58ms vs 1.19ms/call, measured, so left as-is)
  is negligible either way.
- `sim_cache.get()`/`put()` were doing a full-file `json.load()`/full-file
  `json.dump()` on EVERY call, including cache HITS - real, unnecessary disk I/O
  (only ~5-20ms at today's ~1782-entry/450KB cache, but grows without bound as the
  cache accumulates across sweeps, and this session's overnight run + every future
  sweep only adds to it). **Fixed**: `core/sim_cache.py` now keeps one in-memory
  copy per process (safe - `run_full_sweep_mv.py`'s worker pool is
  `ThreadPoolExecutor`, same process/module, already guarded by the existing
  `threading.Lock`), loaded once lazily, still write-through to disk on every
  `put()` (same crash-safety/cross-process visibility as before - a concurrent
  second process's own new writes just aren't visible to this process's copy until
  restart, which costs a missed cache-hit, never a wrong answer). Verified correct
  with an isolated round-trip test against a throwaway cache file before trusting
  it (get-miss, put, get-hit, disk-matches, fresh-process-reload-matches - all
  passed) - deliberately NOT tested against the real `sim_cache.json` while the
  overnight progression was actively using it.
- Re-confirmed `MAX_WORKERS=2`/`SIMSERVER_POOL_SIZE=2` (the documented fix for the
  6C/12T Ryzen 5 5600X's "747ms/call at (4,4) vs 101ms/call at (2,2), 7.4x slower
  from oversubscription" finding, already in place from earlier this session) is
  still the active, correct setting - `core/optimizer.py`'s own separate
  `MAX_WORKERS=4` ThreadPoolExecutor functions (`greedy_sweep`, `trinket_pairs`,
  `set_bonus_branch`, `ranged_exhaustive`) are dead code relative to the CURRENT
  pipeline - confirmed `run_full_sweep_mv.py` never calls any of them (grep, zero
  matches) - they're leftover from the superseded Stage 4 greedy-sweep approach,
  only reachable via the old `core/run_optimizer.py` entry point. Not a live risk,
  left untouched.
- Isolated `pool.run()` timing (warm pool, single process, no competing load)
  showed genuinely near-linear scaling with iteration count (1 iter ~0.02-0.03s,
  1000 iter ~0.15-0.22s, 30000 iter ~5.1-5.2s) - real Monte Carlo compute time, not
  hidden fixed overhead. A separate same-process test run WHILE the overnight
  progression's sweep subprocess was also active showed much noisier, higher
  numbers (0.14-0.35s at 1000 iter) - almost certainly the same oversubscription
  effect above, self-inflicted by running a competing foreground test during an
  active sweep (exactly the confound this file already warned about once before -
  stopped running more competing sim calls once recognized, rather than chasing a
  second false lead).

**Not attempted tonight, on purpose**: Stage 7's real decomposition idea (avoid a
full re-screen when only one slot's gear actually changed) is the one lever that
would have mattered most FOR THIS SPECIFIC overnight task specifically - each week's
`sim_cache` key hashes the FULL 17-slot config, so a one-slot gear change this week
means next week's screen/resolve passes get essentially zero cache reuse from this
week's run, even for candidates in completely unrelated slots. Confirmed real by
watching it happen live across the progression's weeks, not just theorized. Left
alone deliberately - it's a genuine architecture change (already scoped as its own
priority stage in CLAUDE.md), not something to redesign unsupervised overnight while
the user was asleep and unable to review the direction, per this file's own "work in
stages, stop at checkpoints" rule.

**Correction to the above, found by actually reading this file's own history before
more testing**: my own "isolated pool.run() timing" experiment earlier tonight was a
mistake I didn't catch until writing it up - it called `simserver_client.get_pool()`/
`pool.run()` DIRECTLY, bypassing the `USE_SIMSERVER` flag entirely. `USE_SIMSERVER=
False` is the current, deliberate, hard-won production state (see this file's own
earlier `simserver.exe` crash investigation - hangs at exactly request #34 of
`RunRaidSimConcurrentAsync`, root cause not found, explicitly flagged there as "not
something to guess at blind"). I was unknowingly exercising that same known-buggy
path in my "safe" investigation - got lucky (well under 34 calls), but it was a real
risk taken unknowingly, because I hadn't read this file's history first. The REAL
active path when `USE_SIMSERVER=False` is `adapter.run()` - a fresh `wowsimcli.exe`
per call, which per this file's own much earlier entry "reloads and unmarshals the
whole embedded item DB (~2.3MB protobuf) fresh on every invocation" - almost
certainly the real, correctly-identified-in-spirit-but-wrong-subprocess source of the
original `bridge.exe` memory's ~0.3s/call finding. Have NOT re-measured `adapter.run()`
directly tonight - the honest next step for a real fixed-cost win is there, not
simserver.exe (stays off until the #34 crash is Go-level root-caused).

**Lesson for future overnight cycles, including future me**: read this file's own
recent history before re-investigating something that sounds unclaimed - "no code
changes this cycle" a few entries up was there for a reason, and a plausible-sounding
independent finding can just be re-discovering (or in this case, accidentally
bypassing) a decision that already cost real effort to reach.

**User guidance, received mid-run, for the NEXT optimization cycle (not acted on
tonight - correctness-risking pipeline changes don't get made unsupervised
overnight)**:
1. Lowering `RESOLVE_ITERATIONS` from 30k to 5k is still explicitly on the table per
   the user, possibly paired with an additional cheap "elimination phase" (a low-
   iteration pre-filter before the expensive pass) - revisits the already-reverted 5k
   experiment above and the 4-tier funnel idea (pre-screen/screen/confirm@5k/
   resolve@30k) already sketched in CLAUDE.md's idea-collection section. Right shape
   is probably an ADDITIVE opt-in confirm-tier, not silently replacing 30k as the
   reported number again - noise-honesty still applies.
2. "Build a memory for the sim, not just a cache" - a different architecture than
   today's flat gear-hash-keyed `sim_cache.json`, closer in spirit to Stage 7's
   already-scoped decomposition idea. Not scoped yet - needs real design discussion
   with the user, not an overnight guess.

**Real bug found and fixed mid-run, overnight**: the first progression attempt
crashed at week 3 with `ValueError: item_id 32235 not found in candidate pool for
slots ['head']`. Root cause: the driver's acquisition step only knew about the
curated 71-item pool (`opt.load_candidates()`), but the tiered report it reads
winners FROM also includes ~500 additional full-DB-sweep candidates
(`data/cache/full_sweep_candidates.json`, merged in by `run_full_sweep_mv.py`'s own
`main()`) - weeks 1-2's winners (Claw of the Phoenix, Bristleblitz Striker) happened
to be in the curated pool, week 3's winner (Cursed Vision of Sargeras, a real T6
Black Temple head drop) wasn't. Fixed by replicating the exact same curated+sweep
merge logic (`load_full_candidate_pool()` in the driver script, mirroring
`run_full_sweep_mv.py` lines ~177-243) rather than guessing at a narrower patch.
Resumed from the known-good week 1-2 state (replayed, not recomputed) rather than
restarting from week 0 - saved ~27 minutes of already-correct compute. **Result: all
4 weeks completed successfully** - Claw of the Phoenix -> offhand (+96.9), Bristleblitz
Striker -> ranged (+74.2), Cursed Vision of Sargeras -> head (+66.7), Bow-stitched
Leggings -> legs (+62.0). Real `character.json` verified restored correctly afterward
(head back to Rift Stalker Helm, offhand back to Blade of the Unrequited - her real
gear, not the trial progression's).

**Runtime investigation, continued after the progression finished (exclusive machine
access, no more competing load)** - cleanly re-measured the REAL active path
(`adapter.run()`, confirmed `USE_SIMSERVER=False`) this time:
- `wowsimcli.exe --help` (bare process spawn + Go runtime init, zero DB/sim work):
  ~0.075-0.085s, tight across 5 calls.
- A real 1-iteration sim call via `adapter.run()`: ~0.165s.
- So process-spawn/Go-startup and DB-load-plus-sim-setup are roughly EQUAL
  contributors (~0.08s each) to the ~0.16s/call floor - refines the earlier "DB
  reload dominates" hypothesis (an even earlier NOTES.md entry) to "roughly 50/50."
  At ~500-700 screening calls per sweep, that floor alone is ~80-115s of a run's
  total time.
- Read (not modified) `sim_concurrent.go` and the `simsignals` package directly,
  hunting for a fixed-size resource near the documented "#34 crash" threshold -
  found nothing obvious in either (a plain Go map + mutex in `simsignals`, no
  fixed-capacity anything in `runSimConcurrent`'s own channel/goroutine setup
  beyond `threads = runtime.NumCPU()` = 12, nowhere near 32-34). The actual resource
  exhausted is somewhere deeper, still not found.
- **Conclusion: the ~0.16s/call floor is real and not fixable without a persistent
  process** (both halves are one-shot-CLI-inherent) - `simserver.exe` already exists
  and already solves this (measured ~30% faster end-to-end when it worked, an
  earlier entry above), it's just disabled by the unresolved #34-crash bug. That bug
  is the actual highest-value remaining lever, but fixing it needs real Go-level
  debugging (goroutine dump via SIGQUIT, or profiling deeper into `RunSim`'s
  internals) by a session with the time AND the user's presence to cross-verify
  correctness against wowsims.com - not another blind attempt. Deliberately stopped
  the investigation here rather than guessing at a fix in vendored, DPS-correctness-
  critical concurrent Go code unsupervised.

## 2026-08-24 (morning, with the user) - progress-percentage logging + confirm@5k tier

Two real features built and validated this morning, with the user awake to review
(unlike the overnight work above, which deliberately stayed conservative).

**Progress-percentage logging** (`run_with_progress()` in `run_full_sweep_mv.py`):
every concurrent pass (screening, confirming, resolving, raid-AP lookups, 2H
screening) now prints "Label: done/total (pct%)" at ~5% intervals via
`as_completed()` instead of a blocking `ThreadPoolExecutor.map()`. Order of
results is completion order, not submission order - verified both call sites only
ever build a dict/set from the results (order-independent) before making the
change. Unit-tested standalone (37 dummy items, concurrent, results verified
complete and correct) before trusting it in the real pipeline. Real precursor to
the GUI progress indicator already noted in this file's future-scope section.

**Confirm@5k tier, added between the existing screen(1k) and resolve(30k) passes**:
every leaderboard candidate (`to_resolve`) now gets a cheap 5k confirm pass first;
only items still borderline at 5k (by `CONFIRM_CLEAR_MARGIN_MULTIPLE`, see below),
plus the #1 pick per (tier,slot) (always full precision, unchanged existing
policy), escalate to the real 30k pass. Every report row gets a `resolve_iterations`
field so the shown number's actual precision is always disclosed ("(confirmed
@5000)" vs full vs "(screened only)") - noise-honesty via disclosure, not by
pretending 5k is 30k-precise.

**Real timing, three clean/uncached full sweeps against her real current gear,
same seed, same day**:
| version | time | notes |
|---|---|---|
| baseline (sim_cache in-memory fix only, no confirm tier) | 928.8s (15.5 min) | this morning's first clean run, already down from last night's ~1064s baseline |
| confirm@5k added, still using the reused 8x margin | 853.0s (14.2 min) | 36/140 leaderboard items skipped 30k |
| confirm@5k, tuned margin (see below) | pending - about to re-run | |

**The 8x margin (reused from `mv.CLEAR_MARGIN_MULTIPLE`, calibrated for the 1k
screen -> 30k jump) was too conservative for the 5k confirm tier specifically** -
the user caught this directly ("seems to be tuned very harsh") before I'd even
finished reporting the first confirm-tier timing. Real reasoning: 8x was sized for
1k's noise, which is ~5.5x worse than 30k's; 5k's noise is only ~2.45x worse than
30k's, so the SAME multiplier applied to the tighter 5k noise produces a much
higher absolute DPS bar than necessary (~11-12 DPS here, vs the on-file A/B
evidence that 5k already reliably matches 30k down to ~7 DPS).

**Empirically re-tuned rather than guessed**: wrote a one-off analysis script
(`E:\Claude\Temp\Gearing-Tool\tune_confirm_multiplier.py`) that reconstructs the
same `to_resolve` leaderboard the real pipeline built and pulls BOTH the confirm@5k
and resolve@30k value for all 140 candidates from that morning's real run (mostly
cache hits - a real, if imperfect, near-free reuse of already-spent compute; ~14
items came back as cache misses for reasons not yet root-caused, flagged but not
blocking since the resulting decision-count cross-check against the real run's
"104/140 escalated" figure landed close enough (~105) to trust the paired data).
Swept `CONFIRM_CLEAR_MARGIN_MULTIPLE` from 2 (the tied-within-noise boundary itself)
to 8 (the old reused value) against this real data:

| multiplier | non-top items skipping 30k (of 60) | worst-case drift among skipped |
|---|---|---|
| 8 (old) | 35 | 1.37 DPS |
| 5 | 46 | 1.37 DPS |
| **3 (chosen)** | **48** | **1.37 DPS** |
| 2 (tie boundary) | 51 | 1.37 DPS |

**Zero sign flips or verdict changes among skipped items at ANY tested multiplier**
- the only 3 real 5k/30k sign disagreements in the whole 140-item set (Swiftstrike
Bracers, Shadow-walker's Cord, Gronnstalker's Leggings) all had ratio (|mv5k|/
noise5k) between 0.19 and 0.79 - nowhere near even the loosest 2x threshold, and
both tiers already correctly flagged them "tied within noise" regardless of which
number gets shown. The drift ceiling among skipped items stays flat at 1.37 DPS
across the whole 2-8 range - loosening the multiplier doesn't trade safety for
speed here, it just reclaims efficiency 8x was leaving unused. Set
`CONFIRM_CLEAR_MARGIN_MULTIPLE = 3` - a full step above the 2x tie-check boundary
(so a "confirmed" item is never just barely outside "tied"), not the theoretical
minimum-risk value, as a deliberate small safety margin beyond what this one
dataset alone would strictly justify.

**Real structural ceiling on how much this tier can help, worth being honest
about**: of the 140 leaderboard candidates, 80 were #1 picks per (tier,slot) -
these ALWAYS escalate to 30k regardless of multiplier tuning (existing, unchanged
policy). The confirm tier's savings are bounded by the ~60 non-#1 items, not the
full 140 - the real ceiling on this lever is the number of (tier,slot) buckets a
sweep produces, not the margin multiplier.

**Final clean/uncached timing, tuned margin (3x), same real gear/seed as the two
runs above**: 782.5s (13.1 min) - 51/140 leaderboard candidates confirmed @5k
already clear (vs 36/140 at the old reused 8x margin). Three-run progression today:
928.8s (sim_cache fix only) -> 853.0s (confirm tier, 8x margin) -> 782.5s (confirm
tier, tuned 3x margin) - a 15.8% reduction from this morning's own baseline, ~26%
from last night's original ~1063.8s.

**SCREEN_ITERATIONS lowered 1000 -> 500, also empirically validated before
changing it** - the user invited trying a 5th tier; investigated whether a cheap
prescreen pass would help first and concluded it wouldn't (see below), so tested
lowering the existing screen pass instead. Screened the full real ~650-candidate
pool at BOTH 500 and 1000 iterations and compared every (tier,slot) bucket's
**top-8 SET**, not just per-item mv agreement (the actual decision this constant
drives - which items even reach the confirm/resolve tiers at all, a categorically
different risk than the confirm-tier's "how precise" decision). 77/80 buckets
matched exactly. The 3 that didn't were all old-content/vanilla-carryover weapon
buckets (Frostguard, Annihilator, Heartstriker, etc.) where every swapped item sat
at mv ~= -61.3 DPS - deep downgrades clustered within a fraction of a DPS of each
other, nowhere near a real upgrade, reordering noise among items that could never
surface in the report regardless. Safe to lower.

**Real per-call cost precisely measured across the iteration range this decision
spans** (single process, exclusive machine): 100->0.204s, 250->0.219s, 500->0.249s,
1000->0.305s, 2000->0.415s. Confirms the fixed per-call floor (~0.19-0.20s) already
found the previous night dominates even at 1000 iterations - only about a third of
the 1000-iter cost is real iteration-dependent compute. This directly explains (and
quantifies, rather than just re-confirms) an EARLIER session's finding already on
file in this document ("prescreen at 10... i don't think this is faster"):
**recommended against building a prescreen tier** - for an extra low-iteration pass
over all ~650 candidates to pay for itself against the floor, it would need to
filter the pool by more than 3x before the real screen pass even starts, and unlike
every other change made today, a prescreen tier could silently DROP a real upgrade
from consideration based on a noisy low-iteration estimate rather than just report
it less precisely - a categorically different, higher-stakes kind of risk. Declined
to build it for concrete, quantified reasons instead of just citing the old result.

**Final clean/uncached timing, all changes stacked**: 772.7s (12.9 min) - down
from 782.5s (confirm tier alone). Full progression today: 1063.8s (original) ->
928.8s (sim_cache fix) -> 853.0s (confirm@5k, 8x) -> 782.5s (confirm@5k, tuned 3x)
-> **772.7s (+ SCREEN_ITERATIONS 500)** - a 27.4% reduction overall, every step
validated against real ground truth before being kept, none of it guessed.

**Dropped the "#1 pick always gets 30k" special case, and removed the visible
per-item precision-tier flag** - the user asked to squeeze the resolve count
toward 60 or below. Real structural finding first: this run has 80 distinct
(tier,slot) buckets, and the #1 item in EVERY bucket was unconditionally
escalating to 30k regardless of margin (an explicit policy from earlier in this
project - "if a screened item ends up on top, actually sim it"). That's a hard
floor of 80 resolve calls on its own - no amount of margin tuning could ever get
below it. Tightening `CONFIRM_CLEAR_MARGIN_MULTIPLE` toward the 2x tie boundary
only found 9-12 more non-#1 items to spare (89 -> ~89 across the whole 2-8
range) - the real lever was the #1-always-escalates rule itself.

Presented this tradeoff plainly rather than silently overriding an explicit past
decision: applying the SAME margin check to #1 picks (dropping the special case)
would cut resolve count to ~15-20, but meant most #1 recommendations would show
as "(confirmed @5k)" instead of a full 30k number. The user's actual answer
clarified the REAL constraint wasn't the precision tier itself, it was "no
visible flag that could make the user unsure about the sim... no need to flag the
item if you are sure 5k and 30k are almost the same." That reframes the problem
entirely: noise-honesty via disclosure was never required to mean "show the
implementation detail of which pass produced a number" - it means "don't hide
real uncertainty." An item that clears `CONFIRM_CLEAR_MARGIN_MULTIPLE` has
ALREADY been verified (empirically, this session) to carry no more real
uncertainty than a 30k number would - the flag was disclosing an implementation
detail, not a real risk.

**Validated the #1-pick group specifically before making the change** (same
rigor as every other change today, not assumed to transfer from the non-#1
validation): pulled real 5k-vs-30k pairs for all 80 #1-pick items from the
just-completed real run. Zero sign flips, max drift 1.38 DPS - identical safety
margin to the non-#1 group (1.37 DPS). Confirmed safe to extend.

**Two changes made together**: (1) the escalation decision (`need_full_resolve`
in `run_full_sweep_mv.py`) now applies `CONFIRM_CLEAR_MARGIN_MULTIPLE` uniformly
to every `to_resolve` item, #1 picks included - no more automatic escalation. (2)
The per-item display flag now only distinguishes "resolved" (confirmed @5k OR
resolved @30k, shown identically) from "(screened only)" (never passed ANY
confirm-precision check - this is real, undisclosed-otherwise uncertainty, so it
still gets flagged). `resolve_iterations` stays in the underlying tiered_report
JSON for anyone who wants the detail; it's just not surfaced in the printed
report anymore.

**Final clean/uncached timing, all changes stacked**: 515.1s (8.6 min) - 19/163
leaderboard candidates needed the full 30k pass (144 confirmed @5k), down from
89/163 before this change. Full progression today: 1063.8s (original) -> 928.8s
(sim_cache) -> 853.0s (confirm@5k, 8x) -> 782.5s (confirm@5k, tuned 3x) -> 772.7s
(+ SCREEN_ITERATIONS 500) -> **515.1s (+ uniform margin, no visible flag)** - a
**51.6% reduction overall**. Every step validated against real 30k ground truth
before being kept; zero verdict changes found anywhere across the whole session.

## 2026-08-24 (with the user) - simserver.exe's "#34 crash" ROOT CAUSE FOUND AND FIXED

The user asked directly whether I wanted to work on the simserver.exe crash next, now
present to cross-check correctness (the precondition I'd set for even attempting this
- see the earlier overnight entries' repeated "not something to guess at blind"
caution). Took it on properly this time instead of more source-reading.

**Real diagnostic approach, not more guessing**: reproduced the hang directly (bypassing
the Python wrapper entirely - raw stdin/stdout to `simserver.exe`), confirmed it stalls
at exactly call #33/34 as previously documented, and confirmed via `tasklist` the
process was genuinely STUCK (alive, using memory) not crashed. First attempt at a live
diagnostic - `CTRL_BREAK_EVENT` via `GenerateConsoleCtrlEvent` - just force-killed it
(exit code `0xC000013A` = `STATUS_CONTROL_C_EXIT`, Windows' default handler, no dump).
Root cause of THAT: `syscall.SIGBREAK` doesn't exist in Go's standard `syscall` package
(`go doc` confirmed) - the real API is `signal.Notify(ch, os.Interrupt)`, which Go
documents as catching BOTH ^C and ^BREAK on Windows. Added a small, purely diagnostic,
zero-risk handler to `simserver/main.go` (`installDiagnosticDumpHandler()` - a few
lines, does not touch `runOne`/`RunRaidSimConcurrentAsync`/anything simulation-related)
that dumps all goroutine stacks to a file on this signal instead of letting Windows
kill the process blind. Rebuilt, smoke-tested for correctness first (real DPS number,
sane range), then reproduced the hang again and sent the break signal.

**Got a real, conclusive goroutine dump this time.** The stuck goroutine
(`goroutine 329`) was NOT anywhere in simulation logic at all - it was blocked inside
Go's own `log.Printf` -> `syscall.WriteFile`, at `sim_concurrent.go:528` (the "All %d
sims finished successfully." line), stuck in Windows' I/O completion port machinery
trying to WRITE a log line to stderr. **This was never a resource exhaustion in the sim
engine** - it's a **stderr pipe-buffer deadlock**: `simserver_client.py`'s
`SimServerProcess` only ever read `stdout`; nothing drained `stderr` after the startup
"ready" line. `simserver.exe` logs 2 lines per call ("Running N iterations...", "All N
sims finished successfully.") via Go's `log` package - once ~33 calls' worth of log
lines filled the small Windows anonymous pipe buffer, the child process blocked forever
inside its own blocking write, waiting for buffer space nothing was ever going to free.
This exactly explains the deterministic "always exactly #34" symptom that three
previous overnight sessions investigated and left unresolved (checked
`sim_concurrent.go`'s own channel/goroutine setup and the `simsignals` package for a
fixed-size resource near 32-34 and found nothing there either - now clear why: the bug
was never in either of those files, it was in the Python side never reading a pipe).

**Real fix, Python-only, zero Go-engine risk**: `simserver_client.py`'s
`SimServerProcess` now starts a daemon thread on construction that continuously drains
`stderr` into a bounded (`maxlen=200`) `collections.deque` for the process's whole
lifetime, so the pipe never fills. Error reporting (`run()`'s "process died?" path) now
reads from that buffered tail instead of calling `.read()` directly on the stream
(avoids a race with the draining thread). The diagnostic signal handler stays in
`simserver/main.go` too - harmless, and useful if anything like this ever recurs.

**Verified thoroughly before trusting it, given the stakes of re-enabling a path that
feeds every reported DPS number**:
- 150 sequential calls via the real `SimServerProcess` class (not the raw stdin/stdout
  test) - sailed straight through the old #34 hang point to completion, no errors.
- **Correctness cross-check**: same seed, same config, simserver path vs the
  proven-reliable file-based `adapter.run()` path - DPS matched to 4 decimal places
  (2249.0420 both times).
- **200 concurrent, mixed-iteration (500/5000/30000) calls** through the real
  production `SimServerPool` + `ThreadPoolExecutor` pattern (matching
  `run_full_sweep_mv.py`'s actual usage) - 0 errors, 269.1s.
- **A full real clean/uncached sweep** with `USE_SIMSERVER` flipped back to `True` -
  completed cleanly, same resolve/confirm counts as the immediately-prior
  simserver-disabled run (19/163 resolved, 144 confirmed @5k - deterministic, matches
  exactly), and **all 53 displayed DPS values in the report matched the
  simserver-disabled run's report exactly**, item for item (same seed => deterministic
  regardless of which sim path computed it) - zero correctness impact, confirmed at
  full production scale, not just synthetic stress-test scale.

**`USE_SIMSERVER` flipped back to `True`** in `adapters/tbc/valuation.py`, with the
full root-cause writeup replacing the old "reverted, not root-caused" comment.

**Final clean/uncached timing, simserver re-enabled on top of everything else today**:
418.0s (7.0 min) - down from 515.1s. Full progression today: 1063.8s (original) ->
928.8s (sim_cache) -> 853.0s (confirm@5k, 8x) -> 782.5s (confirm@5k, tuned 3x) ->
772.7s (+ SCREEN_ITERATIONS 500) -> 515.1s (+ uniform margin, no visible flag) ->
**418.0s (+ simserver re-enabled)** - a **60.7% reduction overall**, essentially
two-thirds of the original runtime. Every single change validated against real ground
truth or exact cross-checks before being kept; zero verdict changes and zero
correctness regressions found anywhere across the entire session.

## 2026-08-24 (user driving, ~20 min window) - phase breakdown + a real negative result

Added `[+Ns]` elapsed-time markers at each phase boundary in `run_full_sweep_mv.py`
(cheap, permanent, real precursor to the GUI progress feature) and re-ran clean to see
where time goes now that simserver.exe actually works. Real breakdown (427s total):
Screening 71.0s (17%), **Confirming 135.8s (32%, the new biggest phase)**, Resolving
91.8s (21%), **Rescue check 83.9s (20%)**, 2H analysis 44.5s (10%).

**Found rescue check running fully sequentially** - a plain `for` loop, never
converted to the `run_with_progress` pattern every other pass in this file already
uses. Parallelized it (and the small 2H-resolve loop alongside it) - mechanically
safe, same proven helper, no new logic.

**Real result: no measurable speedup (83.9s -> 91.8s, statistically flat/slightly
worse), despite the code genuinely running concurrently** (confirmed via real
progress-percentage output, not just trusting the diff). Worth understanding why
rather than quietly reverting: a single 30k-iteration sim call already uses all 12
logical threads internally (`runtime.NumCPU()`, same "Running N iterations on 12
concurrent sims" line seen everywhere else). Running 2 such calls concurrently via
an OUTER `ThreadPoolExecutor(max_workers=2)` doesn't add throughput - both calls
split the same 12 real threads, so 2 "concurrent" expensive calls run at roughly
half speed each, netting out close to the sequential total. This is the SAME
oversubscription effect the `(4,4) -> 747ms vs (2,2) -> 101ms` finding from earlier
in this file already established, just showing up at the individual-call level
instead of the pool-size level: outer concurrency only pays off when the work items
themselves are cheap enough that the per-call fixed floor (not raw CPU) dominates
(screening/confirming - many calls, each already using less than the full CPU
budget relative to its own cost) - it does NOT pay off for a small number of
already-maximally-parallel expensive calls (resolve/rescue-check).

**Kept the parallelization anyway** - correctness verified unchanged (zero diff
across all 53 displayed values vs the pre-change run), and it's not a regression,
just a wash on wall-clock time. The real, durable value is the progress-percentage
output every other pass already gets (a real GUI-relevant improvement even without
a speed win) and code consistency (one pattern for every concurrent pass in this
file, not almost-every). Documented here so a future session doesn't re-attempt
"parallelize the expensive passes more" as if it were untested - it's a genuine,
now-confirmed negative result for this specific class of change, not an oversight.

**Real remaining levers, not attempted this session (time-boxed to a ~20 minute
window, flagged as suggestions rather than rushed)**:
- Confirming (135.8s, now the single biggest phase) processes 163 items at 5000
  iterations each - real compute, not obviously wasteful, but CONFIRM_ITERATIONS
  itself was never re-tuned against the NEW (much cheaper) per-call cost profile
  simserver provides. Worth a proper empirical pass (same methodology as today's
  margin tuning - real paired data against 30k ground truth) to see if a lower
  confirm-tier iteration count is now safe and worth it, given the per-call floor
  that justified 5000 as a reasonable middle ground has partly changed shape.
- The SCREEN-level `CLEAR_MARGIN_MULTIPLE` (still 8x, gates entry into `to_resolve`
  at all - a categorically different, higher-stakes decision than the confirm-tier
  margin) was never revisited even though `SCREEN_ITERATIONS` dropping to 500 changed
  its noise floor the same way it changed the confirm-tier's. Not touched today on
  purpose - this one risks silently dropping a real candidate from consideration
  entirely, not just showing it at lower precision, so it deserves the same careful,
  supervised empirical validation as everything else, not a rushed pass.
- `SIMSERVER_POOL_SIZE`/`MAX_WORKERS` retested today at (2,3,4,6) with the FIXED
  simserver - much flatter curve than the old (4,4)-vs-(2,2) finding (139.8-148.7ms/
  call across the whole range), suggesting some of that earlier 7.4x oversubscription
  measurement may itself have been confounded by the (now-fixed) stderr pipe-deadlock
  bug. (2,2) still looks like a fine, safe choice - no action taken, just flagged as
  worth knowing the old number may not be as solid as it looked.

## 2026-08-24 (continued) - screen-level margin tuning: tried it, real regression, reverted

Followed up on suggestion #2 from the list above (the screen-level `CLEAR_MARGIN_MULTIPLE`,
still 8x, gates entry into `to_resolve` at all). Real, careful validation first: 296
leaderboard-eligible items total, 134 excluded (screened-only) at the current 8x. Pulled
real 30k ground truth for all 56 items in the ratio-3-to-8 band (the ones a lower
multiplier would newly exclude) - zero sign flips, and the only 2 real upgrades in that
band (the ones where precision actually matters for what's shown) agreed to within
0.3-0.9 DPS. The margin choice itself was genuinely validated safe.

**Found and closed a real correctness gap while doing this**: rescue-check only ever
looks at items already in `to_resolve` - excluding more candidates via a lower margin
would silently stop checking some of them for rescue potential (the exact "Attumen's
Gloves" scenario the whole rescue mechanism exists for). Added a safety net: any real
downgrade in a currently-active set-bonus slot always enters `to_resolve` regardless of
margin, so rescue-check coverage can never regress no matter how the general margin is
tuned.

**Real result: a 97s net REGRESSION (430s -> 527s), despite every individual piece being
individually correct.** The margin lowering itself worked (confirm phase: 163 items/
135.8s -> 157 items/119.5s, ~16s saved). But the safety net, doing exactly what it was
built to do, surfaced far more real active-set-slot downgrades than the OLD (accidental)
limiting via the 8x margin had ever exposed the rescue-check pass to: 55 candidates
instead of 23. `rescue_check()` is 2 real 30k calls per candidate - that phase alone went
from 91.8s to 204.3s, swamping the confirm-phase savings several times over. **Reverted
both changes together** rather than keep a net-negative result - `SCREEN_CLEAR_MARGIN_
MULTIPLE` and the safety-net logic are gone, `to_resolve` is back to the original
`mv.CLEAR_MARGIN_MULTIPLE=8`-only decision. Verified the revert restores the known-good
~430s timing before considering this closed.

**Real lesson, worth remembering before anyone re-touches this area**: the OLD 8x margin
was accidentally doing double duty - as a screening-precision gate AND as an implicit cap
on how much work the rescue-check pass could ever be asked to do. Decoupling those two
purposes (which is the objectively "more correct" design) exposed a real cost that had
been invisible specifically because the coverage gap was quietly limiting rescue-check's
own workload. A future attempt at closing this gap should scope the safety net much more
narrowly - e.g. only the single least-bad real downgrade per active-set slot (matching
`best_non_set_alt`'s existing "one alternative per slot" pattern elsewhere in
`set_bonus.py`) rather than every leaderboard-ranked downgrade in that slot - not attempted
this session, flagged for whoever picks this up next.

## 2026-08-24 (continued) - real ledger bug: Beast Lord Armor showing as "upgrades"

User caught this looking at the published ledger: Beast Lord Armor pieces (Helm -50.4,
Mantle -36.8, Cuirass -72.9, Handguards -35.7, Leggings -60.4 - all clear, deep
downgrades vs. her real Rift Stalker gear) were showing up in the "upgrades" list for
several slots. Real root cause, not a display bug: the `upgrades` filter in
`run_full_sweep_mv.py` was `(not tied and mv > 0) or set_note or rescue_note` - ANY item
carrying a `set_note` got included regardless of its own mv sign. `set_note` itself gets
attached to every piece of a set the moment that set has ANY real (non-tied) bonus
threshold ANYWHERE (checked via `isolate_bonus_value`, which only asks "is this bonus
real in isolation," never "is this set worth switching to at all"). Beast Lord Armor's
4pc bonus (+73.4) IS real in isolation - so every Beast Lord piece got the note and
therefore got shown, even though her actual Rift Stalker Armor already strictly beats
every Beast Lord combination (`best_four_of_five` was already printing "full 5pc is
-54.6 vs this" for Beast Lord, right there in the log, just never checked against
anything).

**This was never really about Beast Lord Armor specifically - it's a general gap**: the
set_note mechanism was designed for the real, validated Gronnstalker's-style case (an
individual piece looks bad alone, but the FULL transition to that set is genuinely worth
considering) - but it never checked whether the full transition actually clears the bar
of "better than what she has now" before deciding to flag every piece of that set.
Any tracked set with a real bonus, however unrelated to her current gear, would trigger
this - not a Beast-Lord-only issue.

**Fix**: gate the whole `set_notes_by_item` population per set_name on whether
`best_four_of_five`'s own `combined_dps` for that set actually beats her real baseline
DPS (`baseline_screen["combined"]`) - reusing a comparison the code already had all the
inputs for, just never made. A set `best_four_of_five` can't evaluate (fewer than 5 real
tier pieces available anywhere) still gets the note, since there's no real transition
number to compare in that case - conservative fallback, not a full fix for that narrower
edge case. Verified directly: Beast Lord Armor items dropped from the report entirely (0
occurrences, confirmed via `tiered_report.json`); `Set-bonus check` went from 15 flagged
items across 18 sets to 10 flagged items across the same 18 sets - the 5 removed are
exactly the 5 Beast Lord Armor pieces. Re-verified in the browser (zero JS console
errors, "Beast Lord" no longer appears anywhere in the rendered page).

**Also stripped the dead Interaction Matrix section from the ledger HTML** (per the
user, already flagged as a known cleanup item from the Stage 5 pivot) - the CSS
(`kind-complement`/`kind-substitute`/`kind-artifact` styles), the legend rows
referencing it, the `<section id="interactions-section">` HTML block, and the JS
rendering code that reads `DATA.interactions` are all gone. `build_ledger_data.py` still
writes an empty `"interactions":[]` key into the data blob (harmless - nothing reads it
anymore) - left as-is rather than touching the data pipeline for a purely cosmetic
cleanup.

Republished the ledger artifact (same URL) with both fixes, verified rendering correctly
(no console errors, confirmed both changes took effect) before publishing.

**Second, separate real bug caught right after, same session**: the user spotted
"Shoulderpads of the Stranger" (-8.6 DPS) and "Mantle of the Tireless Tracker" (-21.9
DPS) also showing up with no explanation - looked identical to the just-fixed Beast Lord
bug, but the real cause was completely different this time. Checked the raw data first
rather than assuming: both items DO have a legitimate `rescue_note` (the real, validated
rescue-check mechanism - "breaks Rift Stalker Armor's bonus, but a real +19.8 DPS gain
once broken elsewhere") - the Python-side inclusion (`... or r.get("rescue_note")` in the
`upgrades` filter) was correct and working as designed. The actual bug: the ledger HTML's
JS template only ever rendered a note panel for `it.set_note` - `it.rescue_note` was
never wired into the template at all, going back to whenever the rescue-check feature was
first built. Every rescue-flagged item in the ledger has been showing as an unexplained
downgrade since rescue-check existed, not just Beast Lord Armor - this is a much bigger
count than the first bug (grepping the current data: Fists of Mukoa, Grips of Damnation,
Liar's Tongue Gloves, Gloves of Dexterous Manipulation, Gloves of the Unbound,
Shoulderpads of Assassination, Mail of Fevered Pursuit, Razorfury Mantle, Shoulders of
the Hidden Predator, and more, on top of the two the user actually spotted).

**Fix**: added a `rescue_note` rendering block in the ledger HTML's JS, styled the same
as the existing `set-note` panel (reusing the CSS class, just labeled "Rescue" instead of
"Set bonus"), and included `rescue_note` in the `setRescue` row-highlight check alongside
`set_note` (same "not a standalone upgrade, here's why it's still listed" treatment).
Pure HTML/JS fix - no Python data-pipeline change needed, since the data was always
correct. Verified directly: "Shoulderpads of the Stranger" now shows a "RESCUE" panel
with the real explanation text. Republished (same URL) after confirming zero console
errors.

Real lesson: two genuinely different root causes produced the same visible symptom
("unexplained downgrade in the upgrades list") back to back - worth actually checking the
data before assuming a second occurrence of the first bug's cause.

**Rescue -> Sidegrade rename, with a real verified number behind it first**: the user
asked directly whether "Mantle of the Tireless Tracker + Cursed Vision in head" is
actually better than her real current T5 shoulder - checked with a fresh sim rather than
reasoning about it. Real, verified numbers: baseline (current Rift Stalker Helm +
Mantle, full 4pc intact) 2685.5 DPS; +Cursed Vision alone 2698.7 (+13.3); +Cursed Vision
AND Mantle of the Tireless Tracker together 2707.1 (+21.7 total) - confirms the paired
combo genuinely beats her current setup, while Mantle of the Tireless Tracker ALONE
(current head kept) is a real -21.7 DPS downgrade, matching its own row. The rescue
note's "+8.4 DPS gain once broken elsewhere" is the INCREMENTAL value of adding the
shoulder swap on top of an already-taken head swap - not a standalone claim - and the
old wording didn't make that "package deal" dependency clear.

User's real point, though, wasn't really about the wording precision - it was the
practical loot-council framing: this class of item should read as "don't compete for
it if someone else has a genuine solo use, but grab it for the bank if it's going free
anyway - it becomes a real sidegrade once you've also made the other swap." Renamed
"Rescue" -> "Sidegrade" throughout (the note text in `run_full_sweep_mv.py`, the
"Sidegrade check"/"Sidegrade-checking" print/progress labels, and the ledger HTML's
label) and rewrote the note text to lead with the loot-priority guidance first, DPS
math second. Internal code names (`rescue_check`, `rescue_note`, `rescue_mv`,
`rescue_candidates` in `set_bonus.py`/`run_full_sweep_mv.py`) intentionally left
unrenamed - user-facing copy changed, not the underlying API, lower risk. Re-ran the
sweep (warm cache, 1.1s), rebuilt the ledger data, verified the new wording renders
correctly (real text confirmed present, zero console errors), republished.

**2026-08-24: automated ledger consistency checking built** (`core/check_ledger_consistency.py`),
the item queued directly after the two bugs above and the Absolute BiS Simulator plan. Three
real bug classes had already been caught by eye this project - Beast Lord false-positive
upgrades (a filter-gating bug), rescue_note never rendered (a template bug), and the
2026-08-23 raw-dict-of-dicts splice (a silent-blank-page bug) - and none of them had any
automated check that would have caught them before a human spotted the symptom. The script
re-derives `run_full_sweep_mv.py`'s own stated gating invariants (every shown item must be a
real upgrade OR carry a set_note OR a rescue_note; `tied_within_noise` must match the real
2-sigma rule; a rescue_note must carry a positive `rescue_mv`; a `resolved:true` row must
carry a real `resolve_iterations`) and checks them against the real `tiered_report.json`,
re-derives `build_ledger_data.py`'s transform and diffs it against the real
`ledger_data.json`, and diffs the published HTML's embedded `DATA` blob against
`ledger_data.json` byte-for-byte (the actual mechanism that would have caught 2026-08-23's
bug immediately).

**First real run found a genuine, previously-undetected bug**: the 2H weapon leaderboard's
`resolve_2h_row()` sets `resolved = True` but never wrote `resolve_iterations` - unlike the
main leaderboard's three-tier (resolve/confirm/screen) bookkeeping at the same file's
`resolve_one()` callsite, which does. Fixed by writing `resolve_iterations = RESOLVE_ITERATIONS`
on resolve and defaulting unresolved 2H rows to `SCREEN_ITERATIONS`, mirroring the main
leaderboard's pattern exactly. Backfilled the one real, known-correct value (30000 - the only
iteration count that code path ever resolves at) directly into the already-cached
`tiered_report.json`, `ledger_data.json`, and the published HTML's DATA blob rather than
re-running a 15-20 minute sweep for a field with zero display effect (grep-confirmed:
`resolve_iterations` only appears in the DATA blob itself, no render template reads it).
Committed as `57bc2d7`. Re-ran the checker clean afterward: 656 assertions, 0 failures.

Run it with `python core/check_ledger_consistency.py` any time after a sweep, before
republishing - it exits non-zero on a real failure, so it's suitable to run as a real gate,
not just an optional spot-check.

**2026-08-24: `variant` field retrofitted into `core/gear_config.py`/`optimizer.py`'s
`Candidate`** - closing a real, confirmed gap the Absolute BiS Simulator planning session's
Explore agent found: CLAUDE.md's own "day one" architecture rule ("item identity carries a
`variant` field from day one... retrofitting identity through a cache, state file, and
history log later is genuinely painful - do it now while it's free") was stated as decided
but never actually implemented anywhere in this repo's shipped code, despite the vendored DB
already carrying 82 real WotLK-tagged (`expansion: 3`) items today. Fixed here rather than
only in the new tool, since it's this repo's own `item_entry()`/`Candidate` that stated the
rule and never followed it, and the fix is genuinely free while nothing depends on the old
shape.

`gear_config.item_entry()` gained an optional `variant: str | None = None` fourth parameter,
included in the returned dict only when truthy (same pattern as `enchant`/`gems`) -
`config_hash()` already hashes the full entry dict, so a future variant-bearing entry
correctly gets its own cache key with zero further changes needed there.
`optimizer.Candidate` gained a matching `variant` slot/param, threaded through
`as_entry()`. Both call sites (`optimizer.py` lines ~72 and ~193) call positionally without
the new arg, so real TBC configs are provably unaffected - verified directly: the no-variant
entry is byte-identical to before, a with-variant entry produces a different `config_hash`
than the same item without one, and `check_ledger_consistency.py` still passes clean (656/0)
against the real cached pipeline output after the change. Still correctly a no-op for TBC
today - nothing in this repo's TBC-only DB has a real variant-duplicate item_id yet, and
nothing should invent one. The Absolute BiS Simulator plan (see the plan file referenced
there) is where a real WotLK variant actually gets exercised, once that tool exists.

**2026-08-24: gem choice broadened from "pure Agility everywhere" (N=1-verified) to
real per-item verification (N=37).** The earlier disproof of the "smart" STAT_WEIGHTS-based
hybrid heuristic (Ranger-General's Chestguard: pure Agility 2701.4 beat the hybrid's 2651.6,
see the entry above this session) only ever tested ONE item - it never actually established
that pure Agility beats a REAL socket-bonus match on every item, just that a crude linear
score is a bad way to decide. `gem_optimizer.verify_gem_choice()` (new) does the real
comparison instead - pure Agility vs the item's own socket-bonus-chased loadout
(`chase_bonus_gems_for_item()`, real color-matching against each socket's actual declared
color, not a STAT_WEIGHTS score), both sides evaluated by the actual sim with the item
genuinely equipped. `core/verify_gem_choices.py` ran this across all 37 of her real
candidates with sockets (out of 71 total candidates - more than half the pool has sockets,
a bigger blast radius than expected), screened at 3k iterations then resolved any close call
at 30k (same funnel discipline as `marginal_value.mv_single_tiered`).

Real result: pure Agility does NOT generalize. 9 items have a real, resolved, outside-noise
DPS gain from chasing their own bonus instead (noise_stdev ~0.5 at 30k, deltas +1.07 to
+3.03 DPS): Rift Stalker Mantle/Leggings, Gronnstalker's Leggings, Scaled Greaves of the
Marksman, Demon Stalker Greathelm, Barrel-Blade Longrifle, Necklace of the Deep, Fel Leather
Gloves, Gauntlets of the Dragonslayer. 21 items clearly still favor pure Agility (some by a
lot - Star-Strider Boots -20.5, Belt of Deep Shadow -18.9) and 7 are genuinely tied within
noise either way. Full real numbers: `data/cache/gem_choice_verification.json`.
`gem_optimizer.best_gems_for_item()` now applies the 9 confirmed winners
(`CHASE_BONUS_ITEM_IDS`) and keeps pure Agility as the default for every other item,
including anything never checked - real per-item data, not a formula claimed to generalize
past what was actually verified.

One of the 9 (Rift Stalker Mantle, item 30143) is CURRENTLY EQUIPPED - `build_owned_config`
already re-optimizes her own gems the same way candidates get treated (matching CLAUDE.md's
MV(i) = DPS*(P∪{i}) - DPS*(P) formula: DPS*(P) is the best achievable from P, not "whatever's
literally socketed"), so her own real baseline DPS was itself understated by ~1.6 DPS by the
old pure-Agility-everywhere default before this fix - not just a candidate-ranking issue.
Triggered a full re-sweep (`run_full_sweep_mv.py`) to refresh `tiered_report.json` under the
corrected baseline and gem choices before republishing - every reported MV number in the
ledger is downstream of `baseline_screened`, so a stale baseline after a gem-logic fix would
be a real, not just cosmetic, error.

Remaining known-crude edge, flagged rather than silently left: `_best_gem_of_color()` picks
the representative gem for a color via the same crude STAT_WEIGHTS score used elsewhere
(only to construct ONE real candidate loadout for the sim to judge, never as the final
decision) - if a color ever has more than one real Hunter-relevant gem choice worth
distinguishing, only the top-scored one ever gets sim-tested. Not hit in practice yet (each
color's real Hunter-relevant gem pool is small), so left as-is rather than building out
multi-candidate-per-color testing for a case that hasn't actually occurred.

Re-ran the full sweep afterward (471.1s) to refresh `tiered_report.json` under the corrected
baseline/gem logic, rebuilt `ledger_data.json`, verified the fresh render locally (local HTTP
server, zero console errors, real DATA match, Sidegrade notes present - `text-transform:
uppercase` makes them read "SIDEGRADE" in `innerText`, a case-sensitivity false alarm in my
own verification script, not a real bug) and republished. New `baseline_screened` = 2689.3
(vs the old 2689.8 - the ~0.5 DPS shift is well within screening noise, not a red flag; the
real +1.61 DPS Rift Stalker Mantle gain is inside that noise band at this iteration count).
`check_ledger_consistency.py` clean (671/0) both before and after the splice - it correctly
caught the intermediate state (sweep done, HTML not yet re-spliced) as a real failure, exactly
the class of bug it exists to catch.
