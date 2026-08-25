"""Local, per-machine config that shouldn't travel via git (see
.gitignore's data/local_config.json entry) - today just where the GUI's Run
Report writes finished HTML reports. Plain load()/save() rather than a
class, and kept at core/ level rather than gui/ - a future CLI command
could read/write it too, not just the GUI.
"""
import json
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
