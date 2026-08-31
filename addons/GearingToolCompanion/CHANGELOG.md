# GT Companion Changelog

## 1.0.2 (2026-08-31)
- Fixed the minimap button icon rendering off-center inside its ring border.

## 1.0.1 (2026-08-31)
- Character data (bags, bank, reputation, arena ratings, identity) is no longer restricted to
  max-level (70) characters - a leveling character you're actively gearing up now gets tracked
  and shown in `/gtlist`/the character list too, not just once they hit the level cap.
- Fixed the minimap button icon to use the real RGT badge art, correctly anchored to the button.

## 1.0.0 (2026-08-30)
Initial versioned release - first version to carry a `## Version:` field at all. Everything
below existed before this release but had no version number attached to it.

- Real branding: "GT Companion" title, RGT badge icon (minimap button + status panel), matching
  Ruban's Gearing Tool's own visual identity.
- Bank contents, bag contents, reputation standings, and arena team ratings captured to
  SavedVariables - none of which WowSimsExporter's own export reaches Gearing Tool for.
- Character identity (name/realm/class/race/faction/level/professions) captured natively,
  independent of any other addon's own internal format.
- Every character on the account tracked separately with a timestamp - `/gtlist` shows all of
  them at a glance, with search-by-name filtering.
- Minimap button: left-click opens a status panel (what's been captured, when), right-click
  saves immediately. Movable by dragging.
- Triggers WowSimsExporter's own export automatically on login (if WSE is installed), so a
  character who logs in and changes nothing that session still gets freshly exported.
