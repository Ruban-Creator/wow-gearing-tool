# GT Companion

Companion addon for [Ruban's Gearing Tool](https://github.com/Ruban-Creator/wow-gearing-tool), a
gear-upgrade valuation tool for WoW Classic: The Burning Crusade (Anniversary). GT Companion
captures the character data the tool needs that no other export addon reaches - drop it in
alongside WowSimsExporter and you're covered.

## What it captures

- **Bank contents** - WowSimsExporter only reads your bags, never your bank.
- **Bag contents** - captured to SavedVariables directly, no copy-paste needed.
- **Reputation standings** - for reputation-gated gear (e.g. Exalted-only rewards).
- **Arena team ratings** - for rating-gated PvP gear.
- **Character identity** - name, realm, class, race, faction, level, professions.

Every character on your account is tracked separately, with a timestamp, so Ruban's Gearing Tool
can tell which character's data is current across your whole roster - not just one.

## Using it

Nothing to configure - just play. GT Companion saves automatically:
- Bags update as your inventory changes.
- Bank saves whenever you open your bank.
- Reputation and arena ratings save on login and whenever they change.
- It also triggers WowSimsExporter's own gear/talent export on login, so a character who logs in
  and changes nothing that session still gets freshly exported.

**Minimap button** (the round RGT badge):
- Left-click - open the status panel, showing exactly what's been captured and when.
- Right-click - save everything right now.
- Drag - move the button anywhere around the minimap.

**`/gtlist`** - opens a searchable list of every character this addon has ever saved on your
account, with a timestamp and WowSimsExporter status for each.

## Requirements

- WoW Classic: The Burning Crusade (Anniversary) - Interface 20506.
- [WowSimsExporter](https://www.curseforge.com/wow/addons/wowsimsexporter) installed alongside it
  (GT Companion complements it, doesn't replace it - your gear/talent export still comes from WSE).

## Why a separate addon

Ruban's Gearing Tool needs bank contents, bag contents, reputation, and arena ratings to decide
whether an upgrade is something you can *actually* go get right now, not just something that
exists somewhere in the game. WowSimsExporter's own real export doesn't reach any of that - GT
Companion exists purely to fill that gap, and does nothing else.

## License

MIT - see [LICENSE](https://github.com/Ruban-Creator/wow-gearing-tool/blob/master/LICENSE).
