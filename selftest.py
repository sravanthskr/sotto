"""
selftest.py - offline checks that don't touch the network or your API key.

Run it to confirm app discovery, the tool registry, memory, notes, reminders,
window control, and file organising all work:
    python selftest.py
"""

import tempfile
import time as _time
from datetime import datetime, timedelta
from pathlib import Path

import fileops
import tools
import winctl
from memory import Memory
from notes import Notes
from reminders import ReminderManager


def main():
    print("== app discovery ==")
    tools.build_app_index(verbose=True)
    probes = ["telegram", "chrome", "notepad", "vlc", "pycharm", "musicbee",
              "obsidian", "signal", "docker desktop", "mp3tag"]
    found = sum(1 for q in probes if tools.resolve_app(q))
    print(f"  resolved {found}/{len(probes)} probes, {len(tools.APP_INDEX)} shortcuts indexed")

    print("\n== tool registry ==")
    for name, entry in sorted(tools.REGISTRY.items()):
        flags = "danger" if entry["danger"] else "safe"
        props = list(entry["schema"]["function"]["parameters"].get("properties", {}).keys())
        print(f"  {name:18} [{flags}] args={props}")
    for entry in tools.REGISTRY.values():
        fn = entry["schema"]["function"]
        assert fn.get("name") and fn.get("description") and "parameters" in fn, fn
    print(f"  {len(tools.REGISTRY)} schemas valid")

    print("\n== memory ==")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mem.json"
        m = Memory(path=p)
        m.add_fact("The user's name is Sravanth.")
        m.add_fact("The user's name is Sravanth.")   # duplicate -> ignored
        m.set_summary("Talked about building an assistant.")
        m2 = Memory(path=p)                          # reload from disk
        assert m2.facts() == ["The user's name is Sravanth."], m2.facts()
        print("  facts + summary persist ok")

    print("\n== notes ==")
    with tempfile.TemporaryDirectory() as td:
        n = Notes(path=Path(td) / "notes.json")
        n.add("buy milk")
        n.add("call the bank")
        assert len(n.search("bank")) == 1
        assert len(Notes(path=Path(td) / "notes.json").list()) == 2
        print("  notes add/search/persist ok")

    print("\n== reminders ==")
    with tempfile.TemporaryDirectory() as td:
        fired = []
        rm = ReminderManager(on_fire=fired.append, path=Path(td) / "rem.json", tick=0.2)
        rm.add("hydrate", datetime.now() + timedelta(seconds=0.5))
        assert len(rm.list()) == 1
        rm.start()
        _time.sleep(1.2)
        rm.stop()
        assert fired and fired[0]["message"] == "hydrate", fired
        assert rm.pending_count() == 0
        print("  reminder fired on time and cleared ok")

    print("\n== window control ==")
    titles = winctl.list_windows()
    print(f"  detected {len(titles)} open window(s): {titles[:5]}")

    print("\n== files ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fileops.ORGANIZE_LOG = root / "undo.json"   # keep the test self-contained
        for fn in ("a.txt", "b.jpg", "c.mp4"):
            (root / fn).write_text("x")
        msg = fileops.organize_downloads(path=root)
        assert (root / "Documents" / "a.txt").exists()
        assert (root / "Images" / "b.jpg").exists()
        assert (root / "Videos" / "c.mp4").exists()
        print(f"  {msg}")
        back = fileops.undo_organize()
        assert (root / "a.txt").exists() and (root / "b.jpg").exists()
        print(f"  {back}")

    print("\nAll offline checks passed.")


if __name__ == "__main__":
    main()
