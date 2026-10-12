"""Outreach templates.

What makes these open and get answered (see README for the reasoning):
  - Subjects under 60 characters, specific, no hype words, no "Quick question".
    A named referrer in the subject beats everything else; next best is a
    concrete gap the reader already cares about (Maven).
  - First line is about the reader (the Hook column), not about Vaeros.
  - One-sentence problem, three proof points, one ask with a time box.
  - Under 150 words. Plain text. No attachments on first touch.
"""

from dataclasses import dataclass

from .tracker import Investor

SIGNATURE = """Phil

Phillip Williams, MD
Founder & CEO, Vaeros, Inc.
m: 347.933.3454 | vaeros.ai"""

PITCH = (
    "Maven tracks where the Department's assets are. It does not track which operators are "
    "fit to run them. Vaeros closes that gap: standard video in, a FHIR R4-native Tactical "
    "Readiness Score out, delivered as a headless data feed into Maven."
)

PROOF_POINTS = """- Tradewinds Awardable (September 2026)
- Palantir Defense SDK acquired; Second Front MNDA executed for Game Warden deployment
- Layer 1 kinematic extraction demonstrated at TRL 6; patent pending"""

CREDENTIALS = "Harvard Medical School, HSS orthopedic surgery residency, Kerlan-Jobe sports medicine fellowship"


@dataclass
class Draft:
    to: list[str]
    subject: str
    body: str
    reply_to_message_id: str = ""


def _greeting(inv: Investor) -> str:
    return f"Hi {inv.first_name}," if inv.first_name else "Hi,"


def _hook_line(inv: Investor) -> str:
    # The personal first line is the single biggest driver of replies, so it is left for
    # Phil to write; the Hook column suggests the angle. Drafts are never sent unedited.
    if not inv.hook:
        return ""
    return f"[EDIT: one personal line. Angle: {inv.hook}]\n\n"


def cold_first_touch(inv: Investor) -> Draft:
    if inv.lead_source not in ("", "Cold Outreach"):
        subject = f"{inv.lead_source} suggested I reach out (Vaeros)"
        opener = f"{inv.lead_source} suggested we connect.\n\n"
    else:
        subject = "Maven's missing data layer (Vaeros, $2M Seed)"
        opener = _hook_line(inv)
    body = f"""{_greeting(inv)}

{opener}{PITCH}

Where we are:
{PROOF_POINTS}

I'm raising a $2M Seed to fund the live Maven integration build. Background: {CREDENTIALS}.

Worth 20 minutes next week? Happy to send the deck ahead of time.

{SIGNATURE}"""
    return Draft(to=[inv.partner_email] if inv.partner_email else [], subject=subject, body=body)


def follow_up(inv: Investor) -> Draft:
    """Bump on our own thread when a first touch has gone 5+ days without a reply."""
    body = f"""{_greeting(inv)}

Bumping this in case it got buried. One line version: Vaeros is the human readiness data feed for Maven, and we are raising a $2M Seed to build the live integration.

Is a 20 minute call next week possible? If the timing is wrong, a quick no is just as helpful.

{SIGNATURE}"""
    return Draft(to=[inv.partner_email] if inv.partner_email else [],
                 subject="Re: Maven's missing data layer (Vaeros, $2M Seed)", body=body)


def post_meeting(inv: Investor) -> Draft:
    body = f"""{_greeting(inv)}

Thank you for the time today. As promised, I'm sending the deck and data room access separately.

Next step on our side: [fill in]. Next step on yours: [fill in].

The round is moving this quarter, so I'll check back on [date] unless I hear from you sooner.

{SIGNATURE}"""
    return Draft(to=[inv.partner_email] if inv.partner_email else [],
                 subject="Vaeros: deck and next steps", body=body)


def referrer_nudge(inv: Investor, referrer_email: str) -> Draft:
    """Nudge the person making a warm intro. Short, easy to act on, gives them an out."""
    first = inv.lead_source.split()[0]
    fund = inv.fund_name.split(" (")[0].split(" - ")[0]
    body = f"""{first},

Circling back on the {fund} intro. If it's easier, forward the blurb from my last note as is, or tell me who you have in mind and I'll write to them mentioning you, so all you need to do is give them a heads up.

If the timing isn't right on your side, no problem at all, just let me know.

{SIGNATURE}"""
    return Draft(to=[referrer_email], subject=f"Re: Vaeros Seed Round / {fund} Intro", body=body)


TEMPLATES = {
    "cold": cold_first_touch,
    "follow_up": follow_up,
    "post_meeting": post_meeting,
}


def for_status(inv: Investor, referrers: dict[str, str] | None = None) -> Draft | None:
    """Pick the right template for where the investor sits in the pipeline."""
    referrers = referrers or {}
    if inv.status == "Target":
        return cold_first_touch(inv)
    if inv.status == "Intro Requested":
        if inv.lead_source in referrers:
            return referrer_nudge(inv, referrers[inv.lead_source])
        if inv.lead_source == "Cold Outreach":
            return follow_up(inv)
        return None
    if inv.status == "Meeting Set":
        return post_meeting(inv)
    return None  # Diligence onward is bespoke.
