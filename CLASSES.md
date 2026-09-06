# Building a new class/spec profile — known gotchas

Checklist of real, previously-hit problems to check for whenever a new profile is added
(`profiles/tbc/<new_profile>/`) or an existing one's gem/enchant data is touched. Every item here
is a real bug this project actually hit, not a hypothetical — cross-referenced to where it was
found and fixed so the reasoning isn't lost. Update this file whenever a new class/spec surfaces
a new gotcha; don't let the lesson live only in NOTES.md's session log.

## Gems

- **Always the objectively-best choice, unconditionally** - never "respect what she currently has
  socketed," even for an item she already owns. `gem_optimizer.best_gems_for_item()` computes this
  fresh every time; `optimizer.build_owned_config()`/`load_candidates()` never fall back to a
  literal current gem. `DPS*(P)` is the best achievable from `P`, not "whatever's actually
  socketed right now."
- `primary_gem_id` (profile.json) must be a real id that exists in `db.json`'s `gems` collection,
  sourced from the same phase/preset file the rest of the profile's data came from - never guessed
  from a stat-weight table. Color/stat family must match the class's real primary stat (Agility,
  Strength, Intellect+SpellDamage, etc).
- A pure-primary-stat gem doesn't always win a socket bonus check - `chase_bonus_gems.json`'s
  `item_ids` set is real, sim-verified exceptions only (`core/verify_gem_choices.py`'s real A/B
  methodology: pure primary-stat vs the item's own socket-bonus-chased loadout, real DPS, not a
  linear EP guess). A new profile starts with an **empty** chase-bonus set, not inherited from
  another class - verify its own candidates before assuming any bonus is worth chasing.
- **This exception is REVOKED as of 2026-08-31 - do not reuse `chase_bonus_gems.json` across
  sibling specs, even with byte-identical EP weights.** The original claim (below, kept for the
  historical record) was that "byte-identical EP weights -> same socket-bonus verdict, since it's
  purely a function of stat weights, never rotation/pet/class mechanics" was proven wrong by a
  real, full re-verification: Beastmastery Hunter's `chase_bonus_gems.json` had been reused
  verbatim from Survival Hunter's own (byte-identical EP weights, spot-checked at the time) since
  2026-08-25, but a real 22-item `core/verify_gem_choices.py` re-run found **10 genuine, resolved
  socket-bonus wins** (+2.6 to +10.5 DPS, all clearly outside noise) that the spot-check missed
  entirely - BM's real Ravager pet contributes ~30% of her total DPS, and effective stat value
  shifts with that pet-DPS-share the same way already documented below for Demonology vs
  Affliction/Destruction Warlock. A byte-identical EP-weight table does NOT capture a pet's own
  separate contribution - two specs can share literal Agility/Hit/Crit weights on paper and still
  disagree on whether a specific item's socket bonus is worth it, because the pet's share of total
  DPS is a real, separate variable the EP table doesn't encode. **Always run the full
  `verify_gem_choices.py` pass for every new profile, no exception based on sibling-spec EP-weight
  equality alone** - a spot-check on a handful of items is not sufficient replacement, since this
  exact case (Beastmastery) WAS spot-checked and still missed 10 real wins.

  <details><summary>Original (now-revoked) reasoning, 2026-08-25</summary>

  Claimed: when a new profile shares its *entire* item pool with an already-verified profile (two
  specs under one class dir, e.g. Beastmastery/Survival Hunter) AND its real EP weights are
  confirmed byte-identical to that profile's own (check both specs' real `presets.ts` preset
  blocks directly, don't assume), reusing the already-verified `chase_bonus_gems.json` list was
  considered defensible, not a shortcut - the socket-bonus-vs-pure-stat question was assumed to be
  purely a function of stat weights, never rotation/pet/class mechanics. Spot-checking a handful of
  fresh real sim calls on any candidates the prior run never covered was meant to catch a bad reuse
  - it did not (see above).
  </details>

- **Gem selection is phase-aware as of 2026-09-06 (`time_horizon.get_current_phase()`,
  `gem_optimizer._phase_legal_default_gem()`/`_all_gems()`) - a new profile's `primary_gem_id` gets
  this automatically, nothing extra to wire up.** But any dev tool that calls into gem selection
  (`build_owned_config()` and anything downstream of it) now REQUIRES
  `time_horizon.set_current_phase()` to have been called first, or it raises loud - check every new
  standalone script the same way `verify_default_enchants.py`/`verify_gem_choices.py`/
  `build_profile_settings.py` needed this added on 2026-09-07.
