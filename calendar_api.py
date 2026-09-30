"""calendar_api.py - calendar reading (ICS link, zero setup) + Google OAuth scaffolding.

Read path works today: the user pastes their calendar's secret ICS link (Google
Calendar settings -> "Secret address in iCal format", or any ICS URL/file).
Full CRUD needs a connected Google account (one-time product-level OAuth client).
"""

import datetime as _dt
import json
import re
import time
import urllib.parse
import urllib.request

import accounts

# ---------------------------------------------------------------------------
# ICS reading (no OAuth, no developer setup)
# ---------------------------------------------------------------------------
def _fetch(url):
    from pathlib import Path
    if url.startswith("file:"):
        return Path(url[7:]).read_text(encoding="utf-8", errors="replace")
    p = Path(url)
    if p.exists():
        return p.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": "RealAssistant/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def _unfold(text):
    return (text.replace("\r\n ", "").replace("\r\n\t", "")
                .replace("\n ", "").replace("\n\t", ""))


def _parse_dt(value):
    v = value.strip()
    if v.endswith("Z"):
        try:
            return _dt.datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
        except Exception:
            return None
    if "T" in v:
        try:
            return _dt.datetime.strptime(v, "%Y%m%dT%H%M%S").timestamp()
        except Exception:
            return None
    try:
        return _dt.datetime.strptime(v, "%Y%m%d").timestamp()
    except Exception:
        return None


def parse_events(ics_text):
    """Returns list of event dicts: {start, end, summary, location, rrule}."""
    text = _unfold(ics_text)
    events = []
    for block in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        ev = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.split(";")[0].upper()
            if key == "DTSTART":
                ev["start"] = _parse_dt(val)
            elif key == "DTEND":
                ev["end"] = _parse_dt(val)
            elif key == "SUMMARY":
                ev["summary"] = val.strip()
            elif key == "LOCATION":
                ev["location"] = val.strip()
            elif key == "RRULE":
                ev["rrule"] = val.strip()
        if ev.get("start"):
            events.append(ev)
    return events


def _expand(event, window_start, window_end, cap=40):
    """Expand an event into occurrences within the window (basic daily/weekly rules)."""
    start = event["start"]
    dur = max(0, (event.get("end") or start + 1800) - start)
    occurrences = []
    rrule = event.get("rrule")
    if not rrule:
        if window_start <= start <= window_end:
            occurrences.append((start, start + dur))
        return occurrences
    parts = dict(p.split("=", 1) for p in rrule.split(";") if "=" in p)
    freq = parts.get("FREQ", "").upper()
    interval = int(parts.get("INTERVAL", "1") or "1")
    until = _parse_dt(parts["UNTIL"]) if "UNTIL" in parts else None
    count = int(parts.get("COUNT", "0") or "0")
    step = {"DAILY": 86400, "WEEKLY": 604800}.get(freq)
    if not step:
        if window_start <= start <= window_end:
            occurrences.append((start, start + dur))
        return occurrences
    step *= max(1, interval)
    t = start
    seen = 0
    while t <= window_end and (not until or t <= until) and (not count or seen < count) and len(occurrences) < cap:
        if t >= window_start:
            occurrences.append((t, t + dur))
        t += step
        seen += 1
    return occurrences


def window_events(days=1):
    ics = accounts.get_ics()
    if not ics:
        return None
    try:
        text = _fetch(ics["url"])
        events = parse_events(text)
    except Exception as e:
        return f"Error: couldn't fetch the calendar link ({str(e)[:120]})."
    now = time.time()
    end_of_window = now + days * 86400
    occ = []
    for ev in events:
        for (s, e) in _expand(ev, now - 3600, end_of_window):
            occ.append((s, e, ev))
    occ.sort(key=lambda x: x[0])
    lines = []
    for s, e, ev in occ[:30]:
        day = _dt.datetime.fromtimestamp(s).strftime("%a %d %b")
        t1 = _dt.datetime.fromtimestamp(s).strftime("%H:%M")
        t2 = _dt.datetime.fromtimestamp(e).strftime("%H:%M")
        loc = f" @ {ev['location']}" if ev.get("location") else ""
        lines.append(f"{day} {t1}-{t2}: {ev.get('summary', '(untitled)')}{loc}")
    return lines


