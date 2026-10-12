import datetime as dt
import tempfile
import unittest
from pathlib import Path

from crm import compliance, gmail_sync, templates, tracker

TODAY = dt.date(2026, 10, 13)


def ms(date: dt.date) -> str:
    return str(int(dt.datetime(date.year, date.month, date.day, tzinfo=dt.timezone.utc).timestamp() * 1000))


class FakeGmail:
    """Just enough of the Gmail API client surface for sync()."""

    def __init__(self, threads):
        self.threads_by_id = {t["id"]: t for t in threads}
        self.drafts_made = []

    def users(self):
        return self

    def threads(self):
        return self

    def drafts(self):
        return self

    def list(self, userId, q, maxResults):
        self._result = {"threads": [{"id": i} for i in self.threads_by_id]}
        return self

    def get(self, userId, id, format, metadataHeaders):
        self._result = self.threads_by_id[id]
        return self

    def create(self, userId, body):
        self.drafts_made.append(body)
        self._result = {"id": f"d{len(self.drafts_made)}"}
        return self

    def execute(self):
        return self._result


def message(sender, date, subject="Hello"):
    return {"id": f"m-{sender}-{date}", "internalDate": ms(date),
            "payload": {"headers": [{"name": "From", "value": sender}, {"name": "Subject", "value": subject}]}}


class TrackerTests(unittest.TestCase):
    def test_pipeline_file_loads_and_dcvc_is_tracked(self):
        rows = tracker.load()
        dcvc = tracker.find(rows, "DCVC")
        self.assertEqual(dcvc.lead_source, "Lane Dilg")
        self.assertEqual(dcvc.status, "Intro Requested")
        self.assertEqual(dcvc.next_action_date, "2026-10-13")
        self.assertTrue(dcvc.is_due(TODAY))

    def test_round_trip(self):
        rows = tracker.load()
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "p.csv"
            tracker.save(rows, path)
            self.assertEqual(tracker.load(path), rows)

    def test_rejects_unknown_status_and_bad_date(self):
        with self.assertRaises(ValueError):
            tracker.Investor("X", status="Contacted")
        with self.assertRaises(ValueError):
            tracker.Investor("X", next_action_date="10/13/2026")

    def test_passed_is_never_due(self):
        self.assertFalse(tracker.Investor("X", status="Passed", next_action_date="2026-01-01").is_due(TODAY))


class ComplianceTests(unittest.TestCase):
    def test_every_template_is_clean_for_every_row(self):
        for inv in tracker.load():
            for make in templates.TEMPLATES.values():
                d = make(inv)
                self.assertEqual(compliance.check(d.subject, d.body, d.to), [], inv.fund_name)

    def test_flags_lexicon_terms_but_allows_credential(self):
        self.assertEqual(compliance.check("Hi", "Trained at Harvard Medical School."), [])
        self.assertTrue(compliance.check("Hi", "A clinical tool for patients."))

    def test_flags_trl_overclaims(self):
        self.assertTrue(compliance.check("Hi", "Our platform is at TRL 6."))
        self.assertEqual(compliance.check("Hi", "Layer 1 kinematic extraction at TRL 6."), [])
        self.assertTrue(compliance.check("Hi", "We have architected the IL5 boundary."))
        self.assertTrue(compliance.check("Hi", "The model is validated on military populations."))
        self.assertTrue(compliance.check("Hi", "Game Warden deployment is authorized."))

    def test_blocks_baylor_recipient(self):
        self.assertTrue(compliance.check("Hi", "Body", ["someone@bcm.edu"]))


class SyncTests(unittest.TestCase):
    def test_cold_row_advances_and_reply_is_flagged(self):
        inv = tracker.Investor("Founders Fund", partner_name="Trae Stephens", fund_domain="foundersfund.com",
                               next_action_date="2026-10-14")
        gmail = FakeGmail([{"id": "t1", "messages": [
            message("Phillip Williams <pwilliams@vaeros.ai>", dt.date(2026, 10, 8)),
            message("Trae <trae@foundersfund.com>", dt.date(2026, 10, 10)),
        ]}])
        report = gmail_sync.sync([inv], TODAY, make_drafts=False, service=gmail)
        self.assertEqual(inv.status, "Intro Requested")
        self.assertEqual(inv.last_touch, "2026-10-10")
        self.assertEqual(inv.next_action_date, "2026-10-13")  # reply waiting -> due today
        self.assertIn("REPLY WAITING ON YOU", report[0])

    def test_invite_sets_meeting(self):
        inv = tracker.Investor("Lux", fund_domain="luxcapital.com", status="Intro Requested")
        gmail = FakeGmail([{"id": "t1", "messages": [
            message("x@luxcapital.com", dt.date(2026, 10, 12), subject="Invitation: Vaeros / Lux")]}])
        gmail_sync.sync([inv], TODAY, make_drafts=False, service=gmail)
        self.assertEqual(inv.status, "Meeting Set")

    def test_one_referrer_nudge_covers_both_lane_rows_and_is_not_repeated(self):
        rows = [r for r in tracker.load() if r.lead_source == "Lane Dilg"]
        gmail = FakeGmail([])
        gmail_sync.sync(rows, TODAY, service=gmail)
        self.assertEqual(len(gmail.drafts_made), 1)
        self.assertEqual(gmail.drafts_made[0]["message"]["threadId"], "1a0f55483428ef5c")
        gmail_sync.sync(rows, TODAY, service=gmail)  # same day re-run
        self.assertEqual(len(gmail.drafts_made), 1)

    def test_due_row_without_email_is_skipped(self):
        inv = tracker.Investor("Sequoia", partner_name="Shaun Maguire", next_action_date="2026-10-13")
        report = gmail_sync.sync([inv], TODAY, service=FakeGmail([]))
        self.assertIn("no Partner Email", report[0])


if __name__ == "__main__":
    unittest.main()
