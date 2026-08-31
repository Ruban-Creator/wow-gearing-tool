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
   `C:\Users\<user>\go\bin`). Neither is on PATH by default in an already-open shell — add both
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

**2026-08-24: GearingToolCompanion rewritten to capture character identity + a multi-
character list**, groundwork for CLAUDE.md's Stage 6 (multi-class/spec support) requested
directly by the user ("collects everything we need name, class, race, professions... store
multiple characters and have a list showing all saved data with timestamps"), done while away
from the game client since the real multi-class simulation work itself needs the user present
with real alt characters to test against. `GTCompanionDB` was already keyed per-character
(`CharKey()`/`Entry()`), so multi-character storage was already structurally true - what was
actually missing was capturing identity at all (name/realm/class/race/faction/level/
professions, via `DumpIdentity()`/`DumpProfessions()`) and a UI to see it. New `/gtlist` slash
command + panel lists every saved character, most-recent first, with a real timestamp per
character - the actual "list ... with timestamps" ask. The existing `/gtexport` status panel
now also shows identity/professions for the current character, not just bag/bank/rep counts.

Also found and fixed a real, pre-existing, unrelated bug while reviewing the file:
`local bankIsOpen = false` was declared ~60 lines AFTER `SaveBank()` already referenced it -
Lua has no hoisting, so a `local` declared later in a chunk is invisible to code written
earlier, meaning `SaveBank()` was compiled against a plain global `bankIsOpen` (always nil,
since every real assignment targeted the local declared afterward). `if not bankIsOpen then
return end` was therefore always true, so `SaveBank()` could never actually save anything
regardless of whether the bank was genuinely open - silently undoing the exact fix its own
surrounding comment describes. Moved the declaration before `SaveBags()`/`SaveBank()`.

**NOT live-tested** - written without game client access, and no local Lua interpreter was
available to verify syntax either (checked statically: parens/braces balance only). Real
in-game verification is a next-session task: `/gtlist` for the character list, `/gtexport` +
opening the bank to confirm the `bankIsOpen` fix actually works now, and eyeballing
`DumpIdentity()`'s output against the character sheet and profession windows directly - this
file has already been burned twice by this exact client (Interface 20506) behaving differently
than documented Blizzard API (the reputation `hasRep` bug, the arena team API), so
`GetProfessions`/`GetProfessionInfo` being long-stable elsewhere is not itself a guarantee here.
Per CLAUDE.md's addon-sync rule, this repo copy is now the most-recently-edited (source of
truth) - needs copying into the live WoW AddOns folder to actually test.

**2026-08-24 (overnight, autonomous - user asleep, "keep moving through stops, save questions
for me" instruction): multi-character GUI built end to end**, all 4 stages of the approved plan
(`C:\Users\<user>\.claude\plans\staged-purring-lynx.md`). See `CLAUDE.md`'s "Future scope"
section for the real, current summary of what exists now. Detail worth keeping here:

- **Stage A**: `ingest/list_characters.py` real-tested against this machine's actual live
  SavedVariables - found 3 real characters (Lerynia/Survival Hunter, Béarforceone/Balance Druid,
  Rubán/Arms Warrior - genuinely useful future Stage 6 test data). Found and fixed a real edge
  case the plan didn't anticipate: GTCompanion's newest entry for both Lerynia and Rubán had an
  *empty* identity block (predates today's addon identity-capture update, no login since) but a
  *newer timestamp* than WSE - the confirmed "newer wins" policy would have picked an empty
  block over real data. Added a narrow guard (`_is_empty_identity`) so an empty block never wins
  regardless of timestamp - still whole-block, not a per-field merge, just not choosing a
  strictly-worse empty option when a real one exists.
- **Real regression caught and disclosed, not hidden**: testing `gear sync` live against
  Lerynia's actual current WSE export found it has 0 equipped items right now (a stale/ungeared
  export, not a bug in anything built today) - this overwrote `data/character.json` with that
  empty-equipped state. Nothing is actually lost (SavedVariables files were only ever read, never
  written), fully recoverable by re-exporting in-game, but flagged clearly in `QUESTIONS.md`
  rather than silently left for the user to discover.
- **Stages B+C merged**: built real styling directly instead of a deliberately-plain pass first,
  since "should look nice" was a confirmed requirement from the start. Picked `pywebview`
  (local HTML/CSS/JS, no server/port) over customtkinter/Flet/Dear PyGui - full CSS control for
  the least effort, given v1's whole surface is a list+detail view. Verified two ways since a
  native window can't be screenshotted or clicked into directly by this session: a test-only
  `gui/assets/preview.html`+`preview_mock.js` harness (fakes `window.pywebview.api` with real
  captured data) driven in an actual browser via DOM/computed-style checks, and three separate
  real `python`/packaged-exe launches confirmed via their actual OS window title through
  PowerShell. No human has looked at the actual rendered window yet - flagged for when the user
  is back.
- **Stage D packaging - two real gotchas hit and fixed, not just anticipated**: (1) PyInstaller's
  static import analysis can't see `ingest/list_characters.py`/`build_character.py` being loaded
  via a dynamic `sys.path.insert()` + bare `import` (the same pattern already used everywhere
  else in this repo) - solved by deliberately NOT bundling them, instead resolving `REPO_ROOT` via
  `os.getcwd()` when frozen (`sys.frozen`) so they load as real on-disk source from the repo
  checkout the exe is run from. (2) That same blind spot meant `slpp` (a REAL pip dependency of
  `build_character.py`, several import-levels deeper) also got silently omitted - a genuine first
  packaged build crashed with `ModuleNotFoundError: No module named 'slpp'` before
  `hiddenimports=["slpp"]` was added to `packaging/gearing_tool_gui.spec`. Final windowed
  `dist/gearing-tool-gui.exe` (~13MB) launches clean, confirmed via its real window title.
- **`QUESTIONS.md`** (new, repo root) - a running log of every real judgment call made
  autonomously overnight (empty-identity tie-break, the fixed phase2-5 grid UI choice, the
  Lerynia data-staleness heads-up, the Stage B/C merge) for the user to review, not blocking
  anything. Matches their explicit instruction rather than stopping at each plan checkpoint.

**2026-08-24: addon now tries to trigger WowSimsExporter's own export directly on login**,
per the user's ask. Real finding from reading WSE's actual installed source
(`WowSimsExporter.lua`/`SavedDataManager.lua`): WSE only registers its gear/talent/enchant/
glyph CHANGE listeners on initial login - it never calls its own save function just from
logging in. A character who logs in and changes nothing that session never gets freshly
exported at all, confirmed as the real cause of the earlier Lerynia stale-export incident
(0 gear items in her most recent WSE data). New `TriggerWSEExport()` (called right after
`SaveIdentity()` in the `PLAYER_ENTERING_WORLD` handler) reuses WSE's own real save path
instead of faking a UI interaction: WSE is an AceAddon-3.0 addon
(`LibStub("AceAddon-3.0"):NewAddon("WowSimsExporter", ...)`, confirmed in its source), and
AceAddon-3.0's own documented `GetAddon(name)` is the standard way another addon retrieves
it (`LibStub` itself is a real shared global once any Ace3-based addon has loaded, which WSE
will have by `PLAYER_ENTERING_WORLD` regardless of load order). Calling the real
`WowSimsExporter:OnCharacterChanged("GearingToolCompanionLogin")` correctly respects the
user's own real WSE settings (`autoSaveEnabled`, `supportedClasses`, max-level gating) rather
than forcing a save WSE itself wouldn't have made. Records the attempt (`ok`/`reason`/`at`)
into `GTCompanionDB[key].wse_export_trigger`, surfaced in both the status panel and `/gtlist`
per "record that as well in our list." **NOT live-tested** - written from reading WSE's real
source, not guessed, but never actually run in-game. Verify: log in, check `/gtlist` shows a
recent trigger result, and confirm WSE's own SavedVariables timestamp for the character
actually advanced (or just re-run `gear sync` and see equipped items are no longer stale).

**2026-08-25: five real multi-profile bugs found and fixed by user review of Rubán's and
Béarforceone's actual ledgers - a checklist for Stage 6.3 (Shaman) and beyond**, since every
one of these is a "the code worked for Hunter, so it looked fine" trap that only surfaced once
a SECOND and THIRD profile with genuinely different data shape existed. When building the next
profile, check each of these against the new class's own real data before trusting its ledger:

1. **A helper that hardcodes a provenance label instead of doing the real DB source lookup will
   silently mask real data the DB actually has.** `core/build_wowsims_reference_bis.py` labeled
   every reference-BiS item `"wowsims Phase N <Spec> preset"` instead of calling
   `run_full_sweep_mv.describe_source_and_tier()` like the rest of the pipeline - Hunter never
   exposed this because her reference BiS was hand-curated from Wowhead (real source text from
   the start), but Warrior/Druid's wowsims-preset-sourced reference BiS meant 28 of 63 items
   across both profiles had a real DB drop source sitting right there, unused. Fixed via
   `_real_source()` (imports `run_full_sweep_mv` for its own `describe_source_and_tier`, only
   falls back to the preset label when the DB genuinely has no source - same "Source unclear"
   floor as everywhere else, so a genuine gap reads identically wherever it shows up). Check:
   after building a new profile's reference_bis, spot check a few items against
   `sim/tbc-new/assets/database/db.json`'s own `sources` field before assuming the preset label
   was the only option.
2. **`describe_source_and_tier()` only understands `drop`/`crafted`/`rep` source types** - real
   PvP/Arena-purchased items (Onslaught set, Season gear generally) have `sources: None` in this
   DB build entirely (no vendor/arena source type tracked at all). This is a genuine sim DB
   data-completeness gap, not a parser bug - don't try to "fix" it by inventing a vendor-price
   source, per the ground rules. Every future profile with PvP set pieces in its candidate pool
   will hit this the same way.
3. **A "melee weave" settings variant is a real, distinct Survival Hunter rotation mechanic, not
   a generic "2H weapon alternative" concept** - `run_full_sweep_mv.py`'s 2H-weapon-options
   section unconditionally used Hunter's weave framing/settings (`SETTINGS_2H`, "weave ON/OFF"
   labels and math) for ANY profile with an offhand slot, which was meaningless for Balance
   Druid (a caster choosing a 2H staff vs 1H+offhand is not "weaving" anything). Fixed via
   `is_weave_profile = SETTINGS_2H != SETTINGS_TEMPLATE` (true exactly when a profile has its
   own real `settings_template_2h.json`) gating both the sim calls (no more redundant
   same-settings-twice sim call for a non-weave profile) and every user-facing label, in both
   `run_full_sweep_mv.py`'s console output AND `report_template.html`'s heading/subtitle
   (`two_hand_meta.weave_supported`). Only Hunter should ever see "melee weave" language -
   check this explicitly for any future profile that reuses the 2H-alternative section
   (dual_wield or one_hand_plus_offhand_item topologies).
4. **A per-profile feature flag not being read yet is a real, easy-to-forget landmine** -
   `arms_warrior/profile.json`'s own `raid_ap_contribution` note already self-documented "this
   flag isn't actually read by run_full_sweep_mv.py today" (it degraded correctly anyway only
   because `expose_weakness.measured_ew_uptime()` looks for a real Hunter-only spell id and
   silently finds nothing for a Warrior sim - accidentally safe, not correctly gated). The
   user-visible half of this gap was `report_template.html` always rendering the "Debuff (AP/ea)"
   column/legend row even when every value was `null` for a non-Hunter profile. Fixed by
   threading the real flag through: `build_ledger_data.build()` now takes `profile_dir`, reads
   `profile["raid_ap_contribution"]["enabled"]` for real, and the template only renders the
   column/legend when `DATA.raid_ap_enabled` is true. **Second, sneakier bug found fixing this
   one**: `.legend-row{display:flex}` in the page's own CSS beats the browser's default
   `[hidden]{display:none}` at equal specificity, so setting `.hidden = true` on the legend row
   left it visibly unchanged - author CSS always wins over the UA stylesheet at a specificity
   tie, hidden attribute or not. Fixed by setting `.style.display = 'none'` directly (inline
   style always wins short of `!important`). **General lesson: never assume `element.hidden =
   true` actually hides something - check whether any CSS rule sets `display` on that same
   element/class first**, this template already had two other working examples
   (`#two-hand-section`, `#bis-empty`) that happened to have no such competing rule, which is
   exactly why this one slipped through unnoticed.
5. **A curated candidate_pool.json built as a union across every phase a data source ships
   (wowsims presets: P2-P5) needs its own explicit phase filter - it doesn't inherit one just
   because the sweep's OTHER discovery path (`sweep_all_loot.py`) already has one.** Hunter's
   own `candidate_pool_survival.json` was hand-curated to Phase 3 only from day one, so this
   never came up for her; Warrior/Druid's reference-BiS-derived pool spans every phase wowsims
   ships, and nothing filtered it before candidates got built from it - a "Phase 3 Ledger" was
   listing real Phase 4/5 raid loot (Black Temple's own T6 tier is correctly Phase 3 on this
   server's real schedule and stayed, confirmed by cross-checking Hunter's own long-established
   Phase 3 report also includes T6 - but genuinely later content like Sunwell Plateau and
   Zul'Aman drops, phase 4/5, had no business appearing at all). Fixed by filtering `candidates`
   (from `opt.load_candidates()`) against each item's own real `db["phase"]` field right after
   loading, mirroring `sweep_all_loot.eligible()`'s existing `item.get("phase", 99) > max_phase`
   check - same real DB field, not invented data. **Any future profile whose reference-BiS/
   candidate pool is built from a multi-phase source (which is now the standard approach per
   the Stage 6.1 decision to prefer wowsims presets over hand-curated Wowhead) needs this same
   filter applied - it is not automatic.**

After all five fixes: re-ran Hunter's full pipeline as a regression check - byte-identical
except the one new field each fix intentionally adds (`weave_supported`, `raid_ap_enabled`).
`check_ledger_consistency.py` clean on all three characters (only the pre-existing, harmless
"achieved_bis empty" warning on Warrior/Druid). Also found while running that checker: the
on-disk `data/characters/<name>/cache/ledger_data_<phase>.json` cache file is not actually
written by the real GUI flow (`gui/api.py`'s `run_report()` only builds it in memory) - it was
stale from an earlier manual debug run and caused false-positive consistency-check failures
that had nothing to do with these five bugs. Not fixed (no real consumer needs it on disk
today), just worth knowing if that checker ever reports a mismatch again.

**Same session, added afterward: a sixth item, this one flagged by the user rather than found
by review - Armor Penetration Rating needs a visible warning tag, not just its normal linear EP
weight.** ArP's real value is nonlinear (stacks toward the 100%-armor-reduction cap; Stage 5's
interaction matrix would catch multi-ArP-item combinations properly via real joint sims, but
it's dropped from the active pipeline for time-budget reasons - see the 2026-08-23 entry above),
so a candidate carrying meaningful ArP needs a human sanity-check before trusting several
independently-ranked picks are actually additive. Verified this was a live, current-data risk
before building anything: Warrior's AND Hunter's own real `stat_weights.json` both weight ArP
(stat id `"23"`) nonzero (0.23 and 0.9 respectively) - not Warrior-only, and the DB has 50 real
phase<=3 items carrying it, several substantial (350 rating on Leggings of Divine Retribution,
335 on Cataclysm's Edge). Implemented as a real per-profile flag, not hardcoded to one class:
`run_full_sweep_mv.item_arp_rating()` reads an item's real base-stat ArP off
`sim/tbc-new/assets/database/db.json`, gated on `stat_weights.get_active().get("23", 0) > 0` (so
casters like Balance Druid, whose stat_weights.json has no ArP entry at all, never see it) -
attached to every tiered-leaderboard row AND the 2H-alternative rows. `build_ledger_data.py`
threads the same gate through as `arp_relevant` (loads `stat_weights.json` independently rather
than trusting shared global state ordering across process boundaries). `report_template.html`
renders a real "ArP <rating>" tag next to the item name (reusing the existing `--bad`/`--bag-bg`
warning palette already used for "Locked") plus a gated legend row explaining why. Verified live
after a real re-sweep of all three characters: Rubán shows 9 real flagged items across 8 slots
(up to ArP 350), Lerynia's Hunter profile is also `arp_relevant: true` (confirms this isn't
Warrior-specific), Béarforceone correctly shows `arp_relevant: false` throughout. Same
`.legend-row{display:flex}` vs `[hidden]` pitfall from bug #4 above was avoided from the start
by using `.style.display='none'` directly rather than `.hidden`, now that it's a known trap.
Scope note: this is a warning label, not a real fix for the underlying gap - it doesn't compute
a real joint-sim value for stacked ArP items, it just tells a human to go verify manually before
trusting the ranking. Re-enabling Stage 5's interaction matrix (scoped to ArP-carrying candidates
specifically, the same way it already special-cased Hit/Expertise Rating candidates before being
dropped) would be the real fix if this becomes a recurring pain point.

**Same session, one more: set pieces now rank by isolated mv + the real bonus threshold they
complete, not isolated mv alone.** Per the user (2026-08-25): a set piece that's the specific
piece crossing a real, currently-achievable 2pc/4pc threshold (given what's already owned of
that set elsewhere) was ranked in the per-slot leaderboard purely by its own isolated mv, which
can make it look like a weak pick even when the real, achievable combined value (with its bonus)
beats standalone alternatives. Confirmed with the user which of three real design options to
build (isolated mv + the specific threshold this piece completes, vs. sorting by the whole set's
best-combo DPS, vs. a display-only badge with no new number) before writing anything, since the
"fair" number to credit a single piece with is genuinely ambiguous (a 4pc bonus doesn't belong
to any one piece intrinsically) - picked the first.

Implementation: `threshold_values_by_set` captures the real per-threshold isolated bonus values
(`set_bonus.isolate_bonus_value()`) that the existing `set_note` text already computes - no new
sim calls, same gating as `set_notes_by_item` (a set whose own best-combo DPS doesn't beat
baseline gets no credit, matching the 2026-08-24 fix that keeps a non-competitive set's pieces
out of the "upgrades" list entirely). Per-candidate `set_bonus_credit` in the row-assembly loop:
real total owned pieces of that set in `baseline_config`, minus 1 if the candidate's OWN target
slot currently holds a same-set piece (it would be replaced, not stacked), plus 1 for the
candidate itself - any threshold newly crossed by that transition gets summed in. New
`rank_value(r) = r["mv"] + (r.get("set_bonus_credit") or 0)` replaces `r["mv"]` as the sort key
in both the tier/slot leaderboard cut AND the final display sort (not the resolve-vs-screen
precision decision, which stays keyed on the real isolated mv/noise - the credit is a ranking
concept, not a "how sure are we of this number" one). The *displayed* DPS number for each item
stays its honest isolated mv, unchanged - only where it sorts changes; the existing `set_note`
text already explains the bonus threshold values in prose, so no new UI number was added (kept
minimal, matching what was actually asked for).

Verified real, not just "doesn't crash": re-ran full sweeps for all three characters. Only one
candidate in the whole current sweep actually got a nonzero credit - Béarforceone's Wyrmhide
Spaulders (crosses Oathbound's Wyrmhide Battlegear's real 2pc threshold given she already owns
one other Wyrmhide piece), and correctly a NEGATIVE credit (-14.2, that bonus is actually bad) -
confirms the logic handles a harmful bonus correctly too, not just positive ones. Zero credits
fired for Lerynia or Rubán's current real gear state (expected - crediting only fires when a
candidate is specifically the piece completing a threshold given CURRENT baseline ownership,
which is a real but situational condition, not "every set piece gets a bonus"). Confirmed this
is conservative-by-design, not a bug: a set she owns zero pieces of yet never gets credited for
any single candidate, since one piece alone never crosses a 2pc+ threshold - matches reality.
Regression check: diffed Lerynia's new tiered_report.json against the known-good baseline by
item NAME ORDER specifically (not deep dict equality, which now differs harmlessly due to the
new `arp_rating`/`set_bonus_credit` keys being present on every row) - zero real reordering,
confirming `rank_value()` is a true no-op whenever credit is 0, exactly as designed.

