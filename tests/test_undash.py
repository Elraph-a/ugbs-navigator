"""The model's replies reach students without em dashes, and still read well."""

import pytest

from core.generate import undash, undash_stream

CASES = [
    # Bold list labels, the model's favourite: "**Label** – text".
    ("1. **Get the form** – pick it up at the AAD.", "1. **Get the form**: pick it up at the AAD."),
    ("**Endorsement** — have your Head sign it.", "**Endorsement**: have your Head sign it."),
    # A dash used as a pause becomes a comma.
    ("You can defer — but only for a semester.", "You can defer, but only for a semester."),
    ("Fees—including the levy—are due now.", "Fees, including the levy, are due now."),
    # Ranges read as "to".
    ("Open Monday – Friday, 8am – 5pm.", "Open Monday to Friday, 8am to 5pm."),
    ("It takes 10 — 12 days.", "It takes 10 to 12 days."),
    # A dash used as a bullet becomes a hyphen bullet.
    ("— Bring your ID card", "- Bring your ID card"),
    # Left alone: unspaced ranges, hyphens, and text without dashes.
    ("Pages 1–3 of the 2025/2026 schedule.", "Pages 1–3 of the 2025/2026 schedule."),
    ("A well-known, up-to-date form.", "A well-known, up-to-date form."),
]


@pytest.mark.parametrize("raw, clean", CASES)
def test_undash(raw, clean):
    assert undash(raw) == clean


@pytest.mark.parametrize("raw, clean", CASES)
def test_stream_matches_whole_text_however_it_is_split(raw, clean):
    # Tokens arrive in arbitrary pieces; a dash pattern split across two of
    # them must be cleaned exactly as if it had arrived whole.
    for size in (1, 2, 3, 5):
        pieces = [raw[i : i + size] for i in range(0, len(raw), size)]
        assert "".join(undash_stream(iter(pieces))) == clean


def test_stream_still_streams():
    # Word-by-word delivery must survive: text is released at each safe point
    # rather than held until the end.
    pieces = ["You ", "can ", "defer ", "now ", "or ", "later."]
    released = list(undash_stream(iter(pieces)))
    assert len(released) > 2
    assert "".join(released) == "You can defer now or later."
