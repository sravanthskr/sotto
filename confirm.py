"""
confirm.py - a real confirmation prompt for risky actions.

Tries a native Windows dialog first (topmost, so you can't miss it). If there's no
desktop session to draw on, it falls back to a console y/n prompt. The dialog is
modal: nothing runs until you answer.
"""

import ctypes

_MB_YESNO = 0x00000004
_MB_ICONWARNING = 0x00000030
_MB_TOPMOST = 0x00040000
_MB_SETFOREGROUND = 0x00010000
_IDYES = 6


def ask(question, detail="", title="RealAssistant"):
    """Return True if the user approves, False otherwise."""
    text = question if not detail else f"{question}\n\n{detail}"
    try:
        result = ctypes.windll.user32.MessageBoxW(
            None, text, title,
            _MB_YESNO | _MB_ICONWARNING | _MB_TOPMOST | _MB_SETFOREGROUND,
        )
        return result == _IDYES
    except Exception:
        pass
    # No GUI available - fall back to the console.
    try:
        ans = input(f"  [!] {question} {detail} [y/n]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")