- **`_all_gems()`'s phase filter also excludes `unique`/`requiredProfession`-gated gems - a real,
  separate correctness fix, not just phase-legality.** Found 2026-09-07 re-verifying
  `chase_bonus_gems.json` under this fix: Survival Hunter's ENTIRE 9-item chase-bonus list (built
  2026-08-24) turned out to have been verified against an illegally-selected substitute gem for
  off-color sockets - the pre-fix `_best_gem_of_color()` picked "Crimson Sun" (33131, unique +
  Jewelcrafting-only) as the best RED representative, a real gem no character could legally
  multi-socket without the profession. Once excluded, every one of those 9 "wins" flipped to a
  real, resolved LOSS (up to -11.94 DPS) - the socket-bonus loadout was never actually beating pure
  primary-stat once restricted to legally-obtainable gems. **Any `chase_bonus_gems.json` verified
  before 2026-09-06 needs a real re-run of `verify_gem_choices.py`-style logic with the active
  chase-bonus set forced empty first** (comparing an item already in the file against itself is a
  tautology - `best_gems_for_item()` special-cases listed ids to already return the chase loadout,
  so a naive re-run of `verify_gem_choices.py` unmodified can never re-check an existing entry, only
  find brand-new ones). See NOTES.md's 2026-09-07 entry for the full per-profile results.

## Non-obvious real filename conventions

- **A `6p`/`9p` (or similar percentage-looking) suffix in a wowsims gear-set filename can mean a
  hit-rating TARGET ("6% hit"/"9% hit"), not a tier-set piece count** - confirmed for Hunter's own
  `bm/dw_6p.gear.json`/`2h_9p.gear.json` naming (`presets.ts` labels them literally "DW - 6% hit"),
  easy to misread as "6-piece tier" at a glance, especially since tier-piece-count variants ARE a
  real thing this project has hit elsewhere (Feral Cat Druid, per the current staging plan). Check
  the real label in `presets.ts` before assuming which axis a numeric gear-set suffix encodes.
  CLAUDE.md already has a standing default for the hit-target axis specifically: always the 6%
  (moonkin present) variant, permanently - a hit-target toggle was considered and explicitly
  dropped (2026-08-31), not just deferred. Never use 9% for any profile.

## Enchants

