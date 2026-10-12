"""Pre-send checks drawn from the Master Operating Document v4.0.

Every draft the CRM writes passes through check() first. A draft with any
violation is not created in Gmail; the violations are printed instead.

Sources:
  - Lexicon purge (v3.0 change log; Brand Standard v1.0 section 3)
  - TRL Disclosure Lock (section 1.4)
  - Cohort-validated positioning rule, no DEI framing (section 1.5)
  - BCM IP clean-room rule: no Baylor addresses (section 1.4)
"""

import re

# Proper nouns from the credential rule that legitimately contain a prohibited word.
_ALLOWED_PHRASES = ["Harvard Medical School"]

_PROHIBITED_TERMS = {
    r"clinic(al|ally|ian|ians|s)?": "prohibited lexicon term (use: readiness data layer)",
    r"medical(ly)?": "prohibited lexicon term (Vaeros is an AI software and data analytics company)",
    r"health ?care|health services": "prohibited lexicon term (use: readiness / human performance data)",
    r"patients?": "prohibited lexicon term (use: operator)",
    r"diagnos(is|es|e|tic|tics)": "prohibited lexicon term (use: readiness score / kinematic finding)",
    r"bias mitigation|fairness|DEI": "Brand Standard 3: use cross-cohort kinematic validity / readiness accuracy",
    r"dashboards?|platform UI": "Brand Standard 3: Vaeros is a data layer, payload or feed",
    r"Baylor|BCM": "Brand Standard 3: no academic-institution affiliation in Vaeros material",
}
# Case-sensitive: "DoD" survives only in citations; display copy says "the Department".
_DOD = re.compile(r"\bDoD\b")

_TRL_OVERCLAIMS = {
    r"\barchitected\b": "TRL lock: Layer 2 is 'underway', never 'architected'",
    r"\b(IL[45](/IL[45])?|Game Warden)\b[^.\n]{0,40}\b(authorized|accredited|certified|live)\b":
        "TRL lock: Layer 2 / Game Warden is underway, not authorized",
    r"(?<!not )(?<!not yet )\bvalidated (on|in|with|across) (military|service members|warfighters)":
        "TRL lock: the predictive model is NOT yet validated on military populations",
    r"\b(integrated (with|into) Maven|Maven integration (is )?(complete|live|done))":
        "TRL lock: SDK/MNDA are access instruments, not integration claims",
    r"\bde-?bias(ed|ing)?\b|\badvanc\w* equity\b|\bDEI\b":
        "Positioning rule: frame as cross-cohort predictive stability, never DEI",
}

_BLANKET_TRL = re.compile(r"\bTRL ?\d\b", re.IGNORECASE)
_LAYER1_SCOPE = re.compile(r"Layer 1|kinematic extraction", re.IGNORECASE)
_BAYLOR = re.compile(r"@([\w.-]+\.)?(bcm\.edu|bcm\.tmc\.edu|baylor\.edu)\b", re.IGNORECASE)


def check(subject: str, body: str, recipients: list[str] | tuple[str, ...] = ()) -> list[str]:
    """Return a list of human-readable violations; empty means clear to draft."""
    problems = []
    text = f"{subject}\n{body}"
    scrubbed = text
    for phrase in _ALLOWED_PHRASES:
        scrubbed = scrubbed.replace(phrase, "")

    for pattern, why in _PROHIBITED_TERMS.items():
        for m in re.finditer(rf"\b{pattern}\b", scrubbed, re.IGNORECASE):
            problems.append(f"'{m.group(0)}': {why}")

    for m in _DOD.finditer(text):
        problems.append(f"'{m.group(0)}': Brand Standard 3: write 'the Department' in display copy")
    if "!" in text:
        problems.append("'!': Brand Standard 3: no exclamation points")

    for pattern, why in _TRL_OVERCLAIMS.items():
        for m in re.finditer(pattern, text, re.IGNORECASE):
            problems.append(f"'{m.group(0)}': {why}")

    for m in _BLANKET_TRL.finditer(text):
        window = text[max(0, m.start() - 120): m.end() + 40]
        if not _LAYER1_SCOPE.search(window):
            problems.append(f"'{m.group(0)}': TRL lock: scope TRL 6 to Layer 1 kinematic extraction only")

    for addr in recipients:
        if _BAYLOR.search(addr):
            problems.append(f"'{addr}': clean-room rule: never route Vaeros mail through a Baylor address")

    if len(subject) > 60:
        problems.append(f"subject is {len(subject)} chars: keep it under 60 so it is not truncated on mobile")

    return problems
