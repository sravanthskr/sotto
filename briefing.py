"""
briefing.py - a quick daily briefing: greeting, date/time, weather, reminders, system status.

Weather comes from wttr.in (free, no API key). Calendar integration needs OAuth and is a
later step, so the briefing stays fully local + free for now.
"""

import re
import shutil
import urllib.request
from datetime import datetime

from config import DOWNLOADS_DIR  # noqa: F401  (kept for future use)

_WTTR_TIMEOUT = 8


def _wttr(city, fmt):
    url = f"https://wttr.in/{city}?format={fmt}"
    req = urllib.request.Request(url, headers={"User-Agent": "curl/8.0"})
    with urllib.request.urlopen(req, timeout=_WTTR_TIMEOUT) as r:
        return r.read().decode("utf-8", "replace").strip()


def get_weather(city=""):
    """Short one-line weather, e.g. 'Hyderabad: Partly cloudy +30C'."""
    try:
        return _wttr(city, "%l:+%C+%t") or "Couldn't get the weather right now."
    except Exception as e:
        return f"Error: couldn't reach the weather service ({e})."


def greeting_for(hour):
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _html_to_text(html):
    html = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#39;", "'").replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


def read_webpage(url, max_chars=4000):
    """Fetch a page and return its readable text (so the assistant can answer from it)."""
    url = (url or "").strip()
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            raw = response.read(800000).decode("utf-8", "replace")
    except Exception as e:
        return f"Error: couldn't open that page ({e})."
    text = _html_to_text(raw)
    if not text:
        return "That page had no readable text."
    max_chars = int(max_chars or 4000)
    return text[:max_chars] + ("...(truncated)" if len(text) > max_chars else "")


def daily_briefing(city="", reminders=None):
    now = datetime.now()
    parts = [f"{greeting_for(now.hour)} - it's {now:%A %d %B, %H:%M}."]

    weather = get_weather(city)
    if weather and not weather.startswith("Error"):
        parts.append(f"Weather: {weather}.")

    if reminders is not None:
        try:
            items = reminders.list()
        except Exception:
            items = []
        if items:
            names = "; ".join(r["message"] for r in items[:3])
            parts.append(f"{len(items)} reminder(s) waiting: {names}.")

    try:
        total, used, free = shutil.disk_usage("C:\\")
        parts.append(f"Disk free: {free / 1024 ** 3:.1f} GB.")
    except Exception:
        pass

    return " ".join(parts)
