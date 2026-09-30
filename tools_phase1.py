"""tools_phase1.py - Phase 1: Email & Calendar tools.

Safety model:
- Credentials (app passwords / OAuth tokens) are NEVER accepted through model tool
  calls - they are entered locally via Settings -> Accounts (bridge methods) and
  stored DPAPI-encrypted. These tools only USE a connected account.
- email_send / email_send_draft are danger=True -> they pass through the app's
  existing confirmation gate before anything is sent.

Imported at the very end of tools.py.
"""

from tools import tool

_NO_EMAIL = ("No email account connected yet. Add one in Settings -> Accounts "
             "(Gmail / Outlook app password), then try again.")
_NO_CAL = ("No calendar linked yet. Add an ICS link in Settings -> Accounts, or connect a "
           "Google account for full calendar control.")


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
@tool(name="email_status", description="Check which email/calendar accounts are connected.")
def email_status():
    import accounts
    lines = accounts.status_lines()
    return "Connected: " + "; ".join(lines) if lines and lines[0] != "nothing connected yet" else "Nothing connected yet."


@tool(
    name="email_summary",
    description=("List the most recent emails (headers only) so you can tell the user what needs "
                 "attention. Use email_read on the interesting ones. Read-only."),
    parameters={
        "type": "object",
        "properties": {
            "hours": {"type": "integer", "description": "Look back this many hours (default 24)."},
            "unread_only": {"type": "boolean", "description": "Only unread (default false)."},
        },
    },
)
def email_summary(hours=24, unread_only=False):
    import accounts
    if not accounts.get_email_account():
        return _NO_EMAIL
    import mail
    days = max(1, int(round(hours / 24)) if hours >= 24 else 1)
    rows = mail.list_inbox(limit=20, unread_only=bool(unread_only), days=days)
    if isinstance(rows, str):
        return rows
    if not rows:
        return "Inbox looks empty for that window."
    lines = [f"[{r['uid']}] {r['from'][:60]} | {r['subject'][:80]} | {r['date'][:31]}" for r in rows]
    return ("Recent emails (newest first):\n" + "\n".join(lines) +
            "\n\nRead any of them with email_read, using the [uid] number.")


@tool(
    name="email_search",
    description="Search the inbox (words in subject/body/sender). Returns headers with uid numbers.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search words."},
            "limit": {"type": "integer", "description": "Max results (default 10)."},
        },
        "required": ["query"],
    },
)
def email_search(query, limit=10):
    import accounts
    if not accounts.get_email_account():
        return _NO_EMAIL
    import mail
    rows = mail.list_inbox(limit=int(limit or 10), query=query)
    if isinstance(rows, str):
        return rows
    if not rows:
        return f"No emails found for '{query}'."
    return "\n".join(f"[{r['uid']}] {r['from'][:60]} | {r['subject'][:80]}" for r in rows)


@tool(
    name="email_read",
    description="Read one email's content by its uid number (from email_summary or email_search).",
    parameters={
        "type": "object",
        "properties": {"uid": {"type": "string", "description": "The uid number shown in [brackets]."}},
        "required": ["uid"],
    },
)
def email_read(uid):
    import accounts
    if not accounts.get_email_account():
        return _NO_EMAIL
    import mail
    msg = mail.read_message(str(uid).strip("[] "))
    if isinstance(msg, str):
        return msg
    return (f"From: {msg['from']}\nTo: {msg['to']}\nDate: {msg['date']}\nSubject: {msg['subject']}\n\n{msg['body']}")


@tool(
    name="email_draft",
    description=("Write an email draft (saved locally, nothing is sent). Returns a draft id that "
                 "email_send_draft can send after the user approves."),
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email."},
            "subject": {"type": "string", "description": "Subject line."},
            "body": {"type": "string", "description": "Draft body text."},
        },
        "required": ["to", "subject", "body"],
    },
)
def email_draft(to, subject, body):
    import mail
    did = mail.add_draft(to, subject, body)
    return f"Draft saved (id {did}). Say 'send it' after checking, or ask me to edit it."


