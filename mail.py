"""mail.py - email over IMAP/SMTP.

Works today with app passwords (Gmail, Outlook/Hotmail) - no developer setup needed.
Read-only listing/search first; sending exists but is only reachable through the
confirmation-gated email_send tool.
"""

import email
import imaplib
import json
import re
import smtplib
import ssl
import time
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from pathlib import Path

import accounts

PROVIDERS = {
    "gmail": {"imap": "imap.gmail.com", "smtp": "smtp.gmail.com", "imap_port": 993, "smtp_port": 587},
    "outlook": {"imap": "outlook.office365.com", "smtp": "smtp-mail.outlook.com", "imap_port": 993, "smtp_port": 587},
}

DRAFTS_FILE = Path(accounts.DATA) / "mail_drafts.json"


def provider_for(address):
    d = (address or "").split("@")[-1].lower()
    if "gmail" in d or "googlemail" in d:
        return "gmail"
    if any(x in d for x in ("outlook", "hotmail", "live", "msn")):
        return "outlook"
    return None


def connect(address, app_password):
    provider = provider_for(address)
    if not provider:
        return ("Error: for now I can connect Gmail and Outlook/Hotmail accounts. "
                "(A general IMAP option can come later.)")
    try:
        m = imaplib.IMAP4_SSL(PROVIDERS[provider]["imap"], PROVIDERS[provider]["imap_port"], timeout=20)
        m.login(address, app_password)
        m.select("INBOX", readonly=True)
        m.logout()
    except imaplib.IMAP4.error as e:
        hint = " For Gmail, create an App Password (Account -> Security -> 2-Step Verification -> App passwords)." if provider == "gmail" else ""
        return f"Error: sign-in failed ({str(e)[:120]}).{hint}"
    except Exception as e:
        return f"Error: couldn't reach the mail server ({str(e)[:120]})."
    accounts.set_email_account(provider, address, app_password)
    return f"Connected {address} - inbox is ready."


def _imap(readonly=True):
    acc = accounts.get_email_account()
    pw = accounts.email_password(acc)
    if not acc or not pw:
        return None, "Error: no email account connected yet."
    m = imaplib.IMAP4_SSL(PROVIDERS[acc["provider"]]["imap"], PROVIDERS[acc["provider"]]["imap_port"], timeout=20)
    m.login(acc["address"], pw)
    m.select("INBOX", readonly=readonly)
    return m, None


def _hdr(msg, name):
    try:
        return str(make_header(decode_header(msg.get(name, "") or "")))
    except Exception:
        return msg.get(name, "") or ""


def list_inbox(limit=20, unread_only=False, days=None, query=""):
    m, err = _imap()
    if err:
        return err
    try:
        criteria = []
        if unread_only:
            criteria.append("UNSEEN")
        if days:
            since = time.strftime("%d-%b-%Y", time.localtime(time.time() - days * 86400))
            criteria.append(f"SINCE {since}")
        if query:
            criteria += ["TEXT", f'"{query}"']
        crit = "(" + " ".join(criteria) + ")" if criteria else "ALL"
        typ, data = m.search(None, crit)
        ids = data[0].split()[-max(1, min(50, limit)):]
        rows = []
        for i in reversed(ids):
            typ, d = m.fetch(i, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            msg = email.message_from_bytes(d[0][1])
            rows.append({"uid": i.decode(), "subject": _hdr(msg, "Subject"),
                         "from": _hdr(msg, "From"), "date": _hdr(msg, "Date")})
        return rows
    finally:
        try:
            m.logout()
        except Exception:
            pass


def read_message(uid):
    m, err = _imap()
    if err:
        return err
    try:
        typ, d = m.fetch(str(uid).encode(), "(RFC822)")
        if not d or not d[0]:
            return "Error: message not found."
        msg = email.message_from_bytes(d[0][1])
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                    body = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                    break
            if not body:
                for part in msg.walk():
                    if part.get_content_type() == "text/html":
                        html = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
                        body = re.sub(r"<[^>]+>", " ", html)
                        break
        else:
            body = msg.get_payload(decode=True).decode(msg.get_content_charset() or "utf-8", "replace")
        body = re.sub(r"[ \t]+", " ", body)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        return {"subject": _hdr(msg, "Subject"), "from": _hdr(msg, "From"),
                "to": _hdr(msg, "To"), "date": _hdr(msg, "Date"), "body": body[:8000]}
    finally:
        try:
            m.logout()
        except Exception:
            pass


def send(to, subject, body):
    acc = accounts.get_email_account()
    pw = accounts.email_password(acc)
    if not acc or not pw:
        return "Error: no email account connected yet."
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = acc["address"]
    msg["To"] = to
    s = smtplib.SMTP(PROVIDERS[acc["provider"]]["smtp"], PROVIDERS[acc["provider"]]["smtp_port"], timeout=30)
    try:
        s.starttls(context=ssl.create_default_context())
        s.login(acc["address"], pw)
        s.send_message(msg)
    finally:
        try:
            s.quit()
        except Exception:
            pass
    return f"Sent to {to}."


# ---------------- local drafts ----------------
def _load_drafts():
    try:
        return json.loads(DRAFTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_drafts(items):
    accounts.DATA.mkdir(parents=True, exist_ok=True)
    DRAFTS_FILE.write_text(json.dumps(items, indent=2), encoding="utf-8")


def add_draft(to, subject, body):
    items = _load_drafts()
    did = str(int(time.time()))
    items.append({"id": did, "to": to, "subject": subject, "body": body, "ts": time.time()})
    _save_drafts(items)
    return did


def get_draft(did):
    return next((d for d in _load_drafts() if d["id"] == str(did)), None)


def list_drafts():
    return _load_drafts()
