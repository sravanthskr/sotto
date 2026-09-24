"""
core.py - the engine.

Everything an interface needs lives on the Assistant object. The console in main.py is
just one front-end; a future GUI or voice front-end drives the same Assistant without
touching the internals.

    assistant = Assistant(on_text=print)
    assistant.start()
    reply = assistant.ask("open chrome for me")
"""

import json
from datetime import datetime

from config import (
    SYSTEM_PROMPT, RECENT_TURNS_KEPT, SUMMARIZE_WHEN_TURNS_OVER, MAX_TOOL_ROUNDS,
    PROACTIVE, PROACTIVE_INTERVAL,
)
import ai_engine
import tools
from learn import FactLearner
from memory import Memory
from notes import Notes
from proactive import ProactiveWatcher
from reminders import ReminderManager


class Assistant:
    """The brain + hands + memory, with no opinions about how it's displayed."""

    def __init__(self, on_text=None, on_tool=None, on_reminder=None,
                 on_proactive=None, on_learned=None):
        self.on_text = on_text            # callable(chunk:str)
        self.on_tool = on_tool            # callable(name:str, args:dict, result:str)
        self.on_reminder = on_reminder    # callable(message:str)
        self.on_proactive = on_proactive  # callable(message:str)
        self.on_learned = on_learned      # callable(facts:list[str])

        self.memory = Memory()
        tools.set_memory(self.memory)
        self.notes = Notes()
        tools.set_notes(self.notes)
        self.learner = FactLearner(self.memory)

        self.reminders = ReminderManager(on_fire=self._handle_reminder)
        tools.set_reminders(self.reminders)

        self.watcher = ProactiveWatcher(
            notify=self._handle_proactive,
            config={"enabled": PROACTIVE, "interval_seconds": PROACTIVE_INTERVAL},
        )

        self.turns = []

    # -- lifecycle --------------------------------------------------------
    def start(self):
        tools.build_app_index()
        self.reminders.start()
        self.watcher.start()

    def stop(self):
        self.reminders.stop()
        self.watcher.stop()

    # -- default (console-less) callbacks ---------------------------------
    def _handle_reminder(self, reminder):
        message = reminder["message"]
        (self.on_reminder or (lambda m: print(f"\n*** Reminder: {m} ***\n")))(message)

    def _handle_proactive(self, message):
        (self.on_proactive or (lambda m: print(f"\n[proactive] Heads up - {m}.\n")))(message)

    def _handle_learned(self, facts):
        (self.on_learned or (lambda f: print(f"\n[memory] learned: {'; '.join(f)}")))(facts)

    # -- context ----------------------------------------------------------
    def _build_messages(self, user_text):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        now = datetime.now()
        messages.append({"role": "system",
                         "content": f"Current date and time: {now:%A %d %B %Y, %H:%M}."})
        context = self.memory.context_block()
        if context:
            messages.append({"role": "system", "content": context})
        for group in self.turns[-RECENT_TURNS_KEPT:]:
            messages.extend(group)
        messages.append({"role": "user", "content": user_text})
        return messages

    # -- one user turn ----------------------------------------------------
    def ask(self, user_text):
        """Run a turn. Streams text via on_text; returns the assistant's spoken text."""
        messages = self._build_messages(user_text)
        group = [{"role": "user", "content": user_text}]
        spoken = []

        def emit(chunk):
            spoken.append(chunk)
            if self.on_text:
                self.on_text(chunk)

        for _round in range(MAX_TOOL_ROUNDS):
            message = ai_engine.stream_ai(messages, tools=tools.schemas(), on_text=emit)
            messages.append(message)
            group.append(message)

            calls = message.get("tool_calls")
            if not calls:
                break

            for call in calls:
                fn = call.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if tools.is_dangerous(name):
                    result = tools.run_confirmed(name, args)
                else:
                    result = tools.run(name, args)
                if self.on_tool:
                    self.on_tool(name, args, result)
                tool_message = {"role": "tool", "tool_call_id": call.get("id"),
                                "name": name, "content": result}
                messages.append(tool_message)
                group.append(tool_message)
        else:
            final = ai_engine.stream_ai(messages, tools=None, on_text=emit)
            messages.append(final)
            group.append(final)

        self.turns.append(group)
        self._compress()
        self.learner.learn_async(group, on_new=self._handle_learned)
        return "".join(spoken).strip()

    def _compress(self):
        if len(self.turns) <= SUMMARIZE_WHEN_TURNS_OVER:
            return
        old, recent = self.turns[:-RECENT_TURNS_KEPT], self.turns[-RECENT_TURNS_KEPT:]
        flat = [message for group in old for message in group]
        try:
            fresh = ai_engine.summarize(flat)
        except Exception:
            return
        self.memory.set_summary((self.memory.summary() + " " + fresh).strip())
        self.turns[:] = recent

    # -- small conveniences for front-ends --------------------------------
    def remembered_count(self):
        return len(self.memory.facts())

    def pending_reminders(self):
        return self.reminders.pending_count()

    def installed_app_count(self):
        return len(tools.APP_INDEX)