**Stage 6.3 (Elemental Shaman): a fourth profile with no real character to export from.**
`ingest/build_synthetic_character.py` (new) builds a character.json-shaped dict directly from a
wowsims preset `gear_sets/*.gear.json` file, reusing `build_character.resolve_items()` unchanged
(the wowsims gear-set format already matches `resolve_items()`'s expected `{id, enchant, gems}`
raw-item shape, confirmed by inspecting `p3.gear.json` directly rather than assuming). Real
race/professions come from the spec's own `presets.ts` `OtherDefaults` - not fabricated - only
the character name/realm itself (`Test-Elemental-Synthetic`) is a deliberate placeholder.
`profile.json` gets a `synthetic_character: true` flag.

Real bug this surfaced, only found by testing through the actual GUI layer (`Api.run_report()`)
instead of stopping at the CLI/pipeline-function level like earlier stages' checkpoints did:
`gui/api.py`'s `_run_report_job()` unconditionally re-syncs `character.json` from a real
WowSimsExporter export before every single report run (correct for a real character - keeps
data fresh - but `build_character.build()` raises `SystemExit` when no real export exists at
all). Fixed by checking the new `synthetic_character` flag and loading the already-built
character.json from disk instead of re-syncing in that case. Worth remembering for Stage 6.4
(Enhancement) and any future profile built the same way: **a synthetic profile needs this same
`synthetic_character` flag from the start**, or its very first `Api.run_report()` call fails with
a real, confusing `SystemExit` error that has nothing to do with the profile itself.

