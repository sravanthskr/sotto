"""
verify_apps.py - list every application the scanner can currently find.

Run:  python verify_apps.py
If an app is missing, add its .exe path to CUSTOM_APP_PATHS in tools.py.
"""

import tools


def main():
    tools.build_app_index(verbose=True)
    print("\n--- ALL APPS FOUND ---")
    for name in sorted(tools.APP_INDEX):
        print(f"  {name}")
    print("----------------------")
    print(f"Total apps found: {len(tools.APP_INDEX)}")

    print("\nLooking for a few common ones...")
    for probe in ("telegram", "chrome", "vlc", "pycharm", "musicbee"):
        target = tools.resolve_app(probe)
        print(f"  {probe:10} -> {target or 'NOT FOUND'}")


if __name__ == "__main__":
    main()
