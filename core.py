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
    PROACTIVE, PROACTIVE_INTERVAL, CONFIRM_MODE, LEARN_EVERY_N_TURNS,
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
                 on_proactive=None, on_learned=None, on_status=None, on_confirm=None):
        self.on_text = on_text            # callable(chunk:str)
        self.on_tool = on_tool            # callable(name:str, args:dict, result:str)
        self.on_reminder = on_reminder    # callable(message:str)
        self.on_proactive = on_proactive  # callable(message:str)
        self.on_learned = on_learned      # callable(facts:list[str])
        self.on_status = on_status        # callable(state:"thinking"|"speaking"|"idle")
        self.on_confirm = on_confirm      # callable(question:str, detail:str) -> bool
        self.confirm_mode = CONFIRM_MODE  # "dialog" or "chat"

        self.memory = Memory()
        tools.set_memory(self.memory)
        tools.set_confirmer(self._confirm)
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
        self._turn_count = 0

    # -- lifecycle --------------------------------------------------------
    def start(self):
        tools.build_app_index()
        self.reminders.start()

    def start_watcher(self):
        self.watcher.start()

    def stop(self):
        self.reminders.stop()
        self.watcher.stop()

    # -- status / confirmation --------------------------------------------
    def _status(self, state):
        if self.on_status:
            self.on_status(state)

    def _confirm(self, question, detail):
        """Yes/no gate for risky actions - chat-style so voice can answer it too."""
        if self.on_confirm:
            return bool(self.on_confirm(question, detail))
        if self.confirm_mode == "chat":
            try:
                answer = input(f"  [!] {question} [yes/no]: ").strip().lower()
            except EOFError:
                return False
            return answer in ("y", "yes", "yeah", "yep", "ok", "okay", "sure",
                              "do it", "go ahead")
        from confirm import ask
        return ask(question, detail)

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
        first = {"v": True}

        def _text_tool_call(content):
            """Recover tool calls that free models emit as plain text (JSON or XML)."""
            if not content:
                return None
            import re as _re
            body = content
            fence = _re.search(r"```(?:json|xml|tool_call)?\s*([\s\S]*?)```", content)
            if fence:
                body = fence.group(1)

            def _mk(name, args):
                if not isinstance(name, str):
                    return None
                name = name.strip().lower()
                aliases = {"email": "email_summary", "gmail": "email_summary",
                           "mail": "email_summary", "calendar": "calendar_today",
                           "open_app": "open_application", "open": "open_application",
                           "launch_app": "open_application", "launch": "open_application",
                           "open_program": "open_application", "open_url": "open_website",
                           "browse": "open_website", "website": "open_website",
                           "search": "search_web", "web_search": "search_web",
                           "google": "search_web", "play": "play_media",
                           "screenshot": "take_screenshot", "volume": "set_volume",
                           "weather": "get_weather", "note": "add_note",
                           "remind": "set_reminder",
                           "processes": "top_processes", "list_processes": "top_processes",
                           "check_processes": "top_processes", "get_processes": "top_processes",
                           "ram": "top_processes", "memory": "top_processes",
                           "memory_usage": "top_processes", "system_resources": "top_processes",
                           "resources": "top_processes", "task_manager": "top_processes",
                           "cpu": "top_processes", "performance": "top_processes"}
                name = aliases.get(name, name)
                if name not in tools.REGISTRY:
                    try:
                        import difflib
                        close = difflib.get_close_matches(name, list(tools.REGISTRY.keys()), n=1, cutoff=0.72)
                        if close:
                            name = close[0]
                    except Exception:
                        pass
                if name not in tools.REGISTRY:
                    return None
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                if not isinstance(args, dict):
                    args = {}
                try:
                    schema = tools.REGISTRY[name]["schema"]["function"].get("parameters", {})
                    allowed = list(schema.get("properties", {}).keys())
                    if allowed:
                        syn = {"app": "app_name", "application": "app_name", "program": "app_name",
                               "name": "app_name", "target": "app_name", "title": "app_name",
                               "site": "url", "link": "url", "website": "url", "address": "url",
                               "q": "query", "text": "query", "search": "query", "term": "query",
                               "what": "query", "level": "percent", "value": "percent",
                               "sort_by": "by", "sort": "by", "metric": "by",
                               "order": "by", "kind": "by"}
                        fixed, used = {}, set()
                        for k, v in args.items():
                            key = k if k in allowed else None
                            if key is None:
                                cand = syn.get(str(k).lower())
                                if cand in allowed and cand not in used:
                                    key = cand
                            if key is None:
                                rest = [a for a in allowed if a not in used]
                                key = rest[0] if rest else None
                            if key:
                                fixed[key] = v
                                used.add(key)
                        args = fixed
                except Exception:
                    pass
                return {"id": "textcall0", "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)}}

            im = _re.search(r"<invoke\s+name=\"([^\"]+)\"", body)
            if im:
                name = im.group(1)
                args = {}
                for pm in _re.finditer(r"<parameter\s+name=\"([^\"]+)\">\s*([\s\S]*?)\s*</parameter>", body):
                    args[pm.group(1).strip()] = pm.group(2).strip()
                return _mk(name, args)
            fm = _re.search(r"<function=([^>\s]+)>", body)
            if fm:
                name = fm.group(1)
                args = {}
                for pm in _re.finditer(r"<parameter=([^>\s]+)>\s*([\s\S]*?)\s*</parameter>", body):
                    args[pm.group(1).strip()] = pm.group(2).strip()
                return _mk(name, args)
            cand = None
            m = _re.search(r"<tool_call>\s*([\s\S]*?)\s*</tool_call>", body, _re.I)
            if m:
                try:
                    cand = json.loads(m.group(1))
                except Exception:
                    cand = None
            if cand is None:
                jm = _re.search(r"\{[\s\S]*\}", body)
                if jm:
                    try:
                        cand = json.loads(jm.group(0))
                    except Exception:
                        cand = None
            if not isinstance(cand, dict):
                return None
            tc = cand.get("tool_calls")
            if isinstance(tc, list) and tc:
                inner = tc[0] or {}
                if isinstance(inner, dict):
                    fn2 = inner.get("function")
                    if isinstance(fn2, dict):
                        return _mk(fn2.get("name"), fn2.get("arguments") or fn2.get("args") or {})
                    return _mk(inner.get("name"), inner.get("arguments") or {})
            fc = cand.get("function_call")
            if isinstance(fc, dict) and fc.get("name"):
                return _mk(fc.get("name"), fc.get("arguments") or {})
            name = cand.get("tool") or cand.get("name") or cand.get("function")
            args = cand.get("arguments") or cand.get("args") or cand.get("parameters") or {}
            if isinstance(name, dict):
                args = name.get("arguments", args)
                name = name.get("name")
            return _mk(name, args)
        def emit(chunk):
            if first["v"]:
                self._status("speaking")
                first["v"] = False
            spoken.append(chunk)
            if self.on_text:
                self.on_text(chunk)

        used_tools = False
        for _round in range(MAX_TOOL_ROUNDS):
            first["v"] = True
            self._status("thinking")
            message = ai_engine.stream_ai(messages, tools=tools.schemas(), on_text=emit)
            messages.append(message)
            group.append(message)

            calls = message.get("tool_calls")
            if not calls:
                recovered = _text_tool_call((message.get("content") or "").strip())
                if recovered:
                    calls = [recovered]
                    message["tool_calls"] = calls
                    message.pop("content", None)
            if not calls:
                break
            used_tools = True

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
            first["v"] = True
            self._status("thinking")
            final = ai_engine.stream_ai(messages, tools=None, on_text=emit)
            messages.append(final)
            group.append(final)

        # the model sometimes returns nothing on a tight token budget - try once more
        if not "".join(spoken).strip() and not used_tools:
            first["v"] = True
            self._status("thinking")
            retry = ai_engine.stream_ai(messages, on_text=emit, max_tokens=1500)
            messages.append(retry)
            group.append(retry)

        # still nothing? a provider hiccup can return a completely empty message with
        # no error (fast, silent). Make one plain call through the full provider chain
        # before giving up, so a turn never dies silently.
        if not "".join(spoken).strip():
            self._status("thinking")
            plain = ai_engine.complete(messages, max_tokens=1000)
            if plain.strip():
                emit(plain.strip())
                messages.append({"role": "assistant", "content": plain.strip()})

        self._status("idle")
        self.turns.append(group)
        self._compress()
        self._turn_count += 1
        if self._turn_count % max(1, LEARN_EVERY_N_TURNS) == 0:
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
