"""Automated consistency checking for the ledger pipeline.

run_full_sweep_mv.py -> tiered_report.json -> build_ledger_data.py ->
ledger_data.json -> spliced into phase3_ledger.html's `const DATA = {...};`.

Every stage of this pipeline has broken silently at least once this project
(see NOTES.md): the Beast Lord Armor bug (an item with negative MV and no
set_note still showing as an "upgrade" - a real filter-gating bug in
run_full_sweep_mv.py), the rescue_note-never-rendered bug (data was correct,
the HTML template just had no render block for it), and the 2026-08-23
raw-dict-of-dicts splice bug (the JS threw partway through rendering "tiers"
and everything past "Achieved BiS" silently went blank - no error surfaced
to a reader unless they opened devtools). None of these were caught before
a human spotted them by eye. This script re-derives the pipeline's own
stated invariants and checks real output against them, so the same three
classes of bug get caught automatically before the next publish.

Usage: python core/check_ledger_consistency.py [--html PATH]
Exit code 0 = all checks passed. Non-zero = at least one real failure.
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
DEFAULT_HTML = r"E:\Claude\Temp\Gearing-Tool\phase3_ledger.html"
TOP_N_SHOWN = 5  # must match build_ledger_data.py


class Report:
    def __init__(self):
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.checked = 0

    def check(self, ok: bool, msg: str):
        self.checked += 1
        if not ok:
            self.failures.append(msg)

    def warn(self, ok: bool, msg: str):
        if not ok:
            self.warnings.append(msg)


def item_is_real_upgrade(r: dict) -> bool:
    return not r.get("tied_within_noise") and r.get("mv", 0) > 0


def check_tier_item(r: dict, rep: Report, where: str):
    for field in ("name", "mv", "noise_stdev", "tied_within_noise", "item_id", "slot", "tier", "resolved"):
        rep.check(field in r, f"{where}: missing required field '{field}' on {r.get('name', '?')!r}")

    # The exact predicate run_full_sweep_mv.py itself gates inclusion on
    # (line ~753): real upgrade, OR a genuine set_note, OR a genuine
    # rescue_note. Anything else present is the Beast Lord bug class -
    # a downgrade shown with no explanation for why it's there at all.
    justified = item_is_real_upgrade(r) or bool(r.get("set_note")) or bool(r.get("rescue_note"))
    rep.check(justified, f"{where}: {r['name']!r} (mv={r.get('mv'):+.1f}, tied={r.get('tied_within_noise')}) "
                          f"has no set_note/rescue_note and is not a real upgrade - unexplained downgrade shown")

    # tied_within_noise should match the pipeline's own 2-sigma rule
    # (run_full_sweep_mv.py line ~869: abs(mv) < 2 * noise_stdev).
    if "mv" in r and "noise_stdev" in r and r["noise_stdev"] is not None:
        expected_tied = abs(r["mv"]) < 2 * r["noise_stdev"]
        rep.check(r.get("tied_within_noise") == expected_tied,
                   f"{where}: {r['name']!r} tied_within_noise={r.get('tied_within_noise')} but "
                   f"|mv|={abs(r['mv']):.2f} vs 2*noise_stdev={2*r['noise_stdev']:.2f} implies {expected_tied}")

    # rescue_note is only ever supposed to be attached to a real, positive
    # sidegrade (run_full_sweep_mv.py line ~634: mv_if_set_broken > 0,
    # not tied). rescue_mv is that number surfaced alongside the note.
    if r.get("rescue_note"):
        rep.check("rescue_mv" in r and r["rescue_mv"] is not None,
                   f"{where}: {r['name']!r} has rescue_note but no rescue_mv")
        if r.get("rescue_mv") is not None:
            rep.check(r["rescue_mv"] > 0,
                       f"{where}: {r['name']!r} rescue_mv={r['rescue_mv']:+.1f} is not positive - "
                       f"a sidegrade note should only ever describe a real positive-MV swap")

    # resolved items should carry a real, higher-precision iteration count -
    # a resolved:true row with a screen-tier iteration count would mean the
    # "resolved" flag is lying about its own precision.
    if r.get("resolved") and "resolve_iterations" in r:
        rep.check(r["resolve_iterations"] and r["resolve_iterations"] > 0,
                   f"{where}: {r['name']!r} is resolved but resolve_iterations is missing/zero")


def check_tiered_report(report: dict, rep: Report) -> None:
    for key in ("baseline_screened", "achieved_bis", "tiers", "two_hand", "two_hand_meta"):
        rep.check(key in report, f"tiered_report.json: missing top-level key '{key}'")

    rep.check(isinstance(report.get("baseline_screened"), (int, float)) and report["baseline_screened"] > 0,
               "tiered_report.json: baseline_screened is missing or non-positive")

    seen_ids: dict[tuple, dict] = {}
    for tier_name, slot_dict in report.get("tiers", {}).items():
        for slot_name, rows in slot_dict.items():
            where = f"tiers[{tier_name!r}][{slot_name!r}]"
            rep.check(isinstance(rows, list), f"{where}: expected a list, got {type(rows).__name__}")
            for r in rows:
                check_tier_item(r, rep, where)
                # Same item_id should never carry contradictory mv values
                # across two different report locations - a sign of a stale
                # cache entry or a duplicate-write bug.
                key = (r.get("item_id"), r.get("slot"))
                if key in seen_ids and abs(seen_ids[key].get("mv", 0) - r.get("mv", 0)) > 0.5:
                    rep.check(False, f"{where}: item_id={key[0]} in slot {key[1]!r} has mv={r.get('mv'):+.1f} "
                                      f"but was already seen with mv={seen_ids[key].get('mv'):+.1f} "
                                      f"in tier {seen_ids[key].get('tier')!r}")
                seen_ids[key] = r

    # A real, harmless state for a character whose gearing hasn't been
    # chased/optimized yet (every slot still has real upgrades available,
    # so none is "done") - not a bug. Was a hard failure (rep.check) until
    # it fired for two different real, less-progressed characters in a
    # row (Rubán, Béarforceone) - the assumption "everyone has at least one
    # finished slot" turned out to just be a Lerynia-specific artifact of
    # how much attention her gear has had, not a real invariant. Softened
    # to a warning per the user's own call.
    achieved = report.get("achieved_bis", [])
    rep.warn(len(achieved) > 0, "tiered_report.json: achieved_bis is empty (harmless if this character's gear isn't fully optimized yet)")
    for entry in achieved:
        rep.check("slot" in entry and "items" in entry, f"tiered_report.json: malformed achieved_bis entry {entry!r}")

    # missing_enchants: absence entirely is a soft warning only, since a
    # cached report from before this feature landed (2026-08-25) genuinely
    # predates the key - real, not a bug. An empty list on a FRESH report
    # is separately harmless too (either every slot's already on its real
    # BiS enchant, or the profile has no verified default_enchants.json
    # data yet - a disclosed DB-coverage gap, see NOTES.md, not a pipeline
    # defect).
    rep.warn("missing_enchants" in report, "tiered_report.json: missing_enchants key absent (report predates the Missing Enchants feature)")
    for entry in report.get("missing_enchants", []):
        for field in ("slot", "item_name", "bis_enchant_id", "bis_name", "mv", "noise_stdev"):
            rep.check(field in entry, f"tiered_report.json: malformed missing_enchants entry, missing '{field}': {entry!r}")
        rep.check(entry.get("mv", 0) > 0, f"tiered_report.json: missing_enchants entry has non-positive mv (should have been filtered): {entry!r}")

    # Stage 6.3 (2026-08-25): a weave-supported profile's two_hand rows must
    # ALL carry a real boolean `weave` tag (which comparison each row came
    # from - weave-on vs the real no-weave-at-all pass) so the report can
    # group them without silently interleaving two numbers that assume
    # different scenarios; a non-weave profile's rows must have NONE, same
    # shape as before this feature existed - a mix would mean the two
    # run_2h_pass() calls disagreed on whether to tag at all.
    two_hand_meta = report.get("two_hand_meta", {})
    weave_supported = two_hand_meta.get("weave_supported")
    for r in report.get("two_hand", []):
        for field in ("name", "item_id", "mv", "tier"):
            rep.check(field in r, f"two_hand: missing field '{field}' on {r.get('name', '?')!r}")
        if r.get("resolved"):
            rep.check(r.get("resolve_iterations", 0) > 0,
                       f"two_hand: {r.get('name')!r} is resolved but resolve_iterations is missing/zero")
        if weave_supported:
            rep.check(isinstance(r.get("weave"), bool),
                       f"two_hand: {r.get('name')!r} on a weave-supported profile is missing a real boolean 'weave' tag")
        else:
            rep.check("weave" not in r,
                       f"two_hand: {r.get('name')!r} has a 'weave' tag on a profile with weave_supported=false")


def check_transform(report: dict, ledger_data: dict, rep: Report) -> None:
    """Re-derive build_ledger_data.py's own transform and diff against its real output."""
    rep.check(ledger_data.get("baseline_dps") == report.get("baseline_screened"),
               f"ledger_data.json: baseline_dps={ledger_data.get('baseline_dps')} != "
               f"tiered_report.json baseline_screened={report.get('baseline_screened')}")
    rep.check(bool(ledger_data.get("sim_commit_sha")),
               "ledger_data.json: sim_commit_sha is missing/empty - ground rule requires it on every output")

    expected_tier_names = [name for name, slots in report.get("tiers", {}).items() if slots]
    got_tier_names = [t["name"] for t in ledger_data.get("tiers", [])]
    rep.check(expected_tier_names == got_tier_names,
               f"ledger_data.json: tier order/set mismatch - expected {expected_tier_names}, got {got_tier_names}")

    ledger_tiers_by_name = {t["name"]: t for t in ledger_data.get("tiers", [])}
    for tier_name, slot_dict in report.get("tiers", {}).items():
        if not slot_dict:
            continue
        lt = ledger_tiers_by_name.get(tier_name)
        rep.check(lt is not None, f"ledger_data.json: tier {tier_name!r} present in tiered_report.json but missing")
        if lt is None:
            continue
        ledger_slots_by_name = {s["slot"]: s for s in lt["slots"]}
        for slot_name, rows in slot_dict.items():
            ls = ledger_slots_by_name.get(slot_name)
            rep.check(ls is not None,
                       f"ledger_data.json: tier {tier_name!r} slot {slot_name!r} present in "
                       f"tiered_report.json but missing from ledger_data.json")
            if ls is None:
                continue
            expected_more = max(0, len(rows) - TOP_N_SHOWN)
            rep.check(ls.get("more") == expected_more,
                       f"ledger_data.json: {tier_name!r}/{slot_name!r} 'more' count is {ls.get('more')}, "
                       f"expected {expected_more} ({len(rows)} rows - top {TOP_N_SHOWN} shown)")
            shown = rows[:TOP_N_SHOWN]
            got_ids = [it.get("item_id") for it in ls.get("items", [])]
            expected_ids = [it.get("item_id") for it in shown]
            rep.check(got_ids == expected_ids,
                       f"ledger_data.json: {tier_name!r}/{slot_name!r} item order/content mismatch - "
                       f"expected item_ids {expected_ids}, got {got_ids}")

    rep.check(ledger_data.get("achieved_bis") == report.get("achieved_bis"),
               "ledger_data.json: achieved_bis does not pass through tiered_report.json unchanged")
    rep.check(ledger_data.get("missing_enchants", []) == report.get("missing_enchants", []),
               "ledger_data.json: missing_enchants does not pass through tiered_report.json unchanged")
    rep.check(ledger_data.get("two_hand") == report.get("two_hand"),
               "ledger_data.json: two_hand does not pass through tiered_report.json unchanged")
    rep.check(ledger_data.get("two_hand_meta") == report.get("two_hand_meta"),
               "ledger_data.json: two_hand_meta does not pass through tiered_report.json unchanged")


