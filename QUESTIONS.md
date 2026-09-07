# Open Questions

Real, currently-unresolved questions genuinely awaiting the user's decision - nothing else. This
file is NOT a memory/history log (that's `NOTES.md`) and not a scoped-work queue (that's
`TODO.md`) - a resolved question gets removed from here, not marked "RESOLVED" and left in place,
so this file only ever shows what's actually still open. See `NOTES.md`'s own dated entries for
the full history of everything that used to be tracked here.

<!-- New questions get appended below as they come up. Remove an entry the moment it's answered -
     the answer belongs in NOTES.md (if it's a real technical decision worth a build-log entry) or
     nowhere further at all (if the answer is simply "yes"/"no" and nothing else depends on it). -->

## CLAUDE.md staleness pass (2026-09-07) - real findings, none fixed yet, for a joint pass

Per the user's own request ("do a last check on claude.md that nothing in there is stale... add it
to questions for tomorrow so we can finalize the claude.md file"). Real findings from a full re-read
after this session's own Stage 4 corrections landed - none auto-fixed beyond what the plan itself
called for, since the user wants to finalize this file together rather than have it keep drifting
under one-sided edits:

1. **Real, direct contradiction: "Stage 7" vs "Backlog #8."** The "Staging" section's own Stage 7
   paragraph (added 2026-08-23) still reads "PRIORITY... this is now a real near-term priority to
   design properly, not a someday idea" about decomposing the re-sweep cache. Further down in
   "Future scope," "Backlog #8 (decomposed re-sweep caching) — CLOSED, 2026-09-06" explicitly
   states the user decided AGAINST this exact idea after seeing the real cost/payoff (rejected on
   sound technical grounds - no clean "provably independent slot" case in WoW's combat math, plus a
   dedicated machine's uncertain payoff). A reader hitting Stage 7's text first would believe this
   is still an active priority; it isn't. Fix is mechanical (point Stage 7's own text at the later
   closure, or delete/shrink it to a one-line pointer) but touches enough surrounding prose that it
   felt like a "decide together" edit rather than a unilateral one.

2. **The entire "Future scope (deferred to final implementation, not now)" section's own framing is
   stale.** Its opening paragraph ("User wants a GUI eventually: run a sim on demand, a phase
   toggle..., a character-select dropdown..., and a raid/zone scope filter") is written in
   forward-looking, not-yet-built language - but literally every item it lists is marked **Done**/
   **Built** inline just a few paragraphs later in the SAME section (raid/zone scope filter done
   2026-08-31, character-select dropdown built 2026-08-24, progress indicator/resolve-iterations
   done 2026-08-31). The section header itself ("deferred... not now") no longer matches its own
   contents - it reads as a wishlist but is mostly a shipped-features log with a few genuinely
   still-open items mixed in (the interaction_matrix.py entry point, backlog #8's now-closed
   question). Worth a real restructure (e.g. split into "Shipped" vs "Still genuinely deferred")
   rather than another inline "**Done**" patch.

3. **The `Architecture` section's illustrative example path is stale.** `SPEC PROFILE
   (profiles/)   — data only, e.g. profiles/tbc/survival-hunter.yaml` (hyphenated, single `.yaml`)
   doesn't match reality at all - profiles have been a `profiles/tbc/<snake_case_name>/` directory
   of several `.json` files since the 2026-08-24 Stage 6.0 migration (`profile.json`,
   `settings_template.json`, `candidate_pool.json`, etc.). A newcomer reading just this section
   would expect a single YAML file per profile. Minor (it's illustrative, not load-bearing), but
   easy to fix and worth doing in the same pass.

4. **Minor overclaim, not a hard error**: "Package goals are effectively covered by Stage 5's
   interaction matrix now that it's built" (Staging section) sits right below the SAME section's own
   admission that `core/interaction_matrix.py` has "no checked-in entry point... imported by
   nothing" and was only ever run via an ad-hoc one-off script. "Effectively covered... now that
   it's built" reads as more finished/usable than the surrounding text actually supports - worth
   softening or cross-referencing the entry-point gap explicitly.

5. **The `SimAdapter` Python class stub in Architecture** (`class SimAdapter: def run(...)`, etc.)
   is a conceptual/illustrative contract, not a literal class that exists anywhere in the real
   codebase (the real adapter is a set of module-level functions across `adapters/tbc/adapter.py`/
   `valuation.py`, not one class with these exact method names). This was probably always meant as
   illustrative rather than literal - flagging only because a newcomer could reasonably go looking
   for a `class SimAdapter` and not find one. Lowest priority of the five; may not be worth changing
   at all if the intent really was always "this is the conceptual shape, not literal code."

