# Actions for you — 2026-09-01 overnight session

Real, current list of what's actually on YOU (a decision, an account, an in-game action) after
tonight's autonomous pass on backlog #7 and #8. Not a status report — see NOTES.md's 2026-09-01
entry and CLAUDE.md/FUTURE_TASKS.md for the full technical writeups. This file is meant to be
asked about directly ("what do I have to do?") and regenerated/updated at the end of a future
autonomous session the same way — treat it as disposable, not an append-only log like NOTES.md.

## Decide: backlog #8 (re-sweep speed after a raid week)

Real investigation found the original idea ("joint search over shared-pool slots") doesn't match
how the tool actually works anymore — no such search exists today, and backlog #16 (shipped hours
before this pass) already solved the underlying coupling problem a different way. The REAL
remaining cost (a full re-sweep after 1-2 new items ends up ~100% cache-missing) is real and
understood, but fixing it safely means proving per-class/per-rotation independence claims (e.g.
"does Warrior's Rage economy near a haste breakpoint actually not care about a new Ring's
Agility?") — not something to assume and ship overnight into a component every reported DPS
number depends on.

**Your call, three real options** (full detail in `FUTURE_TASKS.md`'s #8 entry):
1. Accept re-sweeps stay ~15-20 min for now — nothing forces this to be fixed soon, it's an
   annoyance, not a blocker.
2. Greenlight a *different*, lower-risk feature instead: a "what changed since last sweep" diff
   view (compares the new report against the previous one via `report_storage.py`, zero
   cache-correctness risk since it's pure display-layer comparison). This is NOT what #8
   originally asked for (it doesn't make sweeps faster), but serves the same real want ("I got new
   gear, what's different?").
3. Greenlight the real, substantial work: proving per-slot independence bounds one profile at a
   time before touching the cache key at all. Genuinely more than a session's worth of careful
   work, not a quick fix.

## Still open, unstarted (not touched tonight, per your own scope)

- **#14 — build the real scheduled sim-update-checking agent.** `CLAUDE.md`'s "Sim update
  procedure" is a tested runbook, but nothing runs it on a schedule yet. Needs a real decision on
  what machine/mechanism runs it (this dev machine on a schedule? something else?).
- **#15 — the `sources: None` DB gap** (255 real items across all 15 profiles have no known
  drop source). Practical symptom already fixed (correct tier bucketing via the phase fallback).
  Real fix options on file: report upstream to `wowsims/tbc-new`, or maintain a small local
  overlay file — both need per-item verification against something like Wowhead, not bulk-guessed.
- **SmartScreen cert decision** — accepted as-is for now; revisit once the installer is
  distributed more broadly than this dev machine (a real cost decision, ~$100-600/yr depending on
  cert type — see `FUTURE_TASKS.md`).

## Done since this file was written

- **CurseForge**: live. "GT Companion" by RubanCreator - https://www.curseforge.com/wow/addons/gt-companion
  - confirmed via a real fetch of the listing (6 downloads already, last update Aug 31), not just
  taken on your word. Nothing left to do here; CLAUDE.md's own note is updated.

## What did NOT need your input tonight

Backlog #7 (the "confirm@5000" 4th precision tier) turned out to already be live in production,
shipped 2026-08-24 — verified directly against a real character's own report data (79 of 98 real
rows resolved at 5000 iterations, 10 at full 30000, matching exactly what #7 asked for). Nothing
for you to review here — it was a documentation gap only, now closed (see CLAUDE.md's new "Done,
2026-09-01, backlog #7" note).

No code changed tonight (`core/`, `adapters/`, `gui/` untouched) — no exe/installer rebuild was
needed. Everything committed and pushed; see the git log for the exact commit.