def extract_html_data_blob(html_path: str) -> dict | None:
    with open(html_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"const DATA = (\{.*?\});\s*$", text, re.MULTILINE)
    if not m:
        return None
    return json.loads(m.group(1))


def check_html(ledger_data: dict, html_path: str, rep: Report) -> None:
    if not os.path.exists(html_path):
        rep.warn(False, f"HTML check skipped - {html_path} not found (scratch artifact dir, may not exist here)")
        return

    with open(html_path, encoding="utf-8") as f:
        html_text = f.read()

    html_data = extract_html_data_blob(html_path)
    rep.check(html_data is not None, f"{html_path}: could not find/parse 'const DATA = {{...}};' block")
    if html_data is not None:
        # This is exactly the 2026-08-23 bug class: the DATA blob spliced
        # into the HTML silently drifting from the real ledger_data.json it
        # was supposed to be a copy of.
        rep.check(html_data == ledger_data,
                   f"{html_path}: embedded DATA blob does not match data/cache/ledger_data.json - "
                   f"the ledger was published from stale or hand-edited data")

    # Guards against the rescue_note-never-rendered bug class: the render
    # template silently missing a block for a field the data actually has.
    rep.check("it.set_note" in html_text, f"{html_path}: no render block references it.set_note")
    rep.check("it.rescue_note" in html_text, f"{html_path}: no render block references it.rescue_note")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="Lerynia-Thunderstrike")
    parser.add_argument("--phase", default="phase3")
    parser.add_argument("--html", default=DEFAULT_HTML, help="Path to the published ledger HTML")
    parser.add_argument("--skip-html", action="store_true", help="Skip the HTML splice check")
    args = parser.parse_args()

    rep = Report()

    char_cache_dir = os.path.join(REPO_ROOT, "data", "characters", args.character, "cache")
    tiered_path = os.path.join(char_cache_dir, f"tiered_report_{args.phase}.json")
    ledger_path = os.path.join(char_cache_dir, f"ledger_data_{args.phase}.json")

    if not os.path.exists(tiered_path):
        print(f"FATAL: {tiered_path} not found - run core/run_full_sweep_mv.py first")
        return 2
    if not os.path.exists(ledger_path):
        print(f"FATAL: {ledger_path} not found - run core/build_ledger_data.py first")
        return 2

    report = json.load(open(tiered_path, encoding="utf-8"))
    ledger_data = json.load(open(ledger_path, encoding="utf-8"))

    check_tiered_report(report, rep)
    check_transform(report, ledger_data, rep)
    if not args.skip_html:
        check_html(ledger_data, args.html, rep)

    print(f"Ledger consistency check: {rep.checked} assertions, {len(rep.failures)} failure(s), "
          f"{len(rep.warnings)} warning(s).\n")

    for w in rep.warnings:
        print(f"WARN: {w}")
    if rep.warnings:
        print()

    if rep.failures:
        for f in rep.failures:
            print(f"FAIL: {f}")
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
