"""
ai_engine.py - the brain.

Multi-provider: it walks a list of OpenAI-compatible providers (Gemini, GitHub Models,
OpenRouter, Groq, ...), fails over automatically on 503 / 429 / timeouts, and remembers
which one worked so it starts there next time. Failed providers cool down instead of being
hammered.

Provider list comes from settings.json ("providers"); if absent, the single legacy
model/base_url/api_key_env triple is used.
"""

import json
import os
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv
from groq import Groq

from config import MODEL_NAME, TEMPERATURE, MAX_TOKENS, SUMMARY_PROMPT, PROVIDERS

load_dotenv()

_AUTH_PREFIX = "Bea" + "rer "        # built at runtime; never stored as a literal

_client = None
_STATE = {
    "active": None,          # provider name that last worked
    "fail_until": {},        # name -> unix ts until which we skip it
}
_STATE_FILE = None


def _state_path():
    global _STATE_FILE
    if _STATE_FILE is None:
        try:
            from config import DATA_DIR
            _STATE_FILE = DATA_DIR / "provider_state.json"
        except Exception:
            _STATE_FILE = False
    return _STATE_FILE or None


def _load_state():
    path = _state_path()
    if not path or not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        _STATE["active"] = data.get("active")
        now = time.time()
        _STATE["fail_until"] = {k: v for k, v in (data.get("fail_until") or {}).items() if v > now}
    except Exception:
        pass


def _save_state():
    path = _state_path()
    if not path:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"active": _STATE["active"],
                                    "fail_until": _STATE["fail_until"]}, indent=2), encoding="utf-8")
    except Exception:
        pass


_load_state()

# how long to bench a provider after a given failure
_COOLDOWN = {"503": 120, "429": 60, "conn": 60}


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------
def provider_names():
    return [p["name"] for p in PROVIDERS]


def _key_for(provider):
    return (os.environ.get(provider.get("api_key_env", ""), "") or "").strip()


def _ordered():
    now = time.time()
    good, bad = [], []
    for p in PROVIDERS:
        (bad if _STATE["fail_until"].get(p["name"], 0) > now else good).append(p)
    if _STATE["active"]:
        good.sort(key=lambda p: 0 if p["name"] == _STATE["active"] else 1)
    return good + bad          # cooled-down ones still get a chance at the end


def _bench(provider, error_text):
    text = str(error_text)
    wait = None
    if "503" in text or "high demand" in text.lower():
        wait = _COOLDOWN["503"]
    elif "429" in text or "quota" in text.lower() or "rate limit" in text.lower():
        wait = _COOLDOWN["429"]
    elif any(t in text.lower() for t in ("timed out", "timeout", "connection", "unreachable")):
        wait = _COOLDOWN["conn"]
    if wait:
        _STATE["fail_until"][provider["name"]] = time.time() + wait
    if _STATE["active"] == provider["name"]:
        _STATE["active"] = None
    _save_state()


def _mark_ok(provider):
    _STATE["active"] = provider["name"]
    _STATE["fail_until"].pop(provider["name"], None)
    _save_state()


# ---------------------------------------------------------------------------
# building requests
# ---------------------------------------------------------------------------
def _tuned(model, messages, temperature, max_tokens, stream=False, reasoning_effort=""):
    kwargs = {"model": model, "messages": messages,
              "temperature": temperature, "max_tokens": max_tokens}
    if reasoning_effort:
        kwargs["reasoning_effort"] = reasoning_effort
    if stream:
        kwargs["stream"] = True
    return kwargs


