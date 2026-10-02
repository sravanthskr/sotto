"""
ui_app.py - launches the desktop app.

    .\run.bat ui          (or: python ui_app.py)

A native window (no browser) hosting the UI in ui/, wired to the same Assistant the
console and voice front-ends use.
"""

import os
from pathlib import Path

import webview

from ui_bridge import Api

INDEX = Path(__file__).parent / "ui" / "index.html"
STORAGE = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RealAssistant" / "webview"


def main():
    api = Api()
    window = webview.create_window(
        "Sotto",
        str(INDEX),
        js_api=api,
        width=1180,
        height=780,
        min_size=(360, 90),   # small enough for the floating mini overlay (normal window 1180x780)
        background_color="#F6F7F6",
    )
    api.set_window(window)
    try:
        api.start()
    except Exception:
        pass
    webview.start(private_mode=False, storage_path=str(STORAGE))


if __name__ == "__main__":
    main()