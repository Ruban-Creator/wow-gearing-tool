# Changelog

Real, user-facing changes to Ruban's Gearing Tool (RGT) itself - the desktop app/installer, not
the underlying sim engine (see the GUI's own Settings modal for the vendored `wowsims/tbc-new`
version). For the in-game companion addon's own, separate changelog, see
`addons/GearingToolCompanion/CHANGELOG.md`.

Version format: `{stage} - v{major.minor}.{build}`, e.g. `Pre-Release - v0.7.0001`. See
`core/version.py` for the real bump rules.

## Pre-Release - v0.7.0006 (2026-09-07)

- **Real bug fix**: found and fixed the real cause of Run Report sometimes silently failing to
  start at all on a character with no cached data yet (a fresh install, or a character run for the
  first time) - a pre-flight check could crash invisibly before the actual sweep ever got a chance
  to run. Run Report should now always start, even on a genuinely first-ever run.
- **Coverage improvement**: 6 more profiles (Balance Druid, Enhancement Shaman, all 3 Warlock
  specs, Arcane Mage) gained a real, verified ring enchant recommendation where none existed
  before.

## Pre-Release - v0.7.0005 (2026-09-07)

- **Real accuracy fix**: your report's "Baseline DPS" now reflects your gear exactly as it really
  is - real gems, real enchants, no substitution - instead of an idealized number that assumed
  every socket/slot was already optimally filled. Upgrade comparisons are unaffected (they still
  fairly compare fully-optimized gear on both sides); only the headline number and Missing
  Enchants' math changed to be honest about your actual, current DPS.
- **Real accuracy fix**: gem recommendations for Phase 1 and Phase 2 reports no longer assume a
  Phase 3 gem you can't actually have yet - phase-legal alternatives are used instead.
- **Real accuracy fix**: a real pet-DPS double-counting bug affecting every report for Survival/
  Beastmastery Hunter, all 3 Warlock specs, and Balance Druid has been fixed - the sim already
  includes pet damage in the reported total, and this tool was adding it again on top. Affected
  reports were inflated by roughly your pet's own DPS share.
- **New: Missing Gems** - alongside Missing Enchants, your report now also flags any socketed item
  where a real, phase-legal, better gem loadout is available and shows the real DPS gain.
- **Real accuracy fix**: several classes' "chase this item's socket bonus" gem recommendations were
  verified against a gem that isn't actually legal to use (profession-gated or already-unique
  elsewhere) - corrected across 11 profiles, several of which had every one of their socket-bonus
  recommendations reversed once restricted to gems you can actually obtain.
- **Coverage improvement**: Demonology and Destruction Warlock both gained a real, newly-verified
  chest enchant recommendation.

## Pre-Release - v0.7.0004 (2026-09-06)

- **Real bug fix**: a report whose underlying file had moved or been deleted (including every
  report generated before the 2026-08-29 data-location migration) still showed a "View Report"
  button that failed when clicked. The report list now checks the file actually exists first and
  shows "No report published yet" instead - this also protects against a user manually deleting
  or moving a report file themselves at any point.

## Pre-Release - v0.7.0003 (2026-09-06)

- **Real accuracy fix**: Shadow Priest's weapon oil (Superior Wizard Oil) was silently never
  applying its Spell Damage bonus in any sim result - fixed, giving her a real ~1.5% DPS increase
  in every report from here on.

## Pre-Release - v0.7.0002 (2026-09-06)

- **Out of Mana readout**: every report now shows how much of the fight your baseline was out of
  mana, with a real warning when it's high enough to skew mana/spirit item values.
- **Fight duration sanity checks**: a visible warning when the fight duration looks like a typo
  (under 30s or over 600s), and a real, interactive check before running a sweep that offers a
  shorter duration if the current one leaves your character meaningfully out of mana.
- **Used Consumables**: a new report button showing the exact potion/flask/food/weapon-oil the
  sweep actually simmed with.
- **Combat Potion choice** for casters (Balance Druid, Elemental Shaman, Shadow Priest, Arcane
  Mage, and all 3 Warlock specs): pick Destruction Potion, Super Mana Potion, or Fel Mana Potion
  per character - some builds genuinely gain more DPS from a mana potion than the default burst
  potion, and this lets you test which one wins for your own gear.
- **Real accuracy fix**: 10 of 15 class/spec profiles were silently never using their configured
  combat potion in any sim result at all (a missing internal setting, not a report you'd have
  noticed) - fixed, so every affected report's numbers are now more accurate than before, whether
  or not you touch the new Combat Potion selector.

## Pre-Release - v0.7.0001 (2026-09-06)

- Starting point for real, tracked versioning - RGT didn't carry its own version number before
  this. Not a full retroactive changelog of every prior change (see `NOTES.md` for that history);
  entries from here on describe what changed since the previous version bump.
