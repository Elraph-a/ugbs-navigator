"""Strip personal identifiers out of an enquiry before it is stored.

Students describe their situation to get a useful answer, so enquiries routinely
contain illness, money trouble, disciplinary matters and contact details. The
analytics need the category, the routed office, the confidence and the timestamp
-- never who asked. This module is the gate between the two.

Redaction happens on the way *in* to storage, not on the way out of it. Once an
identifier is written to disk, redacting the display is theatre.

The name rules are deliberately conservative: they fire on explicit
self-identification ("my name is ...") rather than trying to spot every proper
noun, because over-redaction destroys the text the knowledge-gap clustering
depends on. This limitation is recorded in the report rather than hidden.
"""

from __future__ import annotations

import re

PLACEHOLDER = "[REDACTED]"

# University of Ghana student numbers are 8 digits; the older format is 5-7.
# Bounded by \b so ordinary years and fees are left alone.
STUDENT_ID = re.compile(r"\b\d{8}\b")

# Ghanaian mobile numbers: +233 24 123 4567, 0244123456, 024-412-3456.
PHONE = re.compile(
    r"(?:\+233[\s-]?|\b0)\d{2}[\s-]?\d{3}[\s-]?\d{4}\b"
)

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Explicit self-identification only. The trigger phrase is matched case-
# insensitively via a scoped flag, but the captured name stays case-sensitive:
# with IGNORECASE applied to the whole pattern, "i am sick" would redact "sick".
#
# Two rules rather than one. "my name is" reliably precedes a name, so one to
# three capitalised words are taken. "i am" mostly does not ("I am a level 400
# student"), so it requires at least two capitalised words before it will fire.
NAME_DECLARED = re.compile(
    r"\b(?i:my name is|this is)\s+"
    r"((?:[A-Z][a-z'-]+)(?:\s+[A-Z][a-z'-]+){0,2})\b"
)

NAME_SELF = re.compile(
    r"\b(?i:i am|i'm)\s+"
    r"((?:[A-Z][a-z'-]+)(?:\s+[A-Z][a-z'-]+){1,2})\b"
)

# Index numbers students quote when chasing results, e.g. "index number 10345678".
INDEX_NUMBER = re.compile(
    r"\b(?:index|student|id)\s*(?:number|no\.?|#)?\s*[:=]?\s*\d{4,10}\b",
    re.IGNORECASE,
)


def redact(text: str) -> tuple[str, list[str]]:
    """Return ``(clean_text, kinds_found)``.

    ``kinds_found`` records *what type* of identifier was present, never the
    value itself. It is useful for reporting how often students volunteer
    personal data, which is a finding worth putting in the report.
    """
    if not text:
        return "", []

    found: list[str] = []

    def substitute(pattern: re.Pattern[str], label: str, value: str) -> str:
        nonlocal found
        if pattern.search(value):
            found.append(label)
            return pattern.sub(PLACEHOLDER, value)
        return value

    clean = text
    # Email before phone: an address can contain digit runs that look like numbers.
    clean = substitute(EMAIL, "email", clean)
    clean = substitute(INDEX_NUMBER, "index_number", clean)
    clean = substitute(STUDENT_ID, "student_id", clean)
    clean = substitute(PHONE, "phone", clean)

    for pattern in (NAME_DECLARED, NAME_SELF):
        if pattern.search(clean):
            found.append("name")
            # Replace only the captured name, keeping the trigger phrase so the
            # sentence still reads as a question for the gap clustering.
            clean = pattern.sub(
                lambda m: m.group(0).replace(m.group(1), PLACEHOLDER), clean
            )

    return clean, sorted(set(found))


def contains_pii(text: str) -> bool:
    _, found = redact(text)
    return bool(found)