@tool(
    name="email_send",
    description="Send an email now. Always confirm with the user before calling this.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient."},
            "subject": {"type": "string", "description": "Subject."},
            "body": {"type": "string", "description": "Body text."},
        },
        "required": ["to", "subject", "body"],
    },
    danger=True,
)
def email_send(to, subject, body):
    import accounts
    if not accounts.get_email_account():
        return _NO_EMAIL
    import mail
    return mail.send(to, subject, body)


@tool(
    name="email_send_draft",
    description="Send a previously saved draft by id. Always confirm with the user first.",
    parameters={
        "type": "object",
        "properties": {"draft_id": {"type": "string", "description": "Draft id."}},
        "required": ["draft_id"],
    },
    danger=True,
)
def email_send_draft(draft_id):
    import accounts
    if not accounts.get_email_account():
        return _NO_EMAIL
    import mail
    d = mail.get_draft(draft_id)
    if not d:
        return f"Error: no draft with id {draft_id}."
    return mail.send(d["to"], d["subject"], d["body"])


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
@tool(
    name="calendar_connect_ics",
    description=("Link a calendar by its read-only ICS link (e.g. the 'Secret address in iCal "
                 "format' from Google Calendar settings). Zero setup, read-only. Give the URL."),
    parameters={
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The https:// ICS link (or a local .ics file path)."}},
        "required": ["url"],
    },
)
def calendar_connect_ics(url):
    import accounts
    import calendar_api
    try:
        text = calendar_api._fetch(url.strip())
        n = len(calendar_api.parse_events(text))
        accounts.set_ics(url.strip())
        return f"Calendar linked - found {n} events in the feed."
    except Exception as e:
        return f"Error: couldn't read that calendar link ({str(e)[:140]})."


@tool(name="calendar_today", description="What's on the calendar for the rest of today.")
def calendar_today():
    import calendar_api
    import accounts
    lines = calendar_api.window_events(days=1)
    if lines is None:
        if calendar_api.google_configured():
            lines = calendar_api.gcal_events(days=1)
            if lines is None:
                return _NO_CAL
        else:
            return _NO_CAL
    if isinstance(lines, str):
        return lines
    return "Today:\n" + "\n".join(lines) if lines else "Nothing on the calendar for today."


@tool(name="calendar_week", description="What's on the calendar over the next 7 days.")
def calendar_week():
    import calendar_api
    lines = calendar_api.window_events(days=7)
    if lines is None:
        if calendar_api.google_configured():
            lines = calendar_api.gcal_events(days=7)
            if lines is None:
                return _NO_CAL
        else:
            return _NO_CAL
    if isinstance(lines, str):
        return lines
    return "Next 7 days:\n" + "\n".join(lines) if lines else "Nothing on the calendar this week."


@tool(
    name="calendar_add",
    description=("Create a calendar event (needs a connected Google account). Times are ISO format "
                 "like 2026-10-01T15:00:00."),
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Event title."},
            "start": {"type": "string", "description": "Start (ISO, e.g. 2026-10-01T15:00:00)."},
            "end": {"type": "string", "description": "End (ISO)."},
            "location": {"type": "string", "description": "Optional location."},
        },
        "required": ["summary", "start", "end"],
    },
)
def calendar_add(summary, start, end, location=""):
    import calendar_api
    try:
        return calendar_api.gcal_create(summary, start, end, location)
    except Exception as e:
        return f"Error: couldn't create the event ({str(e)[:140]})."


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------
@tool(
    name="connect_google",
    description=("Start connecting a Google account (Gmail + Calendar full access). Opens the "
                 "browser for sign-in. Only works if the app has Google client credentials set up."),
    parameters={"type": "object", "properties": {}},
)
def connect_google():
    import calendar_api
    if not calendar_api.google_configured():
        return ("Google isn't set up yet: the app needs one-time google_client_id / "
                "google_client_secret in settings.json (see ACCOUNTS_SETUP.md). For quick email "
                "today: Settings -> Accounts -> Email (app password) instead.")
    if calendar_api.google_token():
        return "Google is already connected."
    import threading
    threading.Thread(target=calendar_api.start_google_oauth, daemon=True).start()
    return "Browser opened - sign in to Google there; once you approve, it's connected."


@tool(name="account_status", description="Which accounts are connected (email, calendar, google).")
def account_status():
    import accounts
    return " | ".join(accounts.status_lines())
