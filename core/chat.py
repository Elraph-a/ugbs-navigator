"""A conversation about the University documents.

Each turn goes through three stages:

  1. Triage   Is this a question, small talk, or something off-topic? And if it
              is a follow-up ("how much is it?"), what is the standalone question?
  2. Resolve  `core.agent.resolve` finds what the documents say. Deterministic:
              routing, retrieval, and every check that protects a student.
  3. Answer   The model writes one conversational reply from that material,
              streamed as it is written, with the conversation as context.

The model sees the whole conversation, so a student can refer back ("and if I
graduated in 1994?"). But University facts may only come from this turn's
MATERIAL. Memory is for understanding the question; the documents are for
answering it.
"""

from __future__ import annotations

import json
import re
import textwrap
import time
from collections.abc import Iterator

from core import config, router
from core.agent import (
    GREETING_REPLY,
    OFF_TOPIC_REPLY,
    conversational_reply,
    resolve,
)
from core.generate import (
    complete,
    llm_available,
    normalise_citations,
    reply_stream,
    used_citations,
)
from core.redact import redact

# How much conversation travels with each turn. Enough to resolve "it" and "that"
# several exchanges back; not so much that an old answer crowds out this turn's
# material.
HISTORY_MESSAGES = 8
HISTORY_CHARS = 1500

# Routing confidence above which a first message is treated as a question
# without asking the triage model. Same bar the resolver uses to trust the
# catalogue over weak retrieval.
RECOGNISED = 0.7

# Words that make a follow-up depend on the conversation for its meaning.
# "this"/"that" only count when they are not naming a time: "register for my
# courses this semester" is self-contained, "how much is that?" is not.
REFERS_BACK = re.compile(
    r"\b(?:it|its|them|they|there|same|what about|how about|and if|what if|"
    r"(?:this|that|these|those)(?!\s+(?:semester|year|term|week|month|session|"
    r"academic|morning|afternoon|evening)\b))\b",
    re.IGNORECASE,
)

IDENTITY = """\
You are the UGBS Service Navigator, a conversational assistant for students of \
the University of Ghana Business School (UGBS). You help with administrative \
procedures: registration, transcripts, fees, results and grade changes, \
examinations, deferment and withdrawal, student ID cards, graduation, courses, \
and finding student support. You are part of a student project for OMIS 404 at \
UGBS, not an official University service."""

SYSTEM_ANSWER = IDENTITY + """

How to answer:
- Talk like a knowledgeable, friendly member of staff. Use the conversation: the \
student may refer back to something said earlier.
- Answer the actual question in your first sentence. Be concise. Use a numbered \
list for steps and short paragraphs otherwise. Bold only the one or two facts \
that matter most.
- Every University fact (offices, rooms, phone numbers, emails, fees, dates, \
deadlines, processing times, documents required and steps) must come from the \
MATERIAL attached to the latest message. Never use outside knowledge for these, \
never guess, and never carry over a figure that is not in the material.
- Cite the passages you rely on as [1], [2]: a number in square brackets and \
nothing else. Steps from a listed procedure can be stated without a citation.
- If the MATERIAL marks something NOT AVAILABLE, or says there is no verified \
answer, tell the student plainly that you don't have verified information on it \
and name the office to ask if the material gives one. Do not fill the gap with \
general advice presented as fact.
- If you rely on a procedure marked SYNTHETIC, add one short sentence noting it \
is an illustrative guide written for this project, not an official University \
publication.
- Never predict how an individual student will do. Never answer questions \
outside University administration.
- Stop when the answer is complete. No filler closing lines.
- Write in natural, flowing sentences. Never use em dashes or en dashes as \
punctuation. Use a comma, a full stop, a colon or brackets instead, or rephrase \
so the sentence reads smoothly."""

# The same writing rule, for conversational and off-topic replies.
_STYLE = """

Write in natural, flowing sentences. Never use em dashes or en dashes as \
punctuation. Use a comma, a full stop, a colon or brackets instead, or rephrase \
so the sentence reads smoothly."""