# ---------------------------------------------------------------------------
# Google OAuth (full API path - needs a one-time client id/secret in settings)
# ---------------------------------------------------------------------------
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_SCOPES = ("https://www.googleapis.com/auth/gmail.readonly "
                 "https://www.googleapis.com/auth/gmail.send "
                 "https://www.googleapis.com/auth/calendar")


def google_configured():
    try:
        from config import load_settings
        s = load_settings() or {}
        return bool(s.get("google_client_id") and s.get("google_client_secret"))
    except Exception:
        return False


def start_google_oauth(timeout=180):
    """Opens the browser, catches the loopback redirect, stores tokens."""
    if not google_configured():
        return ("NOT_CONFIGURED: the product owner must add google_client_id / google_client_secret "
                "to settings.json once (see ACCOUNTS_SETUP.md).")
    import http.server
    import socket
    import threading
    import webbrowser
    from config import load_settings

    s = load_settings()
    cid = s["google_client_id"]
    secret = s["google_client_secret"]

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    redirect = f"http://127.0.0.1:{port}/"
    result = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"] = (q.get("code") or [""])[0]
            result["error"] = (q.get("error") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>RealAssistant connected. You can close this tab.</h2>")

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    url = GOOGLE_AUTH + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code",
        "scope": GOOGLE_SCOPES, "access_type": "offline", "prompt": "consent",
    })
    webbrowser.open(url)
    t.join(timeout)
    server.server_close()
    code = result.get("code")
    if not code:
        if result.get("error") == "access_denied":
            return ("Google refused the sign-in (access_denied). Usual fix: add your Google address as a Test "
                    "user in Google Cloud -> APIs & Services -> OAuth consent screen -> Test users, save, then "
                    "click Connect again.")
        return "Error: I didn't get the Google sign-in back (timed out?). Try again."
    data = urllib.parse.urlencode({
        "code": code, "client_id": cid, "client_secret": secret,
        "redirect_uri": redirect, "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(GOOGLE_TOKEN, data=data, timeout=30) as r:
        tok = json.load(r)
    tok["obtained"] = time.time()
    accounts.set_oauth("google", tok)
    return "Google account connected."


def google_token():
    tok = accounts.get_oauth("google")
    if not tok:
        return None
    if tok.get("expires_in") and time.time() > tok["obtained"] + int(tok["expires_in"]) - 120:
        if tok.get("refresh_token"):
            from config import load_settings
            s = load_settings()
            data = urllib.parse.urlencode({
                "client_id": s.get("google_client_id", ""), "client_secret": s.get("google_client_secret", ""),
                "refresh_token": tok["refresh_token"], "grant_type": "refresh_token",
            }).encode()
            try:
                with urllib.request.urlopen(GOOGLE_TOKEN, data=data, timeout=30) as r:
                    fresh = json.load(r)
                tok.update(fresh)
                tok["obtained"] = time.time()
                accounts.set_oauth("google", tok)
            except Exception:
                return None
    return tok.get("access_token")


def gcal_events(days=1):
    token = google_token()
    if not token:
        return None
    now = _dt.datetime.now(_dt.timezone.utc)
    params = urllib.parse.urlencode({
        "timeMin": now.isoformat(),
        "timeMax": (now + _dt.timedelta(days=days)).isoformat(),
        "singleEvents": "true", "orderBy": "startTime", "maxResults": "30",
    })
    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events?" + params,
        headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    out = []
    for it in data.get("items", []):
        start = it.get("start", {}).get("dateTime") or it.get("start", {}).get("date")
        out.append(f"{start}: {it.get('summary', '(untitled)')}")
    return out


def gcal_create(summary, start_iso, end_iso, location=""):
    token = google_token()
    if not token:
        return "Error: no Google account connected (needed to add events)."
    body = json.dumps({"summary": summary, "location": location,
                       "start": {"dateTime": start_iso}, "end": {"dateTime": end_iso}}).encode()
    req = urllib.request.Request(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        data=body, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)
    return f"Created: {data.get('summary')} ({data.get('htmlLink', '')})"
