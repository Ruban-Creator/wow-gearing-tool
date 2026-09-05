# Actions for you — updated 2026-09-06

Real, current list of what's actually on YOU (a decision, an account, an in-game action). Not a
status report — see CLAUDE.md/FUTURE_TASKS.md for full technical writeups, NOTES.md for the dated
build/investigation log. This file is meant to be asked about directly ("what's left on the
todo?") and gets rewritten fresh each time it's revisited — treat it as disposable, not an
append-only log like NOTES.md.

## Open, no decision needed yet - pick one whenever you want to

- **#14 — build the real scheduled sim-update-checking agent.** `CLAUDE.md`'s "Sim update
  procedure" is a tested runbook, but nothing runs it on a schedule yet. Real question when you
  want to pick this up: what machine/mechanism actually runs it (this dev machine on a schedule?
  something else?).
- **#15 — the `sources: None` DB gap** (255 real items across all 15 profiles have no known drop
  source in the sim's own database). The practical symptom is already fixed (items still bucket
  into the correct tier). The real fix options on file: report it upstream to `wowsims/tbc-new`,
  or maintain a small local overlay file — both need per-item verification against something like
  Wowhead, not bulk-guessed.
- **SmartScreen cert decision** — accepted as unsigned for now; revisit once the installer is
  distributed more broadly than this dev machine (a real cost decision, ~$100-600/yr depending on
  cert type — see `FUTURE_TASKS.md`).

Nothing here is urgent or blocking anything else - genuinely just "whenever you feel like it."

## Closed since the last update

- **Backlog #8 (re-sweep speed)** — fully closed 2026-09-06. The real want ("what changed after a
  raid week") got the "Since Your Last Sweep" report section, already live. The original ask
  (make the sweep itself faster) was investigated two real ways - proving per-item independence
  claims (rejected as unsound, not just risky - WoW's combat math has no clean "zero effect" case)
  and a dedicated sim machine (rejected - the one certain benefit doesn't need new hardware, the
  speed benefit is genuinely uncertain, and the "get everyone's data to one machine" piece isn't
  built) - and you decided not to pursue either. Nothing left open here.
- **Backlog #7 (confirm@5000 tier)** — turned out to already be shipped (2026-08-24); just needed
  the paperwork closed, done 2026-09-01.
- **CurseForge** — live: "GT Companion" by RubanCreator, https://www.curseforge.com/wow/addons/gt-companion

No code changes are pending a rebuild right now - everything committed and pushed as of the last
real code change (the diff-view feature, 2026-09-04).
