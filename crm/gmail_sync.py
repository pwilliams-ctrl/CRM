"""Scan Gmail for investor activity and create outreach drafts.

What a sync does, per pipeline row:
  1. Searches Gmail for the partner email, the fund's domain, and (for intro rows)
     the referrer plus the fund name. Records the newest thread and Last Touch date.
  2. Flags rows that got an inbound reply since our last outbound message.
  3. Advances status only where the evidence is unambiguous:
       Target -> Intro Requested   when we have emailed the fund
       any    -> Meeting Set       when a calendar invite with the fund's domain exists
     Everything else (Diligence, Term Sheet, Passed) stays a human call.
  4. For rows due today or earlier, creates a Gmail DRAFT (never sends) using the
     template for the row's status, after it passes compliance.check().

Auth: place an OAuth "Desktop app" client file at credentials.json (Google Cloud console,
Gmail API enabled). First run opens a browser and writes token.json. Scopes are read-only
plus compose (drafts); the CRM cannot send mail.
"""

import base64
import datetime as dt
import json
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path

from . import compliance, templates
from .tracker import Investor

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"]
ME = "pwilliams@vaeros.ai"
REFERRERS_PATH = ROOT / "data" / "referrers.json"


def gmail_service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    token = ROOT / "token.json"
    creds = Credentials.from_authorized_user_file(token, SCOPES) if token.exists() else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            creds = InstalledAppFlow.from_client_secrets_file(ROOT / "credentials.json", SCOPES).run_local_server(port=0)
        token.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# People who must never be asked for investor intros (24 Oct 2026: Lane Dilg is conflicted
# out of Department-adjacent fundraising). Listing them here keeps every nudge path off them.
CONFLICTED = {"lane.dilg@gmail.com"}


def load_referrers() -> dict[str, str]:
    refs = json.loads(REFERRERS_PATH.read_text()) if REFERRERS_PATH.exists() else {}
    return {name: email for name, email in refs.items() if email.lower() not in CONFLICTED}


def build_query(inv: Investor, referrers: dict[str, str]) -> str | None:
    terms = []
    if inv.partner_email:
        terms.append(f"from:{inv.partner_email} OR to:{inv.partner_email}")
    if inv.fund_domain:
        terms.append(f"from:{inv.fund_domain} OR to:{inv.fund_domain}")
    ref_email = referrers.get(inv.lead_source)
    if ref_email:
        short_name = inv.fund_name.split(" (")[0].split(" - ")[0]
        terms.append(f'((from:{ref_email} OR to:{ref_email}) "{short_name}")')
    if not terms:
        return None
    return "(" + " OR ".join(terms) + ") -in:draft"


def _header(msg: dict, name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h["name"].lower() == name.lower():
            return h["value"]
    return ""


def summarize_thread(thread: dict, inv: Investor) -> dict:
    """Reduce a Gmail thread to the facts the tracker needs."""
    messages = thread.get("messages", [])
    last_out = last_in = None
    invite = False
    for msg in messages:
        when = dt.datetime.fromtimestamp(int(msg["internalDate"]) / 1000, dt.timezone.utc).date()
        sender = parseaddr(_header(msg, "From"))[1].lower()
        if sender == ME:
            last_out = max(last_out or when, when)
        else:
            last_in = max(last_in or when, when)
            if inv.fund_domain and sender.endswith("@" + inv.fund_domain) and _header(msg, "Subject").startswith("Invitation:"):
                invite = True
    newest = max(d for d in (last_out, last_in) if d) if (last_out or last_in) else None
    return {
        "thread_id": thread["id"],
        "last_touch": newest,
        "last_out": last_out,
        "last_in": last_in,
        "awaiting_us": bool(last_in and (not last_out or last_in > last_out)),
        "invite": invite,
        "message_id": messages[-1]["id"] if messages else "",
    }


def apply_summary(inv: Investor, s: dict, today: dt.date) -> list[str]:
    """Update a row from a thread summary. Returns notes on what changed."""
    changes = []
    if s["last_touch"] and (not inv.last_touch or s["last_touch"].isoformat() > inv.last_touch):
        inv.last_touch = s["last_touch"].isoformat()
        inv.gmail_thread_id = s["thread_id"]
        changes.append(f"last touch {inv.last_touch}")
    if inv.status == "Target" and s["last_out"]:
        # For cold rows "Intro Requested" means first touch is out and we are waiting on them.
        inv.status = "Intro Requested"
        inv.next_action_date = (s["last_out"] + dt.timedelta(days=5)).isoformat()
        changes.append(f"first touch found; status -> Intro Requested, follow up {inv.next_action_date}")
    if s["invite"] and inv.status in ("Target", "Intro Requested"):
        inv.status = "Meeting Set"
        inv.add_note("Calendar invite found in Gmail; status set to Meeting Set.", today)
        changes.append("status -> Meeting Set")
    if s["awaiting_us"]:
        inv.next_action_date = today.isoformat()
        changes.append("REPLY WAITING ON YOU")
    return changes


def create_draft(service, draft: templates.Draft, thread_id: str = "") -> str:
    msg = MIMEText(draft.body)
    msg["to"] = ", ".join(draft.to)
    msg["subject"] = draft.subject
    payload = {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    created = service.users().drafts().create(userId="me", body=payload).execute()
    return created["id"]


def sync(investors: list[Investor], today: dt.date, make_drafts: bool = True, service=None) -> list[str]:
    service = service or gmail_service()
    referrers = load_referrers()
    report = []
    drafted_to: set[tuple[str, ...]] = set()
    for inv in investors:
        query = build_query(inv, referrers)
        if query:
            found = service.users().threads().list(userId="me", q=query, maxResults=5).execute().get("threads", [])
            summaries = [
                summarize_thread(service.users().threads().get(userId="me", id=t["id"], format="metadata",
                                                              metadataHeaders=["From", "Subject"]).execute(), inv)
                for t in found
            ]
            summaries = [s for s in summaries if s["last_touch"]]
            if summaries:
                newest = max(summaries, key=lambda s: s["last_touch"])
                changes = apply_summary(inv, newest, today)
                if changes:
                    report.append(f"{inv.fund_name}: " + "; ".join(changes))

        if make_drafts and inv.is_due(today):
            draft = templates.for_status(inv, referrers)
            if draft is None:
                continue
            if not draft.to:
                report.append(f"{inv.fund_name}: due, but no Partner Email yet; draft skipped")
                continue
            if tuple(draft.to) in drafted_to:
                inv.next_action_date = (today + dt.timedelta(days=3)).isoformat()
                report.append(f"{inv.fund_name}: covered by the draft already made to {draft.to[0]}")
                continue
            problems = compliance.check(draft.subject, draft.body, draft.to)
            if problems:
                report.append(f"{inv.fund_name}: draft BLOCKED by compliance: " + " | ".join(problems))
                continue
            # Replies to our own thread (follow-ups, referrer nudges) stay in that thread.
            in_thread = inv.gmail_thread_id if draft.subject.startswith("Re:") else ""
            draft_id = create_draft(service, draft, in_thread)
            drafted_to.add(tuple(draft.to))
            # Push the date out so the next sync doesn't stack a second draft on this one.
            inv.next_action_date = (today + dt.timedelta(days=3)).isoformat()
            inv.add_note(f"Draft in Gmail: '{draft.subject}'. Review and send.", today)
            report.append(f"{inv.fund_name}: draft created ({draft_id})")
    return report
