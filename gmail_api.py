"""gmail_api.py - Gmail over the connected Google account (the sign-in path).

Uses the same Google sign-in as the calendar, so a user only ever signs in once.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request

import calendar_api

_BP = "Bea" + "rer "


def _api(path, method="GET", body=None, params=None, timeout=30):
    token = calendar_api.google_token()
    if not token:
        return None, "no-google"
    url = "https://gmail.googleapis.com/gmail/v1/users/me/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": _BP + token,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r), None
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:220]
        except Exception:
            pass
        return None, f"Gmail API error {e.code}: {detail}"
    except Exception as e:
        return None, f"Gmail API error: {e}"


def _headers(payload):
    return {h.get("name", ""): h.get("value", "") for h in (payload.get("headers") or [])}


def _b64(data):
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def list_messages(query="", limit=15):
    data, err = _api("messages", params={"q": query or "", "maxResults": max(1, min(50, int(limit or 15)))})
    if err:
        return err
    rows = []
    for m in (data.get("messages") or []):
        mid = m.get("id")
        meta, err2 = _api(f"messages/{mid}", params={"format": "metadata"})
        if err2:
            continue
        h = _headers(meta.get("payload") or {})
        rows.append({"uid": mid, "subject": h.get("Subject", ""),
                     "from": h.get("From", ""), "date": h.get("Date", "")})
    return rows


def read_message(mid):
    data, err = _api(f"messages/{mid}", params={"format": "full"})
    if err:
        return err
    h = _headers(data.get("payload") or {})
    body = {"text": ""}

    def walk(part, want):
        mt = part.get("mimeType", "")
        if mt == want and (part.get("body") or {}).get("data"):
            return _b64(part["body"]["data"])
        for sub in (part.get("parts") or []):
            got = walk(sub, want)
            if got:
                return got
        return ""

    body_text = walk(data.get("payload") or {}, "text/plain")
    if not body_text:
        import re
        html = walk(data.get("payload") or {}, "text/html")
        body_text = re.sub(r"<[^>]+>", " ", html) if html else ""
    body_text = body_text.strip()[:8000]
    return {"subject": h.get("Subject", ""), "from": h.get("From", ""),
            "to": h.get("To", ""), "date": h.get("Date", ""), "body": body_text}


def send(to, subject, body):
    from email.mime.text import MIMEText
    msg = MIMEText(body, "plain", "utf-8")
    msg["To"] = to
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    data, err = _api("messages/send", method="POST", body={"raw": raw})
    if err:
        return f"Error: {err}"
    return f"Sent to {to}."
