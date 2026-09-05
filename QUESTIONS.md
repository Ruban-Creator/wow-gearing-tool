# Open Questions

Real, currently-unresolved questions genuinely awaiting the user's decision - nothing else. This
file is NOT a memory/history log (that's `NOTES.md`) and not a scoped-work queue (that's
`TODO.md`) - a resolved question gets removed from here, not marked "RESOLVED" and left in place,
so this file only ever shows what's actually still open. See `NOTES.md`'s own dated entries for
the full history of everything that used to be tracked here.

<!-- New questions get appended below as they come up. Remove an entry the moment it's answered -
     the answer belongs in NOTES.md (if it's a real technical decision worth a build-log entry) or
     nowhere further at all (if the answer is simply "yes"/"no" and nothing else depends on it). -->

## Affliction Warlock: should the profile spec into Unstable Affliction?

Found 2026-08-25 while building `profiles/tbc/affliction_warlock/`: wowsims' own canonical
Affliction talent build does NOT spec into Unstable Affliction (confirmed by counting the real
talent-string segment length against the proto field count, then confirmed by a combat log
showing 0 UA casts) - despite the APL script referencing it and the spec's own name strongly
implying otherwise. The profile currently follows this literal wowsims default.

If you'd rather this profile spec into UA (a real, valid alternate Affliction build some players
prefer), that's a deliberate deviation from the literal wowsims default to make, not a bug to fix -
flag if you want that swap made.
