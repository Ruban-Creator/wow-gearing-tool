"""RGT's own version identity - separate from the vendored sim's own version
(see repo_root.py's sim_version_label()/sim_commit_sha(), which track
wowsims/tbc-new's own release, not this tool's).

Format: "{STAGE} - v{MAJOR_MINOR}.{BUILD:04d}", e.g. "Pre-Release - v0.7.0001".

Bump rules, per the user (2026-09-06):
- STAGE/MAJOR_MINOR change ONLY on the user's own explicit instruction
  (Pre-Release -> Alpha v0.8 -> Beta v0.9 -> Release v1.0) - never bump these
  unilaterally.
- BUILD increments by 1 every time the GUI/tool is rebuilt for real,
  packaged distribution (a real PyInstaller+Inno Setup rebuild) - add a
  matching CHANGELOG.md entry at the same time, same convention as every
  other real change in this project needing a record. Never bump BUILD for
  an in-progress, not-yet-rebuilt code change alone.
"""

STAGE = "Pre-Release"
MAJOR_MINOR = "0.7"
BUILD = 4


def version_string() -> str:
    return f"{STAGE} - v{MAJOR_MINOR}.{BUILD:04d}"
