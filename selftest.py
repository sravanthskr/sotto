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

import briefing
import display
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

    print("\n== safety & new tools ==")
    for n in ("shutdown_pc", "restart_pc", "cancel_shutdown", "sleep_pc", "lock_pc",
              "delete_path", "look_up"):
        assert n in tools.REGISTRY, n
    assert tools.is_dangerous("shutdown_pc") and tools.is_dangerous("delete_path")
    assert not tools.is_dangerous("cancel_shutdown")
    import confirm    # noqa: F401  (confirmation dialog module loads)
    import sysactions  # noqa: F401
    danger = [n for n, e in tools.REGISTRY.items() if e["danger"]]
    print(f"  new tools registered; {len(danger)} dangerous tools gated: {sorted(danger)}")

    print("\n== learning & memory tools ==")
    import learn
    assert learn.parse_facts('sure: ["likes coffee", "uses PyCharm"]') == ["likes coffee", "uses PyCharm"]
    assert learn.parse_facts("nothing here") == []
    with tempfile.TemporaryDirectory() as td:
        m = Memory(path=Path(td) / "m.json")
        m.add_fact("likes coffee")
        m.add_fact("uses PyCharm")
        removed_msg = m.remove_fact("coffee")
        assert "Forgot 1" in removed_msg, removed_msg
        assert m.facts() == ["uses PyCharm"], m.facts()
        m.clear()
        assert m.facts() == []
        print("  parse + remove + clear ok")

    print("\n== audit log ==")
    import audit
    with tempfile.TemporaryDirectory() as td:
        audit.AUDIT_LOG = Path(td) / "audit.log"
        audit.log("open_application", {"app_name": "Chrome"}, "Opened Chrome.")
        rows = audit.recent(5)
        assert rows and rows[0]["tool"] == "open_application"
        print(f"  writes + reads back ok ({len(rows)} row)")

    print("\n== files: read & search ==")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "note.txt").write_text("hello voiceStra world")
        (root / "sub").mkdir()
        (root / "sub" / "deep_note.txt").write_text("nested content")
        assert "hello voiceStra world" in tools.read_file(str(root / "note.txt"))
        assert "note.txt" in tools.find_files("note", root=str(root))
        assert "deep_note.txt" in tools.find_in_files("nested", root=str(root))
        print("  read_file, find_files, find_in_files ok")

    print("\n== new tool registry entries ==")
    for n in ("list_facts", "forget_fact", "read_file", "find_files",
              "find_in_files", "show_audit"):
        assert n in tools.REGISTRY, n
    print("  all present")

    print("\n== display & briefing ==")
    vol = display.get_volume()
    br = display.get_brightness()
    print(f"  volume={vol} brightness={br}  (None = not supported on this display)")
    left, top, right, bottom = winctl._work_area()
    assert right > left and bottom > top, (left, top, right, bottom)
    print(f"  work area ok: {right - left}x{bottom - top}")
    assert briefing.greeting_for(9) == "Good morning"
    assert briefing.greeting_for(15) == "Good afternoon"
    assert briefing.greeting_for(21) == "Good evening"
    print("  greeting logic ok")

    print("\n== registry: display + briefing tools ==")
    for n in ("snap_window", "set_brightness", "get_brightness", "set_volume", "get_volume",
              "get_weather", "daily_briefing"):
        assert n in tools.REGISTRY, n
    print("  all present")

    print("\nAll offline checks passed.")


if __name__ == "__main__":
    main()
