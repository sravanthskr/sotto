"""
main.py - the manager.

Runs the loop, builds the context (system prompt + memory + recent turns), dispatches
tool calls, and keeps the rolling memory tidy. Never orphans tool messages, never
crashes the loop on a bad tool call.
"""

import json
import sys
from datetime import datetime

from config import (
    MODEL_NAME, SYSTEM_PROMPT, RECENT_TURNS_KEPT, SUMMARIZE_WHEN_TURNS_OVER,
    MAX_TOOL_ROUNDS, PROACTIVE, PROACTIVE_INTERVAL, ensure_settings_file,
)
import ai_engine
import tools
from learn import FactLearner
from memory import Memory
from notes import Notes
from proactive import ProactiveWatcher
from reminders import ReminderManager


def _setup_console():
    """Stop non-cp1252 characters (smart quotes, dashes) from crashing output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


_setup_console()


def build_messages(memory, turns, user_text):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    now = datetime.now()
    msgs.append({"role": "system",
                 "content": f"Current date and time: {now:%A %d %B %Y, %H:%M}."})
    ctx = memory.context_block()
    if ctx:
        msgs.append({"role": "system", "content": ctx})
    for group in turns[-RECENT_TURNS_KEPT:]:
        msgs.extend(group)
    msgs.append({"role": "user", "content": user_text})
    return msgs


def handle_turn(memory, turns, user_text, learner=None):
    messages = build_messages(memory, turns, user_text)
    group = [{"role": "user", "content": user_text}]
    state = {"speaking": False, "spoke": False, "tool": False}

    def on_text(chunk):
        if not state["speaking"]:
            print("AI: ", end="", flush=True)
            state["speaking"] = True
            state["spoke"] = True
        print(chunk, end="", flush=True)

    def end_line():
        if state["speaking"]:
            print()
            state["speaking"] = False

    for _round in range(MAX_TOOL_ROUNDS):
        mdict = ai_engine.stream_ai(messages, tools=tools.schemas(), on_text=on_text)
        end_line()
        messages.append(mdict)
        group.append(mdict)

        calls = mdict.get("tool_calls")
        if not calls:
            break

        for tc in calls:
            state["tool"] = True
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if tools.is_dangerous(name):
                result = tools.run_confirmed(name, args)
            else:
                result = tools.run(name, args)

            print(f"  [{name} -> {result}]")
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "name": name,
                "content": result,
            }
            messages.append(tool_msg)
            group.append(tool_msg)
    else:
        # Hit the round cap while still wanting tools - get one final spoken line.
        mdict = ai_engine.stream_ai(messages, tools=None, on_text=on_text)
        end_line()
        messages.append(mdict)
        group.append(mdict)

    if not state["spoke"]:
        print("AI: done." if state["tool"]
              else "AI: hmm, I didn't catch that - say it again?")

    turns.append(group)
    _maybe_compress(memory, turns)
    if learner is not None:
        learner.learn_async(group, on_new=_announce_learned)


def _maybe_compress(memory, turns):
    """Compress old turns into the rolling summary, but only drop them on success."""
    if len(turns) <= SUMMARIZE_WHEN_TURNS_OVER:
        return
    old, recent = turns[:-RECENT_TURNS_KEPT], turns[-RECENT_TURNS_KEPT:]
    flat = [m for group in old for m in group]
    try:
        fresh = ai_engine.summarize(flat)
    except Exception as e:
        print(f"  [memory: compression skipped ({e})]")
        return
    combined = (memory.summary() + " " + fresh).strip()
    memory.set_summary(combined)
    turns[:] = recent
    print("  [memory: compressed older turns]")


def _on_reminder(reminder):
    print(f"\n*** Reminder: {reminder['message']} ***\n")


def _on_proactive(message):
    print(f"\n[proactive] Heads up - {message}.\n")


def _announce_learned(facts):
    print(f"\n[memory] learned: {'; '.join(facts)}")


def main():
    ensure_settings_file()
    print(f"Starting up... (model: {MODEL_NAME})")
    tools.build_app_index(verbose=True)

    mem = Memory()
    tools.set_memory(mem)
    learner = FactLearner(mem)

    notes = Notes()
    tools.set_notes(notes)

    reminders = ReminderManager(on_fire=_on_reminder)
    tools.set_reminders(reminders)
    reminders.start()

    watcher = ProactiveWatcher(
        notify=_on_proactive,
        config={"enabled": PROACTIVE, "interval_seconds": PROACTIVE_INTERVAL},
    )
    watcher.start()

    facts = mem.facts()
    if facts:
        print(f"[memory] remembered {len(facts)} thing(s) about you.")
    pending = reminders.pending_count()
    if pending:
        print(f"[reminders] {pending} reminder(s) waiting.")
    print("Ready. Type 'exit' to quit.\n")

    turns = []
    try:
        while True:
            try:
                user_text = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not user_text:
                continue
            if user_text.lower() in ("exit", "quit"):
                break
            try:
                handle_turn(mem, turns, user_text, learner)
            except Exception as e:
                print(f"  [error] {e}")
    finally:
        reminders.stop()
        watcher.stop()


if __name__ == "__main__":
    main()
