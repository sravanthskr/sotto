"""
ui_app.py - launches the desktop app.

    .\\run.bat ui          (or: python ui_app.py)

A native window (no browser) hosting the UI in ui/, wired to the same Assistant the
console and voice front-ends use.
"""

from pathlib import Path

import webview

from ui_bridge import Api

INDEX = Path(__file__).parent / "ui" / "index.html"


def main():
    api = Api()
    window = webview.create_window(
        "RealAssistant",
        str(INDEX),
        js_api=api,
        width=1180,
        height=780,
        min_size=(900, 600),
        background_color="#f5f5f7",
    )
    api.start()
    webview.start()


if __name__ == "__main__":
    main()