SYSTEM_CHAT = IDENTITY + """

This message is conversational: a greeting, thanks, goodbye, small talk, or a \
question about you. Reply naturally in one to three short sentences and, where it \
fits, invite the student to ask about a procedure.

About yourself, if asked: you answer from published University of Ghana \
documents (the General Regulations for Junior Members, the College of Humanities \
handbook, Academic Affairs Directorate pages, the 2025/2026 fee schedule and the \
graduate academic calendar); you show your sources; you say plainly when nothing \
published covers a question; you remember the conversation, so follow-up \
questions work; and a few procedures (deferment, withdrawal, ID cards, \
graduation, student support) are illustrative guides written for this project.

Do not state any University fees, offices, contacts, dates or procedures in this \
reply.""" + _STYLE

SYSTEM_CONCEPT = IDENTITY + """

The student has asked what a general term means, and no University document
defines it. Explain the term itself in two or three plain sentences, the way a
helpful member of staff would.

- Explain the general meaning only. State no University of Ghana fee, figure,
  date, rule, threshold, office or procedure, not even one you believe you know.
- If the term has a University-specific version (how it is calculated here, what
  counts as a pass, which office handles it), say plainly that the documents you
  hold do not cover that, and that the student should confirm it with their
  department or the relevant office.
- Do not invent a citation. There is nothing to cite.""" + _STYLE

OFF_TOPIC_NOTE = """

The student has asked about something outside University administration. Do not \
answer it, even if you know the answer. Say briefly and warmly that it is outside \
what you can help with, and mention what you can help with."""

ANALYSE_PROMPT = """\
You triage one message sent to the UGBS Service Navigator, an assistant that \
answers questions about University of Ghana Business School administrative \
procedures (registration, transcripts, fees, results, examinations, deferment, \
withdrawal, student ID cards, graduation, courses, student support).

Classify the LATEST MESSAGE and rewrite it as a standalone question.

Return only a JSON object: {"kind": "...", "query": "..."}

kind:
- "question": asks for information about the University, its procedures, \
offices, fees, dates, documents, rules, courses or support. This includes \
follow-ups to earlier answers ("how much is it?", "what about graduates?") and \
requests to predict the student's own results.
- "chat": greetings, thanks, goodbyes, small talk, or questions about the \
assistant itself.
- "off_topic": asks for information or help unrelated to the University, such as \
sport, food, entertainment, general knowledge or doing assignments.

query: the latest message rewritten as one complete, self-contained question, \
using the conversation to resolve words like "it", "that", "there" or "what \
about". Keep every detail the student gave about themselves (level, programme, \
graduation year, urgency). If it is already self-contained, repeat it unchanged."""


# --------------------------------------------------------------------------
# Conversation plumbing
# --------------------------------------------------------------------------

