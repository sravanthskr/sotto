"""
learn.py - quietly learns durable facts about the user from normal conversation.

After a turn, we ask the model to pull out anything worth remembering long-term and
store it. It runs in a background thread so it never slows the chat down.
"""

import json
import threading

import ai_engine
from config import LEARN_PROMPT


def _conversation_text(messages):
    lines = []
    for m in messages:
        role = m.get("role")
        if role == "user" and m.get("content"):
            lines.append(f"user: {m['content']}")
        elif role == "assistant" and m.get("content"):
            lines.append(f"assistant: {m['content']}")
    return "\n".join(lines)


def parse_facts(raw):
    """Pull a JSON array of short strings out of the model's reply, forgivingly."""
    if not raw:
        return []
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        data = json.loads(raw[start:end + 1])
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str):
            item = item.strip()
            if 3 <= len(item) <= 200:
                out.append(item)
    return out


def extract_facts(messages, known):
    known_block = "; ".join(known) if known else "(nothing yet)"
    convo = _conversation_text(messages)
    prompt = [
        {"role": "system", "content": LEARN_PROMPT},
        {"role": "user", "content": f"ALREADY KNOWN: {known_block}\n\nCONVERSATION:\n{convo}"},
    ]
    try:
        raw = ai_engine.complete(prompt, max_tokens=200, temperature=0.0)
    except Exception:
        return []
    return parse_facts(raw)


class FactLearner:
    """Runs fact extraction in the background so the chat stays snappy."""

    def __init__(self, memory):
        self.memory = memory
        self._lock = threading.Lock()

    def learn_async(self, messages, on_new=None, min_chars=30):
        text = _conversation_text(messages)
        if len(text) < min_chars:
            return
        threading.Thread(
            target=self._run, args=(list(messages), on_new), daemon=True
        ).start()

    def _run(self, messages, on_new):
        with self._lock:
            known = self.memory.facts()
            added = []
            for fact in extract_facts(messages, known):
                if self.memory.add_fact(fact) == "Noted.":
                    added.append(fact)
            if added and on_new:
                try:
                    on_new(added)
                except Exception:
                    pass
