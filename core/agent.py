"""Resolve one question against the University documents. No language model.

`resolve()` does everything that has to be deterministic: route the question to
the office that owns it, plan which procedure variants apply, search the corpus,
and run the checks that protect a student -- coverage of time-varying data,
undocumented services, prediction requests, the confidence gate. It hands back
MATERIAL: the verified procedures, the passages, and anything it declined to
cover and why. `core.chat` turns that into a conversational reply.

Keeping this free of the model is the point. Whether a question can be answered
is decided here, reproducibly, before any text is generated; the model only
decides how to say it.

Why plan variants at all? Because real enquiries carry qualifiers that change
which procedure applies. "I'm a graduate student, I need my transcript urgently,
and I graduated in 1994" is one question with three conditions, each routing to a
different published variant. A single retrieval returns the generic transcript
passage and quietly gives a graduate a procedure that does not apply to them.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from core import config, retrieve as retrieval, router

# Qualifiers that select a procedure variant within a category. The category key
# matters: "MBA" in a question about fees says something about the student's
# programme, not that they want a graduate transcript. Without this scoping the
# agent bolts a transcript procedure onto a fee enquiry.
QUALIFIERS: dict[str, list[tuple[tuple[str, ...], str]]] = {
    "transcripts": [
        (("graduate", "postgraduate", "masters", "master's", "mphil", "phd", "mba"), "transcript_graduate"),
        (("urgent", "urgently", "express", "same day", "same-day", "quickly", "asap", "rush"), "transcript_express"),
        (("1990", "1991", "1992", "1993", "1994", "1995", "before 1996", "pre-1996"), "transcript_pre_1996"),
        (("on behalf", "for my friend", "proxy", "someone else"), "transcript_proxy_collection"),
    ],
}

# Any year the question pins down, e.g. "2027/2028", "2027/28" or a bare "2027".
YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")

# Questions asking the system to forecast or judge one student's outcome. No
# retrieval threshold catches these: "will I pass my exams this semester" routes
# confidently to examinations and retrieves real examination text, then answers a
# question the documents never address. The system holds published procedure, not
# a view on anybody's future, and saying so is the honest response.
PREDICTION_PATTERNS = re.compile(
    r"\b(will i (pass|fail|graduate|get|make)|am i going to|are my chances|"
    r"what are my chances|do you think i|predict my|how likely am i|"
    r"will i be able to)\b",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------
# Obvious conversation
#
# With a model available these are only used to *detect* small talk cheaply --
# the reply itself is written by the model. With no model (LLM_PROVIDER=
# extractive, or a failed call) the canned replies below are what the student
# sees, so they have to stand on their own.
# --------------------------------------------------------------------------

# "What is MIS Web?", "what does deferment mean?" -- a question about what
# something IS, rather than what to do about it.
DEFINITION_PATTERNS = re.compile(
    r"\b(?:what(?:'s| is| are)\b|what do(?:es)? .{1,40}\bmean\b|what do you mean by\b|"
    r"define\b|meaning of\b|explain what\b)",
    re.IGNORECASE,
)

# Words that make a question ask for a University fact rather than a meaning.
# "What is the transcript fee" must stay on the strict path: an explanation of
# what a fee is would be useless, and a figure from the model would be a
# fabrication. Only questions with none of these may be answered generally.
FACT_SEEKING = re.compile(
    r"\b(fee|fees|cost|costs|price|charge|charges|how much|amount|deadline|"
    r"deadlines|date|dates|when|where|room|hours|pass mark|classification|"
    r"require|required|requirement|requirements|need|needed|document|documents|"
    r"form|forms|step|steps|procedure|process|apply|applying|register|"
    r"registration|submit|collect|eligib)\w*",
    re.IGNORECASE,
)

GREETING = re.compile(
    r"^\s*(hi|hiya|hello|hey|yo|good\s+(morning|afternoon|evening|day)|greetings|"
    r"how\s+are\s+you|please)\b[\s,.!-]*",
    re.IGNORECASE,
)
THANKS = re.compile(
    r"^\s*(thanks|thank\s+you|thx|ta|much\s+appreciated|appreciate\s+it|"
    r"ok(ay)?\s+thanks|great|perfect|nice|cool)\b[\s,.!]*$",
    re.IGNORECASE,
)
FAREWELL = re.compile(
    r"^\s*(bye|goodbye|good\s*bye|see\s+you|later|cheers)\b[\s,.!]*$", re.IGNORECASE
)
CAPABILITY = re.compile(
    r"\b(what\s+can\s+you\s+do|what\s+do\s+you\s+do|who\s+are\s+you|what\s+are\s+you|"
    r"what\s+is\s+this|how\s+do\s+you\s+work|how\s+can\s+you\s+help|what\s+can\s+you\s+help|"
    r"help\s+me|^help$|your\s+purpose|are\s+you\s+(a\s+)?(bot|ai|robot|human))\b",
    re.IGNORECASE,
)

GREETING_REPLY = (
    "Hello. I answer questions about University of Ghana Business School "
    "administrative procedures, such as registration, transcripts, fees, results, "
    "examinations, deferment, student ID cards, graduation and student support.\n\n"
    "Ask in your own words and I will tell you which office handles it, what to "
    "bring, and which document says so. If nothing published covers your question, "
    "I will say so rather than guess.\n\n"
    "For example:\n"
    "- How do I request an official transcript?\n"
    "- What do I need to register this semester?\n"
    "- I want to defer a semester, what is the procedure?"
)

CAPABILITY_REPLY = (
    "I am an enquiry assistant for UGBS students, built as a student project. I am "
    "not an official University service.\n\n"
    "I search published University of Ghana documents: the General Regulations for "
    "Junior Members, the College of Humanities handbook, Academic Affairs "
    "Directorate pages, the fee schedule and the academic calendar. Every answer "
    "shows the source it came from.\n\n"
    "What I can do:\n"
    "- Tell you which office owns your issue, and where to go\n"
    "- Give the steps, the documents to bring, and published fees\n"
    "- Say plainly when nothing published answers your question\n\n"
    "What I will not do: invent a fee, a deadline or an office, or predict how you "
    "will do academically. Confirm anything with a deadline or a payment with the "
    "office itself before acting on it."
)

THANKS_REPLY = "You're welcome. Ask me anything else about UGBS procedures."
FAREWELL_REPLY = "Goodbye. Come back whenever you need an administrative procedure."
OFF_TOPIC_REPLY = (
    "That is outside what I can help with. I answer questions about University of "
    "Ghana Business School administrative procedures, such as registration, "
    "transcripts, fees, results, examinations, deferment, ID cards, graduation and "
    "student support."
)


def conversational_reply(question: str) -> tuple[str, str] | None:
    """Return ``(kind, canned reply)`` when this turn is plainly conversation.

    A greeting attached to a real question is not small talk: "hi, how do I get a
    transcript?" must be answered as the transcript enquiry, so the greeting is
    stripped and the remainder decides.
    """
    text = question.strip()
    if not text:
        return None

    remainder = GREETING.sub("", text, count=1).strip()
    greeted = remainder != text

    # A greeting carrying a real question is an enquiry.
    if greeted and len(remainder.split()) >= 3:
        return None

    if CAPABILITY.search(text):
        return "capability", CAPABILITY_REPLY
    if THANKS.match(text):
        return "thanks", THANKS_REPLY
    if FAREWELL.match(text):
        return "farewell", FAREWELL_REPLY
    if greeted and len(remainder.split()) < 3:
        return "greeting", GREETING_REPLY

    return None


# Below this, an enquiry the catalogue could not place is treated as out of scope.
# Measured against the gold set: genuine enquiries retrieve at 0.46-0.68 while
# off-topic ones land at 0.33-0.41, so an unplaced enquiry needs clear evidence
# before it is answered from the corpus alone.
UNROUTED_FLOOR = 0.60

# How many passages go to the model. A procedure with catalogue steps needs only
# supporting detail; a corpus-only answer rests entirely on its passages.
#
# Kept tight on purpose. Passages are most of each prompt, and the model host's
# free tier allows 8,000 tokens a minute: at six passages that is two or three
# answers before it starts throttling.
PASSAGES_WITH_STEPS = 2
PASSAGES_CORPUS_ONLY = 4
PASSAGES_TOTAL = 4


# --------------------------------------------------------------------------
# Tools
# --------------------------------------------------------------------------

def tool_lookup_office(question: str) -> dict:
    """Which service and office owns this enquiry. Deterministic catalogue lookup."""
    return router.route(question)


def tool_search_policy(question: str) -> dict:
    """Retrieve supporting passages and apply the confidence gate."""
    return retrieval.retrieve(question)


def tool_log_gap(question: str, reason: str) -> dict:
    """Record that the system could not answer. The dashboard's knowledge-gap
    register is built from these, so a refusal produces an administrative
    output rather than just a dead end."""
    return {"logged": True, "reason": reason, "question": question}


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------

def coverage_problem(question: str, service: dict | None) -> str:
    """Refuse when the question names an edition of time-varying data we do not hold.

    Fees, calendars and timetables change every academic year. Our fee schedule
    is for one specific year, so answering "what will the 2027/2028 fee be" with
    the 2025/2026 schedule would be wrong in the most damaging way available --
    confidently, specifically, and about money.

    Only applies to services that declare `time_varying`, so a question that
    happens to mention 1994 while asking about a transcript is unaffected.
    """
    if not service or not service.get("time_varying"):
        return ""

    asked = {int(m.group(0)) for m in YEAR_PATTERN.finditer(question)}
    if not asked:
        return ""

    covered = {
        int(year)
        for year in re.findall(r"\b(?:19|20)\d{2}\b", service.get("data_year", ""))
    }

    if covered and not (asked & covered):
        years = "/".join(str(y) for y in sorted(asked))
        return (
            f"The question asks about {years}, but the only {service['category'].replace('_', ' ')} "
            f"data indexed is for {service['data_year']}. Figures for other years are not "
            "published in the sources we hold, and estimating them would be inventing a number."
        )

    return ""


def _mentions(phrase: str, text: str) -> bool:
    """Whole-word phrase match.

    Plain substring matching sent every pre-1996 enquiry to the wrong office:
    "I graduated in 1994" contains "graduate", which fired the postgraduate
    qualifier and put the School of Graduate Studies on the answer. "graduate
    student" must match; "graduated" must not.
    """
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


def plan(question: str, primary: dict) -> list[dict]:
    """Decide which service variants this question actually touches."""
    services, _ = router.load_catalogue()
    lowered = question.lower()

    steps: list[dict] = []
    if primary.get("service"):
        steps.append({"service_id": primary["service"]["id"], "reason": "best route match"})

    seen = {s["service_id"] for s in steps}
    category = primary.get("category")
    for phrases, service_id in QUALIFIERS.get(category, []):
        if service_id in seen or service_id not in services:
            continue
        hit = next((p for p in phrases if _mentions(p, lowered)), None)
        if hit:
            steps.append({"service_id": service_id, "reason": f"qualifier {hit!r}"})
            seen.add(service_id)

    # A specific variant can supersede the generic one. A pre-1996 graduate must
    # not be handed the standard "submit on the STS portal" procedure alongside
    # the correct one -- the portal does not cover them, and offering both is how
    # a student ends up at the wrong desk.
    superseded: set[str] = set()
    for step in steps:
        service = services.get(step["service_id"])
        if service:
            superseded.update(service.get("supersedes", []))

    if superseded:
        steps = [s for s in steps if s["service_id"] not in superseded]

    # A question with no route still gets one retrieval attempt: the corpus may
    # cover something the catalogue does not.
    if not steps:
        steps.append({"service_id": None, "reason": "no catalogue match; searching corpus"})

    return steps


# --------------------------------------------------------------------------
# Resolve
# --------------------------------------------------------------------------

def _select_passages(procedures: list[dict]) -> list[dict]:
    """The passages the model sees, numbered globally so citations are unambiguous.

    Deduplicated across procedures: every transcript variant is published on the
    same page, so without this the model is handed the same passage three times.
    """
    chosen: list[dict] = []
    seen: set[str] = set()

    for procedure in procedures:
        if procedure["status"] != "ok":
            continue
        service = procedure["service"]
        limit = (
            PASSAGES_WITH_STEPS
            if service and service.get("steps")
            else PASSAGES_CORPUS_ONLY
        )
        for hit in procedure["hits"][:limit]:
            if hit["chunk_id"] in seen:
                continue
            seen.add(hit["chunk_id"])
            chosen.append(hit)

    return chosen[:PASSAGES_TOTAL]


def resolve(query: str) -> Iterator[dict]:
    """Find what the University documents say about one standalone question.

    Yields ``{"type": "step", ...}`` events as it works -- the real control flow,
    streamed to the interface -- and finishes with one
    ``{"type": "material", "material": {...}}``.
    """
    trace: list[dict] = []
    services, _ = router.load_catalogue()

    # Refuse a prediction before spending any retrieval on it.
    if PREDICTION_PATTERNS.search(query):
        reason = "asks the system to predict an individual outcome"
        tool_log_gap(query, reason)
        yield {
            "type": "step",
            "id": "scope",
            "label": "Checking the question is one I can answer",
            "detail": reason,
            "tone": "refused",
        }
        yield {
            "type": "material",
            "material": {
                "query": query,
                "prediction": True,
                "procedures": [],
                "passages": [],
                "escalated": True,
                "escalation_reason": reason,
                "office": router.office_for_category("course_advising"),
                "category": "course_advising",
                "routing_confidence": 0.0,
                "retrieval_confidence": 0.0,
                "trace": [{"tool": "verify_scope", "result": reason}],
            },
        }
        return

    primary = tool_lookup_office(query)
    trace.append(
        {
            "tool": "lookup_office",
            "result": primary["service"]["id"] if primary["service"] else None,
            "routing_confidence": primary["routing_confidence"],
        }
    )
    yield {
        "type": "step",
        "id": "route",
        "label": "Identifying the responsible office",
        "detail": (primary["office"] or {}).get("name") or "no office matched",
        "confidence": primary["routing_confidence"],
    }

    steps = plan(query, primary)
    trace.append({"tool": "plan", "result": [s["service_id"] for s in steps], "detail": steps})
    planned_names = [
        (services.get(s["service_id"]) or {}).get("name", "open search") for s in steps
    ]
    yield {
        "type": "step",
        "id": "plan",
        "label": f"Planning {len(steps)} procedures" if len(steps) > 1 else "Planning the answer",
        "detail": ", ".join(planned_names),
    }

    procedures: list[dict] = []
    best_confidence = 0.0
    # Why the last candidate was turned away, when nothing recorded a
    # procedure-level reason. Logged as the escalation reason, so it has to name
    # the bar that was actually applied.
    turned_away = ""

    for step in steps:
        service = services.get(step["service_id"]) if step["service_id"] else None

        # Search on the service name when there is one: it is a cleaner query
        # than the student's sentence, which carries conditions that muddy
        # retrieval.
        search_query = f"{service['name']}. {query}" if service else query

        # The service name is the label rather than folded into a sentence: the
        # names start with a verb ("Request a graduate transcript"), so
        # "searching for request a graduate transcript" reads like broken English.
        search_label = service["name"] if service else "Open search"
        step_id = f"search:{step['service_id']}"

        yield {
            "type": "step",
            "id": step_id,
            "label": search_label,
            "detail": "searching published documents",
            "pending": True,
        }

        found = tool_search_policy(search_query)
        best_confidence = max(best_confidence, found["confidence"])
        trace.append(
            {
                "tool": "search_policy",
                "for": step["service_id"],
                "confidence": found["confidence"],
                "passed_gate": found["passed_gate"],
                "hits": len(found["hits"]),
            }
        )
        yield {
            "type": "step",
            "id": step_id,
            "label": search_label,
            "detail": f"{len(found['hits'])} passages, best match {found['confidence']:.2f}",
            "confidence": found["confidence"],
        }

        # Check one: does our data even cover the year asked about?
        gap = coverage_problem(query, service)
        if gap:
            trace.append({"tool": "verify_coverage", "for": step["service_id"], "result": gap})
            yield {
                "type": "step",
                "id": f"verify:{step['service_id']}",
                "label": "Checking the years we hold",
                "detail": "the year asked about is not in the indexed data",
                "tone": "refused",
            }
            procedures.append(
                {
                    "service": service,
                    "status": "not_available",
                    "reason": "outside the coverage of the indexed data",
                    "note": gap,
                    "hits": [],
                }
            )
            continue

        documented = bool(service and service.get("documented"))

        # Check two: a service we know is undocumented must not be dressed up
        # with whatever the corpus happened to return.
        if service and not documented:
            yield {
                "type": "step",
                "id": f"verify:{step['service_id']}",
                "label": "Checking for a published procedure",
                "detail": "none published for this service",
                "tone": "refused",
            }
            procedures.append(
                {
                    "service": service,
                    "status": "not_available",
                    "reason": "no published procedure",
                    "note": service.get("not_documented_note")
                    or "No published procedure was found for this service.",
                    "hits": [],
                }
            )
            continue

        if not found["passed_gate"]:
            # A documented service carries its own verified source: the catalogue
            # entry, hand-transcribed from a published document and citing it.
            # Retrieval only adds supporting detail there, so a weak retrieval
            # score should not suppress a procedure the router placed with high
            # confidence. Without this, "Where do I find the schedule of fees?"
            # was refused on a retrieval score of 0.4198 against a 0.42 threshold
            # -- while the correct steps sat in the catalogue, unused.
            #
            # This does not loosen the guardrail. Everything that protects a
            # student has already run: the coverage check, the undocumented-service
            # refusal and the prediction refusal.
            if documented and primary["routing_confidence"] >= 0.7:
                trace.append(
                    {
                        "tool": "verify_scope",
                        "for": step["service_id"],
                        "result": f"retrieval weak ({found['confidence']:.2f}) but the "
                        "catalogue holds a verified procedure; answering from it",
                    }
                )
                yield {
                    "type": "step",
                    "id": f"verify:{step['service_id']}",
                    "label": "Checking the published procedure",
                    "detail": "answering from the verified catalogue entry",
                    "tone": "verified",
                }
            else:
                turned_away = (
                    f"nothing relevant found (best match {found['confidence']:.2f}, "
                    f"below the {config.settings.confidence_threshold} threshold)"
                )
                continue

        # An enquiry the catalogue could not place needs strong retrieval before
        # the corpus alone is allowed to answer it. Without this, any question at
        # all matches *something* well enough to clear the base threshold.
        if service is None and found["confidence"] < UNROUTED_FLOOR:
            turned_away = (
                f"nothing relevant found (best match {found['confidence']:.2f}, below "
                f"the {UNROUTED_FLOOR} bar for questions the catalogue does not recognise)"
            )
            trace.append({"tool": "verify_scope", "result": turned_away})
            continue

        procedures.append(
            {
                "service": service,
                "status": "ok",
                "reason": None,
                "note": None,
                "hits": found["hits"],
            }
        )

    answered = [p for p in procedures if p["status"] == "ok"]
    escalated = not answered
    reason = None

    # Two kinds of question the gate used to decline for no good reason: one the
    # catalogue can define, and one that asks what a general term means.
    asks_meaning = bool(DEFINITION_PATTERNS.search(query))
    named_office = router.office_by_term(query) if asks_meaning else None
    # A question about a University fact never takes either path, however it is
    # phrased: "what is the transcript fee" needs the figure, not an explanation.
    general = asks_meaning and not named_office and not FACT_SEEKING.search(query)

    if escalated and named_office:
        escalated = False
        trace.append({"tool": "define_term", "result": named_office["id"]})
        yield {
            "type": "step",
            "id": "define",
            "label": "Looking up the term",
            "detail": f"{named_office['name']}, from the verified catalogue",
            "tone": "verified",
        }
    elif escalated and general:
        escalated = False
        trace.append({"tool": "explain_generally", "result": "no University facts"})
        yield {
            "type": "step",
            "id": "define",
            "label": "Explaining the term",
            "detail": "in general terms; no University document defines it",
        }

    if escalated:
        # Keep the specific reason, so the knowledge-gap register distinguishes
        # "we hold the wrong year" from "nobody published this" from "retrieval
        # found nothing". Those call for three different administrative actions.
        recorded = [p["reason"] for p in procedures if p.get("reason")]
        reason = recorded[0] if recorded else turned_away or (
            f"nothing relevant found (best match {best_confidence:.2f})"
        )
        tool_log_gap(query, reason)
        trace.append({"tool": "log_gap", "result": reason})

    # The office shown must belong to the procedure actually given. A graduate
    # asking for a transcript is answered by the School of Graduate Studies, and
    # naming the AAD because that is where the generic route pointed would send
    # them to the wrong desk -- the exact failure this project exists to prevent.
    leading = next((p["service"] for p in answered if p["service"]), None)
    office = (
        router.office_for_service(leading)
        if leading
        else named_office
        or primary.get("office")
        or (router.office_for_category(primary["category"]) if primary.get("category") else None)
    )

    yield {
        "type": "material",
        "material": {
            "query": query,
            "prediction": False,
            "procedures": procedures,
            "passages": _select_passages(procedures),
            # Attached whenever the student asked what a named office is, even
            # if a procedure also matched: "what is the School of Graduate
            # Studies?" found the graduate transcript route and answered that
            # it held no description of the School itself.
            "defines": named_office,
            "general": general and not answered,
            "escalated": escalated,
            "escalation_reason": reason,
            "office": office,
            "category": primary.get("category"),
            "routing_confidence": primary["routing_confidence"],
            "retrieval_confidence": round(best_confidence, 4),
            "trace": trace,
        },
    }


def answer(question: str) -> dict:
    """One question, no history, final response only.

    Kept here because the evaluation and older callers import it from this
    module. It runs the full conversational path in `core.chat`, so what gets
    measured is exactly what ships.
    """
    from core.chat import answer as chat_answer

    return chat_answer(question)