- **Same unconditional-best policy as gems now** (reversed from an earlier "keep her real current
  enchant" design, 2026-08-25 - see NOTES.md's Missing Enchants entries for the full story).
  `gear_config.get_active_default_enchants()` is the single source; every default-enchant lookup
  in `optimizer.py`, `run_upgrade_sweep.py`'s full-world-item sweep, and `set_bonus.py`'s tier-set
  comparison must route through it (or `optimizer.achievable_enchant()` - see below), never a
  literal `it.get("enchant", 0)` read off her real gear.
- **Raw wowsims-preset enchant ids are NOT reliable - verify every one, every profile, no
  exceptions.** `core/build_default_enchants.py` extracts real candidate ids from that profile's
  own `sim/tbc-new/ui/<class>/<spec>/gear_sets/pN.gear.json`; `core/verify_default_enchants.py`
  then runs a REAL isolated sim delta per slot before trusting any of them. Real, confirmed results
  so far: Warrior 9/9, Elemental Shaman 9/11 (2 legitimate zero-DPS utility enchants, not a data
  bug), Enhancement Shaman 3/10, Balance Druid 1/11 (only the weapon verified - see below), Hunter
  12/12 hand-researched (but even hand-researched data had a real gap - missed her ranged scope
  entirely until a live sim checkpoint caught it).
- **The isolated-verification methodology matters - get it wrong and everything silently passes.**
  Compare "candidate enchant" against a **zero-enchant baseline for that one slot** (strip it,
  don't touch anything else), never against her real current gear directly - if she already has
  that exact enchant equipped, a naive "apply it, diff against real baseline" test shows a false
  `delta=0.00` "doesn't work" even for a perfectly real, functional enchant. Bit Warrior's own
  verification pass once already (4/9 → 9/9 once fixed).
- **A `delta > 0` verified enchant is not automatically the BEST choice for that slot - check for
  real alternatives if a number looks surprising.** Hunter's own feet slot: the file's assumed
  BiS ("Cat's Swiftness") verified real (non-zero) vs no-enchant, but her actual current pick
  ("Dexterity") beat it by +7.3 DPS in a real head-to-head test - only caught because the Missing
  Enchants ledger surfaced a **negative** delta live (current beats assumed-BiS). That check
  (`run_upgrade_sweep.py`'s Missing Enchants pass requiring `delta > 0`, never displaying a
  downgrade as a recommendation) is a real safety net, not just cosmetic - keep it.
- **When most or all of a profile's raw candidate ids show a flat `+0.00` delta, check `db.json`
  directly before concluding the items are just useless.** `{e["effectId"] for e in
  db["enchants"]}` - if the candidate id isn't in that set at all, the sim engine doesn't
  implement the effect, period; no amount of re-testing will change the verdict. This is a real,
  systemic gap in some preset files, not isolated to one slot - Balance Druid's own preset had
  9 of 11 non-preset-slot ids simply absent from the DB. The real fix: search `db.json`'s
  `enchants` collection by name for the class-appropriate real equivalent (e.g. "weapon"/"staff"
  for a caster's weapon slot), cross-check against real Wowhead knowledge for what SHOULD be
  BiS, then verify the real candidate via the same isolated-delta test before adopting it. Found
  this way for Balance Druid's weapon: the preset's id (22560) wasn't in the DB at all; "Enchant
  Weapon - Major Spellpower" (effectId 2669, a real, DB-recognized caster weapon enchant) verified
  clean at +22.8 DPS.
- **Ring enchants are a real, separate case: only self-castable by a character who personally has
  Enchanting** - unlike every other slot, there's no "pay any enchanter" option. `db.json`'s
  `enchants` collection already encodes this for free (`requiredProfession` is set ONLY on the 4
  real Ring enchants, 2928-2931, unset on everything else in the game) -
  `item_db.enchant_required_profession_name()` + `optimizer.achievable_enchant(enchant_id,
  known_professions)` gate this generically off that field, not a hardcoded "rings are special"
  branch. Every default-enchant lookup needs to route through `achievable_enchant()`, not just
  `get_active_default_enchants().get(slot)` directly, or a character without Enchanting will get
  a real but structurally-unachievable ring enchant recommended.
- `build_owned_config()`/`load_candidates()` both take a real `known_professions` parameter now
  (default `{"Herbalism", "Mining"}` = Hunter's real value, so existing callers stay unchanged) -
  a new profile's real caller (`run_upgrade_sweep.py`'s `main()`) must pass the character's own
  real professions, not rely on the default.

## profile_dir - never let a call site guess it

- `run_upgrade_sweep.main()`'s `profile_dir` parameter is **required, no default** (was a
  dangerous silent default to Hunter's own profile until 2026-08-25 - see
  `core/character_profiles.py`'s docstring for the real bug this caused twice: a non-Hunter
  character's real gear got swept against Hunter's whole candidate pool/enchants/stat
  weights/settings, silently, with no error). `core/character_profiles.py`'s
  `SUPPORTED_CHARACTERS` map is the one real source of truth for character → profile_dir,
  shared by both `cli/gear.py` and `gui/api.py` - add a new profile there, never hand-type a
  path at a new call site.
- `build_ledger_data.build()`'s `profile_dir` is also required now, same reasoning (lower blast
  radius than the sweep itself, but the same class of bug).

## weapon_topology

Three real values exist: `dual_wield`, `two_hand`, `one_hand_plus_offhand_item`. Each needs real,
distinct handling - confirmed necessary by three different real profiles hitting three different
gaps, not theoretical:

- `slot_for_item()` (`run_upgrade_sweep.py`) must route 2H weapons correctly per topology - a
  `two_hand` profile's mainhand IS its real 2H slot (no separate "should I go 2H" side-analysis
  needed at all); `dual_wield`/`one_hand_plus_offhand_item` both route 2H candidates to the
  separate weapon_2h_candidates side-pool instead.
- `core/build_wowsims_reference_bis.py`'s pool-key mapping for mainhand must be derived from the
  item's real `handType` (proto: MainHand=1/OneHand=2/OffHand=3/TwoHand=4), never hardcoded to
  always mean "weapon_2h" - a profile whose real BiS varies between a 2H weapon and a 1H+offhand
  combo by phase (Balance Druid) needs both `mainhand`/`offhand` pool entries resolved correctly.
- `settings_template_2h.json` (the melee-weave settings variant) is **optional** - only build one
  if the class's actual ROTATION changes with weapon choice (Hunter: real melee-weave APL logic).
  A profile whose rotation doesn't change with weapon choice (a caster: still just casting either
  way) has no reason to need one; `run_upgrade_sweep.py` already falls back to the profile's own
  plain `SETTINGS_TEMPLATE` when no `_2h` variant file exists.

## set_bonus.py - three real Go source forms

