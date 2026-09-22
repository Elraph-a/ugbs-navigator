"""Redaction must catch identifiers without eating the question.

Both directions matter. Under-redaction puts student personal data on disk.
Over-redaction destroys the wording that the knowledge-gap clustering reads, so
the dashboard stops telling administrators anything useful.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.redact import PLACEHOLDER, redact


def test_catches_email_phone_and_student_id():
    text = (
        "My name is Kwame Mensah, student ID 10812345, "
        "call me on 0244123456 or kmensah@st.ug.edu.gh"
    )
    clean, kinds = redact(text)

    assert "Kwame Mensah" not in clean
    assert "10812345" not in clean
    assert "0244123456" not in clean
    assert "kmensah@st.ug.edu.gh" not in clean
    assert set(kinds) == {"name", "index_number", "phone", "email"}


def test_international_phone_format():
    clean, kinds = redact("Reach me on +233 24 412 3456")
    assert "3456" not in clean
    assert "phone" in kinds


def test_leaves_ordinary_questions_untouched():
    text = "How do I request an official transcript?"
    clean, kinds = redact(text)
    assert clean == text
    assert kinds == []


def test_does_not_redact_years_or_fees():
    # Graduation years and cedi amounts are load-bearing for the demo cases.
    text = "I graduated in 1994 and the fee is GHS 30, or 85 by post"
    clean, kinds = redact(text)
    assert clean == text
    assert kinds == []


def test_i_am_does_not_eat_ordinary_words():
    # "i am" is followed by a name far less often than by a description.
    text = "I am a level 400 student and I am sick"
    clean, kinds = redact(text)
    assert clean == text
    assert kinds == []


def test_i_am_still_catches_a_full_name():
    clean, kinds = redact("I am Ama Serwaa and I need help")
    assert "Ama Serwaa" not in clean
    assert "name" in kinds


def test_keeps_the_question_readable():
    # The trigger phrase survives so the text still clusters as an enquiry.
    clean, _ = redact("My name is Kofi Boateng. How do I defer a semester?")
    assert "How do I defer a semester?" in clean
    assert PLACEHOLDER in clean


def test_empty_input():
    assert redact("") == ("", [])
