"""Load, validate, and save the investor pipeline (data/pipeline.csv)."""

import csv
import datetime as dt
from dataclasses import dataclass, field, fields
from pathlib import Path

PIPELINE_PATH = Path(__file__).resolve().parent.parent / "data" / "pipeline.csv"

# "Target" is the pre-outreach state; the other five are the pipeline stages.
STATUSES = ["Target", "Intro Requested", "Meeting Set", "Diligence", "Term Sheet", "Passed"]
ACTIVE_STATUSES = [s for s in STATUSES if s != "Passed"]

COLUMNS = [
    "Fund Name", "Partner Name", "Lead Source", "Status", "Next Action Date", "Notes",
    "Partner Email", "Fund Domain", "Tier", "Location", "Hook", "Last Touch", "Gmail Thread ID",
]


@dataclass
class Investor:
    fund_name: str
    partner_name: str = ""
    lead_source: str = "Cold Outreach"
    status: str = "Target"
    next_action_date: str = ""
    notes: str = ""
    partner_email: str = ""
    fund_domain: str = ""
    tier: str = "2"
    location: str = ""
    hook: str = ""
    last_touch: str = ""
    gmail_thread_id: str = ""

    def __post_init__(self):
        if self.status not in STATUSES:
            raise ValueError(f"{self.fund_name}: unknown status {self.status!r} (use one of {STATUSES})")
        for name in ("next_action_date", "last_touch"):
            value = getattr(self, name)
            if value:
                dt.date.fromisoformat(value)  # raises on a malformed date

    @property
    def first_name(self) -> str:
        if not self.partner_name or self.partner_name.startswith("TBD"):
            return ""
        return self.partner_name.split()[0]

    @property
    def next_action(self) -> dt.date | None:
        return dt.date.fromisoformat(self.next_action_date) if self.next_action_date else None

    def is_due(self, today: dt.date) -> bool:
        return self.status in ACTIVE_STATUSES and self.next_action is not None and self.next_action <= today

    def add_note(self, text: str, today: dt.date) -> None:
        entry = f"[{today.isoformat()}] {text}"
        self.notes = f"{self.notes} {entry}".strip() if self.notes else entry


_ATTRS = [f.name for f in fields(Investor)]
_COL_TO_ATTR = dict(zip(COLUMNS, _ATTRS))


def load(path: Path = PIPELINE_PATH) -> list[Investor]:
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = set(COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        return [Investor(**{_COL_TO_ATTR[c]: (row.get(c) or "").strip() for c in COLUMNS}) for row in reader]


def save(investors: list[Investor], path: Path = PIPELINE_PATH) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(COLUMNS)
        for inv in investors:
            writer.writerow([getattr(inv, a) for a in _ATTRS])


def find(investors: list[Investor], fund_name: str) -> Investor:
    needle = fund_name.lower()
    matches = [i for i in investors if needle in i.fund_name.lower()]
    if len(matches) != 1:
        names = [m.fund_name for m in matches] or "none"
        raise LookupError(f"{fund_name!r} matched {names}; be more specific")
    return matches[0]
