"""Builds a real, correctly-structured release zip for the GT Companion addon -
CurseForge (and a manual in-game install) both expect the zip's top-level entry
to be the addon's own folder name (GearingToolCompanion/...), not the files
loose at the zip root. Reads the real shipped version straight out of the
.toc's own `## Version:` field rather than taking it as a separate argument,
so the zip filename can never drift out of sync with what the addon itself
reports in-game.

Usage: python packaging/build_addon_zip.py
Output: packaging/output/GearingToolCompanion-v<version>.zip
"""
import os
import re
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON_DIR = os.path.join(REPO_ROOT, "addons", "GearingToolCompanion")
OUTPUT_DIR = os.path.join(REPO_ROOT, "packaging", "output")

# Only real, functional addon files - README/CHANGELOG are dev-repo docs, not
# something WoW's addon loader needs or CurseForge requires inside the zip
# (CurseForge shows the README.md's own content as the project page
# description directly from the repo, and CHANGELOG.md the same way for the
# changelog tab - shipping copies inside the zip too would be redundant).
INCLUDE_FILES = ["GearingToolCompanion.lua", "GearingToolCompanion.toc", "icon.tga"]

_VERSION_RE = re.compile(r"^##\s*Version:\s*(\S+)", re.MULTILINE)


def read_version() -> str:
    toc_path = os.path.join(ADDON_DIR, "GearingToolCompanion.toc")
    text = open(toc_path, encoding="utf-8").read()
    m = _VERSION_RE.search(text)
    if not m:
        raise ValueError(f"{toc_path} has no '## Version:' field - can't name the zip.")
    return m.group(1)


def build() -> str:
    version = read_version()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"GearingToolCompanion-v{version}.zip")

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in INCLUDE_FILES:
            src = os.path.join(ADDON_DIR, filename)
            if not os.path.exists(src):
                raise FileNotFoundError(f"Expected addon file missing: {src}")
            zf.write(src, arcname=os.path.join("GearingToolCompanion", filename))

    print(f"Wrote {out_path}")
    return out_path


if __name__ == "__main__":
    build()
