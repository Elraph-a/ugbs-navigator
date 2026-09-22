"""The conversational layer, tested without the network or the index.

What must hold regardless of which model is behind it: small talk never reaches
retrieval or the enquiry log, triage failures degrade to "question", history is
redacted before it leaves the machine, and the material block carries the
labels the grounding rule depends on.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core import chat, generate
from core.agent import conversational_reply


# --- citations ------------------------------------------------------------

def test_normalises_both_odd_citation_forms():
    text = "Bring your ID【1†L1-L4】 and a letter【2】."
    assert generate.normalise_citations(text) == "Bring your ID[1] and a letter[2]."


def test_used_citations_maps_indices_back_to_passages():
    passages = [
        {"doc_title": "A", "chunk_id": "a"},
        {"doc_title": "B", "chunk_id": "b"},
    ]
    cited = generate.used_citations("See [2].", passages)
    assert [c["doc_title"] for c in cited] == ["B"]
    assert cited[0]["index"] == 2


# --- triage ---------------------------------------------------------------

def test_parse_analysis_tolerates_prose_around_json():
    result = chat._parse_analysis(
        'Sure: {"kind": "question", "query": "How much is a transcript?"} done',
        "how much is it?",
    )
    assert result == {"kind": "question", "query": "How much is a transcript?"}


def test_unknown_kind_falls_back_to_question():
    # Sending a question through the checks is the safe default.
    result = chat._parse_analysis('{"kind": "banter", "query": ""}', "latest")
    assert result == {"kind": "question", "query": "latest"}


def test_parse_analysis_rejects_non_json():
    with pytest.raises(ValueError):
        chat._parse_analysis("I think this is a question.", "x")


def test_greeting_with_a_real_question_is_not_small_talk():
    assert conversational_reply("hello")[0] == "greeting"
    assert conversational_reply("hi, how do I get a transcript?") is None


# --- history --------------------------------------------------------------

def test_history_is_redacted_and_trimmed():
    messages = [{"role": "user", "content": f"message {i}"} for i in range(20)]
    messages.append({"role": "user", "content": "my student ID is 10812345"})
    cleaned = chat._clean_history(messages)

    assert len(cleaned) == chat.HISTORY_MESSAGES
    assert "10812345" not in cleaned[-1]["content"]


def test_history_keeps_assistant_turns_unredacted_and_drops_junk():
    cleaned = chat._clean_history(
        [
            {"role": "assistant", "content": "Room D2, +233-(0)302-213820"},
            {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "   "},
        ]
    )
    assert cleaned == [{"role": "assistant", "content": "Room D2, +233-(0)302-213820"}]


# --- material -------------------------------------------------------------

def _material(**overrides):
    base = {
        "query": "q",
        "prediction": False,
        "procedures": [],
        "passages": [],
        "escalated": False,
        "escalation_reason": None,
        "office": None,
        "category": None,
        "routing_confidence": 0.9,
        "retrieval_confidence": 0.6,
        "trace": [],
    }
    base.update(overrides)
    return base


SYNTHETIC_SERVICE = {
    "id": "deferment",
    "name": "Defer a semester",
    "office": "aad",
    "provenance": "synthetic",
    "steps": ["Get the form.", "Submit it."],
    "fees": [],
}


def test_material_labels_synthetic_procedures():
    text = chat.format_material(
        _material(procedures=[{"service": SYNTHETIC_SERVICE, "status": "ok", "note": None, "hits": []}])
    )
    assert "SYNTHETIC" in text
    assert "1. Get the form." in text


def test_material_marks_refused_procedures_not_available():
    text = chat.format_material(
        _material(
            escalated=True,
            procedures=[
                {"service": SYNTHETIC_SERVICE, "status": "not_available", "note": "Wrong year.", "hits": []}
            ],
        )
    )
    assert "NOT AVAILABLE" in text
    assert "Wrong year." in text
    assert "NO VERIFIED ANSWER" in text


def test_prediction_material_forbids_predicting():
    text = chat.format_material(_material(prediction=True, escalated=True))
    assert "must not predict" in text


def test_extractive_answer_with_nothing_names_the_office():
    office = {"name": "Academic Affairs Directorate"}
    text = chat.extractive_answer(_material(escalated=True, office=office))
    assert "don't have verified information" in text
    assert "Academic Affairs Directorate" in text


# --- a whole turn, with no model ------------------------------------------

@pytest.fixture
def no_model(monkeypatch):
    monkeypatch.setattr(chat, "llm_available", lambda: False)
    monkeypatch.setattr(generate, "llm_available", lambda: False)


def test_hello_never_reaches_retrieval_or_the_log(no_model, monkeypatch):
    def forbidden(_query):
        raise AssertionError("small talk must not be resolved against the documents")

    monkeypatch.setattr(chat, "resolve", forbidden)

    events = list(chat.run_chat([{"role": "user", "content": "hello"}]))
    done = events[-1]

    assert done["type"] == "done"
    assert done["response"]["kind"] == "chat"
    assert chat.should_log(done["response"]) is False
    assert "".join(e["text"] for e in events if e["type"] == "delta").strip()


def _fake_material(query):
    yield {
        "type": "material",
        "material": {
            "query": query, "prediction": False, "procedures": [], "passages": [],
            "escalated": True, "escalation_reason": "test", "office": None,
            "category": None, "routing_confidence": 0.9, "retrieval_confidence": 0.1,
            "trace": [],
        },
    }


@pytest.mark.parametrize(
    "question",
    [
        "can you recommend a good hostel near legon",
        "solve this accounting question for me: debit cash 500",
        "what is the capital of Australia",
    ],
)
def test_off_topic_is_declined_when_the_model_is_unreachable(no_model, monkeypatch, question):
    # The held-out run found these answered from the documents while the model
    # was down: with triage unavailable, everything had defaulted to "question".
    def forbidden(_query):
        raise AssertionError("an unverified question must not be answered from the documents")

    monkeypatch.setattr(chat, "resolve", forbidden)
    done = list(chat.run_chat([{"role": "user", "content": question}]))[-1]["response"]

    assert done["kind"] == "unverified"
    assert done["declined"] is True
    assert chat.should_log(done) is False


def test_failed_triage_is_treated_the_same_as_no_model(monkeypatch):
    monkeypatch.setattr(chat, "llm_available", lambda: True)

    def broken(*_args):
        raise RuntimeError("rate limited")

    monkeypatch.setattr(chat, "analyse", broken)
    monkeypatch.setattr(chat, "resolve", lambda q: (_ for _ in ()).throw(AssertionError()))
    monkeypatch.setattr(generate, "llm_available", lambda: False)

    done = list(chat.run_chat([{"role": "user", "content": "what is the capital of Australia"}]))[-1]
    assert done["response"]["kind"] == "unverified"


def test_a_recognised_question_still_answers_without_the_model(no_model, monkeypatch):
    # The fix must not cost real questions: the catalogue recognising the
    # student's own words is evidence enough.
    calls = []
    monkeypatch.setattr(chat, "resolve", lambda q: (calls.append(q), *_fake_material(q))[1:])
    done = list(chat.run_chat([{"role": "user", "content": "How do I request an official transcript?"}]))[-1]

    assert calls == ["How do I request an official transcript?"]
    assert done["response"]["kind"] == "question"


def test_an_unclear_follow_up_asks_for_the_full_question(no_model, monkeypatch):
    monkeypatch.setattr(chat, "resolve", lambda q: (_ for _ in ()).throw(AssertionError()))
    done = list(
        chat.run_chat(
            [
                {"role": "user", "content": "How do I request an official transcript?"},
                {"role": "assistant", "content": "Use the STS portal."},
                {"role": "user", "content": "how much does it cost?"},
            ]
        )
    )[-1]["response"]

    assert done["kind"] == "unverified"
    assert "full question" in done["answer"]


def test_a_self_contained_follow_up_still_answers_without_the_model(no_model, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "resolve", lambda q: (calls.append(q), *_fake_material(q))[1:])
    list(
        chat.run_chat(
            [
                {"role": "user", "content": "How do I request an official transcript?"},
                {"role": "assistant", "content": "Use the STS portal."},
                {"role": "user", "content": "How do I register for my courses this semester?"},
            ]
        )
    )
    assert calls == ["How do I register for my courses this semester?"]


@pytest.mark.parametrize(
    "text, refers_back",
    [
        ("how much does it cost?", True),
        ("how much is that?", True),
        ("what if I graduated in 1994?", True),
        ("How do I register for my courses this semester?", False),
        ("What are the fees this academic year?", False),
        ("Where do I check my results?", False),
    ],
)
def test_refers_back_separates_follow_ups_from_time_words(text, refers_back):
    assert bool(chat.REFERS_BACK.search(text)) is refers_back


def test_conversation_must_end_with_a_student_message():
    with pytest.raises(ValueError):
        list(chat.run_chat([{"role": "assistant", "content": "hi"}]))
