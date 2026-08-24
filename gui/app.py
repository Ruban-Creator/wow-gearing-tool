"""Entry point for the Gearing Tool GUI (picker + report viewer, v1 - see
the approved plan). Run with `python gui/app.py` from the repo root, or as
the packaged .exe's entry point (packaging/gearing_tool_gui.spec) - the exe
is meant to be launched with the repo root as its working directory, e.g.
"Start in: E:\\Claude\\Gearing-Tool" on a shortcut."""
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
        "Gearing Tool",
        url=os.path.join(ASSETS_DIR, "index.html"),
        js_api=api,
        width=900,
        height=650,
        min_size=(700, 500),
        background_color="#14161a",
    )
    webview.start()


if __name__ == "__main__":
    main()
