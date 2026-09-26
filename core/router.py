"""Map an enquiry to the service that owns it, and the office behind that service.

This is a deterministic lookup over data/structured/, not a model call. Scenario 1's
core pain is that students do not know which office handles their issue, so the
answer to "who owns this" has to be right every time -- see CLAUDE.md section 3.

Matching is alias-based and scored, so "I want to take a year off" reaches
deferment without anyone having written that exact phrase into the catalogue.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from core import config

# Words that carry no routing signal. Kept small on purpose: over-trimming loses
# terms like "id" and "fee" that are the whole signal in a short question.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for",
    "from", "get", "have", "how", "i", "if", "in", "is", "it", "me", "my", "need",
    "of", "on", "or", "please", "so", "the", "to", "want", "was", "what", "when",
    "where", "which", "who", "will", "with", "you", "your",
}


def _stem(word: str) -> str:
    """Crudest possible stemmer: drop a plural 's'.

    Students write "fee" and the catalogue says "fees"; without this the whole
    fees service fails to match a question that is plainly about fees. A real
    stemmer would be overkill and would mangle terms like "campus".
    """
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@lru_cache(maxsize=8192)
def _normalise(text: str) -> tuple[str, ...]:
    """Cached: every route re-normalises every alias of every service, and the
    analytics route the whole simulated semester twice. Uncached, the first
    dashboard load took 8.7s. A tuple, so a cached result cannot be mutated."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return tuple(_stem(w) for w in words if w not in STOPWORDS)


@lru_cache(maxsize=1)
def load_catalogue() -> tuple[dict, dict]:
    """Return (services_by_id, offices_by_id). Cached: these files do not change
    while the server is running, and re-reading them per request is waste."""
    services = json.loads(config.SERVICES_FILE.read_text(encoding="utf-8"))["services"]
    offices = json.loads(config.OFFICES_FILE.read_text(encoding="utf-8"))["offices"]
    return (
        {s["id"]: s for s in services},
        {o["id"]: o for o in offices},
    )


def _score(question_words: list[str], service: dict) -> float:
    """How well this service matches the question.

    An alias phrase appearing verbatim is much stronger evidence than a few
    shared words, so a phrase hit is weighted far above token overlap.
    """
    question = " ".join(question_words)
    score = 0.0

    for alias in service.get("aliases", []):
        alias_words = _normalise(alias)
        if not alias_words:
            continue
        alias_phrase = " ".join(alias_words)

        if alias_phrase in question:
            # Longer phrases are more specific: "express transcript" beats "transcript".
            score += 10.0 + 2.0 * len(alias_words)
            continue

        overlap = len(set(alias_words) & set(question_words))
        if overlap:
            score += 2.0 * overlap / len(alias_words)

    name_overlap = len(set(_normalise(service["name"])) & set(question_words))
    score += 1.5 * name_overlap

    return score


def route(question: str, exclude: frozenset[str] = frozenset()) -> dict:
    """Route one enquiry.

    Returns the best service, its office, and a confidence in the routing itself
    (separate from retrieval confidence). ``service`` is None when nothing scores
    above the floor, which is a real answer: it means we do not know who owns this.

    ``exclude`` routes as though those services did not exist. The analytics use
    it to reconstruct the catalogue as it stood before the synthetic procedures
    were added, so the before/after comparison routes the same questions both ways.
    """
    services, offices = load_catalogue()
    words = _normalise(question)

    scored = sorted(
        ((_score(words, s), s) for s in services.values() if s["id"] not in exclude),
        key=lambda pair: pair[0],
        reverse=True,
    )

    best_score, best = scored[0] if scored else (0.0, None)
    runner_up = scored[1][0] if len(scored) > 1 else 0.0

    # Below this the "match" is one or two incidental words.
    if best_score < 3.0:
        return {
            "service": None,
            "office": None,
            "category": None,
            "routing_confidence": 0.0,
            "alternatives": [],
        }

    # Confident when the winner is clearly ahead of the next candidate.
    margin = (best_score - runner_up) / best_score if best_score else 0.0
    routing_confidence = round(min(1.0, 0.5 + margin / 2), 2)

    return {
        "service": best,
        "office": offices.get(best["office"]),
        "category": best["category"],
        "routing_confidence": routing_confidence,
        "alternatives": [
            {"id": s["id"], "name": s["name"], "score": round(score, 1)}
            for score, s in scored[1:4]
            if score >= 3.0
        ],
    }


def office_for_service(service: dict | None) -> dict | None:
    """The office behind a service, with any location that service publishes.

    A location belongs to the procedure it was published for, not to the whole
    office: the University names Room D2 for transcript collection only. Stored
    on the office, it appeared on every Academic Affairs answer -- an ID card or
    deferment question sent the student to the transcript desk.
    """
    if not service:
        return None
    _, offices = load_catalogue()
    office = offices.get(service.get("office"))
    if not office:
        return None
    if service.get("location"):
        return {**office, "location": service["location"]}
    return office


def office_by_term(question: str) -> dict | None:
    """The office or portal a question names, if it names one.

    "What is MIS Web?" is a question the catalogue can answer -- every office
    carries a transcribed description -- but retrieval finds no procedure for
    it, so the confidence gate used to decline. Matching the name here turns
    those into grounded answers instead of refusals.

    Longest term first, so "academic affairs directorate" is not shadowed by
    the "aad" of another office's text.
    """
    lowered = f" {question.lower()} "
    _, offices = load_catalogue()

    terms: list[tuple[str, dict]] = []
    for office in offices.values():
        for term in [office["name"], office["short_name"], *office.get("aliases", [])]:
            if term:
                terms.append((term.lower(), office))
    terms.sort(key=lambda pair: len(pair[0]), reverse=True)

    for term, office in terms:
        if re.search(rf"(?<![\w]){re.escape(term)}(?![\w])", lowered):
            return office
    return None


def office_for_category(category: str) -> dict | None:
    """Fallback when no specific service matched but the topic is known."""
    _, offices = load_catalogue()
    for office in offices.values():
        if category in office.get("handles", []):
            return office
    return None
