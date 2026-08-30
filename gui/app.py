"""Entry point for the Gearing Tool GUI (picker + report viewer, v1 - see
the approved plan). Run with `python gui/app.py` from the repo root, or as
the packaged .exe's entry point (packaging/gearing_tool_gui.spec) - the exe
finds the real repo root itself by walking up from its own on-disk location
(see api.py's _find_repo_root), so no working-directory/"Start in" setup is
required; it can run from dist/ or wherever it's been copied to inside (or
under) a real checkout."""
import os
import sys

import webview

from api import Api

# PyInstaller --add-data "gui/assets;gui/assets" bundles the assets folder
# under sys._MEIPASS (the frozen exe's temp extraction dir) - __file__'s own
# directory only resolves correctly when running from real source. See
# api.py's REPO_ROOT for the same frozen-vs-source split, same reasoning.
if getattr(sys, "frozen", False):
    ASSETS_DIR = os.path.join(sys._MEIPASS, "gui", "assets")
else:
    ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def main():
    api = Api()
    webview.create_window(
        "Ruban's Gearing Tool",
        url=os.path.join(ASSETS_DIR, "index.html"),
        js_api=api,
        width=900,
        height=650,
        min_size=(700, 500),
        background_color="#14161a",
    )
    # Real per-window icon, not just the exe's own embedded resource -
    # create_window() itself has no icon param (checked its signature
    # directly), but start() does. Belt-and-suspenders with the PyInstaller
    # spec's own icon= (packaging/gearing_tool_gui.spec) rather than relying
    # on either alone, since which one actually controls the taskbar/window
    # icon can vary by pywebview's active GUI backend.
    webview.start(icon=os.path.join(ASSETS_DIR, "app_icon.ico"))


if __name__ == "__main__":
    main()
