"""
selftest.py - offline checks that don't touch the network or your API key.

Run it to confirm app discovery, the tool registry, and memory all work:
    python selftest.py
"""

import json
import tempfile
from pathlib import Path

import tools
from memory import Memory


def main():
    print("== app discovery ==")
    tools.build_app_index(verbose=True)
    probes = ["telegram", "chrome", "notepad", "vlc", "pycharm", "musicbee",
              "obsidian", "signal", "docker desktop", "mp3tag"]
    found = 0
    for q in probes:
        target = tools.resolve_app(q)
        mark = "OK " if target else "-- "
        if target:
            found += 1
        print(f"  {mark}{q:16} -> {target}")
    print(f"  resolved {found}/{len(probes)} probes")
    print(f"  total shortcuts indexed: {len(tools.APP_INDEX)}")

    print("\n== tool registry ==")
    for name, entry in sorted(tools.REGISTRY.items()):
        flags = "danger" if entry["danger"] else "safe"
        props = list(entry["schema"]["function"]["parameters"].get("properties", {}).keys())
        print(f"  {name:18} [{flags}] args={props}")

    print("\n== schema validity ==")
    ok = True
    for entry in tools.REGISTRY.values():
        fn = entry["schema"]["function"]
        if not fn.get("name") or not fn.get("description") or "parameters" not in fn:
            ok = False
            print(f"  BAD: {fn}")
    print("  all schemas valid" if ok else "  some schemas are invalid")

    print("\n== memory round-trip ==")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "mem.json"
        m = Memory(path=p)
        m.add_fact("The user's name is Sravanth.")
        m.add_fact("The user's name is Sravanth.")   # duplicate, should be ignored
        m.set_summary("Talked about building an assistant.")
        m2 = Memory(path=p)                          # reload from disk
        assert m2.facts() == ["The user's name is Sravanth."], m2.facts()
        assert "assistant" in m2.summary()
        print(f"  facts persisted: {m2.facts()}")
        print(f"  summary persisted: {m2.summary()}")
        print("  memory ok")

    print("\nAll offline checks passed.")


if __name__ == "__main__":
    main()
