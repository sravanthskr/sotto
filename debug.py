import os

# Get the hidden Start Menu paths
paths = [
    os.path.join(os.getenv('APPDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    os.path.join(os.getenv('PROGRAMDATA'), 'Microsoft', 'Windows', 'Start Menu', 'Programs')
]

found_apps = []

# Scan all folders and files
for path in paths:
    if os.path.exists(path):
        for root, dirs, files in os.walk(path):
            for file in files:
                # Look for shortcuts (.lnk files)
                if file.endswith('.lnk'):
                    found_apps.append(file.replace('.lnk', ''))

# Print all found apps so we can see if Chrome/Telegram are actually there
print("--- APPS FOUND IN START MENU ---")
for app in sorted(found_apps):
    print(app)
print("---------------------------------")
print(f"Total found: {len(found_apps)}")