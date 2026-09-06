# Changelog

Real, user-facing changes to Ruban's Gearing Tool (RGT) itself - the desktop app/installer, not
the underlying sim engine (see the GUI's own Settings modal for the vendored `wowsims/tbc-new`
version). For the in-game companion addon's own, separate changelog, see
`addons/GearingToolCompanion/CHANGELOG.md`.

Version format: `{stage} - v{major.minor}.{build}`, e.g. `Pre-Release - v0.7.0001`. See
`core/version.py` for the real bump rules.

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
