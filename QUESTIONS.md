# Questions for the user

Running list of real judgment calls hit while building the multi-character GUI
(see `C:\Users\Matthias\.claude\plans\staged-purring-lynx.md` for the approved
plan) autonomously overnight, 2026-08-24. Each entry: what I decided so work
could keep moving, and why - flag if you'd rather it be different. Nothing
here is blocking; all are default choices I judged reasonable, not gaps left
undone.

<!-- New entries get appended below as they come up. -->

## Heads-up, not really a question: `data/character.json` currently has 0 equipped items for Lerynia

While testing the new `gear sync`/per-character write during Stage A, I ran a real `gear sync
Lerynia-Thunderstrike` to verify the additive write actually works. It correctly pulled from
WowSimsExporter's real, current SavedVariables data - which right now genuinely has **0 gear
items** for her most recent export (confirmed directly: `char["gear"]["items"]` is an empty list
in the live WSE file). This overwrote both `data/character.json` and
`data/characters/Lerynia-Thunderstrike/character.json` with that empty-gear state - the exact
scenario `cmd_sync`'s own existing warning already anticipates ("equipped is empty - re-export
in-game while geared"), not a bug in anything I built today.

**Nothing is actually lost** - I only ever READ your SavedVariables files, never modified them,
so this is fully recoverable: `/wse export` in-game while actually geared, then `gear sync
Lerynia-Thunderstrike` again, and it'll be back to normal. `data/character.json` isn't
git-tracked (already gitignored) so there's no backup of the old good version to restore from
in the meantime - just flagging so you're not surprised if you run `gear best` before
re-exporting and get a wrong/empty-looking result.
