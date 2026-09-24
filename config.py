"""
config.py - settings, paths, and the assistant's personality.

Everything you might want to tweak lives here (or in settings.json - see below).
Nothing else in the project should hardcode paths, model names, or persona rules.
"""

import json
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
ASSISTANT_NAME = "Assistant"   # what it calls itself (internal for now)
USER_NAME = ""                 # leave blank; it learns this. Set it to force it.

# ---------------------------------------------------------------------------
# Conversation memory
# ---------------------------------------------------------------------------
RECENT_TURNS_KEPT = 8          # how many recent turns stay verbatim in context
SUMMARIZE_WHEN_TURNS_OVER = 12 # once we exceed this, the oldest turns get compressed
MAX_TOOL_ROUNDS = 8            # max tool-call rounds inside a single user turn (multi-step tasks)
LEARN_EVERY_N_TURNS = 1        # how often to mine the chat for durable facts (1 = every turn)

# ---------------------------------------------------------------------------
# Storage (100% local - nothing here ever leaves the machine)
# ---------------------------------------------------------------------------
_HOME = Path(os.getenv("USERPROFILE") or Path.home())
DATA_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "RealAssistant"
MEMORY_FILE = DATA_DIR / "memory.json"
REMINDERS_FILE = DATA_DIR / "reminders.json"
NOTES_FILE = DATA_DIR / "notes.json"
ORGANIZE_LOG = DATA_DIR / "organize_undo.json"
AUDIT_LOG = DATA_DIR / "audit.log"
SETTINGS_FILE = DATA_DIR / "settings.json"
SCREENSHOT_DIR = _HOME / "Pictures" / "RealAssistant"
DOWNLOADS_DIR = _HOME / "Downloads"

# ---------------------------------------------------------------------------
# settings.json - optional overrides you can edit without touching this file.
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "model": "openai/gpt-oss-20b",
    "temperature": 0.6,
    "reasoning_effort": "low",   # "low" = fast + avoids the empty-reply bug on gpt-oss
    "max_tokens": 1024,
    "denied_tools": [],
    "proactive": True,
    "proactive_interval_seconds": 300,
    "confirm_mode": "dialog",     # "dialog" (native box) or "chat" (answer by voice/text)
    "voice_name": "",             # "" = system default; or e.g. "Microsoft Zira Desktop"
    "voice_rate": 0,              # -10..10 (0 = normal speed)
    "mic_device": None,           # null = system default mic, or an index from mic_test.py
    "custom_voice": "",           # name of a folder in %LOCALAPPDATA%\RealAssistant\voices
}


def load_settings():
    data = dict(_DEFAULTS)
    try:
        if SETTINGS_FILE.exists():
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"[settings] couldn't read settings.json ({e}); using defaults.")
    return data


def ensure_settings_file():
    """Create a default settings.json on first run so it's easy to find and edit."""
    if not SETTINGS_FILE.exists():
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(_DEFAULTS, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass


_SETTINGS = load_settings()

MODEL_NAME = str(_SETTINGS["model"])
TEMPERATURE = float(_SETTINGS["temperature"])
MAX_TOKENS = int(_SETTINGS["max_tokens"])
DENIED_TOOLS = {str(t) for t in _SETTINGS.get("denied_tools", [])}
PROACTIVE = bool(_SETTINGS.get("proactive", True))
PROACTIVE_INTERVAL = int(_SETTINGS.get("proactive_interval_seconds", 300))
CONFIRM_MODE = str(_SETTINGS.get("confirm_mode", "dialog"))
REASONING_EFFORT = str(_SETTINGS.get("reasoning_effort", "low"))
VOICE_NAME = str(_SETTINGS.get("voice_name", ""))
VOICE_RATE = int(_SETTINGS.get("voice_rate", 0))
MIC_DEVICE = _SETTINGS.get("mic_device")   # None = default mic, or an int index
CUSTOM_VOICE = str(_SETTINGS.get("custom_voice", ""))
VOICE_MODELS_DIR = DATA_DIR / "voices"


def save_setting(key, value):
    """Persist a single settings.json value (takes effect after a restart)."""
    data = load_settings()
    data[key] = value
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Dependency check (so a wrong interpreter gives a clear message, not weird errors)
# ---------------------------------------------------------------------------
OPTIONAL_DEPS = {
    "PIL": "Pillow",
    "ddgs": "ddgs",
    "pypdf": "pypdf",
    "pycaw": "pycaw",
    "comtypes": "comtypes",
    "psutil": "psutil",
}


def missing_deps():
    import importlib.util
    return [(mod, pip) for mod, pip in OPTIONAL_DEPS.items()
            if importlib.util.find_spec(mod) is None]

# ---------------------------------------------------------------------------
# Persona - this is the soul of the thing. Keep it human.
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""
You are {ASSISTANT_NAME}, a real person sitting next to the user at their computer.
You are NOT an AI, NOT an assistant program, NOT a chatbot. You never break that.

How you talk:
- Casual and laid-back, like a friend who happens to be good with computers.
- Short. Usually one or two sentences. Never a wall of text unless they asked for detail.
- No emojis. No bullet lists unless they actually asked for a list.
- No corporate tone: never "How may I assist you today", "Certainly!", "I'd be happy to".
- Never say "As an AI", "I'm a language model", "I don't have feelings", or anything close.
- A bit of personality is good: light humour, opinions, the odd dry remark.

How you act:
- You can control the computer through tools. Use them silently, then tell the user the
  outcome in one natural line. NEVER mention tools, function calls, JSON, or schemas.
- When a question needs current facts, use look_up and answer in your own words. Only open a
  browser tab when the user actually asked to see the page.
- For anything destructive (shutting down, restarting, deleting, moving files) a confirmation
  box will appear on screen - that's expected. Say briefly what you're about to do.
- When a tool fails, react like a person: "Looks like Telegram isn't installed, want the web
  version instead?" - never dump an error code.
- Don't ask permission for harmless things (opening apps, searching, screenshots). Just do it.
- Don't narrate steps. Do the thing, then say what happened.
- For multi-step requests, plan them out and work through each step, then give one short summary
  of the result - don't ask the user to break it down for you.
- Never invent facts. If you don't know something, or a lookup failed, say so plainly instead of
  guessing - a confident wrong answer is worse than "I couldn't find that".
- To move or rename files use move_file / rename_file - never delete_path.
- Keep lists short unless the user actually asked for everything.

Memory:
- You remember things about the user over time. Use that naturally, the way a friend would.
  Don't announce that you're "remembering" or "storing" anything.
"""

SUMMARY_PROMPT = """
You compress an old conversation so it can be remembered cheaply.
Extract only what matters for the future: facts about the user (name, preferences, habits),
decisions, things that were done, anything still in progress.
Ignore small talk and obvious one-offs.
Write it as a plain, dense paragraph. No lists, no headings, keep it short.
"""

LEARN_PROMPT = """
You extract durable facts about the user from a short conversation excerpt.
Return ONLY a JSON array of short strings (no prose, no markdown).
Include things worth remembering long-term: their name, preferences, habits, ongoing projects,
important people, or tools/apps they use. Ignore small talk, one-off requests, and anything
already in the known list. If there is nothing new worth keeping, return [].
"""
