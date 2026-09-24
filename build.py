"""
build.py - package RealAssistant into a single Windows .exe with PyInstaller.

Usage:
    python -m pip install pyinstaller
    python build.py

The result is dist/RealAssistant.exe. Put your .env file next to the .exe when you
run it (the app reads the key from the working directory).
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent

# Modules that PyInstaller can't always see on its own (imported dynamically / via COM).
HIDDEN_IMPORTS = [
    "pycaw",
    "pycaw.pycaw",
    "comtypes",
    "ddgs",
    "pypdf",
    "PIL",
    "PIL.ImageGrab",
    "dotenv",
    "groq",
    "psutil",
]


def main():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller isn't installed. Run: python -m pip install pyinstaller")
        return 1

    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile",
        "--name", "RealAssistant",
        "--console",
    ]
    for module in HIDDEN_IMPORTS:
        args += ["--hidden-import", module]
    args.append(str(ROOT / "main.py"))

    print("Building RealAssistant.exe (this can take a few minutes)...")
    result = subprocess.run(args, cwd=str(ROOT))
    if result.returncode == 0:
        print(f"\nDone -> {ROOT / 'dist' / 'RealAssistant.exe'}")
        print("Remember to place a .env file next to the .exe before running it.")
    else:
        print("\nBuild failed. If a library is missing, add it to HIDDEN_IMPORTS.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