**Stage 6.4 (Enhancement Shaman): a real, more serious bug found - `build_wowsims_reference_bis
.py` had never actually been exercised on a dual_wield profile before.** Hunter's own dual_wield
reference_bis predates this script entirely (hand-curated from Wowhead in Stage 4), so its
dual_wield handling was pure guesswork that happened to never get tested until Enhancement
Shaman. `optimizer.py`'s own real `_WEAPON_TOPOLOGY_POOLS` expects exactly ONE shared
`"weapon_dual_wield"` pool key covering both mainhand and offhand for this topology - but
`_weapon_pool_key()` always wrote separate `"mainhand"`/`"offhand"` keys regardless of topology.
That's coincidentally correct for `one_hand_plus_offhand_item` (Druid/Elemental - those really
are two independent single-item pools, matching `_WEAPON_TOPOLOGY_POOLS` exactly) and
coincidentally correct for `two_hand` too (a two_hand profile's real candidates always have
`hand_type == HAND_TYPE_TWO_HAND`, so the old unconditional check always returned `"weapon_2h"`
anyway - `optimizer.py`'s real key for that topology). But for `dual_wield`, writing separate
keys meant `opt.load_candidates()`'s `pool_key_to_slots.get(pool_key, [])` returned `[]` for
both (neither `"mainhand"` nor `"offhand"` is a recognized weapon key under `dual_wield`'s real
topology pools) - **the entire curated reference-BiS weapon pool for Enhancement was silently
invisible to the real sweep**, confirmed live: before the fix, `candidate_pool.json`'s real
weapon entries (Syphon of the Nathrezim, Talon of the Phoenix, etc.) never reached `candidates`
at all. Fixed by making `_weapon_pool_key()` branch explicitly on `weapon_topology` instead of
relying on `two_hand`'s coincidental correctness - `dual_wield` now always returns
`"weapon_dual_wield"` for both slots, matching `optimizer.py` exactly. Verified via a real
before/after check: `achieved_bis` for Enhancement now correctly includes `"Weapon"` (her real
current dual-wielded Syphon of the Nathrezim pair, listed twice - a real, correct signal that
only makes sense if the weapon candidates were actually evaluated and found not to be beaten).

A small, incidental second fix landed alongside this (same function's caller): a dual-wield
profile that equips the identical item in both mainhand and offhand now shares one pool_key -
without a dedup guard, the same phase got recorded twice in that item's `seen_in` list. Cosmetic
only (never affected which candidates got evaluated or their MV), caught it removed 4 duplicate
entries from Elemental Shaman's own already-committed `candidate_pool.json` too (an unrelated
item that happened to hit the same phase twice for a different reason) when re-running the
builder to verify.

**Regression discipline paid off finding a second bug within the fix itself**: my first attempt
at this fix added `and weapon_topology != "two_hand"` to the 2H-item branch, reasoning (wrongly)
that `two_hand` needed to be excluded from special-casing - this actually broke Warrior (his real
2H weapon candidates started routing to `"mainhand"` instead of `"weapon_2h"`), caught immediately
by diffing the rebuilt `candidate_pool.json` against the last git commit before moving on, not by
assuming a "generalizing" change was automatically safe. Second attempt (branch on
`weapon_topology` directly, matching `_WEAPON_TOPOLOGY_POOLS` literally instead of reasoning
about it) came back byte-identical for Warrior and Druid.

Full sweep verified for Enhancement after the real fix: real Achieved BiS (Neck/Ranged/Weapon),
`check_ledger_consistency.py` clean (1230 assertions), `arp_relevant: true` (a third real profile
confirmed to weight Armor Penetration, after Warrior and Hunter - not a Warrior-only stat by any
means). Re-ran all four other pipelines (Hunter, Warrior, Druid, Elemental) afterward - all
byte-identical by item order/content.

**Same session, later: two real GUI bugs, found by the user actually running the packaged app
(2026-08-25).** `gui/assets/style.css`'s `.modal-overlay{display:flex}` beat the browser's
default `[hidden]{display:none}` at equal specificity - the SAME bug class already found and
fixed once this session in `report_template.html`'s legend row, but in the GUI's own separate
codebase, and pre-dating today entirely (present since the GUI was first built - just never
exercised by a human clicking Run Report/Settings until now). Every modal rendered permanently
open and unclosable. Fixed identically: `.modal-overlay[hidden]{display:none}` override wins the
specificity fight. Worth remembering as a general pattern for this project now that it's shown up
twice independently: **before shipping any new `hidden`-toggled UI element, check whether its own
CSS (or an ancestor's) sets `display` unconditionally** - the browser default only wins when
nothing else claims that property.

Separately, real Phase 1 support: `PHASES`/`PHASE_LABELS` only ever listed phase2-5 -
deliberate, documented (`reference_bis/phase1.json` didn't exist for any profile), not a code
gap - `time_horizon.py`'s own `bis_until_phase` loop already ranged `1..FINAL_PHASE`
unconditionally from the start, confirmed needing zero changes. Built real phase1.json for all 5
profiles: the 4 wowsims-preset-based ones (Warrior/Druid/Elemental/Enhancement) via
`build_wowsims_reference_bis.py` with a `phase1:pN_x.gear.json` argument added - the real p1 gear
set files already existed in the vendored sim (`p1_arms.gear.json`, `p1_a.gear.json`,
`p1.gear.json`, etc.), just never referenced. Hunter's own reference_bis has always been
hand-curated from Wowhead (predates the wowsims-preset-builder decision) - built her real
phase1.json the same way, from Wowhead's own real Phase 1 Survival Hunter BiS guide.

**Real near-miss in that research, worth remembering**: guessing the Phase 1 URL by analogy to
Phase 2's real, already-committed source (`/tbc/guide/classes/hunter/survival/dps-bis-gear-pve-
phase-1`, swapping "2"→"1") resolved to a real page - but a **Wrath of the Lich King Classic**
guide, not TBC (title said so explicitly: "Naxxramas, Obsidian Sanctum, Eye of Eternity" - no
such raids exist in TBC). Wowhead apparently doesn't have a page at that exact slug for Phase 1
specifically (unlike Phase 2 where it does), and the broken URL didn't 404 - it silently landed
on a same-named guide from a different expansion. Caught by actually reading the resolved page
title/intro text before transcribing anything, not by assuming a URL that "looks right" by
pattern-matching a sibling page's real, already-verified URL is automatically safe. Real, correct
URL found instead via Wowhead's own BiS guide index page
(`/tbc/guides/classes/best-in-slot-guides-burning-crusade-classic`), which lists real per-class
Phase 1 guide links directly - confirmed TBC-correct by title before use.

candidate_pool.json for the 4 wowsims-based profiles needed a full rebuild (adds phase1 entries
into the existing union-across-phases file) - confirmed via git diff that this only ever adds
new "seen_in" phase entries to existing items (or reorders keys, a harmless side effect of
Python dict insertion order shifting when phase1 is now processed first) and never removes real
data - spot-checked specific items that looked like deletions in a raw line-diff and confirmed
both were still present with an added P1 entry. Hunter's own `candidate_pool.json` needed no
rebuild at all - her existing 79-item hand-curated pool already happened to include every real
Phase 1 item, confirmed by checking a sample before assuming a rebuild was necessary.

Ran real Phase 1 sweeps for all 5 characters, `check_ledger_consistency.py` clean on all 5,
regression-verified Hunter's Phase 3 output stays byte-identical (by item order) after adding
Phase 1 data. Rebuilt `dist/gearing-tool-gui.exe` with both fixes and verified live: launched the
real exe, screenshotted it (confirmed via .NET `System.Drawing`/`user32.dll` P/Invoke from
PowerShell - this session had real remote-control access to the user's machine), clicked through
Run Report → Phase 1 → Run, and confirmed a real "Report ready" result registered in
`reports.json` with a fresh timestamp - not just trusted from reading the code.

**Same session, one more real GUI bug: a flood of visible black console windows during every
report run.** The user reported it directly, and it was real - confirmed live in a screenshot,
windows titled after `adapters/tbc/bridge`'s own path. Root cause: the packaged GUI is a
windowed, console-less PyInstaller build (`console=False` in `packaging/gearing_tool_gui.spec`),
so it has no console of its own for a child process to attach to - every plain
`subprocess.run()`/`subprocess.Popen()` call spawning a console-mode child (bridge.exe,
wowsimcli.exe, simserver.exe, git) made Windows allocate a brand-new visible console window for
that child instead, since it had nowhere else to put one. `adapters/tbc/valuation.py`'s
`_build_raid_sim_request()` was the dominant source - it calls bridge.exe on literally every real
sim call (hundreds per sweep), so a full sweep flashed hundreds of black windows across the
screen. Never affected functionality (stdout/stderr aren't read from bridge.exe there at all, and
simserver.exe/wowsimcli.exe both communicate via captured pipes already) - purely a
alarming-for-a-real-user cosmetic issue, but a real one worth fixing immediately once reported.

Fixed by adding `creationflags=subprocess.CREATE_NO_WINDOW` (guarded `if sys.platform ==
"win32" else 0` for cross-platform safety, even though this project only targets Windows today)
to all 7 real subprocess call sites found via a full-codebase grep: `adapters/tbc/adapter.py`
(3 - git version(), bridge.exe, wowsimcli.exe), `adapters/tbc/valuation.py` (1 - the hot-path
bridge.exe call), `adapters/tbc/simserver_client.py` (1 - the persistent simserver.exe Popen),
`core/build_ledger_data.py` (1 - git rev-parse for the report's sim_commit_sha), `ingest/
build_character.py` (1 - the same git call, reused by `build_synthetic_character.py` too).
Verified real, not just "should work": ran a real, uncached full sweep (Rubán, Phase 4) after
rebuilding the exe and polled the running process list the whole time for any newly-spawned
visible windows - none appeared, only legitimate user windows. Real sim call itself confirmed
still working correctly post-fix (plausible DPS, real report generated) - `CREATE_NO_WINDOW`
only suppresses the console allocation, it doesn't affect stdin/stdout/stderr piping at all, so
there was no reason to expect it could break anything, and the live test confirmed it didn't.

**Missing Enchants feature (2026-08-25) - real design reversal, not just a new UI section.**
`optimizer.py`'s `load_candidates()`/`build_owned_config()` used to default every candidate's
(and her own baseline's) enchant to "whatever slot she currently has an enchant on", not the real
best available one - a real, deliberate call made early in the project, explicitly flagged in
`build_owned_config()`'s own old docstring ("Enchants stay real, never invented"). That was
inconsistent with gems, which already got the correct "always assume the objectively-best choice"
treatment (`gem_optimizer.best_gems_for_item()`, unconditional, no "respect her real current gems"
carve-out) - and inconsistent with CLAUDE.md's own stated principle ("keep assuming the
fully-optimal gem/enchant loadout, same as it already does" - only actually true for gems until
now). Fixed per the user's explicit ask ("unenchanted items must never get compared to enchanted
ones") by mirroring gems exactly: `gc.get_active_default_enchants()` (new, mirrors
`get_active_default_gem()`) is now the unconditional source for every slot's enchant, in every
place a Candidate or the owned baseline gets built - `optimizer.py` (both functions),
`run_full_sweep_mv.py`'s own separate full-world-item sweep loop (a second, independent site with
the identical bug, found by grepping for `.get("enchant"` across the whole codebase rather than
assuming the one known site was the only one), and `set_bonus.py`'s tier-set leave-one-out
comparison. `core/interaction_matrix.py`'s own `.get("enchant", 0)` needed no fix - it reads from
an already-built `baseline_config`, which now correctly carries the fixed value upstream.

Real per-profile `default_enchants.json` built via `core/build_default_enchants.py` (reusing
`build_wowsims_reference_bis.py`'s own `resolve_gear_set()`, now capturing each preset item's real
`"enchant"` field alongside `id`/`hand_type`) for the 4 wowsims-preset profiles, and by hand from
Wowhead's real "Hunter DPS Gems & Enchants" guide for Survival Hunter (predates the preset-builder
convention, same as her reference_bis). Every id in every profile's file is real-sim-verified, not
trusted from the source data as-is - `core/verify_default_enchants.py` isolates each slot (strip
its real enchant to 0, compare "0 enchant" vs "candidate enchant" at 3000 iterations, same
methodology as `set_bonus.isolate_bonus_value()`) and drops anything under a 1.0 DPS clear
threshold. Real, disclosed finding from this pass, not smoothed over: **Balance Druid's raw preset
enchant ids verified 0/11 real** (every one showed a ~0.00 delta - not a single recognized effect
in this sim build) and **Enhancement Shaman verified only 3/10** (`back`/`wrist`/`hands`; the rest,
including a `chest` id shared with Druid's own failing set, showed no real effect either) - a
genuine sim-DB-coverage gap for these two profiles' preset data specifically, not a bug in this
tool's own logic (Warrior and Elemental both verified real ids fine on the same source
convention). `default_enchants.json` for both is smaller than a full slot list as a result - those
slots simply have no verified default enchant to assume, same honest "no data" state as before
this feature existed, not a wrong value kept because it came from a real-looking source file.

**Real methodology bug in the verification script itself, caught before it corrupted any data**:
the first version of `verify_default_enchants.py` compared "candidate enchant applied" against the
character's own REAL, unmodified current gear - which trivially shows `delta=0.00` for any slot
where she already happens to have that exact enchant equipped (not "the id is broken", just
"nothing changed"). Caught on Warrior (Rubán's own real current gear already matched 4 of 9
candidate ids exactly, all four showing a false "DROP"). Fixed by stripping the slot under test to
a neutral zero-enchant baseline first, so both sides of the comparison are measured from the same
real starting point - Warrior then verified 9/9.

**Real gap the Stage 2 STOP checkpoint itself caught, live**: re-running `build_owned_config()` for
Lerynia after the fix showed her real `ranged` slot enchant vanish entirely (was her real
Stabilitzed Eternium Scope, effectId 2724) - her hand-researched `default_enchants.json` simply
never had a `ranged` key, because the plan's own working assumption ("rings/waist/trinkets/ranged
never carry a real enchant in the wowsims presets") turned out true for every OTHER profile's
ranged/relic slot (Shaman totems, a Druid idol - genuinely un-enchantable in this game) but false
for a Hunter's actual ranged WEAPON, which does take a real scope enchant. Added and re-verified
(+17.37 DPS, clear real effect) - the other 4 profiles' own auto-built files were checked too and
confirmed correctly ranged-less (their real ranged/relic slot items are relics/totems, not
weapons, so "no enchant" is the true state there, not a parallel oversight).

New `item_db.enchant_by_id()` added (db.json's `enchants` collection, keyed by `effectId`) purely
for display-name resolution in the new "Missing Enchants" ledger section - same "display lookup,
not proof the Go sim engine implements it" caveat as everywhere else this collection gets used.

**Real fourth bug in the same feature, caught live by the user (2026-08-25), same day, after the
above was already believed done**: the user flagged that the Missing Enchants section was
recommending Ring enchants for Lerynia even though "ring enchants require you to be enchanter
yourself" - a real TBC-era game rule this tool had never modeled anywhere. Unlike every other
enchant slot (cloak, chest, weapon, etc.), which any enchanter can apply to any player's gear via
a trade-window service, Ring enchants can only be self-cast by a character who personally has the
Enchanting profession - there's no "pay a stranger" option. Confirmed directly in the DB rather
than taken purely on the user's word: `db.json`'s `enchants` collection already carries a real
`requiredProfession` field per entry, and checking it across the WHOLE collection showed exactly
and only the four real Ring enchants (2928-2931, "Enchant Ring - Spellpower/Striking/Healing
Power/Stats") set it to 3 (Enchanting) - every other enchant in the game, including all the ones
already verified this session, has it unset. This is the identical field/pattern
`item_db.required_profession_name()` already uses for ITEMS (a required crafting profession to
*use* an item) - just never previously checked for enchant effects, and semantically different
(an item's requiredProfession gates who can equip it; an enchant's gates who can even apply it at
all, since normal enchants have no such restriction and only rings do).

Fixed generically, not with a hardcoded "ring" special case, since the DB field itself already
distinguishes the real cases: `item_db.enchant_required_profession_name()` (mirrors
`required_profession_name()`) + `optimizer.achievable_enchant(enchant_id, known_professions)` (new,
returns 0 if gated) - wired into every real default-enchant lookup found in the codebase:
`optimizer.py`'s `load_candidates()`/`build_owned_config()` (the latter gained a real
`known_professions` parameter it never had before, defaulting to Hunter's real Herbalism/Mining so
every existing caller stays behavior-identical unless it explicitly passes real data - same
convention `load_candidates()` already established), `run_full_sweep_mv.py`'s own separate
full-world-item-sweep loop (both the 2H-weapon and general branches), its Missing Enchants
computation itself (so a character without Enchanting never even sees a ring gap listed - not just
silently getting 0 DPS for one), and `build_profile_settings.py`/`verify_default_enchants.py`'s own
`build_owned_config()` calls. `set_bonus.py`'s tier-set leave-one-out comparison needed no change -
confirmed its own `ARMOR_SET_SLOTS` (head/shoulder/chest/hands/legs) never includes rings at all.

Verified live: Lerynia (Herbalism/Mining, no Enchanting) now correctly shows `ring1`/`ring2` as
`None` in both her real baseline (`build_owned_config()`) and her real candidate pool
(`load_candidates()`), where before the fix both assumed the gated Enchant Ring - Stats (2931)
unconditionally. Two in-flight full sweeps (Lerynia, Rubán) that had been started under the
pre-gate code were killed and restarted clean once this landed, rather than trusting output that
predated the fix - confirmed via file mtime that neither killed run had gotten far enough to
overwrite a real `tiered_report_phase3.json` with stale data first.

**Real fifth bug, and a more serious one: Rubán's whole re-run had actually been sweeping against
Hunter's own profile, not his.** Sanity-checking Lerynia's own corrected sweep also surfaced a real
negative Missing Enchants delta (see next entry) - her feet slot's assumed BiS enchant
("Cat's Swiftness", 2939) turned out to be worse than her real current one ("Dexterity", 2657,
+7.3 DPS confirmed by a real head-to-head 30k-iteration sim call, not assumed). Fixed
`default_enchants.json` and hardened `run_full_sweep_mv.py`'s Missing Enchants filter to require
`delta > 0` outright (it previously only checked `tied_within_noise`, never the sign - a real gap
mirroring `is_available_upgrade()`'s own `and r["mv"] > 0` check elsewhere in the same file, just
missed when this feature was first written).

While re-running Rubán's own sweep to pick up that same code, his fresh Missing Enchants output
showed something structurally wrong: both his Hands and Weapon slots listed "Enchant Weapon -
Agility" (effectId 2564) as the recommended BiS - but his own `default_enchants.json` has no such
value anywhere (`hands: 684`, `mainhand: 2673`). 2564 is Survival Hunter's real weapon-enchant id.
Root cause found by inspecting `run_full_sweep_mv.py`'s own `main()` signature: `profile_dir: str
= PROFILE_DIR`, where the module-level `PROFILE_DIR` constant is hardcoded to
`profiles/tbc/survival_hunter` (a leftover default from before multi-profile support existed).
My own ad-hoc verification command this session (`rfsm.main('Rubán-Thunderstrike', 'phase3')`)
never passed `profile_dir` explicitly, so it silently swept his real character.json gear against
HUNTER's candidate_pool.json, default_enchants.json, stat_weights.json, and settings_template.json
- a real-looking, wrong report (his own equipped items still displayed correctly since those come
from his own real character.json, which masked the bug until an enchant-name mismatch made it
visible). Lerynia's own equivalent ad-hoc call happened to be correct by pure coincidence (her real
profile_dir IS Hunter's), so nothing about her earlier results in this session was ever wrong.

Checked whether this was a new bug or a known trap: `gui/api.py` already had a defensive comment
about this exact class of bug from an earlier session ("own profile (run_full_sweep_mv.main()'s
default profile_dir) - caught before it ever shipped") and always passes `profile_dir` explicitly
via its own `SUPPORTED_CHARACTERS` map - the GUI path was never actually affected. But
`cli/gear.py`'s real `cmd_best` command (`gear best <character> <phase>`) had the identical gap -
`run_full_sweep_mv.main(args.character, phase, duration=args.duration)`, no `profile_dir` at all -
meaning the real CLI entry point had this exact bug live the whole time for any non-Hunter
character, not just my own test script.

Fixed at the root instead of patching each call site individually: new `core/character_profiles.py`
(the real `SUPPORTED_CHARACTERS` map, moved out of `gui/api.py` so both the CLI and GUI share one
source of truth instead of two copies that could drift), `gui/api.py` now imports it rather than
defining its own copy, `cli/gear.py`'s `cmd_best` resolves `profile_dir` from it and prints a clear
"no known profile" message for an unsupported character instead of silently guessing, and
`run_full_sweep_mv.main()`'s own `profile_dir` parameter lost its dangerous default entirely
(now required - a call site that forgets it fails loud with a real `TypeError`, not a silent wrong
sweep). Rubán's sweep re-run a third time with the real, explicit `profile_dir` this time.

**Real sixth bug/fix, same day: Béarforceone's real weapon enchant gap, found by the user
directly ("something i'm 100% sure of"), 2026-08-25.** Her `default_enchants.json` had been left
completely empty (`{}`) earlier this session after every one of her 11 raw preset candidates
verified `+0.00` - a real, disclosed data-coverage gap, not investigated further at the time. The
user's report that her weapon specifically was unenchanted prompted a real re-investigation: her
raw preset's mainhand candidate (effectId 22560, from `sim/tbc-new/ui/druid/balance/gear_sets/
p3.gear.json`) is simply **absent from `db.json`'s `enchants` collection entirely** - not a weak
effect, not implemented by this sim build at all, same root cause already documented for
Enhancement Shaman's own failing ids. Checked all 9 of her other non-weapon candidate ids the same
way - also absent from the DB, confirming this specific preset file's enchant ids are broadly
unreliable for this build, not an isolated case.

Real fix, not a guess: searched `db.json`'s own `enchants` collection by name for a real,
DB-recognized caster weapon enchant (`grep`-style scan for "weapon"/"staff" in the name field) -
found `2669, "Enchant Weapon - Major Spellpower"` (+40/+40 to the two spell-damage-family stat
slots), matching real TBC game knowledge for what Balance Druid's actual BiS weapon enchant is.
Verified via the same isolated-delta methodology as everything else: **+22.82 DPS at 30000
iterations**, real and clear. Added to her `default_enchants.json` (now `{"mainhand": 2669}` - the
other 10 slots stay genuinely empty, a disclosed gap, not silently filled with an unverified
guess). All 4 of her existing reports (phase1-4) re-swept and re-verified
(`check_ledger_consistency.py` clean on all 4) to pick up the corrected baseline and the new,
real Missing Enchants entry: "Weapon | Merciless Gladiator's Spellblade | (none) -> Enchant Weapon
- Major Spellpower | +22.8 DPS".

Real lesson worth keeping: when a whole profile's raw preset enchant ids fail verification
near-unanimously, that's a real signal to check `db.json` directly (not just re-run the same
isolated-sim test again) - the fix usually isn't "these items are useless," it's "this specific
id isn't the DB's real id for that effect," findable by searching the enchants collection by name
for the class-appropriate keyword. See the new `CLASSES.md` for this and every other real
class-profile gotcha found so far, kept as a standing checklist rather than left buried in a
single session's NOTES.md entry.

**Stage 6.3 (2026-08-25): 2H-without-weave comparison for weave-capable profiles.** The user asked
directly whether the tool checks "would 2 one-handers get replaced by 1 two-hander even without
weaving" - it didn't. Every 2H candidate for a weave profile (Survival Hunter today) was screened/
resolved only against the weave-ON dual-wield baseline; the weave-OFF baseline was computed and
printed for context but never used as a comparison point for any candidate. Fixed additively (the
existing weave-on comparison and its own recorded rationale are untouched): `run_full_sweep_mv.py`'s
2H section is now a reusable `run_2h_pass()` helper, called once against the weave-on baseline (or
the plain baseline for a non-weave profile, unchanged) and, for a weave profile only, a second time
against the real weave-OFF baseline (`SETTINGS_TEMPLATE`/`no_weave_result`). Each row is tagged a
real boolean `weave` (`True`/`False`) rather than needing a second output list; a non-weave
profile's rows carry no `weave` key at all, same shape as before this feature existed.
`stage_sequence` gained three new conditional entries ("Screening 2H weapons (no weave)",
"Resolving 2H (no weave)", "Resolving top 2H picks (no weave)") - `is_weave_profile` had to move
earlier in `main()` (right after `SETTINGS_2H`/`SETTINGS_TEMPLATE` resolve) so the GUI's own
"Stage X of Y" count knows about them upfront, rather than only being computed later at the 2H
section itself where it used to live.

`report_template.html` renders the two groups separately ("Weaving ON"/"Weaving OFF" sub-labels
inside the existing `.slot-block` pattern, reusing `.slot-label` from the tier-slot rendering)
rather than interleaving both scenarios by raw `mv` - a weave-on MV and a weave-off MV assume
different fight contexts and were never meant to rank against each other on one shared list.
`check_ledger_consistency.py` gained a matching real check: every `two_hand` row on a
`weave_supported` profile must carry a real boolean `weave` tag, and none may on a profile without
one - catches a `run_2h_pass()` call site disagreeing with itself about whether to tag.

Real, live-verified checkpoint: ran a real sweep for Lerynia (Survival Hunter) - weave-on numbers
came back byte-identical to the pre-existing values (Twinblade of the Phoenix +196.7, Halberd of
Desolation +178.9, etc.), and the new weave-off pass ran correctly end to end, producing a real,
legitimate finding: no 2H weapon beats her current DW gear with zero melee weaving at all (makes
real sense - a pure-ranged rotation barely cares what's in the melee weapon slot). Rendered HTML
confirmed live via browser: "top 5 weave-on, top 0 weave-off" with both groups correctly labeled
and a real subtitle explaining both baseline numbers. `check_ledger_consistency.py`: 676/0 clean
(up from 667, the new weave-tag assertions).

**Stage 6.4 (2026-08-25): Beastmastery Hunter, real-verified.** `profiles/tbc/beastmastery_hunter/`
built end to end from `sim/tbc-new/ui/hunter/dps/` (the same real UI dir Survival uses - BM/SV
share one apl file, `default.apl.json`, and one candidate item universe).

Real, non-obvious corrections found during research, worth remembering for the next Hunter-family
profile: the `6p`/`9p` suffix in BM's real gear_sets filenames (`dw_6p.gear.json`, `2h_9p.gear.json`,
etc) is a **hit-rating-target label ("6% hit"/"9% hit"), not a tier-set piece count** - easy to
misread at a glance. Used the real "6%" variant (`dw_6p`) per CLAUDE.md's own already-decided
default ("keep assuming 6% (moonkin present)... never silently switch to 9% without being asked").
BM's real wowsims data ships BOTH `2h_*` and `dw_*` gear variants at every phase as equally
legitimate builds, but `P1_BM_EP_PRESET` and `P1_SV_EP_PRESET` in the shared `presets.ts` are
byte-identical, and both weapon variants embed the exact same real `TypeSimple` rotation JSON
(`timeToWeave`/`useMulti`/`useArcane`/viper thresholds) - confirming BM has no real weave-style
rotation mechanic the way Survival's own 2H side-analysis does. Built `weapon_topology:
dual_wield` (matching Survival's own convention on this identical candidate pool), no
`settings_template_2h.json`, `is_weave_profile=False` - the plain "2H Weapon Options" section
(shared with Balance Druid's own non-weave path) handles "would a 2H weapon beat my DW gear" as a
real side-comparison, same as everywhere else this pattern already exists.

`settings_template.json` built by literally copying Survival's own (already real, already
thousands-of-runs-verified) file and changing exactly two real, confirmed-different fields:
`player.talentsString` (BM's real talents, `522002005150122431051-0550201205`, confirmed
identical across all 4 phases' own real build.json files) and
`player.hunter.options.classOptions.petType` (`"Ravager"`, confirmed from the raw preset builds -
Survival's own file uses `"Owl"`). Verified this was safe by checking the real priorityList's own
spell IDs (34026/34120/27021/27019 - Kill Command/Steady Shot/Arcane Shot/Multi-Shot, all
class-generic core-rotation spells, nothing Survival-specific like Explosive Trap/Black Arrow)
before assuming it transfers.

`default_enchants.json`: 11/11 verified real (matches Survival's own strong hit rate, unlike
Druid/Enhancement's earlier DB-coverage gaps) - `core/verify_default_enchants.py` run fresh, not
inherited. `chase_bonus_gems.json`: reused Survival's own real, already-verified list rather than
re-running the full 38-item `verify_gem_choices.py` pass - defensible because the socket-bonus-
vs-pure-Agility question is purely a function of stat weights (confirmed byte-identical) and never
touches rotation/pet/class mechanics; spot-checked BM's own real candidates not covered by the
prior run (`Cursed Vision of Sargeras`, `Gronn-Stitched Girdle`, `Blade of the Unrequited`) with
fresh real sim calls to confirm the same conclusion holds rather than trusting the inference
blind - all three came back tied-or-loss for pure Agility, consistent.

New `Test-Beastmastery-Synthetic` character (Orc, Engineering/Blacksmithing per the real wowsims
`OtherDefaults`, seeded from `bm/dw_6p.gear.json` phase 3) - no real BM Hunter alt exists.
Real, independent sanity check before the full sweep: `cli/gear.py preset` run directly against
the raw wowsims phase3 BM build file (bypassing this project's own profile entirely) confirmed a
real Ravager pet contributing 632.5 of 2078.3 combined DPS (~30%) - genuine proof the pet/BM
subsystem fires, not just that settings parse. Full sweep then ran clean (no errors), real Achieved
BiS (8 slots) and tiered upgrades with correct set-bonus/sidegrade notes, `check_ledger_
consistency.py` 167/0. Regression: re-ran Survival Hunter's own Phase 3 sweep fresh afterward -
baseline came back byte-identical (2689.3495110209305, matching the long-established value),
672/0 clean.

**Stage 6.5 (2026-08-25): Fury Warrior, real-verified.** `profiles/tbc/fury_warrior/` built from
`sim/tbc-new/ui/warrior/dps/` (same real UI dir Arms uses, but a genuinely separate real
`fury.apl.json` - unlike Hunter's Beastmastery/Survival, Warrior's two specs don't share one apl
file). Real, confirmed-distinct EP weights from `warrior/dps/presets.ts`'s own
`P2_FURY_EP_PRESET` ("P2, P3, P4 & P5 - Fury") - genuinely different Hit/Expertise/Haste priorities
than Arms's own `P3_ARMS_EP_PRESET`, not inherited. `weapon_topology: dual_wield` confirmed via
real `handType` data on the synthetic character's actual weapons (a real Warglaive of Azzinoth
pair: handType=1 MainHand / handType=3 OffHand), not assumed from spec convention.

Real gem verification run fresh, independent of Arms's own list (per CLASSES.md's own stated
reasoning: dual_wield vs two_hand can shift the socket-bonus-vs-pure-Strength math) - all 30 of
Fury's own real socketed candidates tested via `gopt.verify_gem_choice()` directly; 4 real winners
found and adopted (`Vengeance Wrap` +7.1, `Onslaught Bracers` +6.8, `Grips of Silent Justice`
+11.3, `Leggings of the Immortal Night` +19.0 DPS, all clearly outside noise) - a genuinely
different set than Arms's own verified list, confirming the "don't inherit" rule mattered here,
not just theoretical caution. `default_enchants.json`: 10/10 verified real on the first pass (both
weapon slots real - dual-wield needs two, both `2673` "Enchant Weapon - Mongoose").

`settings_template.json` built via the real `core/build_profile_settings.py` pipeline (unlike
Hunter's hand-copy approach) - Warrior's own real `TypeAPL` rotation system means `fury.apl.json`'s
raw content is a complete, valid `player.rotation` value verbatim, same real finding Stage 6.1
already established for Arms. `class_options.json`/`consumables.json`/`loot_eligibility.json`/
`raid_buffs_overlay.json` all copied verbatim from Arms - confirmed via real source reading
(`presets.ts`'s own shared `DefaultOptions`/`OtherDefaults` blocks) that these are genuinely
class-level, not Arms-specific, before copying rather than assuming.

New `Test-Fury-Synthetic` character (Orc, Engineering/Blacksmithing, seeded from `p3_fury.gear.json`,
real `FuryTalents` string `3400502130201-05050005505012050115` confirmed from `presets.ts` directly
- noted a real, separate "Arms - Kebab" hybrid-talent variant exists in the same file but is out of
scope, not a real distinct profile per the confirmed spec inventory).

Real, independent rotation verification - Warrior has no per-phase `.build.json` files like Hunter
did, so `cli/gear.py preset` wasn't usable directly; instead built a real RaidSimRequest by hand
(`valuation._build_raid_sim_request()`, the same real function the sweep pipeline itself uses) and
ran it straight through `wowsimcli.exe`, bypassing the bridge translation step since the request
was already in its target shape. The real combat log (a genuine per-event text log, `SpellID: N`
entries) confirmed **Bloodthirst (spell 30335, real id cross-checked against
`sim/warrior/talents_fury.go`'s own `registerBloodthirst()`) fired 214 times and Whirlwind (spell
1680) fired 202 times** in a single real iteration - direct, unambiguous proof the real Fury
rotation fires, not just that settings parse. Full sweep then ran clean, real Achieved BiS and
"no real upgrades" tiers (a well-itemized synthetic BiS character, as expected),
`check_ledger_consistency.py` 46/0. Regression: Arms Warrior's own Phase 3 sweep re-run fresh
afterward - baseline byte-identical (1770.0316931322793), 1500/0 clean (same familiar
achieved-BiS-empty warning as before, not a new issue).

**Stage 6.6 (2026-08-25): Feral Cat Druid, real-verified.** `profiles/tbc/feral_cat_druid/` built
from `sim/tbc-new/ui/druid/feralcat/` - the real gear-complexity outlier flagged in the staging
plan (P1 alone splits into `bis`/`alt`/`realistic` x `6p`/`9p`) and the profile that surfaced this
session's two most serious real bugs, both now documented in CLASSES.md.

**`weapon_topology` initial assumption was wrong and caught before building further.** Blindly
copying Balance Druid's own `one_hand_plus_offhand_item` precedent (same class) would have been
wrong - checked real `handType` data on the actual BiS mainhand item at every phase (P1-P5:
Terestian's Stranglestaff, Merciless Gladiator's Maul, Vengeful Gladiator's Staff x2, Stanchion of
Primal Instinct) and found `handType=4` (TwoHand) consistently. Real TBC Feral mechanics scale
cat-form damage directly off weapon DPS, making a 2H weapon's much higher DPS budget the
consistent real BiS choice throughout - unlike Balance Druid's own genuinely phase-varying case.
Fixed to `weapon_topology: "two_hand"` before `candidate_pool.json`/`reference_bis` were built.

**Two real, sim-breaking bugs found and fixed, both silent (no error, just wrong output):**
1. `class_options.json` initially used Balance's own `"balanceDruid"` key and `innervateTarget`
   option - wrong proto oneof entirely. Real proto shows `feral_cat_druid = 13` with
   `FeralCatDruid.options` (`classOptions: {}`, empty) AND a **separate real `Rotation` message**
   (`finishingMove`/`biteweave`/`ripMinComboPoints`/`biteMinComboPoints`/`mangleTrick`/
   `maintainFaerieFire`) that has no equivalent in the generic `player.rotation` (TypeAPL) field
   every other profile built so far relies on exclusively. Added with real default values from
   `presets.ts`'s own `DefaultRotation` block. This alone did NOT fix the sim (still 0 DPS).
2. **Root cause, found via real combat-log debugging**: `core/settings_builder.py`'s
   `"distanceFromTarget": profile.get("distance_from_target", 7)` - a hardcoded fallback of 7
   yards (the pipeline's original Hunter/ranged-class default) that every profile before this one
   got away with, since Hunter is genuinely ranged and Warrior's Charge closes the gap as a real
   opener. Feral Cat has no gap-closer at all, so the silent 7-yard default put her out of melee
   range for every ability - confirmed via a hand-built `RaidSimRequest` + direct `wowsimcli.exe`
   call showing "Casting {SpellID: 768}" (Cat Form) looping and "[Player (#1)] No available
   actions! Pausing rotation for 100ms due to resources / CDs." in the real log. Real Feral
   `OtherDefaults` in `presets.ts` specifies `distanceFromTarget: 0` - added explicitly to
   `profile.json` (`"distance_from_target": 0`), rebuilt `settings_template.json`, and the sim
   immediately worked: `{'player_dps': 2233.929242315233, 'player_stdev': 78.4, 'combined':
   2233.929242315233, 'ew_uptime': 0.9}`. Both CLASSES.md-documented now as required checks for
   any future melee profile.

Real EP weights from `P1_EP_PRESET` (`presets.ts`): `{"0":0.78,"1":1.16,"17":0.35,"19":0.35,
"20":1.02,"21":0.77,"22":0.41,"23":0.16,"24":1.02,"41":3.13}` - index 19 (StatFeralAttackPower)
and 41 (StatPhysicalDamage) cross-checked against `sim/tbc-new/proto/common.proto` since neither
appears in any prior profile's own weight table. `consumables.json` matches Enhancement Shaman's
real melee-package convention (potId 22838, flaskId 22854, etc.), not Balance's caster one -
correct spec-appropriate sourcing, not a copy-paste leftover. `loot_eligibility.json` broadened
from Balance's `[2,4,8]` to `[2,3,4,6,8]` (added Fist/Polearm, real Feral-eligible weapon types).

`default_enchants.json` rebuilt fresh after the distance-from-target fix (the pre-fix run had
produced a false all-`+0.00` result, itself a real reason the "when everything shows +0.00, the
sim is broken, not the enchants" CLASSES.md entry is worth having) - clean 11/11 KEEP, real
sensible deltas (head +18.56, shoulder +17.24, back +13.48, chest +19.03, wrist +8.13, hands
+17.21, legs +24.63, feet +6.62, ring1/ring2 +12.88 each, mainhand +39.37). Gem verification: all
21 real socketed candidates in her own `candidate_pool.json` tested fresh via
`gopt.verify_gem_choice()` - every single one showed a negative delta (matching the primary
Agility gem always beats chasing a socket bonus), so `chase_bonus_gems.json` correctly stays
empty, a real verified negative result, not an unfinished check.

New `Test-FeralCat-Synthetic` character (NightElf, Engineering/Enchanting, seeded from
`p3_6p.gear.json`, real Standard-talents string confirmed from `sim.ts`'s
`Presets.StandardTalents.data`, used at 3 real call sites - a second real "Monocat" stay-in-cat-
form variant exists but Standard is the confirmed default).

Real rotation verification via the hand-built-RaidSimRequest + direct `wowsimcli.exe` technique
(no per-phase `.build.json` for this class either): Shred's real spell ID is 27002
(`sim/druid/shred.go`'s own `registerShredSpell()`), Rip's is 27008 (`sim/druid/rip.go`'s
`registerRipSpell()`) - a 100-iteration real combat log showed **Shred firing 430 times and Rip
firing 205 times**, direct proof the real cat-form rotation fires (not Wrath/Starfire). Full sweep
then ran clean (real Achieved BiS across 10 slots, real Malorne Harness 2pc set-bonus math
correctly flagged as a net -82.5/-86.4 DPS per-piece loss offset by a +91.4 2pc bonus, real upgrade
candidates in T6/T4/TBC-Heroics/Other), `check_ledger_consistency.py` 117/0 clean with **no**
achieved-BiS-empty warning (a fully-itemized synthetic BiS character, unlike every prior synthetic
test char). Report built and validated via `check_ledger_consistency.py --html`, 121/0 clean
(embedded DATA blob byte-matches `ledger_data_phase3.json`) - the Claude Browser tool's sandbox
blocks `file://` access so a direct visual open wasn't possible, but the structural HTML check
already verifies the embedded data byte-for-byte, matching the bar used for prior stages' own
report verification. Regression: Balance Druid's own Phase 3 sweep re-run fresh - baseline
byte-identical (1100.271068998754, full cache hit, 0.7s), `check_ledger_consistency.py` 1209/0
clean (same familiar achieved-BiS-empty warning as before, not new).

**Stage 6.7 (2026-08-25): Combat Rogue, real-verified.** `profiles/tbc/combat_rogue/` built from
`sim/tbc-new/ui/rogue/dps/` - the first Rogue profile, `dual_wield` (real handType=2 OneHand
confirmed on both p1.gear.json weapons, weaponType=9 Sword). Clean bootstrap, no sim-breaking bugs
this time (unlike Feral). `RogueOptions`/`Rogue.Rotation` are both real, empty `{}` proto messages
- confirmed no per-spec rotation config exists for Rogue at all, everything is APL-driven
(`swords.apl.json`, "SS/Hemo/Shiv"). Real, non-obvious finisher finding: the apl's real finisher is
**Rupture** (spell 26867, 166 casts in a 100-iteration combat log), not Eviscerate as the plan's
own STOP wording assumed - Sinister Strike (26862, the builder, 331 casts) + Slice and Dice (6774,
63 casts) round out the combo-point rotation. Cross-checked directly against
`sim/rogue/rupture.go`/`slice_and_dice.go`, not assumed.

Real EP weights from `rogue/dps/presets.ts`'s own `P1_EP_PRESET` ("Combat Swords") - PseudoStat
MainHand/OffHandDps weights present in the source preset omitted from `stat_weights.json`, matching
the established convention (this tool's prefilter only scores core Stat indices). Real, distinct
consumables shape: `battleElixirId`+`guardianElixirId` (no flask) and only an off-hand weapon imbue
(`ohImbueId`, no `mhImbueId`) - used exactly as `presets.ts`'s own `DefaultConsumables` specifies,
nothing invented (no drums/scrolls/explosives, none appear in Rogue's own real preset). Only P1-P3
(+ a separate, non-phase-indexed `preraid.gear.json`) real gear_sets exist - no P4/P5, a real,
confirmed data gap matching the pattern already found for other newer classes.

`default_enchants.json`: 10/10 verified clean on the first pass (both weapon slots real, `2673`
"Enchant Weapon - Mongoose" on each). Gem verification: 19 real socketed candidates tested fresh;
2 real, non-tied winners found (`Edgewalker Longboots` +11.09, `Shadowmaster's Boots` +9.04) -
`settings_template.json` rebuilt after adding them since her own equipped boots (Shadowmaster's)
were one of the two, meaning the pre-update settings had baked in a stale, suboptimal gem choice
for that slot. `set_bonus.py` parses Rogue's real `sim/rogue/items.go` cleanly (5 sets - Gladiator's
Vestments, Assassination Armor, Netherblade, Deathmantle, Slayer's Armor - all standard 2/4-piece
inline-map form, no new Go-source form needed).

New `Test-CombatRogue-Synthetic` character (Human, Engineering/Enchanting, seeded from
`p3.gear.json`, real Combat Swords talents string `0053201252-023305200005015002321151` from
`presets.ts` directly). Full sweep ran clean (real Achieved BiS across 9 slots, real Deathmantle
set-bonus math correctly flagging 4 individually-negative pieces offset by their own 2pc/4pc
bonuses, real T5/T6 ring upgrades found, real 2H-weapon side-analysis correctly ran since Rogue is
`dual_wield` - "No 2H weapon beats current gear" - unlike Feral's `two_hand` profile where that
section is skipped entirely), `check_ledger_consistency.py` 130/0 clean (121/0 -> 130/0 with HTML,
no achieved-BiS-empty warning). Regression: zero `core/` files were modified for this stage besides
the purely-additive `character_profiles.py` entry, so no shared-code regression risk existed; spot-
checked Arms Warrior's cached baseline (1770.0316931322793) against the last known-good value
recorded in Stage 6.5's own regression check - unchanged.

**Stage 6.8 (2026-08-25/26): Shadow Priest, real-verified.** `profiles/tbc/shadow_priest/` built
from `sim/tbc-new/ui/priest/dps/` - `one_hand_plus_offhand_item` topology confirmed via real
`handType` data across all 4 gear files: preraid/P1/P2 use a real 1H weapon + offhand (Orb of the
Soul-Eater); P3's real BiS switches to a 2H staff (Zhar'doom, Greatstaff of the Devourer - the same
real item Feral Cat Druid's own P5 BiS uses) with no offhand. A real second `test.apl.json` exists
alongside `default.apl.json` but is never imported in `presets.ts` - confirmed dev fixture, not a
second real rotation, resolving the exact ambiguity the staging plan flagged checking for.

`PriestOptions` has real `armor`/`use_shadowfiend` fields beyond `preShadowform`, but `presets.ts`'s
own `DefaultOptions` only sets `preShadowform: true` - used exactly that (not invented). Real,
live-verified finding: Shadowfiend still summons and contributes real DPS (21.1 avg in a 3000-
iteration test) even with `use_shadowfiend` left at its real proto default (unset/false) - the APL
alone drives the pet summon, confirming that toggle is legacy/inert for a `TypeAPL` rotation, not a
required input. `Priest.Rotation` is a real, empty `{}` proto message, same as Rogue - no per-spec
rotation config needed. Real combat-log verification: Mind Flay (546 casts), Vampiric Touch (462),
Shadow Word: Pain (158), Shadowform pre-cast (2) - real, confirmed Shadow rotation, not Wrath/
Starfire or any other spec's spells.

Real EP weights from `priest/dps/presets.ts`'s own `P3_EP_PRESET` - a real, distinct `P1_EP_PRESET`
also exists (real SpellHitRating/MP5 differences from itemization progression) but wasn't used,
matching this tool's phase3-primary convention. `raid_buffs_overlay.json` left empty despite
Priest's own real `DefaultPartyBuffs` specifying a caster-group totem set (manaSpringTotem/
wrathOfAirTotem) different from the shared baseline's melee-group totems - every prior caster
profile already made the same call to keep raid-comp assumptions uniform across all profiles rather
than tailor per-class, so this isn't a new deviation (see QUESTIONS.md if this should be revisited).

`default_enchants.json`: 8/11 verified, 3 legitimate drops - `Enchant Cloak - Subtlety` (threat
reduction, real zero DPS by design) and `Enchant Boots - Boar's Speed` (movement, real zero DPS),
both confirmed in the DB and correctly recognized as intentional utility picks, not a data gap; the
third, `Enchant Chest - Exceptional Stats`, showed a real but tiny +0.60 DPS delta that didn't clear
the tool's own noise threshold - a legitimate near-zero result, not a bug in the check. Gem
verification: 20 real socketed candidates tested, all negative/non-tied - `chase_bonus_gems.json`
correctly stays empty, same real "pure Spell Damage always wins" result already found for Feral Cat
Druid's own Agility gem.

New `Test-ShadowPriest-Synthetic` character (Undead, Enchanting/Tailoring - real professions from
`presets.ts`'s own `OtherDefaults`, not guessed - seeded from `p3.gear.json`, real Shadow talents
string `500230013--503250510240103051451` from `StandardTalents` directly). Full sweep ran clean
and exercised a real feature not seen fire in any prior stage's own summary: the sidegrade-check
pass flagged 3 real "don't compete now, but bank it" combos (e.g. Cowl of the Illidari High Lord +
Blood-cursed Shoulderpads, a real +5.9 DPS sidegrade once Absolution Regalia's 2pc bonus is already
broken by another swap). `check_ledger_consistency.py` 143/0 clean. Zero `core/` files modified
besides the additive `character_profiles.py` entry - no regression risk.

**Stage 6.9 (2026-08-26): Arcane Mage, real-verified.** `profiles/tbc/arcane_mage/` built from
`sim/tbc-new/ui/mage/dps/` - the profile that surfaced this session's big new engine-version gotcha
(now in CLASSES.md): wowsims' own real canonical P2/P3 preset builds all select `arcaneBraid.apl.json`
(`ROTATION_PRESET_ARCANEBRAID`), whose raw content is a `TypeSimple` rotation encoding `Mage.Rotation`'s
own `conserveStart`/`conserveEnd`/`delayMajorCDs` fields. Using it verbatim produced a real, silent 0
DPS ("No available actions! Pausing rotation" from t=0.00). Root cause, confirmed by grep: no real Go
code in `sim/mage/*.go` consumes those field names - only the proto-generated file does. Cross-checked
against Hunter's own real `TypeSimple` builds (`bm/dw_6p.build.json`), which DO produce real nonzero
DPS via a live `cli/gear.py preset` call - proving this isn't "TypeSimple never works," just that THIS
class's engine-side wiring for it is dead in the current sim version. Switched to `arcane.apl.json`
(real `TypeAPL`, defined in `presets.ts` but never wired into any `makePresetBuild` call - "unreferenced
by a preset build" turned out not to mean "non-functional") - real, confirmed nonzero DPS (2013.2) and
**Arcane Blast firing 332 times** in a 100-iteration combat log.

`one_hand_plus_offhand_item` topology confirmed via real `handType` across 5 gear files - genuinely
the most complex fork found yet: preraid/P1 use 1H+offhand, P2 switches to a 2H staff, and P3 forks
into two real, meaningfully different FULL builds (not just a weapon swap - back/legs/trinket2 also
differ): "Arcane - Staff" (Zhar'doom, the same real item Priest's own P3 BiS uses) and "Arcane - Sword"
(Tempest of Chaos + a real offhand). Used Staff as canonical (listed first in `presets.ts`, no stated
wowsims preference) - both real-verified via direct sim (Staff 2013.2 DPS, Sword 2005.6 DPS, both with
real confirmed Arcane Blast casts), satisfying the plan's "both P3 variants" STOP requirement, but
Sword's own unique items were NOT folded into `candidate_pool.json` as a full alternate set - see
QUESTIONS.md for this real judgment call.

Real EP weights from `mage/dps/presets.ts`'s own `P3_EP_PRESET` (two other real, distinct presets -
P1/P2 - exist but weren't used, matching the phase3-primary convention). `default_enchants.json`:
7/9 verified, 2 legitimate drops (same real zero-DPS utility enchants already found for Priest -
Cloak Subtlety threat reduction, Boar's Speed movement). Gem verification produced a real, genuinely
different result from every prior caster profile: 12 of 16 real socketed candidates were non-tied
POSITIVE winners (Priest and Feral both found zero) - Arcane's own real Hit/Haste/Crit-heavy EP
weights (2.4/0.77/0.76) make chasing a socket bonus beat pure Spell Damage far more often than for a
flatter-weighted caster. `settings_template.json` rebuilt after adding the winners since 5 of them
overlapped her own equipped gear.

New `Test-ArcaneMage-Synthetic` character (Gnome, Engineering/Tailoring, seeded from
`p3ArcaneStaff.gear.json`, real Arcane talents string `2500052300030150330125--053500031003001`
from `ARCANE_TALENTS` directly). Full sweep ran clean, real Tirisfal Regalia set-bonus math
correctly flagged (Leggings of Tirisfal -40.1 DPS alone, +144.6/+118.1 2pc/4pc bonuses), a second
real sidegrade-banking case (2 flagged). `check_ledger_consistency.py` 199/0 clean. Zero `core/`
files modified besides the additive `character_profiles.py` entry - no regression risk.

**Stage 6.10 (2026-08-26): Retribution Paladin, real-verified.** `profiles/tbc/retribution_paladin/`
built from `sim/tbc-new/ui/paladin/retribution/` - hit the SAME real TypeSimple-is-dead-in-this-
engine-version gotcha just found for Arcane Mage: `presets.ts`'s own canonical P1/P2/P3 preset
builds all select `rotationType: TypeSimple` + `APL_SIMPLE` (`RetributionPaladin.Rotation`'s
`useExorcism`/`consecrationRank`/`delayMajorCDs`/`prepullSotC`/`aura` fields), but grepping
`sim/paladin/*.go`/`sim/paladin/retribution/*.go` for those exact field names finds only the
proto-generated file - confirmed dead, same as Mage. Switched to `default.apl.json` (real
`TypeAPL`) - real, confirmed nonzero DPS (2108.6) and **Seal of Command procs firing 292/140 times
plus Crusader Strike 125 times** in a 100-iteration combat log, matching the plan's own STOP
wording exactly.

`weapon_topology: two_hand` confirmed consistently via real `handType=4` across ALL 5 gear files
(preraid/P1/P2/P3/P3Bulwark) - unlike Priest/Mage's own phase-varying cases, no fork here. Per the
plan's own explicit caution to verify rather than assume, checked what "P3Bulwark" actually differs
by: real diff against plain P3 is exactly ONE slot (chest - Bulwark of the Ancient Kings vs
Midnight Chestguard), not a second full build - plain P3 used as canonical, Bulwark's own chest
item not specially added to the pool (it surfaced anyway in the real sweep, as a real "Crafted"
upgrade candidate sourced independently - see below). Real, distinct armor/weapon eligibility from
every other profile: Plate-capable (`armor_ok: [3,4]`, mirroring Arms/Fury Warrior's own Mail+Plate
convention) and Mace/Polearm/Sword only (no Axe/Dagger/Fist), Libram-only ranged slot (not a wand or
physical ranged weapon - Paladins have no ranged weapon skill in TBC).

`default_enchants.json`: 9/9 verified clean on the first pass. Gem verification: 17 real socketed
candidates tested, all negative/tied - `chase_bonus_gems.json` correctly stays empty.

New `Test-RetPaladin-Synthetic` character (Blood Elf, Engineering/Blacksmithing - real race AND
professions sourced directly from `presets.ts`'s own `OtherDefaults`, not guessed, seeded from
`p3.gear.json`, real Retribution talents string `5-053201-0523005120033125331051` from
`DefaultTalents` directly). Full sweep ran clean - real T5/T6 upgrades found, "Bulwark of the
Ancient Kings" (the P3Bulwark variant's own chest item) surfaced independently as a real +12.0 DPS
Crafted-tier candidate anyway, confirming the earlier judgment call not to special-case it was
sound. `check_ledger_consistency.py` 195/0 clean.

**Real, disclosed upstream DB data-quality bug found (not fixed - cosmetic only, doesn't affect any
computed DPS number):** the "Vanilla carryover" tier's "Libram of Hope" upgrade candidate showed a
garbled source description - `Drop: Isalien"].." - "..format(AL["Tier %s Sets (Dire Maul)`. Traced
to the vendored sim's own `db.json`: NPC id 16097's real `name` field literally contains leaked
Lua/AceLocale source text (`'Isalien"].." - "..format(AL["Tier %s Sets'`) instead of a clean name -
almost certainly meant to be "Isalien" (a real Dire Maul vendor who sells this exact item in live
WoW), corrupted by whatever upstream tool wowsims used to scrape NPC names. Per CLAUDE.md's own
ground-rule distinction, this is a DB *data-completeness* issue, not a sim *model* issue - the
computed DPS value (+35.8) is real and correct, only the display label is garbled. Not patched -
touching vendored DB data is out of scope and risks masking a future real upstream fix; flagged in
QUESTIONS.md for awareness instead.

**Stage 6.11 (2026-08-26): Affliction Warlock, real-verified - and the Warlock class-level
bootstrap all three specs reuse.** `profiles/tbc/affliction_warlock/` built from
`sim/tbc-new/ui/warlock/dps/` - real, confirmed: Warlock's own gear_sets are named by RAID TIER
(preraid/t4/t5/t6/za/swp), not by phase (p1-p5) like every other class. Resolved the real
tier-to-phase mapping directly from `db.json`'s own per-item `phase` field (authoritative, not
guessed): t4=phase1, t5=phase2, t6=phase3, za mostly clusters with t6 (phase3, a few phase4 rep
items - not enough for its own phase4 reference_bis), swp=phase5. Built phase1/2/3/5 reference_bis
- phase4 is a real, disclosed gap. `one_hand_plus_offhand_item` topology confirmed via real
`handType` (t4/t5/preraid/swp use 1H+offhand; t6/za both use the real 2H Zhar'doom staff, the same
real item Priest's and Arcane Mage's own P3 staff builds use).

No TypeSimple gotcha here - all 4 real Warlock apls (`affliction`/`demonology`/`destruction`/
`destro_fire`) use `TypeAPL` directly via `makePresetAPLRotation`, confirmed once at the class
level. `Warlock.Rotation` is a real, empty `{}` proto message, same as Rogue/Priest.

Real, non-obvious combat-log finding: the canonical `TalentsAffliction` string
(`05022221112351055003--50500051220001`) does NOT actually spec into Unstable Affliction, despite
Affliction's real APL explicitly referencing it (`dotIsActive` check on spell 30405) - confirmed by
counting the Affliction-tree talent-string segment (20 characters for 21 real talent fields,
`unstable_affliction` being proto field 21) and cross-checking `warlock.Talents.UnstableAffliction`
gates `registerUnstableAffliction()` in `talents.go` - trailing zeros are truncated in this string
format, so the missing 21st digit means 0 points. A 100-iteration combat log confirmed zero UA
casts, and separately confirmed her assigned curse is Curse of Elements (a raid-utility curse, per
the real `P1_AFFLICTION_DEFAULT_SETTINGS` override), not Curse of Agony - so neither of the plan's
own two named example DoTs actually fire for this specific canonical build. The REAL DoT-stacking
rotation that does fire, confirmed via combat log: **Immolate (179), Corruption (162), Siphon Life
(195)** casts, plus Shadow Bolt (316) as filler - a real, working, just differently-shaped
Affliction rotation than assumed. Real pet: Imp (curseOptions=Elements/summon=Imp/
sacrificeSummon=false per the real per-spec override), contributing 82.9 avg DPS.

Real EP weights from `warlock/dps/presets.ts`'s own `P1_AFFLI_DEMO_DESTRO_EP` - explicitly,
confirmed-real SHARED across Affliction/Demonology/Destruction (not per-spec), the class-level
bootstrap this stage exists to build once for reuse by 6.12/6.13. `default_enchants.json`: 6/9
verified, 3 legitimate drops (same familiar zero/near-zero-DPS utility enchants). Gem verification:
25 real candidates tested, 10 real non-tied winners - a genuinely different, larger-magnitude
result than Priest/Feral's own "always zero winners" pattern, closer to Arcane Mage's own
Hit/Haste-favoring result (Warlock's own real EP weights are meaningfully Hit/Haste-heavy too).

New `Test-Affliction-Synthetic` character (Undead, Engineering/Tailoring, seeded from `t6.gear.json`
- phase3, this tool's primary convention - real Affliction talents string from `TalentsAffliction`
directly). Full sweep ran clean, real Voidheart Raiment set-bonus math correctly flagged (4 pieces
individually -50 to -95 DPS, offset by +21.8/+40.2 2pc/4pc bonuses), a third real sidegrade-banking
case. `check_ledger_consistency.py` 167/0 clean.

**Stage 6.12 (2026-08-26): Demonology Warlock, real-verified.** `profiles/tbc/demonology_warlock/`
reuses Affliction's own class-level bootstrap (`stat_weights.json`/`loot_eligibility.json`/
`raid_buffs_overlay.json`/`consumables.json`/gear-tier data copied verbatim, all real class-level,
not spec-level). Real, confirmed correction to the staging plan's own assumption: wowsims' own
canonical `DEMONOLOGY_BUILD` uses `TalentsDemoRuin` ("Demo/Ruin"), **not** `TalentsDemoFelguard` -
the plan had guessed Felguard as "matching TBC live-era convention" without checking the real
source; the real, sourced default is Demo/Ruin, used here instead of the guess.

Real, confirmed pet-focused rotation: **Succubus pet contributes 311.9 avg DPS, ~14% of her 2532.3
combined DPS** (curseOptions=Recklessness/summon=Succubus/sacrificeSummon=false per the real
per-spec override) - satisfies the plan's own "pet DPS contribution visible in the breakdown" STOP
requirement directly from the real pet-DPS breakdown, no combat-log grep needed this time.

`default_enchants.json` reused from Affliction directly (byte-identical gear/candidates, no
rotation-dependent reason for a slot enchant choice to differ) - re-verified clean, same 6 real
KEEP results. **Gem verification was deliberately NOT reused** despite CLASSES.md's own stated
exception nominally applying (byte-identical EP weights) - ran it fresh instead, and this turned
out to matter: only 1 real winner (Girdle of Ruination) vs Affliction's own 10, and several of
Affliction's own real winners (the Voidheart-family items) are real, non-tied LOSSES here -
Demonology's real ~14%-of-DPS pet contribution shifts the practical gem-choice math enough to flip
outcomes, not just a theoretical concern the CLASSES.md exception's own caveat already anticipated.
`settings_template.json` rebuilt after the real, single winner (her equipped gear didn't overlap
it, but rebuilt to keep the file consistent with the verified chase list regardless).

New `Test-Demonology-Synthetic` character (Orc, Engineering/Tailoring, seeded from `t6.gear.json`,
real `TalentsDemoRuin` string directly). Full sweep ran clean, same real Voidheart Raiment
set-bonus math pattern (this time -55 to -131 DPS per piece, +27.6/+32.0 2pc/4pc bonuses - larger
magnitude than Affliction's own, consistent with Demonology's higher overall DPS baseline).
`check_ledger_consistency.py` 209/0 clean.

**Stage 6.13 (2026-08-26): Destruction Warlock, real-verified - closes out the 11-stage plan
(6.3-6.13).** `profiles/tbc/destruction_warlock/` reuses Affliction's own class-level bootstrap.
Real, base (unmodified) `DefaultOptions` from `presets.ts` (curseOptions=Recklessness,
summon=Succubus, sacrificeSummon=true) - `DESTRUCTION_BUILD` uses `P1_DEFAULT_SETTINGS` directly
with no per-spec override, unlike Affliction/Demonology. Real talents: `TalentsDestruction` - a
real, distinct `TalentsDestroNightfall` alternate exists in `presets.ts` but, like Mage's
`arcane.apl.json`/Paladin's dead `TypeSimple` path, is never wired into any real preset build,
confirmed not the canonical default.

Gem verification run fresh (not reused from Affliction, following Demonology's own real precedent
that pet/rotation differences can matter): 9 real non-tied winners, closely matching Affliction's
own 10 - expected, since Destruction (sacrificed pet, no ongoing pet DPS share) is EP-profile-wise
closer to Affliction than to Demonology's own pet-heavy case. `default_enchants.json` reused from
Affliction directly (byte-identical), re-verified clean, same 6 real KEEP results.

**Real Destro-Fire alternate build, verified per the plan's own explicit requirement, without a
separate full profile or sweep** (its own real gear data only reaches phase1 - `destro_fire_t4`,
confirmed via the same `db.json`-sourced tier mapping used throughout this stage - so a dedicated
phase3 sweep isn't meaningful for it the way it is for every other profile). Built
`settings_template_fire.json` directly via `settings_builder.build_settings()` using
`destro_fire.apl.json`, the real `destro_fire_t4.gear.json` equipment, and the real per-spec
override from `P1_FIRE_DEFAULT_SETTINGS` (summon=Imp, sacrificeSummon=true, conjuredId=22788).
Real, confirmed contrast via two separate 100-iteration combat logs: **base Destruction is
Shadow-Bolt-primary (370 casts, 0 Incinerate)**; **Destro-Fire is Incinerate-primary (350 casts, 0
Shadow Bolt)** - exactly the real spell-mix contrast the plan's own STOP wording asked to confirm.

New `Test-Destruction-Synthetic` character (Blood Elf, Engineering/Tailoring, seeded from
`t6.gear.json`, real `TalentsDestruction` string directly). Full sweep ran clean, same real
Voidheart Raiment set-bonus pattern (-64 to -142 DPS per piece, +34.2/+17.6 2pc/4pc bonuses).
`check_ledger_consistency.py` 167/0 clean.

**Plan-closing regression check, real not assumed**: zero `core/` files were modified across the
entire 6.3-6.13 arc besides the purely-additive `character_profiles.py` registry (confirmed via
`git status --porcelain core/` showing nothing else touched) - so the real risk surface for a
Warlock-stage regression was already near-zero. Verified anyway: re-checked every one of the 15
total profiles' own cached `baseline_screened` values in one pass - all present, all real, all
sensible; Arms Warrior's own value (1770.0316931322793) matches byte-for-byte against the exact
figure recorded in Stage 6.5's own regression check, confirming zero drift across the entire
session's 8 new-profile stages (6.4-6.13). The staging plan at
`C:\Users\<user>\.claude\plans\staged-purring-lynx.md` is now fully executed - every stage's own
STOP checkpoint met, every profile's report built and validated, every real finding documented here
and in QUESTIONS.md/CLASSES.md for review.

**Fixed 2026-08-27/28: `set_bonus.best_four_of_five()` silently kept her current gear in the
excluded slot instead of testing its real best alternative, unless her current item there already
happened to belong to the same set being evaluated.** Found by the user cross-checking Lerynia's
own real Phase 3 report against a real wowsims.com reference build: their reference kept
Gronnstalker's Helmet and swapped Legs for Bow-stitched Leggings; this tool's own (pre-fix) report
did the opposite (kept current gear in every excluded slot, since her current gear is Rift Stalker
Armor throughout - a different set entirely, so the old code's `current_item.get("setName") ==
set_name` gate never fired). Verified live via real sim (30000 iter): her current legs (Void Reaver
Greaves) understated the "leave legs out" combo by ~46 DPS relative to Bow-stitched Leggings, which
she wasn't even wearing.

Two real layers fixed, not one, per the user's explicit "no time constraints, go for a real proper
fix" (2026-08-27):
1. The excluded slot now ALWAYS gets a real "keep current gear" sim AND a real "swap to the best
   non-set alternative" sim, regardless of what her current gear there happens to be - the existing
   max-by-real-DPS selection picks whichever's actually better, honestly, per slot.
2. A second, deeper gap found while building (1): the single-candidate crude-EP-score prefilter
   that used to pick "the" alternative (`best_non_set_alt()`) isn't reliable enough to trust alone -
   confirmed live, it picked "Shady Dealer's Pantaloons" over the real, decisively-better
   "Bow-stitched Leggings" for Lerynia's own legs slot (exactly the socket-bonus/threshold-blind-spot
   class of error CLAUDE.md's own ground rules already warn a linear score will make). Real,
   decisive fix: `all_non_set_alts()` replaces the single crude-score guess - now real-sims EVERY
   real non-set candidate in the slot's own pool (drawn from the SAME merged curated+full-sweep
   `candidates` dict `run_full_sweep_mv.py` already builds by the time it calls this function, not
   a narrower pool) and lets the actual DPS numbers decide.

Real, final, production-verified answer for Lerynia's own Gronnstalker's Armor (fresh full sweep,
fix applied, full real candidate pool): **leave Head out, use Cursed Vision of Sargeras there**
(not her current Rift Stalker Helm, not Gronnstalker's Helmet) - beats the full 5-piece set by
+30.2 DPS (screened). This ties back to her own separate Q1 about Cursed Vision of Sargeras: its
own solo MV really is bad (-51.8 DPS alone, a real downgrade) - but it's the objectively correct
piece for THIS specific set-transition combo, once she's already committed to breaking Rift
Stalker Armor via the other 4 Gronnstalker pieces. Both of her questions resolved to the same real
underlying mechanic once verified properly, not two unrelated findings.

`best_four_of_five()`'s own return dict gained `excluded_slot_alt` (the real winning alternative's
name/id, or `None` when keeping current gear won) replacing the removed, never-used
`excluded_slot_uses_alt` boolean from an intermediate fix pass; `run_full_sweep_mv.py`'s own
console print now names the real winning alternative item, not just "non-tier". `best_non_set_alt()`
(single-guess) kept unchanged for `rescue_check()`'s own, narrower, already-self-verifying use (it
runs its own confirming sim on top of the guess) - only `best_four_of_five()`'s own use of it was
replaced.

Regression, real not assumed: `check_ledger_consistency.py` clean for Lerynia (653/0). Re-ran Arms
Warrior (no real 5pc set qualifies for her - no "Best combo" line, matching prior sessions) and
Balance Druid (real "Best combo for Moonglade Raiment" line, correctly names a real alternative,
Thunderheart Vest) - both profiles' own `baseline_screened` values stayed byte-identical to their
long-established known-good figures, confirming this change only affects set-bonus-combo selection
and its printed/reported alternative, never the underlying per-item MV numbers.

**Fixed 2026-08-28: Achieved-BiS Weapon row (and, same root cause, Ring/Trinket too) hidden whenever
EITHER real slot in a shared display bucket had any upgrade candidate.** Real bug logged in
`TODO.md`/`QUESTIONS.md` since 2026-08-26, picked back up per the user's explicit "start with 1"
after the `best_four_of_five()` fix landed. User's chosen direction: split into independent rows
per real slot (matching ring1/ring2's own existing precedent), not a single-row-plus-note.

Root cause, same shape as the `best_four_of_five()` bug: `mainhand`/`offhand` (and `ring1`/`ring2`,
`trinket1`/`trinket2`) share one display bucket (`SLOT_DISPLAY`), but the exclusion check
(`slots_with_upgrades`) operated at the DISPLAY level - any real upgrade candidate anywhere in the
bucket hid the WHOLE bucket, even when one of the two real slots was independently, genuinely
maxed. Real, decisive fix: `marginal_value.mv_single()` now returns `best_slot` - which specific
real slot its own best trial substituted into. Not arbitrary: for a shared-pool item, replacing
whichever of the two real slots is weaker always gives the bigger DPS gain, so `best_slot` reliably
identifies which real slot a rational player would actually put a given candidate in. The
achieved-BiS loop now tracks `real_slots_with_upgrades` (real slot names) instead of display-bucket
names, and only excludes the SPECIFIC real slot each qualifying candidate's own `best_slot` points
at - a single-real-slot bucket (Head, Neck, ...) is unaffected either way, no ambiguity there to
begin with. `best_slot` also gets carried through the confirm/resolve merge-back (previously only
`mv`/`noise_stdev`/`tied_within_noise`/`raid_ap_per_attacker` were copied over at higher precision),
for full consistency even though a slot flip between precision tiers is very unlikely in practice.

Real, live confirmation the fix does real work, not just theoretical: Arms Warrior's own fresh
Phase 3 report now shows `Ring: [Garona's Signet Ring]` and `Trinket: [Bloodlust Brooch]` as
single-item Achieved-BiS rows - previously these buckets would have shown either BOTH items or
NEITHER, never a genuine partial result. `baseline_screened` stayed byte-identical
(1770.0316931322793) for Arms Warrior and (2110.8092691624342) for Retribution Paladin, confirming
zero impact on the underlying MV numbers - only the Achieved-BiS display logic changed.
`check_ledger_consistency.py` clean for Lerynia (653/0) and Arms Warrior (1506/0). Retribution
Paladin (a real `two_hand`-topology profile, single real weapon slot) spot-checked too, confirming
the fix correctly no-ops for single-real-slot buckets.

`TODO.md`'s own entry for this is now resolved - removed.

## 2026-08-28 — Raid-buffs class-realism rework, all 15 profiles (sim commit `3267f8d`)

Per the user's AskUserQuestion choice ("Make each class-realistic"), replaced the shared,
Hunter-shaped raid-buffs baseline (`profiles/tbc/_shared/raid_buffs_received.json`, still every
profile's default) with a real, per-class `raid_buffs_overlay.json` for all 15 profiles - sourced
directly from each class's own real `DefaultPartyBuffs`/`DefaultRaidBuffs` in its
`sim/tbc-new/ui/<class>/<spec>/presets.ts` (or the class-level `presets.ts` for Warrior, which
keeps `WarriorPresets.DefaultPartyBuffs` shared across Arms/Fury rather than per-spec), never
invented or assumed. The `{**shared, **overlay}` merge in `settings_builder.py` is additive-only -
a caster profile that doesn't receive a melee totem has to EXPLICITLY set it to
`"TristateEffectMissing"` (or `false`), not just omit the key, since omitting never removes a key
already present in the shared baseline. A `_MELEE_TOTEMS_OFF` constant (used in the batch-apply
script, not committed as its own file) covers the 8 non-melee profiles' shared explicit-off set:
`graceOfAirTotem`/`strengthOfEarthTotem`/`windfuryTotem`/`battleShout`/`leaderOfThePack`/
`totemTwisting`, all `TristateEffectMissing`/`false`.

Real per-class content landed (party/player buffs only - `raidBuffs`/`debuffs` stay empty, out of
scope for this pass): Survival/Beastmastery Hunter (Braided Eternium Chain, Improved Windfury from
a party shaman); Arms/Fury Warrior (Ferocious Inspiration 2, Braided Eternium Chain, Improved
Windfury, Leader of the Pack); Retribution Paladin (Regular Mana Spring, Improved Windfury,
explicit Sanctity Aura=Missing since she provides her own); Enhancement Shaman (Ferocious
Inspiration 2, Braided Eternium Chain, Leader of the Pack - Grace of Air/Strength of Earth/Windfury
Totem explicitly Missing, matching the real preset's own omission, since Enhancement casts her own
Windfury Totem via her APL's "Totems" action group, not via a partyBuffs setting); Combat Rogue and
Feral Cat Druid left at `{}` (confirmed: no real wowsims-authored preset exists for either, nothing
to source); Balance Druid, Elemental Shaman, Shadow Priest, Arcane Mage, and the Warlock triad all
get `_MELEE_TOTEMS_OFF` plus their own real caster buffs (Moonkin Aura, Wrath of Air Totem, Chain
of the Twilight Owl, Eye of the Night, Totem of Wrath, Mana Spring/Mana Tide as appropriate).

**Real, measured effect, not assumed**: a direct A/B on Balance Druid (Béarforceone) with the old
empty overlay vs the new one showed a real **+204.6 DPS** shift from the buffs alone - this was
never a cosmetic change.

**Real sequencing bug found and fixed during verification** (Béarforceone/Elemental Shaman, "batch
1"): both showed byte-identical `baseline_screened` to their PRE-overlay values despite genuinely
different settings fingerprints and 548 fresh `sim_cache.json` entries under the new fingerprint -
looked exactly like a caching bug at first. Root cause, found via `ls -la --time-style=full-iso`:
`tiered_report_phase3.json` was written at 00:22:35, but `raid_buffs_overlay.json`/
`settings_template.json` weren't rebuilt until 00:37:51/00:38:12 - the sweep had genuinely run
BEFORE the settings rebuild in the original batch launch, a pure launch-ordering mistake, not a
bug in the fingerprint/cache mechanism itself (which is confirmed correct). Fixed by simply
re-running both sweeps against the now-current files.

**Real, more serious bug found during verification** (Enhancement Shaman, "batch 2" - see
CLASSES.md's new entry): her sweep completed cleanly (exit 0, consistency check clean) but
`baseline_screened` came back at a suspiciously low 885.7 DPS against melee peers all in the
2400-3900 range. Diagnosed via a direct action-log pull (`adapter.run()` on her exact baseline
gear config, per-action `targets[].hits/damage` summed) - her white melee auto-attack action
(`OtherActionAttack`, both mainhand and offhand) showed **zero hits, zero misses, zero dodges**
across the entire fight; all her real damage came only from Windfury Weapon procs and
shocks/totems. Root cause: `profiles/tbc/enhancement_shaman/profile.json` never declared
`distance_from_target`, so `core/settings_builder.py`'s `profile.get("distance_from_target", 7)`
silently used the ranged-class fallback (7 yards) instead of her real preset's
`distanceFromTarget: 5` (`sim/tbc-new/ui/shaman/enhancement/presets.ts:139`) - 7 yards is outside
real melee weapon reach, so she could never land a swing. This is the exact bug class CLASSES.md
already documented from the Feral Cat Druid stage (a melee spec with no gap-closer silently
starting out of range) - but Enhancement Shaman predates that audit and was never swept for it
retroactively. Fixed: added `"distance_from_target": 5` to her `profile.json`, rebuilt
`settings_template.json` via `build_profile_settings.py`, re-ran her sweep -
`baseline_screened` corrected to **2435.7**, now in line with her melee peers. Checked all 14
other profiles' `profile.json` for the same gap: Survival Hunter, Beastmastery Hunter, Balance
Druid, and Elemental Shaman also have no explicit `distance_from_target`, but all four are
genuinely ranged/caster specs where the 7-yard fallback never mattered (ranged weapon range and
spell range both comfortably exceed 7 yards) - confirmed safe, not just assumed. Every real melee
profile (Arms/Fury Warrior=25 opener range via Charge, Feral Cat=0, Combat Rogue=5, Retribution
Paladin=5) already had it explicitly set. Enhancement Shaman was the one genuine gap.

**Final verified `baseline_screened` (Phase 3, `SCREEN_ITERATIONS`), all 15 profiles, this pass**:

| Profile | Character | DPS |
|---|---|---|
| Survival Hunter | Lerynia-Thunderstrike | 2740.09 |
| Arms Warrior | Rubán-Thunderstrike | 1844.12 |
| Balance Druid | Béarforceone-Thunderstrike | 1303.45 |
| Elemental Shaman | Test-Elemental-Synthetic | 2176.55 |
| Enhancement Shaman | Test-Enhancement-Synthetic | 2435.74 |
| Beastmastery Hunter | Test-Beastmastery-Synthetic | 3901.63 |
| Fury Warrior | Test-Fury-Synthetic | 2763.54 |
| Feral Cat Druid | Test-FeralCat-Synthetic | 2428.29 |
| Combat Rogue | Test-CombatRogue-Synthetic | 2534.03 |
| Shadow Priest | Test-ShadowPriest-Synthetic | 1720.93 |
| Arcane Mage | Test-ArcaneMage-Synthetic | 2468.31 |
| Retribution Paladin | Test-RetPaladin-Synthetic | 2193.36 |
| Affliction Warlock | Test-Affliction-Synthetic | 2366.07 |
| Demonology Warlock | Test-Demonology-Synthetic | 2860.43 |
| Destruction Warlock | Test-Destruction-Synthetic | 2517.42 |

Every profile's `ledger_data_phaseN.json`/HTML ledger rebuilt after its sweep and
`check_ledger_consistency.py --html` run clean (0 failures, 0 warnings) - Enhancement Shaman
re-verified a second time after the `distance_from_target` fix (200/0). `data/characters/` and
`data/cache/` are both gitignored, so the report/cache artifacts themselves are never committed -
only the profile source files (`raid_buffs_overlay.json`, `settings_template.json`,
`profile.json`) are.

## 2026-08-29 — Folder-structure rework: five physically separated buckets, ahead of a real installer

Prompted by "is this ready for our bundled installer" turning up real gaps twice already
(REPO_ROOT under a frozen PyInstaller build, then this). User's own framing: split the repo into
**The Tool** (source), **The Sim we downloaded** (`sim/tbc-new/` submodule), **The Data we have**
(curated, versioned - `profiles/tbc/`), and **The Production Data we generated** (per-user, was
`data/`) - plus a 5th bucket I proposed and the user approved: **Build Output** (compiled
binaries, gitignored, disposable). Full target layout is now `CLAUDE.md`'s own "Repo layout"
section, kept current rather than duplicated here.

**Build Output (`build/`)**: `wowsimcli.exe`, `bridge.exe`, `simserver.exe` moved out of
`sim/tbc-new/`, `adapters/tbc/bridge/`, and `adapters/tbc/simserver/` respectively into
`build/bin/` - one predictable place instead of three, each nested inside its own source tree.
`dist/gearing-tool-gui.exe` moved to `build/dist/`. Real naming collision caught before it bit:
PyInstaller's own default work directory IS `build/` - reusing that name for this project's own
bucket would silently let a bare `pyinstaller` invocation dump its intermediate cache into the
same place. Fixed via `--distpath build/dist --workpath build/_pyinstaller_work` on the build
command (documented in `packaging/README.md`) - confirmed (not assumed) that a spec file's own
`DISTPATH`/`WORKPATH` globals are read-only convenience references PyInstaller resolves *before*
exec'ing the spec (`build_main.py` line ~1146-1213 in the installed 6.22.2), so setting them
inside the spec file itself would have been a silent no-op, not a real override - would have
looked like it worked (no error) while quietly doing nothing. `build/README.md` is the one
tracked file inside an otherwise fully gitignored directory (`build/*` + `!build/README.md` in
`.gitignore` - confirmed via `git add --dry-run` that this actually works, not just assumed from
the glob syntax).

**Production Data leaves the repo entirely**: `core/repo_root.py` gains `USER_DATA_DIR`
(`%LOCALAPPDATA%\GearingTool\`, falling back to `REPO_ROOT/data` only if `LOCALAPPDATA` genuinely
isn't set) - the same trusted-single-source pattern as `REPO_ROOT` itself, not a config value (an
app's own storage location can't be configured via a file stored... at that location). ~30 call
sites across `core/`, `adapters/tbc/`, `cli/gear.py`, `gui/api.py`, `ingest/` batch-migrated from
`os.path.join(REPO_ROOT, "data", ...)` to `os.path.join(USER_DATA_DIR, ...)`. Two files
(`adapters/tbc/adapter.py`, `adapters/tbc/valuation.py`, `adapters/tbc/simserver_client.py`) had
never been through the original REPO_ROOT consolidation pass at all - each computed its own naive
`__file__`-relative REPO_ROOT, working correctly today only because `adapters/` isn't
PyInstaller-bundled, but a second, uncoordinated copy of the same logic all the same. Routed
through the canonical `repo_root.py` while already touching these files for the exe relocation.

**Real, non-mechanical fix found only by actually testing, not just grepping**: two files
(`ingest/list_characters.py`, `ingest/build_synthetic_character.py`) import `REPO_ROOT` via `from
build_character import REPO_ROOT, ...` rather than `import repo_root` directly - a batch
find/replace that assumed every file has `repo_root` as a bound name left both referencing
`repo_root.USER_DATA_DIR` with `repo_root` never imported, a `NameError` that only surfaced when
`list_characters.list_synthetic_characters()` was actually called, not at import time (the bad
line only runs inside a function body). Fixed by adding `USER_DATA_DIR` to the existing
`from build_character import ...` line instead, mirroring how `REPO_ROOT` was already being
shared - caught by running the real function, not by re-reading the diff.

**`data/acquisition_status.json` split, per the user's own catch** ("isn't that per character
data? looks like Lerynia data" - correct, but incompletely fixed by just moving it): it was two
things sharing one file. `reputation` and `arena.current_rating`/`brackets` are real per-character
generated state (`ingest/build_character.py`'s `update_acquisition_status()` now takes
`name_realm` and writes to `USER_DATA_DIR/characters/<name_realm>/acquisition_status.json`,
creating it fresh if absent rather than requiring it pre-exist as the old code silently did).
`arena.rating_requirements` is a fixed, character-independent game-mechanic table - moved to
`profiles/tbc/reference/arena_rating_requirements.json` (new `reference/` subfolder under Data We
Have, alongside the per-class profile dirs). `core/acquisition_gate.py`'s `load_status(name_realm)`
merges both back into the exact in-memory shape `gate_for_item()` always expected, so that
function needed zero changes. Real content preserved during migration, not regenerated from
scratch - Lerynia's own real 40-faction reputation table and arena rating history copied forward
byte-for-byte.

**Verified end to end, not just import-clean**: a real `gear sync` + `gear best` run (Feral Cat
Druid) against the new locations reproduced the exact known-good cached baseline (2428.3,
byte-identical to the pre-restructuring value) - proof the sim_cache migration round-trips
correctly and the whole bridge.exe/simserver.exe/wowsimcli.exe chain resolves and runs from
`build/bin/`. `check_ledger_consistency.py --skip-html` clean (118/0). `acquisition_gate.py`'s
split verified directly (Lerynia's real 40-faction reputation + arena rating loaded from the new
per-character file, `rating_requirements` merged in correctly from the new shared reference file).
`gui/api.py`'s `get_report_output_dir()`/`get_wow_root()` both resolve through the new
`USER_DATA_DIR` correctly. All 24 touched modules import clean as a batch, not just individually
(catches import-order issues a one-at-a-time check would miss).

Old `data/` directory removed from the repo entirely (`git rm -r --cached data/` + real content
migrated to `%LOCALAPPDATA%\GearingTool\` first, not discarded) - `.gitignore`'s `data/*` entries
are gone since there's no `data/` left to ignore.

**Not done in this pass**: the actual installer wizard (NSIS/Inno Setup) - this was the
prerequisite folder-structure work, not the installer itself. First-run behavior (auto-create
`USER_DATA_DIR`, auto-detect the WoW folder and confirm with the user rather than blind-prompting)
is designed and the underlying `autodetect_wow_root()` already exists and works, but isn't wired
into an actual setup flow yet, since there's no installer UI for it to live in.

## 2026-08-30 — GUI feature: install GearingToolCompanion from the tool itself

Prompted by scoping the installer: GearingToolCompanion isn't published on CurseForge yet, so
there was no way for a user to get it onto their machine except a manual file copy. Per the user,
both entry points (a Settings-panel button, always available, and a banner shown whenever it's
missing/stale - functionally covers "first run" without needing a separate one-time-only flag,
since a fresh install simply hasn't installed it yet).

`gui/api.py`'s `ADDON_SRC_DIR` points at this repo's own `addons/GearingToolCompanion/` mirror
(the real, current source per CLAUDE.md's "Addon sync" section) - installing FROM here is
installing the real thing. `get_addon_status()`/`install_companion_addon()` compare via real
per-file SHA256 hashes, not a version string - the `.toc` has no `## Version:` field to compare
instead, and inventing one would violate the "never invent data" ground rule. Real, live-verified
against this machine's actual installed copy (not just a mock): `get_addon_status()` correctly
reported `installed: true, up_to_date: true`, and a direct `diff` confirmed the real installed
`.lua`/`.toc` files ARE byte-identical to the repo's own mirror - a true positive, not a
coincidence of the test setup.

**Real, pre-existing CSS bug hit again, not a new one**: the banner (`.addon-banner{display:flex}`)
rendered permanently regardless of its `hidden` attribute - the exact same specificity conflict
already documented and fixed for `.modal-overlay` on 2026-08-25 (a bare class rule with its own
`display` declaration beats the UA's `[hidden]` rule at equal specificity). Fixed the same way
(`.addon-banner[hidden] { display: none; }`), caught by actually testing in a browser (the
existing `gui/assets/preview.html`/`preview_mock.js` mock harness), not by re-reading the diff -
the screenshot after clicking "Install" still showed the banner despite `hidden` reading `true` in
the DOM, which is exactly what this class of bug looks like from the outside.

**`preview.html`/`preview_mock.js` were themselves stale** (predated the Settings modal, Run
Report modal, and now the addon banner - missing half of `index.html`'s real DOM, which would have
thrown on load rather than just silently under-rendering). Rebuilt `preview.html` to mirror
`index.html`'s real body exactly, and `preview_mock.js` to stub every `window.pywebview.api.*`
method `app.js` actually calls (previously only 3 of 16 were mocked) - worth keeping current for
any future GUI work, not a one-off fix just for this feature.

## 2026-08-30 — Fixed the last real installer blocker: baked sim commit SHA fallback

Three real call sites (`adapters/tbc/adapter.py`'s `version()`, `ingest/build_character.py`'s
`sim_commit_sha()`, `core/build_ledger_data.py`) each independently ran `git -C sim/tbc-new
rev-parse HEAD` - the exact same pre-REPO_ROOT-consolidation mistake (three copies of the same
logic) and a real installer blocker: a flat installer copy has no `.git` for any of them to read,
so every one of these would raise `CalledProcessError` on a packaged install with no error message
pointing at the real cause.

Consolidated into `core/repo_root.py`'s new `sim_commit_sha()` - prefers the live git call (still
correct immediately after a local submodule bump, no rebuild needed - this repo's own real dev
workflow) and falls back to a static file baked at build time
(`build/bin/sim_commit_sha.txt`, written via `git -C sim/tbc-new rev-parse HEAD >
build/bin/sim_commit_sha.txt`, now documented in `CLAUDE.md`'s Local Setup section) only when git
itself isn't usable. Raises a clear `RuntimeError` if both fail, rather than a fake/empty SHA -
"never invent data" applies to provenance stamps too. All three real paths verified directly, not
assumed: live git call (matches `git -C sim/tbc-new rev-parse HEAD` exactly), the fallback path
(git call monkeypatched to raise `FileNotFoundError`, confirmed it reads the same real SHA from
the baked file), and the clean-failure path (both unavailable, confirmed a real `RuntimeError`
with a message naming both the git command that failed and the missing fallback path). The three
original call sites now just delegate - `ingest/build_character.py`'s own `sim_commit_sha()` is
kept as a thin re-export (existing callers `from build_character import ..., sim_commit_sha`
don't need to change). Two files (`ingest/build_character.py`, `core/build_ledger_data.py`) had
`subprocess`/`_NO_WINDOW ` become fully dead after this and were cleaned up rather than left as
unused imports.

This was the one real remaining installer blocker identified when scoping what an installer
actually needs (see the 2026-08-29 folder-structure entry above) - what's left now is picking an
installer tool (NSIS vs Inno Setup, neither installed on this machine yet) and building the actual
wizard.

## 2026-08-30 — Real bug caught before the first-ever sim update: cache key never tracked sim version

Found while scoping "how do we ever update the sim" (the user's own concern, confirmed real:
pinned commit at the time was exactly tag `v0.0.119`, upstream's latest tag was `v0.0.124` -
22 commits/5 tagged releases behind, on an actively-tagging upstream where the latest tag was
only 4 commits behind `master`'s own tip). `sim_cache.json`'s key
(`gear_hash:settings_fingerprint:iterations:seed`, `core/sim_cache.py`) never accounted for which
sim BINARY actually produced a cached result - swapping `wowsimcli.exe`/`bridge.exe`/
`simserver.exe` for a new sim version, then running the exact same gear+settings, would have
silently served a stale DPS number computed under the OLD sim's math, with no way to tell.

Fixed in `adapters/tbc/valuation.py`'s `_fingerprint_settings()` - folds `repo_root.sim_commit_sha()`
into the hashed payload, so a sim version change invalidates every cache entry automatically. No
caller needed to change (every real caller reaches this one fingerprinting function already, never
`sim_cache.key()` directly). Verified directly: same settings dict fingerprints identically across
repeated calls (stable/deterministic), and differently when `sim_commit_sha()` is monkeypatched to
a different value (confirmed a real, different SHA256 output, not just "probably works").

This was found and fixed BEFORE ever actually updating the sim for the first time - would have
been a real, silent correctness bug the very first time this project's own "update the sim" idea
got exercised for real.

Real, verified wowsims/tbc-new release facts to inform the update-automation design (per the
user's AskUserQuestion answers: a scheduled Claude Code agent, not a dumb script, and do the real
v0.0.119→v0.0.124 update now as this mechanism's first real run):
- Tags are real (`v0.0.NNN`), cut directly off `master` (confirmed `v0.0.124` is a real ancestor
  of `master`, only 4 commits behind its tip at check time) - a stable, deliberate release signal
  to watch, better than raw `master` HEAD (which includes every merged branch, no curation).
- `core/repo_root.py` gains `sim_version_label()` (mirrors `sim_commit_sha()`'s own live-git +
  baked-fallback + never-invent-data pattern) - `git describe --tags --exact-match HEAD` inside
  the submodule, e.g. `"v0.0.119"`, falling back to the baked `sim_version_label.txt` if git isn't
  usable, then to the raw short SHA if even that's missing. Unlike `sim_commit_sha()` this never
  raises - a missing pretty label is cosmetic, not a broken provenance stamp.

## 2026-08-30 — GUI: wowsims credits + running version, per the license's own request

`sim/tbc-new/README.md`'s license section explicitly asks: "we request that anyone using this
software in their own project make sure there is a user visible link back to the original
project" - not just a nice-to-have, the one real condition attached to using it. Added a credits
block to the bottom of the Settings modal: a link to `github.com/wowsims/tbc-new`, the running
version (`sim_version_label()`, e.g. "v0.0.119"), a thank-you line, and real Patreon
(`patreon.com/wowsims`) and Discord (`discord.gg/jJMPr9JWwx`) links - all three URLs pulled
directly from the README, not guessed. `gui/api.py`'s new `get_sim_credits()` is the one real
source for all of it.

Links route through the existing `window.pywebview.api.open_url()` pattern (real `webbrowser.open()`
call, already used for report links) rather than plain `<a target="_blank">` - a native pywebview
window doesn't reliably support that the way a browser tab does. Verified live in the browser
preview harness: clicking a credits link calls `open_url` with the exact real URL and the page
itself never navigates away from the Settings modal.

## 2026-08-30 — First real sim update: v0.0.119 → v0.0.124, and a real `simserver.exe` build bug found doing it

The tool's first-ever sim version bump, following the runbook written earlier the same day (see
CLAUDE.md's "Sim update procedure"). Real diff assessed first (`git diff --name-only` between the
two tags): no `.proto` changes, no `go.mod`/`go.sum` changes, no `item_sets.go` changes for any of
the 15 profiled classes. Real, meaningful changes found: Feral Cat Druid's entire default rotation
was rewritten upstream (`ui/druid/feralcat/apls/default.apl.json`, whole-file replacement, not a
tweak), `sim/core/buffs.go`/`consumes.go` changed moderately (32/24 lines), `sim/common/tbc/
enchants.go` gained 17 lines (a pure addition, no existing lines touched). `assets/database/
db.bin`/`db.json` both updated (already committed inside the submodule, pulled automatically by
the bump - no separate DB regen needed).

**Real bug found during verification, not a sim regression**: rebuilt all three binaries using
this file's OWN documented commands (`wowsimcli.exe --tags=with_db`, `bridge.exe` and
`simserver.exe` both WITHOUT the tag, exactly as previously written here) - every real sim call
through the rebuilt `simserver.exe` then panicked with `"No item with id: <N>"` for literally any
real item, across 12 different profiles/item IDs. Looked exactly like upstream had dropped items
from the DB. Real diagnosis, not assumed: confirmed `db.json`'s Python-side lookup found every
"missing" item fine (`core.item_db.by_id()`); confirmed the item's name string is genuinely present
in `db.bin` via `grep -a`; wrote a standalone Go program (`sim/tbc-new/cmd/dbcheck/`, deleted after
use, never committed) importing `assets/database` directly and confirmed `database.Load()` finds
all 6 "missing" items with no issue. Root cause: `sim/core/database_load.go` (the file that
actually populates the global `ItemsByID` map used by every sim call) is gated behind `//go:build
with_db` - this repo's own documented `simserver.exe` build command never carried that tag, so
`simserver.exe`'s in-memory item database has ALWAYS started completely empty. This only surfaced
now because rebuilding `simserver.exe` from source is itself new (this is the tool's first real
sim update - the standing `simserver.exe` binary before today had presumably been built by hand at
some earlier point with the correct flag, and the docs just never caught up). `bridge.exe` genuinely
doesn't need the tag - confirmed via its own source (`player.Database = nil`, unconditional - it
never looks up an item, only expands the request shape). Fixed: `CLAUDE.md`'s Local Setup section
and the sim-update runbook both corrected to require `--tags=with_db` on `simserver.exe` too, with
the real symptom (`"No item with id"` despite the item genuinely existing) called out explicitly so
a future run - human or the scheduled agent - recognizes it immediately instead of re-deriving this
whole diagnosis.

**Verified after the fix, not just claimed**: a real, live low-iteration (200) sim call for all 15
profiles - 12/15 succeeded with sane DPS numbers close to their known pre-update values (Elemental
Shaman 2178.8 vs 2176.55, Enhancement Shaman 2435.6 vs 2435.74, Beastmastery Hunter 3895.6 vs
3901.63, Fury Warrior 2767.5 vs 2763.54, Feral Cat Druid 2432.2 vs 2428.29 - despite the whole
rotation rewrite, Combat Rogue 2522.7 vs 2534.03, Shadow Priest 1719.4 vs 1720.93, Arcane Mage
2474.8 vs 2468.31, Retribution Paladin 2193.1 vs 2193.36, Affliction Warlock 2365.6 vs 2366.07,
Demonology Warlock 2851.2 vs 2860.43, Destruction Warlock 2516.2 vs 2517.42 - small deltas fully
explained by 200 vs 500-1000 screening iterations, no outliers). The 3 real characters (Lerynia,
Rubán, Béarforceone) failed with `IndexError: list index out of range` in `optimizer.
build_owned_config()` - confirmed this is the pre-existing, already-documented empty-`equipped`
staleness issue (`len(char['equipped']['items']) == 0` for Lerynia, matching earlier session notes
on `data/character.json` needing a fresh in-game re-export), NOT a sim-update regression - the
same 3 characters would fail identically under the OLD sim version too. `check_ledger_consistency.py
--skip-html` re-run clean for two profiles post-update.

Submodule bumped and committed (`sim/tbc-new` now at `v0.0.124`, `7963eeac179ecbc61dce4e40be945e8fe0fd2204`),
`build/bin/sim_commit_sha.txt`/`sim_version_label.txt` re-baked to match. `build/bin/*.exe`
themselves stay gitignored (Build Output, never committed) - only the submodule pointer and doc
fixes are.

## 2026-08-30 — GUI: sim update-check logic (no releases exist yet - that's correct, not a bug)

Per the user: build the CHECK/notify logic now, even though nothing will actually be available
until the scheduled update agent (designed, not running yet) starts publishing releases.
`gui/api.py`'s `check_for_sim_update()` hits this repo's own real GitHub Releases API
(`GET /repos/Ruban-Creator/wow-gearing-tool/releases/latest`, unauthenticated - public repo, 60
req/hr is plenty for a periodic per-launch check) and compares against `repo_root.sim_version_label()`.
Every real failure mode is a distinct, honest state, never silently folded into "no update":
`checked: false` for a real network/HTTP failure, `update_available: null` when a comparison
genuinely can't be made (e.g. the local version fell back to a raw short-SHA, not a clean tag -
`_version_is_newer()` returns `None` rather than guessing), and a real 404 (no release published
yet - today's actual state, verified live against the real repo) reported with its own `note`
field rather than looking identical to "you're current."

GUI surface mirrors the addon-install pattern exactly: a Settings-modal row (manual "Check for
updates" + a "View release" button that only appears when a real `release_url` exists) and a
dismissible launch-time banner, shown only when `update_available === true`. Real UI bug caught
and fixed before it shipped: with both the addon-install banner and this new update banner able to
be visible at once, the addon banner's own `position: fixed` on itself would have made a second
banner render exactly on top of the first. Wrapped both in a shared `.banner-stack` container
(`flex-direction: column-reverse`, the container itself fixed-positioned) instead - verified live
in the browser preview harness with both banners visible simultaneously, correctly stacked with no
overlap.

The actual update ACTION today is "open the release page" (`open_url()`, same pattern as every
other external link) - not an in-app download-and-replace-binaries flow. That's a real, separate,
larger feature (fetching a release asset, verifying it, replacing running `build/bin/*.exe`,
restarting the app) intentionally out of scope for "the logic" as asked - this pass makes the
check/compare/notify real and correct, which the actual install action can build on later without
redesigning the detection side.

## 2026-08-30 — First real installer (Inno Setup), for sharing tomorrow

Installed via `winget install --id JRSoftware.InnoSetup` - lands under
`%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe`, NOT `Program Files` (worth knowing before
hunting for it again). Per-user install target (`{localappdata}\Programs\GearingTool`,
`PrivilegesRequired=lowest`) - no admin/UAC prompt, matches an early-stage personal tool being
shared casually rather than an enterprise deployment.

**Real payload-size finding, checked not assumed**: `sim/tbc-new`'s real working-tree size is
237MB, but grepping `core/`/`adapters/tbc/`/`gui/` for actual file reads at runtime found the
running app only ever touches two things from the whole submodule: `assets/database/db.json`
(Python-side item lookups - `db.bin` is embedded into `wowsimcli.exe`/`simserver.exe` at BUILD
time via `go:embed`, never read from disk at runtime, confirmed via a clean `grep -rln "db\.bin"`
across every Python module coming up empty) and `sim/**/*.go` (`core/set_bonus.py`'s own per-class
text parser, real paths confirmed by reading every profile's `set_bonus_go_source` field). `ui/`,
`proto/`, `cmd/`, `docs/`, `tools/`, `.github/`, `.vscode/` are only touched by dev-only
profile-building scripts (`build_profile_settings.py`, `build_wowsims_reference_bis.py`) that a
real end-user install never runs - confirmed via `apl_source` (the one field that looked like it
might need `ui/*/apls/`) only appearing in those two files, never in any runtime sweep path, and
`settings_template.json` already carrying the resolved rotation baked in. Real result: the
installer's `sim/tbc-new/` payload is ~8.5MB, not 237MB.

`packaging/installer.iss` reads `build/bin/sim_version_label.txt` at COMPILE time
(`#define AppVersion Trim(FileRead(...))`) so the installer's own displayed version always matches
whatever sim build it actually contains - never hand-maintained separately, same "single source of
truth" principle as everything else in this rework. Ships: `build/dist/gearing-tool-gui.exe`,
`build/bin/*` (all 3 exes + the two baked version files), `core/*.py` + `report_template.html`,
`ingest/*.py`, `adapters/tbc/*.py` (NOT `bridge/`/`simserver/` - those are Go source, build-time
only, already compiled into `build/bin/`), `profiles/tbc/*`, the trimmed `sim/tbc-new/` subset
above, `addons/GearingToolCompanion/*` (needed for the in-app addon-installer feature to have a
real source to copy from), `LICENSE`.

First real compile succeeded clean: 33.5MB output (`packaging/output/GearingTool-Setup.exe`).
**Real, unexpected finding while test-installing**: `/VERYSILENT /SUPPRESSMSGBOXES` did NOT
actually suppress the License Agreement page - a real installer window popped up requiring manual
interaction despite the silent flags, confirmed live (the user saw and clicked through it, not a
guess). Not yet root-caused (candidates: something about how the flags were passed through this
session's shell tooling, or a genuine Inno Setup behavior difference with `LicenseFile` set under
`/VERYSILENT` specifically) - flagged here rather than smoothed over, since a future scheduled
agent trying a real silent/unattended install (for automated testing) needs to know this isn't
reliable yet, not discover it fresh.

## 2026-08-30 — Full branding rename: "Ruban's Gearing Tool" (RGT)

Per the user, this is no longer a placeholder/internal name - real commissioned art existed
(`branding/source/icon_sheet.png`, `hero_image.png`, both provided directly, not generated here)
naming the product "Ruban's Gearing Tool" with "RGT" as the short mark. Scope, confirmed with the
user first (AskUserQuestion): app-level branding only - the GitHub repo (`Ruban-Creator/wow-gearing-tool`)
and this local folder path stay unchanged, real risk (breaking shared clone URLs, this session's
own path references) wasn't worth taking for a rename that's cosmetic at the git-remote level.
Deeper internal Python file-naming clarity (the OTHER thing CLAUDE.md's old "Future scope" note
bundled with "the rename") stays explicitly deferred too - real, separate scope, not done here.

**Real assets extracted, not re-generated**: `branding/app_icon.png`/`.ico` (the square helmet+RGT
lockup, cropped from the provided sheet, verified pixel-clean via iterative crop+view rather than
guessed coordinates), `branding/addon_icon.png` (the plain circular badge, unused for now),
`addons/GearingToolCompanion/icon.tga` (the compass-top circular badge specifically - per the
user's own follow-up ask, mid-rename - real 32-bit uncompressed TGA, confirmed via reading its own
header bytes rather than assumed, since WoW addon textures need that specific format and PIL could
have silently written a differently-encoded file), `branding/wizard_image.bmp`/
`wizard_small_image.bmp` (the square hero image letterboxed onto Inno Setup's tall 192x386 wizard
banner shape - checked by rendering and viewing the actual composited result, not assumed to look
right just because the math worked out).

**Real, live-verified changes**:
- `gui/app.py`: window title -> "Ruban's Gearing Tool"; `webview.start(icon=...)` now passes the
  real .ico (checked `webview.create_window()`'s own signature first - no icon param there, only
  on `start()` - so this isn't a guessed API surface). `packaging/gearing_tool_gui.spec` ALSO sets
  `icon=` on the PyInstaller `EXE()` call - belt-and-suspenders since which one actually controls
  the taskbar icon can vary by pywebview's active backend, not just one or the other.
- Exe renamed `gearing-tool-gui.exe` -> `RGT.exe` (PyInstaller spec's `name=`) - rebuilt, real
  window title confirmed via `Get-Process | Select MainWindowTitle` ("Ruban's Gearing Tool").
- GUI sidebar: the old plain-letter "R" badge (`<span class="brand-mark">R</span>`) replaced with
  the real icon image; a real CSS bug avoided by checking first, not by luck - the old
  `.brand-mark` was styled as a colored-background text badge, would have looked broken (visible
  background square behind a transparent-background PNG) if left unchanged rather than restyled
  for an `<img>`. Verified live in the browser preview harness, including that "Ruban's Gearing
  Tool" (longer than "Gearing Tool") doesn't overflow the 280px sidebar.
- `packaging/installer.iss`: `AppName`, `DefaultDirName`, `OutputBaseFilename` all renamed;
  `SetupIconFile`/`WizardImageFile`/`WizardSmallImageFile` wired to the real branding art. Real
  end-to-end retest after rebuild (same install-to-a-separate-location method as the first
  installer test) - the Setup window's own title bar showed "Setup - Ruban's Gearing Tool version
  v0.0.124" live, confirming `AppName`/`AppVersion` both resolved correctly, not just that the
  compile succeeded.

**Addon versioning, added per the user's own follow-up question** ("we probably need versioning
for the update mechanism or?") - real gap: `GearingToolCompanion.toc` had no `## Version:` field at
all before this (confirmed - `get_addon_status()`'s whole content-hash design exists specifically
because of that gap). Added `## Version: 1.0.0` and `## IconTexture:` (pointing at the new
`icon.tga`) to the `.toc`. Real design decision: the hash comparison STAYS the source of truth for
`up_to_date` (a real edit with a forgotten version bump would otherwise report falsely clean) -
the new `## Version:` field is surfaced as a DISPLAY-only value alongside it
(`shipped_version`/`installed_version` in `get_addon_status()`'s return, read fresh from each
side's own `.toc` via a new `_addon_version()` helper, never invented if the field's missing).
`## Title:` tightened to "GT Companion" to match the branding art's own "INCLUDES ADDON: GT
COMPANION" badge - the addon's folder name/SavedVariables names are untouched (breaking those
would orphan any already-configured real install).

**Deliberately NOT done**: the minimap button's icon itself was almost left as the existing
hand-drawn "R" FontString badge (a real, reasoned prior decision - "no external texture file
needed") until the user explicitly asked for the real round logo there instead; done once asked,
real 20x20 texture swap (`SetTexture("Interface\AddOns\GearingToolCompanion\icon.tga")` replacing
the old `iconBg`/`iconLetter` pair), the tracking-ring overlay code untouched since it never
referenced the old badge.

## 2026-08-31 — Real bug: set-bonus gate compared an unrelated item's value, not just the set's own

Caught live by the user looking at Lerynia's real Phase 3 ledger: Beast Lord Armor's 5 pieces were
showing up with a `set_note` again, looking exactly like the 2026-08-24 bug's own signature (every
piece a deep individual downgrade, -30 to -73 DPS, annotated "part of Beast Lord Armor... 4pc bonus
+75.8"). The 2026-08-24 fix (gate the note on whether the SET's own `best_four_of_five` combo
actually beats baseline) was confirmed still intact and correct in the code - this was a genuinely
different, second bug hiding behind the same symptom.

**Real root cause**, found via a live diagnostic (temporary print added, real numbers captured,
reverted before committing): `best_four_of_five()`'s winning combo picks whichever variant gives
the highest DPS across the 4 tier-piece slots AND every real option for the excluded 5th slot -
including every real non-set alternative in the pool, not just "keep her current item there". For
Beast Lord Armor, the winning combo swapped Bow-stitched Leggings (a real item she does NOT
currently own) into the excluded legs slot. The user's own catch, verbatim and correct: **the gate
was comparing "baseline with her current [worse] legs" against "4 Beast Lord pieces + a real,
independent legs upgrade she'd want regardless of Beast Lord" - an apples-to-oranges comparison**,
not "is the 4pc bonus itself worth it." Confirmed with real numbers: `combined_dps=2752.8` vs
`baseline=2740.1` (+12.7, gate FAILS = note shown) - looked like a real, if narrow, win, but that
+12.7 was smuggling in Bow-stitched Leggings' own independent value, not measuring the set alone.

**Fix**: `set_bonus.best_four_of_five()` now returns a second field, `combined_dps_isolated` - the
SAME winning 4-piece combo's DPS, but with her CURRENT gear held in the excluded slot instead of
whichever alternative won the wider search (the `(four, "current")` variant, already computed for
every real 4-piece combo regardless of which variant ultimately wins - no extra sim calls needed).
This is the honest `DPS*(P ∪ {4 set pieces}) − DPS*(P)` comparison, holding everything else equal.
`run_full_sweep_mv.py`'s gate now checks `combined_dps_isolated` instead of `combined_dps` -
`combined_dps` itself is untouched and still drives the "best achievable layout" console print/
report (a legitimately different, still-useful question: "once I'm committed to this set, what's
the best 5th-slot pick").

**Verified with real before/after numbers, not just code review**: re-ran the sweep after the fix
(same cached sim results, so this was fast) - `Set-bonus check: 5 item(s) flagged across 18 set(s)`,
down from 15 before the fix. Beast Lord Armor's own 5 pieces are gone from the flagged set entirely;
`check_ledger_consistency.py`'s own structural checks (does every downgrade shown have a note
explaining why) are unaffected by this change, since it only changes WHICH items get a note, not
whether shown-without-a-note downgrades are still caught.

Same class of bug as 2026-08-24's own fix (comparing the wrong two things), found the same way (the
user reading a real ledger and noticing something that shouldn't be possible) - worth remembering
this mechanism (best_four_of_five's own "try every real alternative for the excluded slot")
deliberately trades a wider search for a real risk of conflating unrelated value, and any FUTURE
change to this function should re-check that the isolated/gating number and the
best-achievable/reporting number stay clearly separated, not silently reunified.

## 2026-08-31 — GUI: confirm addon install with a real success/failure toast

Real UX gap the user hit directly: clicked "Install now" on the addon banner, the banner
disappeared, and they weren't sure anything actually happened. Added a small auto-dismissing toast
(`#toast-banner`, green success styling, 3.5s) shown from BOTH install entry points (the Settings
row's Install/Reinstall/Update button and the banner's own "Install now") - reads the real
`{success, error}` result from `install_companion_addon()` rather than assuming success just
because the call didn't throw, so a real failure (e.g. a permissions error) shows an honest
"Install failed: ..." message instead of a false "success" toast. Verified live in the browser
preview harness: toast appears with the right text and color, stacks cleanly above the other
banners (reuses the same `.banner-stack` container), and auto-hides on its own.

## 2026-08-31 — Repo-review remediation: privacy, performance, correctness, robustness

An external code review (`CODE_REVIEW.md`, ~11,000 lines across Python/Lua/JS/Go reviewed, graded
P1/fix-before-public, P2/real-cost, P3/cleanup) came back ahead of making the repo public. Worked
through essentially the whole thing in the review's own suggested order - every P1/P2 and most P3s,
skipping only the two explicitly-optional structural refactors (the `sys.path.insert`+bare-import
architecture, and splitting `run_full_sweep_mv.py`'s 1,542-line `main()` - both flagged "worth doing
only if already planning a restructure"/"not urgent," not needed for this pass) and §4.1 (68
unclosed `json.load(open(...))` handles across 20 files - real but purely stylistic, no live bug,
deferred as lower-value-per-hour than everything else here) and §5.1 (14 never-imported standalone
tools, informational only - already legitimate maintenance-script pattern, not touched).

**§1 Personal information (P1, blocking public release)**:
- **§1.1** - the developer's real Windows username appeared in 13 places across 7 files (all
  referencing a local plan-file path with no value to a reader even ignoring the privacy angle).
  Stripped to `<user>`; `preview_mock.js`'s mock report path swapped to the real `%LOCALAPPDATA%`
  form the actual code resolves to, a better mock value than the literal path it had.
- **§1.2** - three real characters (a real first name + real WoW characters + a named realm) were
  hardcoded directly in `core/character_profiles.py`'s `SUPPORTED_CHARACTERS` dict - a privacy leak
  for a public repo, and it also meant the tool only ever worked for one person (a second user got
  an empty character list with no way to fix it short of editing source). Real architecture split:
  the 12 built-in synthetic test-fixture characters stay hardcoded (ship with the tool, not personal
  to anyone), a real user's own characters now live in `local_config.json` (outside git, per-machine,
  same pattern as `wow_root`/`report_output_root`) via new `local_config.character_profile_overrides()`/
  `set_character_profile()`. `character_profiles.refresh()` mutates `SUPPORTED_CHARACTERS` in place
  (never reassigns the name) so `gui/api.py`'s own `SUPPORTED_CHARACTERS = character_profiles.
  SUPPORTED_CHARACTERS` alias (copied at import time) sees an update immediately, not just after a
  restart - verified this specific aliasing behavior directly, since getting it wrong would have
  silently broken the GUI's live view. New GUI flow closes the "No profile" dead end the review also
  flagged: a character with no profile gets a real dropdown (`character_profiles.available_profiles()`,
  built from every real `profiles/tbc/*/profile.json`'s own class/spec fields, never hand-maintained)
  and an Assign button. Also fixed a real, adjacent bug this surfaced:
  `ingest/list_characters.py`'s `list_synthetic_characters()` used to iterate the (now extensible)
  full `SUPPORTED_CHARACTERS` map and filter by the ASSIGNED PROFILE's own `synthetic_character` flag
  - which would have double-listed a real user's real character under debug mode if they assigned it
  to a profile that's itself flagged synthetic (most are, since few have a real player yet). Now
  iterates the true built-in fixture list directly. Verified end-to-end against real production data
  on this machine: re-seeded Lerynia/Rubán/Béarforceone into the real `local_config.json` (via
  PowerShell, not Bash - see the sandbox-redirect note below) and confirmed `Api.list_characters()`
  correctly resolves `has_profile: true` for all three and `false` for two other real, unassigned
  characters on the same account.
- **§1.3** - audited full git history for anything sensitive that had been removed later without
  being purged. Found `data/acquisition_status.json` committed across 7 real commits (2026-08-23
  through 2026-08-28) containing a real, live snapshot of Lerynia's actual reputation standings and
  arena rating - moved to `USER_DATA_DIR`/gitignored later, but never scrubbed from history. With the
  user's explicit go-ahead (confirmed before touching history, confirmed again before the actual
  force-push - this is real, deliberate destructive-operation caution, not a rubber stamp): backed up
  the whole repo (`E:\Claude\Gearing-Tool-backup-pre-filter-repo`, kept for now), installed
  `git-filter-repo`, purged the file from all history (`--path data/acquisition_status.json
  --invert-paths`), verified zero remaining hits via `git log --all --full-history`, confirmed
  `.gitmodules`/submodule pointer survived intact, then force-pushed. Safe to do now specifically
  because the repo is still private with no known clones/forks - would be a much bigger deal after
  going public. No credentials/API keys/tokens/secrets found anywhere (also checked, real grep sweep,
  clean) - this was purely an identity/personal-data exposure, never a secrets leak.

**§2 Performance**:
- **§2.1** - `sim_cache.put()` rewrote the ENTIRE cache file (JSON dump + atomic replace) on every
  single cache miss, under the same lock `get()` uses - measured by the review at 14.4ms/put at
  1,782 entries, growing unbounded (this project's real cache has since grown to ~48,600 entries).
  Replaced with an append-only `sim_cache.jsonl` journal - `put()` is now one O(1) line-append,
  periodic compaction once the journal exceeds 2x its unique-key count. One-time migration from the
  old format on first load so an existing install's accumulated cache isn't discarded. Verified
  against a REAL copy of this machine's actual 48,662-entry production cache (not synthetic data) -
  full migration, spot-checked entries byte-identical, put/get/overwrite/forced-compaction all
  confirmed correct.
- **§2.2** - `evaluate()` deep-copied the settings template and re-hashed it on EVERY call, including
  pure cache hits, where it was the entire remaining cost. Split the cheap imbue decision out so it
  runs before the template is ever touched, and memoized the fingerprint computation itself
  (`functools.lru_cache` on `(settings_path, mh_imbue, oh_imbue, bonus_key)` - a tiny real input
  space) so a repeat call skips the deep-copy/canonical-dump/hash entirely. **Verified byte-identical
  to the old fingerprint across every real scenario** (plain items, a real fist-weapon imbue trigger,
  bonus_stats_override, empty items) before trusting this - a mismatch would have silently invalidated
  the entire 48,600-entry cache from §2.1. Measured: ~28ms/call down to ~0.001ms/call once warm. Real
  end-to-end `evaluate()` round-trip also verified: a genuine cache miss (513.7ms, real sim call,
  correct DPS matching the long-established Survival Hunter baseline) followed by a genuine hit
  (0.05ms, identical result).
- **§2.3** - `gc.SLOT_ORDER.index(slot)` was a linear scan inside `optimizer.py`'s two hottest loops
  (`greedy_sweep`: up to 15 slots x 6 passes per run; `set_bonus_branch`). New `gear_config.SLOT_INDEX`
  precomputed once; both loops now do an O(1) dict lookup.
- **§2.4** - five modules (`gem_optimizer`, `sweep_all_loot`, `run_full_sweep_mv`,
  `build_wowsims_reference_bis`, `ingest/build_character`) each had their own independent
  `DB_PATH`+`json.load()` of `db.json`, so a single sweep parsed the same file into several separate
  in-memory copies. `item_db.py` gains `items()`/`gems()`/`npcs()`/`zones()`/`consumables()`
  accessors; all five now go through it. Also fixed a separate real issue in the same file:
  `build_wowsims_reference_bis.py`'s db.json load ran at MODULE IMPORT TIME, making the module
  unimportable without the sim submodule checked out - now lazy. While in `item_db.py`: replaced the
  four `hasattr(fn, "_index")` function-attribute memoization patterns with plain module-level dicts
  built once in `_load()`. Verified every touched call site with real, live execution (not just
  imports) - a real socketed item through `gem_optimizer.best_gems_for_item()`, a real 562-item
  shortlist from `sweep_all_loot.run()`, a real source lookup through
  `run_full_sweep_mv.describe_source_and_tier()`.

**§3 Correctness**:
- **§3.1** - `parse_lua_savedvariables()` used `text.partition("=")` to strip the leading
  `GLOBALNAME = ` off a SavedVariables file - fine for WowSimsExporter (one global, `WSEDB`), but
  GearingToolCompanion.lua declares two (`GTCompanionDB`, `GTCompanionMinimapDB`), and
  partition-on-first-`=` grabbed the first table's content PLUS the entire raw text of the second
  global tacked onto the end. It worked only because `slpp` 1.2.3 silently ignores trailing content
  after a balanced top-level table - **verified this against this machine's real live SavedVariables
  file** (decodes to exactly `GTCompanionDB`'s 5 real characters, nothing from
  `GTCompanionMinimapDB` mixed in), but that was never a real contract, just an accident of the
  library's own tolerance. Fixed with a per-global regex split + explicit `global_name` parameter.
  Real proof the fix works, not just that it doesn't crash: `GTCompanionMinimapDB` (angle: 14.0) now
  parses correctly on its own too - impossible before this fix, since the old code could only ever
  reach the first global in the file. `list_characters.py`'s `isinstance(entry, dict)` guard (which
  was defending against exactly this fragility as a symptom) is gone, not just less likely to fire.
- **§3.2/§3.3** - `render_report.py` spliced `json.dumps(ledger_data)` into a `<script>` block with
  no escaping (`json.dumps` doesn't escape `/`, so a literal `</script>` anywhere in the data would
  terminate the block early); `report_template.html`'s own JS had the same gap the frontend app's
  `escapeHtml()` already avoided - item names/sources/tier names/set-rescue-gate notes went into
  `innerHTML` raw. Fixed both (a `</` -> `<\/` payload escape, `html.escape()` on the Python side,
  a matching `escapeHtml()` added to the template's own JS). **Verified against a real crafted
  injection attempt** (a `</script><script>alert(1)>` tier name, an `<img onerror>` character name)
  - both neutralized, confirmed by direct string inspection of the rendered output, not just "it
  didn't crash."
- Deleted `core/run_gap_analysis.py` (and its only consumer, `core/gap_analysis.py`) - broken (bad
  import order, read the stale pre-restructure `USER_DATA_DIR/character.json` path, hardcoded to
  survival_hunter phases 2-3), unimported anywhere, and its actual job (owned gear vs. reference-BiS
  gap analysis) is now covered more rigorously by the real MV-based Achieved BiS section in the main
  pipeline. History preserved in git if ever needed again.
- Deleted a dead `by_name` dict in `optimizer.resolve_name_to_config()` (built, never read) and a
  stale trailing comment in `valuation.py` that contradicted the rest of its own paragraph
  (implied simserver's crash was still unfixed two lines below `USE_SIMSERVER = True`).

**§4 Robustness**:
- **§4.2** - `autodetect_wow_root()` scanned every drive letter A-Z with no caching, on the GUI's own
  startup path - a mapped-but-disconnected network drive can block `os.path.isdir()` for real
  seconds. Now checks `SystemDrive` first, skips A:/B:, and caches a successful detection under its
  own key (kept separate from the real user-override key so the Settings UI's "is this
  auto-detected vs. user-chosen" distinction stays correct) - re-validated on each read via one cheap
  `.flavor.info` check rather than trusted forever, and `set_wow_root(None)` ("Reset to auto-detect")
  clears it so that button genuinely re-scans. Verified with a real call-counting test: second call
  makes zero additional `isdir()` calls.
- **§4.3** - `Api.open_url()` passed any string straight to `webbrowser.open()` with no validation -
  now allowlisted by scheme (http/https unconditionally, `file:` only when the resolved path is
  under `USER_DATA_DIR`). Verified: a `javascript:` scheme, an arbitrary `file://` path (System32, a
  desktop file), and a non-http `ftp:` URL are all correctly rejected; real report/credit links still
  open.
- **§4.4** - `MAX_WORKERS`/`SIMSERVER_POOL_SIZE` were both hardcoded to 2, correct only because
  that's what the ORIGINAL dev machine's 6C/12T CPU measured safe. New
  `local_config.sim_concurrency()` derives from real `os.cpu_count()` (floored at the measured-safe
  2), overridable via config, called by both modules so they can't drift out of the lockstep their
  own comments already required. Lives in `local_config.py` specifically to avoid a real circular
  import (`run_full_sweep_mv` -> `marginal_value` -> `valuation`, so `valuation` can't import
  `run_full_sweep_mv`).

**§5 Structure**:
- **§5.4** - deleted `run_full_sweep_mv.py`'s module-level `PROFILE_DIR`/`SETTINGS_TEMPLATE`/
  `SETTINGS_2H`/`POOL_PATH` constants (all pinned to survival_hunter, historical pre-Stage-6
  leftover) - confirmed via a real grep that nothing anywhere reads them (every real usage inside
  `main()` reads its own local variables of the same name, built from the real required `profile_dir`
  parameter). This was exactly the loaded-gun shape `character_profiles.py`'s own docstring already
  warns about - the defensive fix for that INCIDENT (`SUPPORTED_CHARACTERS`) was good, but the trap
  itself was still sitting here, unused, for the next call site to reach for by mistake.

**Real, incidental finding**: this session's own Bash tool calls resolve `%LOCALAPPDATA%\GearingTool\`
to an isolated sandbox mirror (`AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Local\
GearingTool\`), not the real path - already documented from an earlier session, re-confirmed
repeatedly here (a "seeded" character-profile assignment silently landing in the sandbox instead of
the real file; a migration test touching a stale mirror cache instead of the real 13MB one). The
PowerShell tool does NOT have this redirect - used it directly for anything that needed to touch the
real production files. Worth remembering for any future session: verify via PowerShell, not Bash,
when a "real machine state" check matters.

Every change in this pass was regression-checked against `check_ledger_consistency.py` (clean
throughout, both a Hunter profile and a non-Hunter one where relevant) and, where the review's own
finding was about a specific runtime value (fingerprints, cache migration, parse output), verified
byte-for-byte or via direct real-data comparison rather than trusted on code-reading alone.

## 2026-08-31 — Full backlog audit + first real file-naming clarity pass

Per the user's explicit request ("double check we have no open questions, no to-do, no unrealised
future features or any other kind of backlog"): swept `TODO.md` (already clean), `QUESTIONS.md`
(found and fixed real staleness - three profile judgment-call entries, BM Hunter/Feral Cat Druid/
Arcane Mage, were actually resolved earlier the same session but never marked RESOLVED in the doc;
a duplicated Retribution Paladin entry consolidated; one genuinely never-asked-before question found
- Destruction Warlock's Destro-Fire scoping - raised to the user directly rather than guessed, answer:
leave as-is), a code TODO/FIXME grep (clean), and `CLAUDE.md`'s "Future scope" section, presented to
the user as a real status table rather than assumed current.

That review surfaced real drift worth recording: the doc's own text still said "not built" for
things that were, in fact, already live (the character-select dropdown, the phase toggle, the
progress indicator in the Run Report modal, tiers 1-2 of the three-tier funnel idea in
`interaction_matrix.py`) - verified each directly against real GUI markup/code before reporting
status, not trusted from memory or the doc's own stale framing. **Lesson: a "Future scope" section
this large needs its own periodic real-verification pass, not just trust in what it said the last
time it was written** - it drifted from reality several times over without anyone (including this
tool's own prior sessions) catching it until asked to check directly.

**Real decision from going through the list together**: item 9 (tool rename) turned out to bundle
two separable things. Per the user - the actual GitHub repo/local folder does NOT need "Ruban" in
its name (stays `wow-gearing-tool`/`Gearing-Tool`); the PRODUCT/branding rename to "Ruban's Gearing
Tool (RGT)" was already done in an earlier session (GUI/installer/addon). What was genuinely still
open: the file-naming clarity pass CLAUDE.md's own Future Scope text had flagged with a concrete
example (`core/run_full_sweep_mv.py` - "mv" = Marginal Value, not obvious to a newcomer) but never
actually done.

**First real pass, executed, not just planned:**
- `core/run_full_sweep_mv.py` → `core/run_upgrade_sweep.py` (`git mv`, preserves history). Every
  real import (4 call sites: `cli/gear.py`, `core/build_ledger_data.py`,
  `core/build_wowsims_reference_bis.py`, `gui/api.py`) and every code-comment mention across the
  WHOLE codebase updated to match - 39 occurrences across 13 Python files, plus 3 more in
  `core/report_template.html`, `gui/assets/app.js`, and `profiles/tbc/arms_warrior/profile.json`
  (a real comment inside profile DATA, not just source code). `build_ledger_data.py`'s own import
  alias (`as sweep_mv`) renamed to `sweep` too, for the same reason as the file itself - no point
  fixing the module name and leaving the confusing abbreviation alive in every call site via the
  alias. `CLAUDE.md`/`CLASSES.md` (living, always-current docs) updated the same way;
  `NOTES.md`/`QUESTIONS.md`'s own historical dated entries deliberately left untouched - those
  describe what was true AT THE TIME they were written, and rewriting them to use a name that didn't
  exist yet would be real revisionism against a dated log, not a correction.
- `core/run_mv_report.py` deleted outright, not renamed - real, additional finding while doing the
  naming pass: its only actual consumer, `core/build_loot_ledger_data.py`, was ALREADY deleted
  earlier this same session (found broken + superseded during the §4.1 file-handle cleanup pass) -
  so nothing produces valid input for `run_mv_report.py` (it read the stale flat
  `USER_DATA_DIR/character.json` path, hardcoded to survival_hunter) and nothing reads its output
  (`mv_report.json`) anymore either. Confirmed via a real grep before deleting, not assumed from the
  file's own age.

**Verified, not assumed clean:** every touched module re-imported successfully (14 modules checked
directly, including the renamed one itself and `cli/gear.py`); `check_ledger_consistency.py` clean
on two different profiles afterward; a real, live full sweep run through the actual CLI entry point
(`python cli/gear.py best Test-Beastmastery-Synthetic phase3`, not a cached/structural check) kicked
off to prove the renamed module works end-to-end through its real entry point, not just on import -
see the next dated entry for the result once it finished.
