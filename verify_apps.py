import tools

# Build the cache using the new tool that scans Start Menu + Taskbar
tools.build_start_menu_cache()

print("\n--- ALL APPS FOUND IN CACHE ---")
# Sort them alphabetically so it's easy to read
for app in sorted(tools.START_MENU_CACHE.keys()):
    print(app)
print("-------------------------------\n")
print(f"Total apps found: {len(tools.START_MENU_CACHE)}")

# Check specifically for Telegram
print("\nSearching for Telegram specifically...")
telegram_found = False
for app in tools.START_MENU_CACHE:
    if "telegram" in app:
        telegram_found = True
        print(f"FOUND: {app}")

if not telegram_found:
    print("Telegram still NOT found in cache. You will need to use the manual override path.")