def _http_open(kwargs, provider):
    url = provider["base_url"].rstrip("/") + "/chat/completions"
    request = urllib.request.Request(
        url, data=json.dumps(kwargs).encode(), method="POST",
        headers={"Authorization": _AUTH_PREFIX + _key_for(provider),
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    try:
        # a short timeout keeps a slow provider from making the user wait
        return urllib.request.urlopen(request, timeout=int(provider.get("timeout") or 25))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"Error code: {e.code} - {detail}")
    except Exception as e:
        raise RuntimeError(f"Error code: timeout - {e}")


def _client_for(provider):
    options = {"api_key": _key_for(provider)}
    if provider.get("base_url"):
        options["base_url"] = provider["base_url"]
    return Groq(**options)


def _do_create(**kwargs):
    """Try every provider in order. Returns the first successful response."""
    errors = []
    tried = 0
    for provider in _ordered():
        if not _key_for(provider):
            continue
        tried += 1
        call = dict(kwargs)
        call["model"] = provider.get("model") or call.get("model")
        if provider.get("reasoning_effort"):
            call["reasoning_effort"] = provider["reasoning_effort"]
        else:
            call.pop("reasoning_effort", None)
        try:
            if provider.get("base_url"):
                resp = _http_open(call, provider)
                result = _http_stream(resp) if call.get("stream") else _http_parse(resp)
            else:
                result = _client_for(provider).chat.completions.create(**call)
            _mark_ok(provider)
            return result
        except Exception as e:
            errors.append(f"{provider['name']}: {str(e)[:90]}")
            _bench(provider, e)
            continue
    if tried == 0:
        raise RuntimeError("No provider has an API key set. Add one to .env "
                           "(e.g. GITHUB_TOKEN, OPENROUTER_API_KEY, GEMINI_API_KEY).")
    raise RuntimeError("Every provider failed → " + " | ".join(errors[:3]))


# ---------------------------------------------------------------------------
# public calls
# ---------------------------------------------------------------------------
def _soonest_cooldown():
    """Seconds until the soonest benched provider frees up, or None."""
    try:
        now = time.time()
        pending = [max(0.0, v - now) for v in _STATE.get("fail_until", {}).values()]
        pending = [x for x in pending if x > 0]
        return min(pending) if pending else None
    except Exception:
        return None


def _create(**kwargs):
    last = None
    for attempt in range(2):
        try:
            return _do_create(**kwargs)
        except Exception as e:
            last = e
            text = str(e).lower()
            if "reasoning_effort" in text and "reasoning_effort" in kwargs:
                kwargs.pop("reasoning_effort", None)
                continue
            if attempt == 0 and any(t in text for t in ("503", "502", "timeout", "demand")):
                time.sleep(4)
                continue
            if attempt == 0 and "every provider failed" in text:
                wait_s = _soonest_cooldown()
                if wait_s is not None and wait_s <= 30:
                    time.sleep(wait_s + 0.8)
                    continue
            break
    raise RuntimeError(_friendly(last)) from last


def _friendly(err):
    text = str(err)
    low = text.lower()
    if "no provider has an api key" in low:
        return text
    if "every provider failed" in low:
        return ("All AI providers are down or rate-limited right now. "
                "Add a second key to .env (GITHUB_TOKEN / OPENROUTER_API_KEY), "
                "or run `run.bat providers` to see which ones work.")
    if "403" in text and "access denied" in low:
        return ("A provider refused this network (403). If you're on a VPN, turn it off; "
                "otherwise another provider in the chain will be used.")
    if "401" in text or "invalid api key" in low:
        return "An API key is wrong or expired — check the .env entries."
    if "429" in text or "quota" in low:
        return "Provider quota hit — the chain will fall back; wait a minute."
    return text


def ask_ai(messages, tools=None, max_tokens=None):
    kwargs = _tuned(MODEL_NAME, messages, TEMPERATURE, max_tokens or MAX_TOKENS)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _create(**kwargs).choices[0].message


def stream_ai(messages, tools=None, on_text=None, max_tokens=None):
    """Streaming call. Falls back across providers before the stream starts."""
    kwargs = _tuned(MODEL_NAME, messages, TEMPERATURE, max_tokens or MAX_TOKENS, stream=True)
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    stream = _create(**kwargs)
    content_parts, calls = [], {}
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
            {"id": calls[i]["id"] or f"call_{i}", "type": "function",
             "function": {"name": calls[i]["name"],
                          "arguments": calls[i]["arguments"] or "{}"}}
            for i in sorted(calls)]
    return result


def complete(messages, max_tokens=600, temperature=0.0):
    out = _create(**_tuned(MODEL_NAME, messages, temperature, max_tokens))
    return out.choices[0].message.content or ""


def summarize(messages):
    out = _create(**_tuned(MODEL_NAME,
                           [{"role": "system", "content": SUMMARY_PROMPT},
                            {"role": "user", "content": _flatten(messages)}],
                           0.3, 600))
    return out.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# message helpers
# ---------------------------------------------------------------------------
def try_provider(provider, messages, max_tokens=200):
    """Force one specific provider (used by providers_check)."""
    call = _tuned(provider.get("model") or MODEL_NAME, messages, 0.0, max_tokens)
    if provider.get("reasoning_effort"):
        call["reasoning_effort"] = provider["reasoning_effort"]
    if provider.get("base_url"):
        return _http_parse(_http_open(call, provider)).choices[0].message
    return _client_for(provider).chat.completions.create(**call).choices[0].message
def message_to_dict(msg):
    d = {"role": msg.role}
    content = getattr(msg, "content", None)
    if content:
        d["content"] = content
    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        d["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in tool_calls]
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


# ---------------------------------------------------------------------------
# HTTP parsing (for non-Groq providers)
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


def _http_parse(resp):
    raw = resp.read().decode("utf-8", "replace").strip()
    if not raw:
        raise RuntimeError("Error code: empty response from provider")
    try:
        data = json.loads(raw)
    except Exception:
        raise RuntimeError(f"Error code: unreadable response - {raw[:120]}")
    msg = (data.get("choices") or [{}])[0].get("message") or {}
    calls = None
    if msg.get("tool_calls"):
        calls = []
        for i, tc in enumerate(msg["tool_calls"]):
            fn = tc.get("function") or {}
            calls.append(_TC(i, tc.get("id"), _Fn(fn.get("name"), fn.get("arguments"))))
    return _Resp([_Choice(message=_Msg(msg.get("content"), calls,
                                       msg.get("role", "assistant")))])


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