A class's tier-set bonus data in `sim/<class>/*.go` can be defined three different ways - all
three are real and already handled, but a new class could plausibly need a fourth:

1. Inline map literal (the original, Hunter's own convention).
2. Bare variable reference - one set's bonus defined by pointing at another set's already-defined
   map (found in Warrior's real PvP sets, Stage 6.1).
3. Function call - the bonus map returned by a Go function instead of a literal
   (`pvpResilience2PBonus(46437)`-style, found in Druid's real PvP sets, Stage 6.2).

Also: **the file path itself is per-class, not a fixed convention** - Hunter's set bonuses live
in `sim/hunter/item_sets.go`; Warrior's are in `sim/warrior/items.go` instead. Check the real
source tree for the new class rather than assuming the Hunter path pattern.

## Other real per-class gotchas already found

- **`core/settings_builder.py`'s `distanceFromTarget` has a hidden, ranged-class-biased default
  (7 yards) that silently breaks any melee spec with no gap-closer.** `profile.get(
  "distance_from_target", 7)` - the fallback was never audited because every profile built before
  Feral Cat Druid was either ranged (Hunter) or had a real opener that closes distance itself
  (Warrior's Charge). A melee spec with no such opener (Feral Cat: no gap-closer at all) silently
  starts 7 yards out of range for every ability, producing a real, confirmed "No available
  actions! Pausing rotation" / 0 DPS failure with NO error - it looks exactly like a broken
  rotation config, not a positioning bug, and burned real debugging time on the wrong hypothesis
  (missing rotation config) before the actual cause was found. **Every new melee profile must set
  `distance_from_target` explicitly in `profile.json`** (0 for true melee range, matching the
  class's own real `OtherDefaults` in `presets.ts`) - never rely on the generic fallback, even if
  the number "sounds about right." **Not just a new-profile check - a real, confirmed miss on a
  profile that predates this entry**: Enhancement Shaman shipped before this gotcha was written
  and was never swept for it retroactively, silently running at 7 yards instead of her real
  preset's `distanceFromTarget: 5` for weeks - unlike Feral Cat's total "No available actions"
  failure, a melee spec whose out-of-range value happens to still permit non-melee actions
  (Windfury Weapon procs, shocks, totems) doesn't fail loudly at all: it just quietly loses every
  white-melee-swing hit (confirmed via a direct action-log pull - `OtherActionAttack` showed zero
  hits/misses/dodges for the whole fight, not just low damage), producing a real-looking but
  roughly-halved DPS number that passes every existing check (sim exits 0, consistency check
  clean) because nothing about it looks broken from the outside. **Whenever this checklist gains a
  new item, re-audit every EXISTING profile against it, not just profiles built afterward** - the
  audit that introduced this entry only checked profiles that didn't exist yet.
- **A class/spec can define its own separate real proto `Rotation` message, entirely distinct from
  the generic `player.rotation` (TypeAPL) field** - found for Feral Cat Druid:
  `FeralCatDruid.rotation` (`finishingMove`/`biteweave`/`ripMinComboPoints`/`biteMinComboPoints`/
  `mangleTrick`/`maintainFaerieFire`) is a real, required, spec-specific config block that lives
  alongside `FeralCatDruid.options`, NOT inside the generic APL rotation. Missing it doesn't error
  either - the sim just runs with default/zero values for those fields, another real "silently
  wrong, not silently absent" trap. Check the class's own real proto message
  (`sim/tbc-new/proto/druid.proto` or equivalent) for a spec-specific `Rotation` field before
  assuming the generic APL config is the whole story, and source real default values from that
  spec's own `presets.ts` `DefaultRotation` block. Also: the JSON key in `class_options.json` must
  match the real proto oneof field's exact camelCase name (`"feralCatDruid"`, not copy-pasted from
  a sibling spec like `"balanceDruid"`) - a mismatched key is silently ignored, not rejected.
- **A wowsims preset's own canonical rotation choice (`TypeSimple`, wired via `makePresetAPLRotation`/an "apl.json" filename) can be genuinely non-functional in the current engine version - always grep the Go engine before trusting it.** Found for Arcane Mage: `presets.ts`'s own real P2/P3 preset builds all select `arcaneBraid.apl.json`, whose raw content is a `TypeSimple` rotation (`{"type":"TypeSimple","simple":{"specRotationJson":"{\"conserveStart\":...}"}}`, matching the real `Mage.Rotation` proto message's own fields) - using it verbatim produced a real, silent 0 DPS with "No available actions! Pausing rotation" from t=0.00. Root cause: `grep -rl "ConserveStart" sim/tbc-new/sim/mage/*.go` returns nothing except the proto-generated file - no real Go code in this engine version consumes Mage's own `TypeSimple` fields, so the rotation compiles to nothing. **This is NOT a universal "TypeSimple never works" rule** - Hunter's own real `.build.json` presets (`bm/dw_6p.build.json` etc.) also use `TypeSimple` and DO work, confirmed via a live `cli/gear.py preset` call, because `sim/hunter/*.go` has real code consuming ITS OWN simple-rotation fields (`timeToWeave`/`useMulti`/etc). The real, general check before trusting any `TypeSimple` preset: grep the class's own `sim/<class>/*.go` for the spec's real `Rotation` proto field names (not just the proto file) - if nothing but the generated `.pb.go` matches, that spec's `TypeSimple` path is dead in this engine version and the real working rotation is whatever `TypeAPL` `.apl.json` file exists instead (even one that isn't wired into any `makePresetBuild` call - "never referenced by a preset build" is not the same as "non-functional", check the engine, not just the TS wiring).
- `adapters/tbc/valuation.py`'s `_normalize()` writes a `petType` field - Hunter-only, must be
  guarded by a presence check (`if "petType" in ...`) or every non-Hunter profile hits a real
  `KeyError`.
- `profile.json`'s `raid_ap_contribution.enabled` flag must default to **off** for every profile
  except Hunter - it models Hunter's specific Expose Weakness/Hunter's Mark "grants OTHER raid
  attackers real AP, invisible to a solo sim" mechanic. Every other real ally-affecting debuff
  checked so far (Warrior's Sunder Armor, Druid's Faerie Fire, Warlock curses, Paladin's Judgement
  of the Crusader) is an enemy-side effect a solo sim already benefits from directly - no new
  per-class raid-AP model needed unless a genuinely new "grants other players a stat, not visible
  to a solo sim" mechanic shows up.
- `loot_eligibility.json`, `class_options.json`, `consumables.json`, `stat_weights.json`, and the
  reference-BiS sourcing all have to be hand-rebuilt from that class's own real
  `sim/tbc-new/ui/<class>/...` / `sim/tbc-new/sim/<class>/...` source files every time - confirmed
  twice now (Warrior, then Druid/Shaman) that there's no shortcut or cross-class reuse possible
  for this part. Real per-class EP weights come from that class's own `<class>/dps/presets.ts` -
  never invented, never copied from another class as a placeholder.
- `core/time_horizon.py`'s `REF_DIR` and `core/sweep_all_loot.py`'s eligibility constants are both
  profile-driven (`set_active_ref_dir()`, `loot_eligibility.json`) - a new profile needs both set
  from its own real data, not left pointing at Hunter's.

## Verifying a real rotation actually fires (not just that settings parse)

- `cli/gear.py preset <build.json> --iterations N --seed N` is the easy path when a real
  `.build.json` preset exists for the class (Hunter's `bm`/`sv` dirs have them per phase; Warrior's
  `dps/` dir does not - confirmed, only `gear_sets/`+`apls/`). It prints real player/pet DPS,
  enough to confirm a pet-heavy spec's pet subsystem fires (Beastmastery Hunter: real Ravager pet
  contributing ~30% of combined DPS).
- When no `.build.json` exists, get a real per-event combat log instead: build a `RaidSimRequest`
  by hand with `adapters/tbc/valuation._build_raid_sim_request(settings, iterations, seed)` (the
  same real function the sweep pipeline itself uses - `settings` needs `player.equipment` already
  set), then call `wowsimcli.exe sim --infile <path> --outfile <path>` **directly**, not through
  `adapter.run()` (which expects an *IndividualSimSettings* path and re-runs the bridge translation
  step - your hand-built request is already in the bridge's OUTPUT shape, so going through
  `adapter.run()` double-converts and fails). The result dict's `logs` field is a real, large
  (500KB+) per-event text log with `SpellID: N` tags - `Counter(re.findall(r'SpellID:\s*(\d+)',
  logs))` surfaces which real abilities actually fired and how often. Cross-check a suspicious
  spell ID against the class's own real Go source (`grep -rn '<id>' sim/tbc-new/sim/<class>/*.go`)
  before trusting it - found real, confirmed this way for Fury Warrior: Bloodthirst's real spell ID
  is 30335, not the commonly-cited 23881 (a different rank/tooltip id), only caught by reading
  `registerBloodthirst()`'s own `core.ActionID{SpellID: 30335}` directly rather than guessing.
