# ACCOUNTS_SETUP.md — connecting email & calendar

**The user-experience rule for this product:** users only ever bring ONE key — the AI key.
Everything else is a **connect / sign-in / permission** flow. No per-app API keys for normal people.
Credentials are typed **in the app** (Settings → Accounts), stored **DPAPI-encrypted** on this PC,
and are **never** sent to the AI or any cloud except the service you're connecting to.

---

## Quick path (works TODAY — 3 minutes)

### 1) Email (Gmail) — app password
1. `.\run.bat ui` → **Settings (Ctrl+Shift+S)** → **Accounts** → **Email** → *Set up*
2. On google.com: **Account → Security → 2-Step Verification → App passwords**
   → create one named "RealAssistant" → copy the 16-character password
3. Paste your address + that password into the sheet → **Connect**
4. Try: *"what needs my attention in email?"* · *"search my email for the invoice"* · *"draft a reply to …"* → *"send it"* (asks to confirm first)

> Outlook/Hotmail note: Microsoft is disabling basic sign-in for apps
> (our test server returned *"Basic authentication is disabled"*). If your Outlook
> app-password connect fails, use Gmail for now — the full Microsoft sign-in path is
> on the roadmap (see below).

### 2) Calendar (read-only, zero setup)
1. Google Calendar → **Settings → [your calendar] → "Secret address in iCal format"** → copy the link
2. In the app: **Settings → Accounts → Calendar link** → paste → **Link calendar**
3. Try: *"what's on my calendar today?"* · *"what's my week look like?"*
   (Daily/weekly recurring events are supported. Read-only — it can see but not change. Revoke anytime in Google settings.)

---

## Full path (for the product version — one-time work by the OWNER, not users)

To unlock **Gmail API + Calendar create/move** without app passwords, register ONE OAuth client:

1. **Google Cloud Console** → new project → **APIs & Services → Enable APIs**: Gmail API + Google Calendar API
2. **OAuth consent screen** → External → add yourself as a test user
3. **Credentials → Create credentials → OAuth client ID → Desktop app** → copy **Client ID + Client secret**
4. **In the app: Settings → Accounts → “Google setup (owner)”** → paste both → Save.
   *(No file editing anywhere — for shipping, the client id travels inside the app so end users never see this.)*
5. In the app: **Accounts → Google → Connect** → browser sign-in once → done.
   From then on: calendar events can be **created/moved** (`calendar_add`), and Google's official
   APIs handle mail with no app passwords.

For distribution: this is registered **once by the product**; every user just clicks *Connect* and
signs in (that's the "no API-key homework for users" rule). Google will require a security
assessment (CASA) only when distributing publicly at scale — personal/testing use is unaffected.

Microsoft equivalent (later): Azure/Entra → App registration → Microsoft Graph permissions
(Mail.ReadWrite, Calendars.ReadWrite) → same Connect button.

---

## Security facts (what we actually do)
- Credentials entered locally → DPAPI-encrypted (user-scoped) → `%LOCALAPPDATA%\RealAssistant\accounts.json`
- The AI model **never sees** passwords/tokens — agents can only *use* a connected account, never read the secret
- Sending email is `danger=True` → the app's confirmation gate always fires before anything is sent
- Calendar ICS links are read-only and revocable in Google settings

## Current status (2026-09-30)
- ✅ Email engine (IMAP/SMTP) + tools + UI — built; live login test pending your account
- ✅ Calendar ICS engine — **tested live** (today + recurring week verified)
- ✅ Google OAuth flow — built; dormant until step 4 above is done
- ✅ DPAPI storage — tested (round-trip verified)
