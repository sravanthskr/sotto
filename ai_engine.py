"""
ai_engine.py - the brain.

Talks to Groq, retries on transient/rate-limit errors, and exposes helpers to
normalise messages. It knows nothing about tools' internals - main.py wires the
tool schemas in from tools.py.
"""

import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv
from groq import Groq

from config import (MODEL_NAME, TEMPERATURE, MAX_TOKENS, SUMMARY_PROMPT, REASONING_EFFORT,
                    API_KEY_ENV, API_BASE_URL)

load_dotenv()

_client = None


def get_client():
    global _client
    if _client is None:
        key = (os.environ.get(API_KEY_ENV) or os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is missing. Create a file named .env next to the project "
                "with one line: GROQ_API_KEY=your_key_here"
            )
        options = {"api_key": key}
        if API_BASE_URL:
            options["base_url"] = API_BASE_URL
        _client = Groq(**options)
    return _client


def _tuned(model, messages, temperature, max_tokens, stream=False):
    kwargs = {"model": model, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens}
    if "gpt-oss" in model and REASONING_EFFORT:
        # gpt-oss is a reasoning model; low effort is faster and avoids empty replies
        kwargs["reasoning_effort"] = REASONING_EFFORT
    if stream:
        kwargs["stream"] = True
    return kwargs


def _create(**kwargs):
    """Call Groq with retries on rate limits / transient errors."""
    last = None
    for attempt in range(3):
        try:
            return _do_create(**kwargs)
        except Exception as e:
            last = e
            text = str(e).lower()
            if "reasoning_effort" in text and "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort", None)   # model doesn't support it
                continue
            transient = any(t in text for t in ("429", "rate", "503", "502", "timeout",
                                                "temporarily", "overloaded"))
            if transient and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
    raise RuntimeError(_friendly(last)) from last


# ---------------------------------------------------------------------------
# Minimal OpenAI-compatible HTTP client (used when base_url points elsewhere)
# ---------------------------------------------------------------------------
class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _TC:
    def __init__(self, index=0, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class _Msg:
    def __init__(self, content=None, tool_calls=None, role="assistant"):
        self.content = content
        self.tool_calls = tool_calls
        self.role = role


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message=None, delta=None):
        self.message = message
        self.delta = delta


class _Resp:
    def __init__(self, choices):
        self.choices = choices


def _http_open(kwargs):
    url = API_BASE_URL.rstrip("/") + "/chat/completions"
    key = (os.environ.get(API_KEY_ENV) or os.environ.get("GROQ_API_KEY") or "").strip()
    request = urllib.request.Request(
        url, data=json.dumps(kwargs).encode(), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        return urllib.request.urlopen(request, timeout=180)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"Error code: {e.code} - {detail}")


def _http_parse(resp):
    data = json.loads(resp.read().decode("utf-8", "replace"))
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    calls = None
    if msg.get("tool_calls"):
        calls = []
        for i, tc in enumerate(msg["tool_calls"]):
            fn = tc.get("function") or {}
            calls.append(_TC(i, tc.get("id"), _Fn(fn.get("name"), fn.get("arguments"))))
    return _Resp([_Choice(message=_Msg(msg.get("content"), calls, msg.get("role", "assistant")))])


def _http_stream(resp):
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except Exception:
            continue
        delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
        calls = None
        if delta.get("tool_calls"):
            calls = []
            for tc in delta["tool_calls"]:
                fn = tc.get("function") or {}
                calls.append(_TC(tc.get("index", 0), tc.get("id"),
                                 _Fn(fn.get("name"), fn.get("arguments"))))
        yield _Resp([_Choice(delta=_Delta(delta.get("content"), calls))])


def _do_create(**kwargs):
    """Route to plain HTTP for non-Groq providers, else the Groq SDK."""
    if API_BASE_URL:
        resp = _http_open(kwargs)
        return _http_stream(resp) if kwargs.get("stream") else _http_parse(resp)
    return get_client().chat.completions.create(**kwargs)


def _friendly(err):
    """Turn common API failures into something a human can act on."""
    text = str(err)
    low = text.lower()
    if "403" in text and "access denied" in low:
        return ("The assistant service refused the request (403 Access denied). "
                "This is usually a VPN/proxy - turn it off and retry. "
                "Run `run.bat api` to test.")
    if "401" in text or "invalid api key" in low or "unauthorized" in low:
        return "The API key looks wrong or expired - check GROQ_API_KEY in .env."
    if "429" in text or "rate limit" in low:
        return "Rate limited by the assistant service - wait a moment and try again."
    return text


def ask_ai(messages, tools=None, max_tokens=None):
    """Send a conversation; return the raw assistant message object."""
    kwargs = _tuned(MODEL_NAME, messages, TEMPERATURE, max_tokens or MAX_TOKENS)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _create(**kwargs).choices[0].message


def stream_ai(messages, tools=None, on_text=None, max_tokens=None):
    """Like ask_ai, but streams text out as it arrives.

    Calls on_text(chunk) for each content piece, and returns the assembled message
    as a plain dict (with any tool calls reassembled from their fragments).
    """
    kwargs = _tuned(MODEL_NAME, messages, TEMPERATURE, max_tokens or MAX_TOKENS, stream=True)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = _create(**kwargs)
    content_parts = []
    calls = {}
    for chunk in stream:
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = choices[0].delta

        text = getattr(delta, "content", None)
        if text:
            content_parts.append(text)
            if on_text:
                on_text(text)

        for tc in (getattr(delta, "tool_calls", None) or []):
            idx = getattr(tc, "index", None)
            if idx is None:
                idx = 0
            slot = calls.setdefault(idx, {"id": None, "name": "", "arguments": ""})
            if getattr(tc, "id", None):
                slot["id"] = tc.id
            fn = getattr(tc, "function", None)
            if fn is not None:
                if getattr(fn, "name", None):
                    slot["name"] += fn.name
                if getattr(fn, "arguments", None):
                    slot["arguments"] += fn.arguments

    result = {"role": "assistant"}
    content = "".join(content_parts)
    if content:
        result["content"] = content
    if calls:
        result["tool_calls"] = [
            {
                "id": calls[i]["id"] or f"call_{i}",
                "type": "function",
                "function": {"name": calls[i]["name"],
                             "arguments": calls[i]["arguments"] or "{}"},
            }
            for i in sorted(calls)
        ]
    return result


def summarize(messages):
    """Compress a chunk of conversation into a short paragraph."""
    out = _create(**_tuned(MODEL_NAME,
                           [{"role": "system", "content": SUMMARY_PROMPT},
                            {"role": "user", "content": _flatten(messages)}],
                           0.3, 600))
    return out.choices[0].message.content.strip()


def complete(messages, max_tokens=600, temperature=0.0):
    """A plain, non-streaming completion that returns just the text."""
    out = _create(**_tuned(MODEL_NAME, messages, temperature, max_tokens))
    return out.choices[0].message.content or ""


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