def _clean_history(messages: list[dict]) -> list[dict]:
    """Earlier turns, redacted and trimmed.

    Student turns are redacted exactly as the latest one is: history is sent to
    an external model, and an ID number typed three messages ago is still an ID
    number.
    """
    cleaned: list[dict] = []
    for message in messages[-HISTORY_MESSAGES:]:
        role = message.get("role")
        content = (message.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if role == "user":
            content, _ = redact(content)
        cleaned.append({"role": role, "content": content[:HISTORY_CHARS]})
    return cleaned


def _transcript(history: list[dict], latest: str) -> str:
    lines = [
        f"{'Student' if m['role'] == 'user' else 'Assistant'}: {m['content'][:500]}"
        for m in history
    ]
    conversation = "\n".join(lines) or "(no earlier messages)"
    return f"CONVERSATION SO FAR:\n{conversation}\n\nLATEST MESSAGE:\n{latest}"


def _parse_analysis(text: str, latest: str) -> dict:
    """Read the triage JSON, tolerating prose around it. Unknown kinds become
    "question": sending a question through the checks is the safe default."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"no JSON in triage reply: {text[:120]!r}")

    data = json.loads(match.group(0))
    kind = str(data.get("kind", "question")).strip().lower()
    if kind not in {"question", "chat", "off_topic"}:
        kind = "question"
    query = str(data.get("query") or "").strip() or latest
    return {"kind": kind, "query": query}


def analyse(history: list[dict], latest: str) -> dict:
    """Triage one turn with the fast model."""
    text = complete(
        [
            {"role": "system", "content": ANALYSE_PROMPT},
            {"role": "user", "content": _transcript(history, latest)},
        ],
        fast=True,
        max_tokens=400,
    )
    return _parse_analysis(text, latest)


# --------------------------------------------------------------------------
# Material
# --------------------------------------------------------------------------

def _describe_office(office: dict) -> str:
    parts = [office["name"]]
    if office.get("description"):
        parts.append(f"what it is: {office['description']}")
    for key, label in (
        ("location", "location"),
        ("postal_address", "post"),
        ("phone", "phone"),
        ("email", "email"),
        ("hours", "hours"),
        ("url", "online"),
    ):
        if office.get(key):
            parts.append(f"{label}: {office[key]}")
    return "; ".join(parts)


def format_material(material: dict) -> str:
    """Everything the model is allowed to state, in one block.

    If a fact is not in here, the model has been told it may not say it. That is
    the grounding rule, applied at the only point where the model sees anything.
    """
    if material["prediction"]:
        return (
            "NOTE: The student is asking you to predict their own individual outcome. "
            "You must not predict. Explain that you only hold published University "
            "procedure, and suggest they speak to their department or academic advisor."
        )

    lines: list[str] = []

    procedures = [p for p in material["procedures"] if p["service"]]
    if procedures:
        lines.append("PROCEDURES (from the verified service catalogue):")
        for procedure in procedures:
            service = procedure["service"]

            if procedure["status"] != "ok":
                lines += [
                    "",
                    f"### {service['name']}: NOT AVAILABLE",
                    f"Reason: {procedure['note']}",
                ]
                continue

            source = (
                "SYNTHETIC: written by the project team, not an official University publication"
                if service.get("provenance") == "synthetic"
                else "published University source"
            )
            lines += ["", f"### {service['name']} ({source})"]

            office = router.office_for_service(service)
            if office:
                lines.append(f"Office: {_describe_office(office)}")
            if service.get("channel"):
                lines.append(f"Channel: {service['channel']}")
            if service.get("eligibility"):
                lines.append(f"Applies when: {service['eligibility']}")
            if service.get("steps"):
                lines.append("Steps:")
                lines += [f"{i}. {step}" for i, step in enumerate(service["steps"], start=1)]
            for fee in service.get("fees") or []:
                extra = f"; additional copies: {fee['additional']}" if fee.get("additional") else ""
                lines.append(f"Fee ({fee['mode']}): {fee['first_copy']}{extra}")
            for key, label in (
                ("fees_note", "Fees note"),
                ("turnaround", "How long"),
                ("turnaround_note", "Timing note"),
                ("caveat", "Caveat"),
                ("data_year", "Figures held for academic year"),
            ):
                if service.get(key):
                    lines.append(f"{label}: {service[key]}")

    office = material.get("office")
    if office:
        lines += ["", f"RESPONSIBLE OFFICE: {_describe_office(office)}"]

    passages = material["passages"]
    if passages:
        lines += ["", "PASSAGES (cite as [n]):"]
        for index, hit in enumerate(passages, start=1):
            heading = hit.get("section") or hit["doc_title"]
            dated = f", published {hit['published_date']}" if hit.get("published_date") else ""
            synthetic = (
                " (SYNTHETIC, written by the project team)"
                if hit.get("provenance") == "synthetic"
                else ""
            )
            lines.append(f"[{index}] {hit['doc_title']}, {heading}{dated}{synthetic}\n{hit['text']}")

    defines = material.get("defines")
    if defines:
        lines += [
            "",
            f"THE STUDENT IS ASKING WHAT THIS IS: {_describe_office(defines)}",
            "Say what it is, in your own words, from the description above. No "
            "procedure was retrieved, so give no steps, fees or dates.",
        ]

    if material["escalated"]:
        lines += [
            "",
            "NO VERIFIED ANSWER: nothing in the University documents held answers "
            "this question. Say so plainly and point the student to the responsible "
            "office above, if there is one.",
        ]

    return "\n".join(lines).strip()


def extractive_answer(material: dict) -> str:
    """The reply with no model: catalogue steps and passages, quoted not written.

    Shown when LLM_PROVIDER=extractive or the model call fails. It cannot
    hallucinate, because it never writes a new sentence about the subject.
    """
    if material["prediction"]:
        return (
            "I can't predict how an individual student will do, because I only hold "
            "published University procedure. For academic guidance, speak to your "
            "department or academic advisor."
        )

    if material.get("general"):
        # Explaining a term in general words is the one thing this fallback
        # cannot do: it only quotes, and nothing held defines the term.
        return (
            "Nothing in the University documents I hold defines that term, and I "
            "can only explain it in my own words when the assistant's language "
            "model is reachable. Your department or the relevant office can "
            "confirm what it means here."
        )

    parts: list[str] = []
    for procedure in material["procedures"]:
        service = procedure["service"]
        if procedure["status"] != "ok":
            if service:
                parts += [f"**{service['name']}**: {procedure['note']}", ""]
            continue
        if service and service.get("steps"):
            parts.append(f"**{service['name']}**")
            parts += [f"{i}. {step}" for i, step in enumerate(service["steps"], start=1)]
            if service.get("turnaround"):
                parts.append(f"\nHow long: {service['turnaround']}.")
            if service.get("provenance") == "synthetic":
                parts.append(
                    "\n_This is an illustrative guide written for this project, "
                    "not an official University publication._"
                )
            parts.append("")

    has_steps = any(
        p["status"] == "ok" and p["service"] and p["service"].get("steps")
        for p in material["procedures"]
    )
    if material["passages"] and not has_steps:
        excerpt = textwrap.shorten(material["passages"][0]["text"], width=500, placeholder=" …")
        parts.append(f"{excerpt} [1]")

    if not "".join(parts).strip():
        office = material.get("office")
        tail = f" The {office['name']} is the office to ask." if office else ""
        return "I don't have verified information on that in the University documents I hold." + tail

    return "\n".join(parts).strip()


# --------------------------------------------------------------------------
# The turn
# --------------------------------------------------------------------------

def should_log(response: dict) -> bool:
    """Only questions are service demand. Greetings and off-topic chat logged as
    enquiries would put small talk into the knowledge-gap register that
    administrators are asked to act on."""
    return response.get("kind") == "question"


def _converse(
    kind: str,
    history: list[dict],
    latest: str,
    canned: tuple[str, str] | None,
    pii: list[str],
    started: float,
) -> Iterator[dict]:
    """A turn that needs no documents: small talk, or a polite decline."""
    system = SYSTEM_CHAT + (OFF_TOPIC_NOTE if kind == "off_topic" else "")
    fallback = (
        canned[1] if canned else OFF_TOPIC_REPLY if kind == "off_topic" else GREETING_REPLY
    )
    meta: dict = {}
    text = ""

    for piece in reply_stream(
        [{"role": "system", "content": system}, *history, {"role": "user", "content": latest}],
        fallback,
        meta=meta,
        max_tokens=350,
        temperature=0.5,
        # A one-line greeting does not need the large model reasoning first:
        # on it, "hello" took 3-5s before a single word appeared.
        fast=True,
    ):
        text += piece
        yield {"type": "delta", "text": piece}

    text = text.strip()
    yield {
        "type": "done",
        "response": {
            "question": latest,
            "message": latest,
            "kind": kind,
            "conversational": kind,
            "answer": text,
            "citations": [],
            "pii_redacted": pii,
            "sections": [
                {
                    "service": None,
                    "answer": text,
                    "citations": [],
                    "refused": False,
                    "conversational": kind,
                }
            ],
            "escalated": False,
            # An off-topic request was declined, even though nothing went wrong.
            "declined": kind == "off_topic",
            "escalation_reason": None,
            "office": None,
            "category": None,
            "routing_confidence": 0.0,
            "retrieval_confidence": 0.0,
            "provider": meta.get("provider", "conversational"),
            "trace": [],
            "elapsed_ms": int((time.time() - started) * 1000),
        },
    }


UNVERIFIED_REPLY = (
    "I can't confirm that's something I can answer from University documents right "
    "now. I answer questions about UGBS administrative procedures, such as "
    "registration, transcripts, fees, results, examinations, deferment, ID cards, "
    "graduation and student support. Try asking about one of those directly."
)

UNVERIFIED_FOLLOW_UP_REPLY = (
    "I couldn't work out what that follow-up refers to just now. Please ask the full "
    "question, for example: “How much does an official transcript cost?”"
)


def _unverified(latest: str, pii: list[str], started: float, follow_up: bool) -> Iterator[dict]:
    """Decline a turn whose scope could not be established.

    Happens only when the triage model is unavailable and the catalogue does not
    recognise the message. No model call is attempted -- if triage just failed,
    the answer call would too -- and nothing is logged: this is the system being
    unable to check, not a student asking something the documents lack, so it
    does not belong in the knowledge-gap register.
    """
    text = UNVERIFIED_FOLLOW_UP_REPLY if follow_up else UNVERIFIED_REPLY
    yield {"type": "delta", "text": text}
    yield {
        "type": "done",
        "response": {
            "question": latest,
            "message": latest,
            "kind": "unverified",
            "conversational": "unverified",
            "answer": text,
            "citations": [],
            "pii_redacted": pii,
            "sections": [
                {
                    "service": None,
                    "answer": text,
                    "citations": [],
                    "refused": True,
                    "conversational": "unverified",
                }
            ],
            "escalated": False,
            "declined": True,
            "escalation_reason": None,
            "office": None,
            "category": None,
            "routing_confidence": 0.0,
            "retrieval_confidence": 0.0,
            "provider": "none (scope not verified)",
            "trace": [],
            "elapsed_ms": int((time.time() - started) * 1000),
        },
    }


def _with_triage(events: Iterator[dict], triage: str) -> Iterator[dict]:
    for event in events:
        if event["type"] == "done":
            event["response"]["triage"] = triage
        yield event


def run_chat(messages: list[dict]) -> Iterator[dict]:
    """Run one turn of the conversation.

    ``messages`` is the conversation so far, oldest first, ending with the
    student's new message. Yields ``step``, ``delta`` and finally ``done``.
    """
    started = time.time()

    if not messages or messages[-1].get("role") != "user":
        raise ValueError("the conversation must end with a student message")

    latest, pii = redact(messages[-1]["content"])
    history = _clean_history(messages[:-1])

    # ---- 1. Triage --------------------------------------------------------
    #
    # An answer needs positive evidence that the question is in scope: either
    # the catalogue recognises it, or the triage model classified it. Earlier
    # this defaulted to "question" whenever triage could not run, so with the
    # model unreachable, "can you recommend a hostel near Legon" matched the
    # welfare guide and accounting homework matched the handbook's course
    # descriptions -- both answered. Without evidence, the turn is declined.
    kind, query = "question", latest
    canned = conversational_reply(latest)
    recognised = router.route(latest)["routing_confidence"] >= RECOGNISED
    # Recorded on the response so the evaluation can tell a measured run from
    # one where the model was unreachable and the fallbacks did the work.
    triage = "not needed"

    if canned:
        # Obvious small talk is spotted without spending a model call on it.
        kind = "chat"
    elif recognised and not history:
        # The catalogue already recognises this as an administrative question,
        # so asking a model "is this a question?" is a wasted round trip -- about
        # 0.85s before the first word. Triage still runs for follow-ups, which
        # need rewriting, and for anything the catalogue does not recognise,
        # which is where off-topic questions turn up.
        kind = "question"
    else:
        analysis = None
        triage = "no model"
        if llm_available():
            try:
                analysis = analyse(history, latest)
            except Exception as exc:  # noqa: BLE001 - handled by the evidence rule below
                analysis = None
                triage = f"failed ({type(exc).__name__})"

        if analysis:
            triage = "model"
            kind = analysis["kind"]
            # On the first turn the student's own words are the query. Letting
            # the model rephrase a question that needs no rephrasing only adds a
            # way for retrieval to drift.
            if history:
                query = analysis["query"]
        elif recognised and not (history and REFERS_BACK.search(latest)):
            # Triage could not run, but the catalogue recognises the message on
            # its own words, which is evidence enough -- unless it leans on the
            # conversation. "how much does it cost?" is recognised (the word
            # "cost" matches the fees service), but without triage to resolve
            # "it", answering would give the general fee schedule instead of the
            # transcript fee being discussed.
            kind = "question"
        else:
            kind = "unverified"

    if kind in ("chat", "off_topic"):
        yield from _with_triage(_converse(kind, history, latest, canned, pii, started), triage)
        return

    if kind == "unverified":
        yield from _with_triage(
            _unverified(latest, pii, started, follow_up=bool(history)), triage
        )
        return

    # ---- 2. Resolve against the documents ---------------------------------
    yield {
        "type": "step",
        "id": "read",
        "label": "Reading your question",
        "detail": f"removed {', '.join(pii)} before searching" if pii else None,
    }

    if query != latest:
        # Visible on purpose: this is the conversation memory at work, and the
        # student can see exactly what was searched for.
        yield {
            "type": "step",
            "id": "understand",
            "label": "Following the conversation",
            "detail": f"searching for: “{query}”",
        }

    material: dict = {}
    for event in resolve(query):
        if event["type"] == "material":
            material = event["material"]
        else:
            yield event

    # ---- 3. Answer --------------------------------------------------------
    user_content = latest
    if query != latest:
        user_content += f"\n\n(Standalone form of this question: {query})"
    if not material.get("general"):
        user_content += (
            "\n\n---\nMATERIAL FOR THIS MESSAGE, the only source of University facts "
            f"you may use:\n\n{format_material(material)}"
        )

    yield {"type": "step", "id": "write", "label": "Writing the answer", "pending": True}

    # A general term nothing defines is explained on its own terms, under a
    # prompt that forbids every University fact. Everything else answers from
    # the material.
    system = SYSTEM_CONCEPT if material.get("general") else SYSTEM_ANSWER

    meta: dict = {}
    text = ""
    for piece in reply_stream(
        [{"role": "system", "content": system}, *history, {"role": "user", "content": user_content}],
        extractive_answer(material),
        meta=meta,
    ):
        text += piece
        yield {"type": "delta", "text": piece}

    text = normalise_citations(text).strip()
    passages = material["passages"]
    citations = used_citations(text, passages) if passages else []

    if material["escalated"]:
        write_detail, tone = "no verified source, so this was recorded for the admin team", "refused"
    elif citations:
        write_detail = f"{len(citations)} source{'' if len(citations) == 1 else 's'} cited"
        tone = "verified"
    else:
        write_detail, tone = "from the verified procedure", "verified"

    yield {
        "type": "step",
        "id": "write",
        "label": "Writing the answer",
        "detail": write_detail,
        "tone": tone,
    }

    sections = [
        {
            "service": procedure["service"],
            "answer": procedure["note"] or "",
            "citations": [],
            "refused": procedure["status"] != "ok",
            "reason": procedure["reason"],
        }
        for procedure in material["procedures"]
    ]

    yield {
        "type": "done",
        "response": {
            "question": query,
            "message": latest,
            "kind": "question",
            "conversational": None,
            "answer": text,
            "citations": citations,
            "pii_redacted": pii,
            "sections": sections,
            "escalated": material["escalated"],
            "declined": material["escalated"],
            # A general explanation rests on no University document, and the
            # interface says so rather than letting it look sourced.
            "general": bool(material.get("general")),
            "escalation_reason": material["escalation_reason"],
            "office": material["office"],
            "category": material["category"],
            "routing_confidence": material["routing_confidence"],
            "retrieval_confidence": material["retrieval_confidence"],
            "provider": meta.get("provider", config.settings.llm_provider),
            "triage": triage,
            "trace": material["trace"],
            "elapsed_ms": int((time.time() - started) * 1000),
        },
    }


def answer(question: str) -> dict:
    """One question with no history; final response only. Used by the evaluation,
    so the numbers measure exactly the path the interface runs."""
    final: dict = {}
    for event in run_chat([{"role": "user", "content": question}]):
        if event["type"] == "done":
            final = event["response"]
    return final
