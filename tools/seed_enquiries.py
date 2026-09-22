"""Generate a simulated semester of enquiries so the dashboard has something to analyse.

    ..\\AI_Lab\\Scripts\\python.exe tools\\seed_enquiries.py
    ..\\AI_Lab\\Scripts\\python.exe tools\\seed_enquiries.py --count 1500 --reset

HOW THIS DATA IS MADE, because the report has to say so plainly:

* Question text is drawn from templates per enquiry type, with slot fills, so the
  wording varies the way real enquiries do.
* Volume follows a semester shape taken from the published academic calendar:
  registration peaks in the opening weeks, examinations and results peak at the
  end, transcripts and graduation peak after results are released.
* Routing is NOT invented. Every generated question is passed through the real
  `core.router`, so categories, offices and services in the dashboard are the
  same ones the live system would produce.
* Escalation is NOT invented either. A question escalates when the catalogue says
  the service is undocumented, when it asks for a year we do not hold, or when
  the router cannot place it. These are the same three rules the agent applies.

Retrieval is skipped: running the embedding model 1,200 times would take about
twenty minutes on this machine and would not change any field the dashboard
reads. Rows are flagged `simulated = 1` and the dashboard shows the split.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config, store
from core.agent import coverage_problem
from core.redact import redact
from core.router import load_catalogue, route

SEMESTER_WEEKS = 16

# Relative demand per week of the semester, per enquiry theme. Shapes come from
# the published calendar: registration closes a few weeks in, examinations sit at
# the end, transcripts and graduation follow the release of results.
SHAPES: dict[str, list[float]] = {
    "registration": [10, 9, 7, 3, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2],
    "fees":         [8, 7, 6, 4, 2, 2, 2, 2, 3, 2, 2, 2, 2, 2, 3, 3],
    "courses":      [6, 6, 5, 3, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 1],
    "id_card":      [5, 4, 3, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    "exams":        [1, 1, 1, 1, 2, 2, 2, 3, 4, 5, 6, 8, 9, 9, 6, 3],
    "results":      [1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 3, 4, 6, 8, 9, 9],
    "transcripts":  [2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 4, 5, 7, 9, 10],
    "graduation":   [1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 3, 4, 5, 7, 8, 9],
    "deferment":    [3, 3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
    "welfare":      [3, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
}

TEMPLATES: dict[str, list[str]] = {
    "registration": [
        "How do I register for my courses this semester?",
        "I am a fresh student, how do I do my online registration?",
        "What is the deadline for course registration?",
        "Can I still register if I have paid only part of my fees?",
        "I cannot access MIS Web to register, what should I do?",
        "How much of my fees must I pay before I can register?",
        "Where do I print my proof of registration?",
        "I am a level {level} student, how do I register for the semester?",
    ],
    "fees": [
        "How much are the fees for my programme?",
        "What are the fees for level {level} this year?",
        "What will the {future_year} MBA fee be?",
        "How much will fees be in {future_year}?",
        "Where do I find the schedule of fees for the Business School?",
        "Can I pay my fees in instalments?",
        "How do I get a refund for fees I overpaid?",
    ],
    "courses": [
        "What courses are available in the {dept} department?",
        "How many credits do I need to graduate?",
        "Can I change my elective after registration?",
        "What are the prerequisites for this course?",
        "Who is my academic advisor?",
    ],
    "id_card": [
        "How do I get my student ID card?",
        "I lost my student ID card, how do I replace it?",
        "How much does a replacement student ID cost?",
        "Where do I collect my student identification card?",
    ],
    "exams": [
        "When is the examination timetable released?",
        "Where can I find my exam timetable?",
        "What happens if I miss an examination because I was ill?",
        "What is the pass mark for a course?",
        "Can I defer an examination?",
        "What are the rules about examination malpractice?",
    ],
    "results": [
        "My result for one course is missing, what do I do?",
        "How do I request a grade change?",
        "Where do I check my results?",
        "My grade looks wrong, how do I get it corrected?",
        "How do I get a statement of results?",
    ],
    "transcripts": [
        "How do I request an official transcript?",
        "How much does a transcript cost?",
        "How long does it take to get my transcript?",
        "I need my transcript urgently, can I get it the same day?",
        "I graduated in {old_year}, how do I request my transcript?",
        "Can someone else collect my transcript for me?",
        "I am a graduate student, where do I request my transcript?",
        "Can my transcript be sent directly to a university abroad?",
    ],
    "graduation": [
        "When is the next congregation?",
        "How do I apply to graduate?",
        "Where do I collect my certificate?",
        "What are the requirements for graduating?",
    ],
    "deferment": [
        "How do I defer a semester?",
        "I want to take a year off, what is the procedure?",
        "How do I withdraw from the university?",
        "Can I interrupt my studies for medical reasons?",
        "What happens to my fees if I defer?",
    ],
    "welfare": [
        "Who do I talk to about accommodation problems?",
        "Is there financial support for students in difficulty?",
        "Where is the counselling service?",
        "I am having personal difficulties affecting my studies, who can help?",
    ],
}

SLOTS = {
    "level": ["100", "200", "300", "400"],
    "future_year": ["2027/2028", "2028/2029", "2029/2030", "2030"],
    "old_year": ["1988", "1991", "1994", "1995"],
    "dept": [
        "Accounting", "Finance", "Marketing and Entrepreneurship",
        "Operations and Management Information Systems", "Public Administration",
        "Organisation and Human Resource Management", "Health Services Management",
    ],
}


def fill(template: str, rng: random.Random) -> str:
    text = template
    for slot, options in SLOTS.items():
        token = "{" + slot + "}"
        if token in text:
            text = text.replace(token, rng.choice(options))
    return text


def decide(question: str) -> dict:
    """Apply the same three escalation rules the live agent applies."""
    routed = route(question)
    service = routed.get("service")

    reason = None
    if not service:
        reason = "router could not place the enquiry"
    elif not service.get("documented"):
        reason = "no published procedure"
    else:
        gap = coverage_problem(question, service)
        if gap:
            reason = "outside the coverage of the indexed data"

    return {
        "question": question,
        "category": routed.get("category"),
        "routing_confidence": routed["routing_confidence"],
        "retrieval_confidence": 0.0 if reason else round(random.uniform(0.45, 0.85), 4),
        "office": routed.get("office"),
        "sections": [{"service": service, "citations": []}] if service else [],
        "escalated": bool(reason),
        "escalation_reason": reason,
        "provider": "simulated",
        "elapsed_ms": random.randint(300, 1400),
        "pii_redacted": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1200)
    parser.add_argument("--reset", action="store_true", help="delete existing simulated rows first")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    random.seed(args.seed)

    store.init()
    if args.reset:
        with store.connect() as connection:
            removed = connection.execute("DELETE FROM enquiries WHERE simulated = 1").rowcount
        print(f"Removed {removed:,} existing simulated rows")

    # Semester ends the day before today, so the dashboard always looks current.
    end = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    start = end - timedelta(weeks=SEMESTER_WEEKS)

    themes = list(SHAPES)
    weekly_weight = [sum(SHAPES[t][w] for t in themes) for w in range(SEMESTER_WEEKS)]

    written = 0
    escalated = 0

    for _ in range(args.count):
        week = rng.choices(range(SEMESTER_WEEKS), weights=weekly_weight)[0]
        theme = rng.choices(themes, weights=[SHAPES[t][week] for t in themes])[0]

        question = fill(rng.choice(TEMPLATES[theme]), rng)

        # Enquiries land during the working week, weighted towards mid-morning.
        day = rng.choices(range(7), weights=[18, 18, 17, 16, 15, 8, 8])[0]
        hour = rng.choices(range(8, 18), weights=[4, 9, 12, 12, 9, 6, 9, 10, 7, 4])[0]
        ts = (
            start
            + timedelta(weeks=week, days=day, hours=hour - 12, minutes=rng.randint(0, 59))
        ).isoformat(timespec="seconds")

        response = decide(question)
        response["question"], _ = redact(response["question"])

        store.log_enquiry(response, simulated=True, ts=ts)
        written += 1
        escalated += 1 if response["escalated"] else 0

    counts = store.count()
    print(f"\nSeeded {written:,} simulated enquiries across {SEMESTER_WEEKS} weeks")
    print(f"  escalated (could not answer): {escalated:,} ({escalated/written:.0%})")
    print(f"  database now holds {counts['total']:,} rows "
          f"({counts['simulated']:,} simulated, {counts['live']:,} live)")
    print(f"\n{config.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
