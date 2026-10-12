"""Command line for the Vaeros investor CRM.

  python -m crm today                     what is due today or overdue
  python -m crm list [--status S]         the whole pipeline (or one stage)
  python -m crm add "Fund" --partner ... --source ... --status ... --next YYYY-MM-DD --notes ...
  python -m crm update "Fund" [--status S] [--next YYYY-MM-DD] [--note "text"] [--partner ...] [--email ...]
  python -m crm draft "Fund" [--template cold|follow_up|post_meeting]   print a compliance-checked draft
  python -m crm sync [--no-drafts]        scan Gmail, update the tracker, create Gmail drafts for due rows
"""

import argparse
import datetime as dt
import sys

from . import compliance, templates, tracker


def _table(rows: list[tracker.Investor]) -> str:
    out = [f"{'Next':<11} {'Status':<16} {'Fund':<40} {'Partner':<24} Source"]
    for r in sorted(rows, key=lambda r: (r.next_action_date or "9999", r.tier)):
        out.append(f"{r.next_action_date or '-':<11} {r.status:<16} {r.fund_name[:39]:<40} "
                   f"{(r.partner_name or '-')[:23]:<24} {r.lead_source}")
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="crm")
    p.add_argument("--today", default=dt.date.today().isoformat(), help="override today's date (YYYY-MM-DD)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("today")
    ls = sub.add_parser("list")
    ls.add_argument("--status", choices=tracker.STATUSES)

    add = sub.add_parser("add")
    add.add_argument("fund")
    add.add_argument("--partner", default="")
    add.add_argument("--source", default="Cold Outreach")
    add.add_argument("--status", default="Target", choices=tracker.STATUSES)
    add.add_argument("--next", default="")
    add.add_argument("--notes", default="")
    add.add_argument("--email", default="")
    add.add_argument("--domain", default="")
    add.add_argument("--tier", default="2")

    up = sub.add_parser("update")
    up.add_argument("fund")
    up.add_argument("--status", choices=tracker.STATUSES)
    up.add_argument("--next")
    up.add_argument("--note")
    up.add_argument("--partner")
    up.add_argument("--email")

    dr = sub.add_parser("draft")
    dr.add_argument("fund")
    dr.add_argument("--template", choices=sorted(templates.TEMPLATES))

    sy = sub.add_parser("sync")
    sy.add_argument("--no-drafts", action="store_true")

    args = p.parse_args(argv)
    today = dt.date.fromisoformat(args.today)
    rows = tracker.load()

    if args.cmd == "today":
        due = [r for r in rows if r.is_due(today)]
        print(_table(due) if due else "Nothing due.")
    elif args.cmd == "list":
        print(_table([r for r in rows if not args.status or r.status == args.status]))
    elif args.cmd == "add":
        if any(r.fund_name.lower() == args.fund.lower() for r in rows):
            print(f"{args.fund} is already in the tracker; use update.", file=sys.stderr)
            return 1
        rows.append(tracker.Investor(
            fund_name=args.fund, partner_name=args.partner, lead_source=args.source, status=args.status,
            next_action_date=args.next, notes=args.notes, partner_email=args.email,
            fund_domain=args.domain, tier=args.tier))
        tracker.save(rows)
        print(f"Added {args.fund}.")
    elif args.cmd == "update":
        inv = tracker.find(rows, args.fund)
        if args.status:
            inv.status = args.status
        if args.next:
            dt.date.fromisoformat(args.next)
            inv.next_action_date = args.next
        if args.partner:
            inv.partner_name = args.partner
        if args.email:
            inv.partner_email = args.email
        if args.note:
            inv.add_note(args.note, today)
        tracker.save(rows)
        print(f"Updated {inv.fund_name}.")
    elif args.cmd == "draft":
        inv = tracker.find(rows, args.fund)
        draft = (templates.TEMPLATES[args.template](inv) if args.template
                 else templates.for_status(inv, _referrers()))
        if draft is None:
            print(f"No default template for status {inv.status!r}; pass --template.", file=sys.stderr)
            return 1
        print(f"To: {', '.join(draft.to) or '(no email on file)'}\nSubject: {draft.subject}\n\n{draft.body}")
        problems = compliance.check(draft.subject, draft.body, draft.to)
        print("\nCompliance: " + ("clear" if not problems else "\n  - " + "\n  - ".join(problems)))
    elif args.cmd == "sync":
        from . import gmail_sync
        for line in gmail_sync.sync(rows, today, make_drafts=not args.no_drafts):
            print(line)
        tracker.save(rows)
    return 0


def _referrers() -> dict[str, str]:
    from .gmail_sync import load_referrers
    return load_referrers()
