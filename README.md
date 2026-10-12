# Vaeros Seed Round CRM

An investor tracker for the $2M Seed round. It scans Gmail, keeps the pipeline current, and
writes compliance-checked outreach **drafts** in Gmail. It can't send mail. Every draft waits
for Phil to review and send it.

## The tracker: `data/pipeline.csv`

Open it in Excel or Google Sheets, or use the CLI. The first six columns are the ones you asked for:

| Column | Values |
|---|---|
| Fund Name | |
| Partner Name | `TBD` = identify the right partner before outreach |
| Lead Source | `Lane Dilg`, `Cold Outreach`, `Alumni`, or any referrer's name |
| Status | `Target` (not yet contacted), `Intro Requested`, `Meeting Set`, `Diligence`, `Term Sheet`, `Passed` |
| Next Action Date | `YYYY-MM-DD` |
| Notes | Dated entries are appended automatically |

Supporting columns: Partner Email, Fund Domain (used for Gmail matching), Tier (1 = best thesis fit),
Location, Hook (the angle for the personal first line), Last Touch, Gmail Thread ID.

**Before sending to anyone on the list, check the partner's name and email on the fund's own site.**
Partners change funds, and the Partner Email column is empty on purpose. Don't guess addresses.

## Daily use

```bash
python -m crm today                         # what's due
python -m crm list --status "Intro Requested"
python -m crm update DCVC --status "Meeting Set" --next 2026-10-20 --note "Call with <partner>"
python -m crm update "Founders Fund" --email trae@...   # unlocks a Gmail draft on next sync
python -m crm draft "J2 Ventures"           # print a draft + compliance result
python -m crm sync                          # scan Gmail, update tracker, create drafts for due rows
```

### What `sync` does
1. Finds the newest thread per row (partner email, fund domain, or referrer + fund name), then
   records Last Touch and the thread ID.
2. Flags **REPLY WAITING ON YOU** and makes the row due today.
3. Changes status only when the evidence is clear: once a first email has gone out, `Target` becomes
   `Intro Requested` with a follow-up 5 days later. A calendar invite from the fund's domain sets
   `Meeting Set`. You set Diligence, Term Sheet and Passed yourself.
4. For due rows, creates a Gmail draft from the template that matches the status: a cold first touch,
   a follow-up bump, a referrer nudge (sent to the referrer in the existing thread), or a post-meeting
   note. One nudge per referrer per run.

Setup (one time, on your Vaeros laptop, **never on Baylor hardware**):
```bash
pip install -r requirements.txt
# Google Cloud console -> enable Gmail API -> OAuth client "Desktop app" -> save as credentials.json here
python -m crm sync --no-drafts   # first run opens a browser to authorize; writes token.json
```
To run it every morning, use cron: `0 6 * * 1-5 cd ~/CRM && python -m crm sync`.

## Compliance gate (`crm/compliance.py`)

Drafts are blocked unless they pass checks drawn from the Master Operating Document v4.0:
- **Lexicon** (Brand Standard v1.0 §3): clinical, medical, healthcare, patient and diagnosis are
  blocked. The exception is the proper noun "Harvard Medical School", which the credential rule requires.
- **TRL Disclosure Lock** (§1.4): TRL 6 must be tied to Layer 1 kinematic extraction. "Architected",
  "IL5/Game Warden authorized", "validated on military populations" and "integrated with Maven" are all blocked.
- **Positioning rule** (§1.5): no DEI or de-biasing framing.
- **Clean-room rule**: no Baylor recipient addresses.
- Subjects must be under 60 characters.

## Why the emails are written the way they are

- **Subject:** a named referrer beats everything else ("Lane Dilg suggested I reach out"). When
  there's no referrer, name a gap the reader already thinks about ("Maven's missing data layer").
  Keep it under 60 characters, and leave out hype words and "quick question".
- **First line:** about the reader. The cold template leaves an `[EDIT: ...]` line with the angle
  from the Hook column. A real personal sentence there is the biggest single lift on replies.
- **Body:** one-sentence problem, three proof points, one ask with a time box. Under 150 words,
  plain text, no attachments on the first touch.
- **Follow-up:** one bump after 5 days that offers an easy "no". A clear no beats silence while
  you're working toward a close this quarter.
- **Warm paths:** before a cold send to a Tier 1 fund, look for a Harvard, Yale, HSS or Kerlan-Jobe
  alumni connection and record it as Lead Source `Alumni`.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Live pipeline page

`web/seed-pipeline.html` is published as a private claude.ai artifact:
https://claude.ai/artifact/HLGYiC315MejcongoTCWJb

It follows Brand Standard v1.0 (Family C-FEO). Stages use the maturity strokes: dotted for Target,
dashed for in motion, solid signal blue for diligence and term sheet. Records live in the artifact's
database. From the page you can:
- **Scan Gmail** through the claude.ai Gmail connector. It updates last touch, flags replies waiting
  on you, and moves first-touched targets forward.
- **Write email** from a stage template, or have Claude write three subject and body versions against
  the brand rules. Every draft goes through the lexicon, TRL-lock and clean-room checks.
- **Create Gmail draft** to land the email in Gmail unsent. Nudges thread into the existing conversation.

The page and the CSV are separate records. After the page goes live, treat it as the source of truth.
