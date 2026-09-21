"""
ai_engine.py - the brain.

Talks to Groq, retries on transient/rate-limit errors, and exposes helpers to
normalise messages. It knows nothing about tools' internals - main.py wires the
tool schemas in from tools.py.
"""

import os
import time

from dotenv import load_dotenv
from groq import Groq

from config import MODEL_NAME, TEMPERATURE, MAX_TOKENS, SUMMARY_PROMPT

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        key = (os.environ.get("GROQ_API_KEY") or "").strip()
        if not key or key.startswith("gsk_xxx"):
            raise RuntimeError(
                "GROQ_API_KEY is missing. Create a file named .env next to the project "
                "with one line: GROQ_API_KEY=your_key_here"
            )
        _client = Groq(api_key=key)
    return _client


def _create(**kwargs):
    """Call Groq with a couple of retries on rate limits / transient errors."""
    last = None
    for attempt in range(3):
        try:
            return get_client().chat.completions.create(**kwargs)
        except Exception as e:
            last = e
            text = str(e).lower()
            transient = any(t in text for t in ("429", "rate", "503", "502", "timeout",
                                                "temporarily", "overloaded"))
            if transient and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    raise last


def ask_ai(messages, tools=None):
    """Send a conversation; return the raw assistant message object."""
    kwargs = dict(model=MODEL_NAME, messages=messages,
                  temperature=TEMPERATURE, max_tokens=MAX_TOKENS)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _create(**kwargs).choices[0].message


def summarize(messages):
    """Compress a chunk of conversation into a short paragraph."""
    out = _create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": _flatten(messages)},
        ],
        temperature=0.3,
        max_tokens=220,
    )
    return out.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------
def message_to_dict(msg):
    """Convert a Groq message object into a plain dict we can store and re-send."""
    d = {"role": msg.role}
    content = getattr(msg, "content", None)
    if content:
        d["content"] = content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        d["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in tool_calls
        ]
    return d


def _flatten(messages):
    lines = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            lines.append(f"(tool {m.get('name', '')} returned: {m.get('content')})")
        elif role == "assistant":
            if m.get("content"):
                lines.append(f"assistant: {m['content']}")
            for tc in (m.get("tool_calls") or []):
                fn = tc.get("function", {})
                lines.append(f"assistant called {fn.get('name')}({fn.get('arguments')})")
        else:
            lines.append(f"{role}: {m.get('content')}")
    return "\n".join(lines)
