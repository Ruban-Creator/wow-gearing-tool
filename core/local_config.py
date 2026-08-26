"""Local, per-machine config that shouldn't travel via git (see
.gitignore's data/local_config.json entry) - today just where the GUI's Run
Report writes finished HTML reports. Plain load()/save() rather than a
class, and kept at core/ level rather than gui/ - a future CLI command
could read/write it too, not just the GUI.
"""
import json
import os
import sys
import string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import repo_root  # noqa: E402
REPO_ROOT = repo_root.REPO_ROOT
CONFIG_PATH = os.path.join(REPO_ROOT, "data", "local_config.json")


def load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save(config: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def report_output_root() -> str | None:
    """None means "use the default" (data/characters/<name>/reports/) - a
    user-configured root overrides that entirely, e.g. if they'd rather the
    HTML files live somewhere they'll actually browse to day to day."""
    return load().get("report_output_root")


def set_report_output_root(path: str | None) -> None:
    """Pass None to clear back to the default."""
    config = load()
    if path is None:
        config.pop("report_output_root", None)
    else:
        config["report_output_root"] = path
    save(config)


def report_output_path(name_realm: str, phase: str) -> str:
    root = report_output_root()
    if root:
        return os.path.join(root, name_realm, f"{phase}.html")
    return os.path.join(REPO_ROOT, "data", "characters", name_realm, "reports", f"{phase}.html")


# The only hardcoded fallback left once wow_root() has no configured value
# AND autodetect_wow_root() finds nothing real - matches this project's own
# original hardcoded WOW_ROOT (ingest/build_character.py, now sourced from
# here instead). Real on the machine this was developed on, but genuinely
# just one person's install location - never assume it's right elsewhere,
# which is the whole reason this got made configurable (per the user,
# 2026-08-26).
_LEGACY_DEFAULT_WOW_ROOT = r"C:\Games\World of Warcraft\_anniversary_"

# Real, common install roots (relative to a drive letter) for the
# Anniversary client specifically - Battle.net's own historical default
# (Program Files (x86)), a newer-install default (Program Files), a flat
# drive-root install, and this project's own original hardcoded location.
# Each candidate is verified via the client's own real .flavor.info file
# (confirmed real content on the dev machine: literally "wow_anniversary")
# before being trusted - never just assumed present because the folder
# exists, since a retail/Classic/Cata-Classic install can sit right next to
# it under a differently-named flavor folder.
_CANDIDATE_SUBPATHS = [
    r"Program Files (x86)\World of Warcraft\_anniversary_",
    r"Program Files\World of Warcraft\_anniversary_",
    r"World of Warcraft\_anniversary_",
    r"Games\World of Warcraft\_anniversary_",
]


def _looks_like_anniversary_client(path: str) -> bool:
    flavor_path = os.path.join(path, ".flavor.info")
    if not os.path.isfile(flavor_path):
        return False
    try:
        with open(flavor_path, encoding="utf-8", errors="ignore") as f:
            return "wow_anniversary" in f.read()
    except OSError:
        return False


def autodetect_wow_root() -> str | None:
    """Scans every real drive letter present on this machine for a real
    Anniversary-client install, verified via the client's own .flavor.info
    file rather than just a matching folder name. Returns the first real
    match found, or None if nothing real was found anywhere - callers must
    handle None (fall back to _LEGACY_DEFAULT_WOW_ROOT, or ask the user),
    never invent a path when this comes back empty."""
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if not os.path.isdir(drive):
            continue
        for subpath in _CANDIDATE_SUBPATHS:
            candidate = os.path.join(drive, subpath)
            if _looks_like_anniversary_client(candidate):
                return candidate
    return None


def wow_root() -> str:
    """The real WoW Anniversary install root used to find addon
    SavedVariables (ingest/build_character.py's find_savedvariables(),
    which feeds both the sync pipeline and the GUI's character picker).
    Precedence: explicit user config > real autodetection (verified via
    .flavor.info, never just a folder-name guess) > the one legacy
    hardcoded default, kept only so a machine that had this working before
    wow_root() existed doesn't regress."""
    configured = load().get("wow_root")
    if configured:
        return configured
    detected = autodetect_wow_root()
    if detected:
        return detected
    return _LEGACY_DEFAULT_WOW_ROOT


def set_wow_root(path: str | None) -> None:
    """Pass None to clear back to autodetect/legacy-default behavior."""
    config = load()
    if path is None:
        config.pop("wow_root", None)
    else:
        config["wow_root"] = path
    save(config)


def debug_mode() -> bool:
    """Off by default - the GUI's real, addon-sourced character picker
    (ingest/list_characters.py) never includes the synthetic test
    characters built for profile verification (Test-*-Synthetic), since
    they have no real WowSimsExporter/GearingToolCompanion SavedVariables
    entry to be discovered from. Debug mode opts into also listing those,
    so a new profile can be smoke-tested through the actual GUI instead of
    only ever the CLI/direct-Python path - per the user, 2026-08-26."""
    return bool(load().get("debug_mode", False))


def set_debug_mode(enabled: bool) -> None:
    config = load()
    if enabled:
        config["debug_mode"] = True
    else:
        config.pop("debug_mode", None)
    save(config)
