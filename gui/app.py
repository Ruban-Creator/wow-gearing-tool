"""Entry point for the Gearing Tool GUI (picker + report viewer, v1 - see
the approved plan). Run with `python gui/app.py` from the repo root, or as
the packaged .exe's entry point (packaging/gearing_tool_gui.spec)."""
import os

import webview

from api import Api

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
