"""Splices real per-run data into report_template.html's placeholder tokens
- the local, self-hosted successor to hand-editing/publishing a Claude.ai
Artifact each time a report is needed (a standalone GUI exe has no way to
call that tool - see the plan's Context section,
C:\\Users\\Matthias\\.claude\\plans\\staged-purring-lynx.md).
"""
import json
import os

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_template.html")


def _format_subtitle(character: dict, phase_num: int) -> str:
    """<b>Name</b> · Race Spec Class · Prof1/Prof2 · Phase N - matches the
    original hand-built ledger's header text exactly, but derived from real
    character.json fields instead of hardcoded, so it stays correct for
    whichever character/phase actually ran (race casing e.g. "NightElf" ->
    "Nightelf" matches the original file's own styling, not WoW's own
    camelCase - a simple first-letter-only-capitalized transform, not a
    race-specific lookup table)."""
    c = character["character"]
    race = c["race"][:1] + c["race"][1:].lower()
    spec_class = f"{c['spec'].capitalize()} {c['class'].capitalize()}"
    professions = "/".join(p["name"] for p in c["professions"])
    return f"<b>{c['name']}</b> · {race} {spec_class} · {professions} · Phase {phase_num}"


def render(ledger_data: dict, character: dict, phase: str) -> str:
    """character is a full character.json dict (build_character.build()'s
    output) - used only for the header's display text, never for anything
    the sim itself reads. phase e.g. "phase3"."""
    phase_num = int(phase.removeprefix("phase"))
    title = f"Phase {phase_num} Upgrade Ledger"
    subtitle = _format_subtitle(character, phase_num)

    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        html = f.read()

    html = html.replace("__REPORT_TITLE__", title)
    html = html.replace("__REPORT_SUBTITLE__", subtitle)
    html = html.replace("__REPORT_DATA_JSON__", json.dumps(ledger_data))
    return html


if __name__ == "__main__":
    import build_ledger_data

    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    name_realm, phase = "Lerynia-Thunderstrike", "phase3"
    character = json.load(open(os.path.join(REPO_ROOT, "data", "characters", name_realm, "character.json"), encoding="utf-8"))
    ledger_data = build_ledger_data.build(name_realm, phase)
    html = render(ledger_data, character, phase)

    out_dir = os.path.join(REPO_ROOT, "data", "characters", name_realm, "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{phase}.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out_path}")
