"""Splices real per-run data into report_template.html's placeholder tokens
- the local, self-hosted successor to hand-editing/publishing a Claude.ai
Artifact each time a report is needed (a standalone GUI exe has no way to
call that tool - see the plan's Context section,
C:\\Users\\<user>\\.claude\\plans\\staged-purring-lynx.md).
"""
import html
import json
import os
import sys

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")


def _format_subtitle(character: dict, phase_num: int) -> str:
    """<b>Name</b> · Race Spec Class · Prof1/Prof2 · Phase N - matches the
    original hand-built ledger's header text exactly, but derived from real
    character.json fields instead of hardcoded, so it stays correct for
    whichever character/phase actually ran (race casing e.g. "NightElf" ->
    "Nightelf" matches the original file's own styling, not WoW's own
    camelCase - a simple first-letter-only-capitalized transform, not a
    race-specific lookup table). Every field is html.escape()'d before
    interpolation (code review §3.2) - Blizzard's real character-name
    charset makes this implausible to actually exploit, but costs nothing
    and matches the discipline gui/assets/app.js's own escapeHtml() already
    applies on the frontend side."""
    c = character["character"]
    name = html.escape(c["name"])
    race = html.escape(c["race"][:1] + c["race"][1:].lower())
    spec_class = html.escape(f"{c['spec'].capitalize()} {c['class'].capitalize()}")
    professions = html.escape("/".join(p["name"] for p in c["professions"]))
    return f"<b>{name}</b> · {race} {spec_class} · {professions} · Phase {phase_num}"


def render(ledger_data: dict, character: dict, phase: str) -> str:
    """character is a full character.json dict (build_character.build()'s
    output) - used only for the header's display text, never for anything
    the sim itself reads. phase e.g. "phase3"."""
    phase_num = int(phase.removeprefix("phase"))
    title = f"Phase {phase_num} Upgrade Ledger"
    subtitle = _format_subtitle(character, phase_num)
    # Separate from the on-page <h1> (which already gets the real name via
    # the subtitle right below it) - the browser tab / bookmark / gallery
    # title needs the name too, or every character's report is
    # indistinguishable from any other open tab showing "Phase 3 Upgrade
    # Ledger".
    page_title = f"{html.escape(character['character']['name'])} — Phase {phase_num} Ledger"

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        page = f.read()

    page = page.replace("__REPORT_PAGE_TITLE__", page_title)
    page = page.replace("__REPORT_TITLE__", title)
    page = page.replace("__REPORT_SUBTITLE__", subtitle)
    # </ escaped to <\/ (valid inside a JSON string, parses identically) so
    # a literal "</script>" inside any string in ledger_data (an item/NPC/
    # zone name from db.json, or a note this tool generates) can't
    # terminate the <script> block early - code review §3.2, json.dumps()
    # does not escape "/" by default.
    payload = json.dumps(ledger_data).replace("</", "<\\/")
    page = page.replace("__REPORT_DATA_JSON__", payload)
    return page


if __name__ == "__main__":
    import build_ledger_data

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import repo_root
    REPO_ROOT = repo_root.REPO_ROOT
    USER_DATA_DIR = repo_root.USER_DATA_DIR
    name_realm, phase = "Lerynia-Thunderstrike", "phase3"
    character = repo_root.load_json(os.path.join(USER_DATA_DIR, "characters", name_realm, "character.json"))
    profile_dir = os.path.join(REPO_ROOT, "profiles", "tbc", "survival_hunter")
    ledger_data = build_ledger_data.build_with_diff(name_realm, phase, profile_dir)
    rendered_html = render(ledger_data, character, phase)

    out_dir = os.path.join(USER_DATA_DIR, "characters", name_realm, "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{phase}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)
    print(f"Wrote {out_path}")
