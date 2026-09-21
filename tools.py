import os
import subprocess
import winreg

START_MENU_CACHE = {}


def build_start_menu_cache():
    print("System: Scanning Start Menu and Taskbar for apps (this happens once)...")
    paths_to_scan = [
        # Standard Start Menu
        os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        os.path.join(os.getenv('PROGRAMDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        # Secret Taskbar folder where pinned apps hide
        os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Internet Explorer', 'Quick Launch', 'User Pinned', 'TaskBar')
    ]

    for path in paths_to_scan:
        if not os.path.exists(path): continue
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('.lnk'):
                    app_name = file.lower().replace('.lnk', '')
                    START_MENU_CACHE[app_name] = os.path.join(root, file)

    print(f"System: Found {len(START_MENU_CACHE)} apps in Start Menu.")


# USER OVERRIDE: If an app won't open, put the direct path to the .exe here!
CUSTOM_APP_PATHS = {
    # Example: "telegram": "C:\\Users\\srava\\AppData\\Roaming\\Telegram Desktop\\Telegram.exe"
}


def open_application(app_name):
    """Opens an application using multiple bulletproof methods."""

    # 1. Built-in Windows system apps
    system_apps = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "file manager": "explorer.exe",
        "explorer": "explorer.exe",
        "paint": "mspaint.exe"
    }

    app_lower = app_name.lower()

    if app_lower in system_apps:
        try:
            subprocess.Popen([system_apps[app_lower]])
            return f"Success: Opened {app_name}."
        except Exception as e:
            return f"Error: {str(e)}"

    # 2. Check custom user paths first!
    if app_lower in CUSTOM_APP_PATHS:
        try:
            os.startfile(CUSTOM_APP_PATHS[app_lower])
            return f"Success: Opened {app_name} via Custom Path."
        except Exception:
            pass

    # 3. Smart Match in Start Menu
    for cached_app, path in START_MENU_CACHE.items():
        if app_lower in cached_app:
            try:
                os.startfile(path)
                return f"Success: Opened {app_name} via Start Menu."
            except Exception:
                pass

    # 4. Windows Registry App Paths Search
    possible_names = [f"{app_name}.exe", f"{app_lower}.exe", app_name]
    for name in possible_names:
        try:
            key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{name}"
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            exe_path, regtype = winreg.QueryValueEx(key, None)
            winreg.CloseKey(key)

            if exe_path:
                os.startfile(exe_path)
                return f"Success: Opened {app_name} via Windows Registry."
        except FileNotFoundError:
            continue
        except Exception:
            continue

    return f"Error: I couldn't find {app_name} on your computer."