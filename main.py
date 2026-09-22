"""
main.py - the manager.

Runs the loop, builds the context (system prompt + memory + recent turns), dispatches
tool calls, and keeps the rolling memory tidy. Never orphans tool messages, never
crashes the loop on a bad tool call.
"""

import json
from datetime import datetime

from config import (
    MODEL_NAME, SYSTEM_PROMPT, RECENT_TURNS_KEPT, SUMMARIZE_WHEN_TURNS_OVER,
    MAX_TOOL_ROUNDS,
)
import ai_engine
import tools
from memory import Memory
from notes import Notes
from reminders import ReminderManager


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


def _confirm(name, args):
    try:
        ans = input(f"  [about to {name} with {args} - do it? y/n]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


def handle_turn(memory, turns, user_text):
    messages = build_messages(memory, turns, user_text)
    group = [{"role": "user", "content": user_text}]

    for _round in range(MAX_TOOL_ROUNDS):
        msg = ai_engine.ask_ai(messages, tools=tools.schemas())
        mdict = ai_engine.message_to_dict(msg)
        messages.append(mdict)
        group.append(mdict)

        calls = mdict.get("tool_calls")
        if not calls:
            break

        for tc in calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}

            if tools.is_dangerous(name) and not _confirm(name, args):
                result = "Cancelled by the user."
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
        final = ai_engine.ask_ai(messages, tools=None)
        mdict = ai_engine.message_to_dict(final)
        messages.append(mdict)
        group.append(mdict)

    for m in reversed(group):
        if m.get("role") == "assistant" and m.get("content"):
            print("AI:", m["content"].strip())
            break

    turns.append(group)
    _maybe_compress(memory, turns)


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


def main():
    print(f"Starting up... (model: {MODEL_NAME})")
    tools.build_app_index(verbose=True)

    mem = Memory()
    tools.set_memory(mem)

    notes = Notes()
    tools.set_notes(notes)

    reminders = ReminderManager(on_fire=_on_reminder)
    tools.set_reminders(reminders)
    reminders.start()

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
                handle_turn(mem, turns, user_text)
            except Exception as e:
                print(f"  [error] {e}")
    finally:
        reminders.stop()


if __name__ == "__main__":
    main()
