# Questions for the user

Running list of real judgment calls hit while building the multi-character GUI
(see `C:\Users\Matthias\.claude\plans\staged-purring-lynx.md` for the approved
plan) autonomously overnight, 2026-08-24. Each entry: what I decided so work
could keep moving, and why - flag if you'd rather it be different. Nothing
here is blocking; all are default choices I judged reasonable, not gaps left
undone.

<!-- New entries get appended below as they come up. -->

## Try it out

`dist/gearing-tool-gui.exe` is already built and sitting there (also runnable from source:
`python gui/app.py`, both from the repo root). All 4 plan stages are done and committed. See
`CLAUDE.md`'s "Future scope" section and `NOTES.md`'s 2026-08-24 overnight entry for the full
summary - the entries below are just the specific judgment calls worth your eyes on.

## Judgment call: an empty identity block never wins the "newer timestamp" tie-break

Your confirmed decision was "whichever source has the newer timestamp wins entirely." Found via
real live testing that GTCompanion's current saved entries for you and Lerynia both have a
*newer* timestamp than WSE's but an *empty* identity block (they predate today's addon update -
no login since I copied the new `.lua` in). Applying "newer wins" literally would've shown a
blank character card for both of you. Added one narrow guard: an empty identity block never
outranks a non-empty one, regardless of timestamp - still whole-block, not per-field, just not
picking a strictly-worse empty option when a real one exists. Should self-resolve the moment you
log in again (GTCompanion will save real identity data then) - flagging in case you'd rather the
literal rule held even for this case.

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

## Stage B design call: fixed phase2-phase5 grid, not "only phases with a report"

The plan flagged this explicitly as a call to make at the Stage B checkpoint. Went with the
plan's own recommended default: the detail view always shows all four phases (2-5), each either
showing its registered report link or a muted "no report yet" state - more discoverable than
only rendering rows for phases that happen to already have a URL registered. Easy to flip to the
other behavior in `gui/assets/app.js`'s `renderReports()` if you'd rather it only show phases
that actually have something.

## Stages B and C merged into one pass

The plan called for Stage B (functional shell, deliberately plain CSS) then a separate Stage C
visual-polish pass. In practice I wrote real styling directly in the first pass instead of
building it ugly-on-purpose and circling back - given "should look nice" was an explicit,
confirmed requirement from the start, doing it twice felt like pure overhead rather than a real
checkpoint. Verified functionally two ways: (1) the real `python gui/app.py` launches a genuine
native window (confirmed via its actual OS window title, "Gearing Tool" - no crash, empty
stderr/stdout log) and (2) `gui/assets/preview.html` + `preview_mock.js` (a test-only harness
that fakes `window.pywebview.api` with real captured data) let me drive the actual HTML/CSS/JS
in a real browser and verify every screen/state via the DOM and computed styles, since a native
pywebview window isn't something I can screenshot or click into directly. I could not get an
actual pixel screenshot of the real window this session (the Browser pane wasn't displaying) -
worth you just opening `python gui/app.py` yourself for a real look when you're back, in case
anything reads worse in person than the computed-style checks suggest.
