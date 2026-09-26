"""Turn the enquiry log into decisions an administrator can actually act on.

Every function here answers a specific question a Business School officer would
ask. That constraint is the point: an analytic that produces a chart but not a
decision is decoration, and the brief says so explicitly.

    demand_by_category      -> which topics need clearer published guidance
    weekly_demand           -> when to open extra service windows
    busiest_hours           -> when to put a second person on the desk
    most_asked              -> what belongs on a FAQ page or noticeboard
    repeat_rate             -> would publishing a few answers remove the traffic
    service_health          -> is the assistant fast enough, and holding up
    knowledge_gaps          -> which documents to publish next
    gap_loop                -> did publishing them actually work
    deflection              -> is the assistant reducing front-desk load
    office_load             -> where to allocate staff
    source_freshness        -> which documents to prioritise for review
    forecast                -> staff ahead of the next peak
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from core import config, router, store


def _rows() -> list[dict]:
    return store.fetch_all(include_simulated=True)


def _week(ts: str) -> str:
    """ISO year-week, so weeks sort correctly across a year boundary."""
    date = datetime.fromisoformat(ts)
    year, week, _ = date.isocalendar()
    return f"{year}-W{week:02d}"


def demand_by_category(rows: list[dict]) -> list[dict]:
    """Which topics students ask about most.

    Decision: where clearer published guidance would remove the most enquiries.
    """
    counts = Counter(r["category"] or "unrouted" for r in rows)
    escalated = Counter(
        (r["category"] or "unrouted") for r in rows if r["escalated"]
    )
    total = sum(counts.values()) or 1

    return [
        {
            "category": category,
            "enquiries": count,
            "share": round(count / total, 4),
            "escalated": escalated.get(category, 0),
            "escalation_rate": round(escalated.get(category, 0) / count, 4),
        }
        for category, count in counts.most_common()
    ]


def weekly_demand(rows: list[dict]) -> dict:
    """Volume per week, overall and by category.

    Decision: when to open extra service windows or send pre-emptive notices.
    Registration enquiries cluster at the start of a semester; knowing that a
    fortnight ahead is the difference between staffing for it and reacting to it.
    """
    by_week: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        by_week[_week(row["ts"])][row["category"] or "unrouted"] += 1

    weeks = sorted(by_week)
    categories = sorted({c for week in by_week.values() for c in week})

    return {
        "weeks": weeks,
        "categories": categories,
        "series": {
            category: [by_week[week].get(category, 0) for week in weeks]
            for category in categories
        },
        "totals": [sum(by_week[week].values()) for week in weeks],
    }


# Each reason a question went unanswered calls for a different administrative
# action, so the register is grouped by reason first and by wording second.
# Clustering wording alone put "we don't hold that year's fees" and "nobody has
# published this procedure" side by side, and then split the fee questions six
# ways by year -- six rows all saying "publish next year's fee schedule".
REASON_GROUPS: list[tuple[str, str, str, str]] = [
    # (key, reason prefix, label, action)
    (
        "unpublished",
        "no published procedure",
        "Procedures the University has not published",
        "Write and publish these procedures.",
    ),
    (
        "no_match",
        "",
        "Questions nothing in the documents answers",
        "Review them: publish guidance where they are University matters, or "
        "confirm they are out of scope.",
    ),
    (
        "not_held",
        "outside the coverage",
        "Figures for a year we don't hold",
        "Index each new fee schedule and calendar as soon as it is published.",
    ),
    (
        "prediction",
        "asks the system to predict",
        "Requests to predict a student's own result",
        "There is nothing to publish, because no document can answer these. Point students to "
        "academic advising.",
    ),
]


def _reason_group(reason: str | None) -> tuple[str, str, str]:
    reason = (reason or "").lower()
    for key, prefix, label, action in REASON_GROUPS:
        if prefix and reason.startswith(prefix):
            return key, label, action
    # Anything else -- nothing relevant found, the router could not place it --
    # means the documents had nothing to offer.
    _, _, label, action = REASON_GROUPS[1]
    return "no_match", label, action


def _normalise_question(question: str) -> str:
    # Years and numbers are the variable part of otherwise identical questions:
    # "fees in 2027" and "fees in 2030" are one gap, not two.
    return " ".join(re.sub(r"\d+", " ", question.lower()).split())


def _distinct_terms(ranked: list[str], limit: int = 5) -> list[str]:
    """Unigrams and the bigrams containing them both rank highly, so raw top
    terms read "service, counselling service, counselling". Keep only terms not
    already covered by one kept."""
    kept: list[str] = []
    for term in ranked:
        if any(term in k or k in term for k in kept):
            continue
        kept.append(term)
        if len(kept) == limit:
            break
    return kept


def _themes_by_service(group: list[dict]) -> list[dict]:
    """When every question in a group was placed on a service, the service IS the
    theme -- and the action: "publish the ID card procedure". Clustering these by
    wording put ID cards, graduation and deferment into one theme of 248."""
    services, _ = router.load_catalogue()
    by_service: dict[str, list[dict]] = defaultdict(list)
    for row in group:
        by_service[row["service_id"]].append(row)

    themes = []
    for service_id, members in by_service.items():
        examples, seen = [], set()
        for row in members:
            key = _normalise_question(row["question"])
            if key in seen:
                continue
            seen.add(key)
            examples.append(row["question"])
            if len(examples) == 3:
                break
        themes.append(
            {
                "theme": services.get(service_id, {}).get("name", service_id),
                "service_id": service_id,
                "volume": len(members),
                "examples": examples,
            }
        )
    return sorted(themes, key=lambda t: t["volume"], reverse=True)


def _themes(group: list[dict]) -> list[dict]:
    """Cluster one reason group by wording.

    The number of themes follows the number of genuinely different questions,
    not a fixed k: a group that is one question asked twenty ways is one theme.
    """
    if all(row.get("service_id") for row in group):
        return _themes_by_service(group)

    normalised = [_normalise_question(r["question"]) for r in group]
    distinct = len(set(normalised))

    # A handful of different questions is clearer listed than summarised. Term
    # extraction on two questions produced labels like "pay fees, need class,
    # gpa need"; the questions themselves say it better.
    if distinct < 4:
        by_question: dict[str, list[dict]] = defaultdict(list)
        for row, key in zip(group, normalised):
            by_question[key].append(row)
        return sorted(
            (
                {
                    "theme": members[0]["question"],
                    "volume": len(members),
                    "examples": [members[0]["question"]],
                }
                for members in by_question.values()
            ),
            key=lambda t: t["volume"],
            reverse=True,
        )

    k = 1 if distinct < 6 else min(5, distinct // 4)

    # Imported only when there is wording to cluster. scikit-learn costs about
    # 120 MB of memory just to import, which is a quarter of the free hosting
    # tier -- and most registers never reach this line.
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    try:
        vectoriser = TfidfVectorizer(
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            # With several themes, drop wording shared by most questions ("how
            # do i"); with one theme, that shared wording *is* the theme.
            max_df=0.8 if k > 1 else 1.0,
            sublinear_tf=True,
        )
        matrix = vectoriser.fit_transform(normalised)
    except ValueError:
        # Nothing but stop words ("who are you") -- no wording to cluster on.
        return [
            {
                "theme": "no distinctive wording",
                "volume": len(group),
                "examples": [r["question"] for r in group[:3]],
            }
        ]

    terms = vectoriser.get_feature_names_out()

    if k == 1:
        labels = [0] * len(group)
        centres = [matrix.mean(axis=0).A1]
    else:
        model = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = list(model.fit_predict(matrix))
        centres = list(model.cluster_centers_)

    themes: list[dict] = []
    for index, centre in enumerate(centres):
        members = [i for i, label in enumerate(labels) if label == index]
        if not members:
            continue

        # Show the questions nearest the centre, and never the same question
        # twice with different years -- an unrepresentative or repetitive
        # example makes an administrator distrust the whole row.
        by_closeness = sorted(members, key=lambda i: -(matrix[i].toarray()[0] @ centre))
        examples, seen = [], set()
        for i in by_closeness:
            if normalised[i] in seen:
                continue
            seen.add(normalised[i])
            examples.append(group[i]["question"])
            if len(examples) == 3:
                break

        ranked = [terms[i] for i in centre.argsort()[::-1][:12]]
        themes.append(
            {
                "theme": ", ".join(_distinct_terms(ranked)[:3]),
                "volume": len(members),
                "examples": examples,
            }
        )

    return sorted(themes, key=lambda t: t["volume"], reverse=True)


def knowledge_gaps(rows: list[dict]) -> list[dict]:
    """Group the questions the system could not answer into actions.

    Decision: which documents the office should publish next -- and which
    unanswered questions need no document at all. This is the analysis the unit
    cannot produce today, and it exists only because the system refuses rather
    than guessing: the guardrail generates the dataset.
    """
    unanswered = [r for r in rows if r["escalated"]]
    if not unanswered:
        return []

    grouped: dict[str, list[dict]] = defaultdict(list)
    meta: dict[str, tuple[str, str]] = {}
    for row in unanswered:
        key, label, action = _reason_group(row["escalation_reason"])
        grouped[key].append(row)
        meta[key] = (label, action)

    groups = []
    for key, members in grouped.items():
        label, action = meta[key]
        themes = _themes(members)
        groups.append(
            {
                "key": key,
                "label": label,
                "theme": label,
                "action": action,
                "volume": len(members),
                "share_of_gaps": round(len(members) / len(unanswered), 4),
                "reason": Counter(m["escalation_reason"] for m in members).most_common(1)[0][0],
                "categories": [
                    c
                    for c, _ in Counter(m["category"] or "unrouted" for m in members).most_common(3)
                ],
                "themes": themes,
                "examples": [e for t in themes for e in t["examples"]][:3],
            }
        )

    return sorted(groups, key=lambda g: g["volume"], reverse=True)


_LOOP_CACHE: dict = {}


def gap_loop(rows: list[dict]) -> dict | None:
    """Did acting on the register work?

    Decision: whether writing the documents the register asks for actually
    reduces unanswered enquiries -- the case for funding that writing.

    The same simulated semester is routed twice: against the catalogue as it was
    before the project team wrote the synthetic procedures (those services
    undocumented, the new welfare service absent), and against the catalogue as
    it is now. Both use the rules the seeder used to generate the semester, so
    the only thing that differs between the two runs is the documents.

    The procedures that closed these gaps were written by the project team, not
    by the University. What this demonstrates is the mechanism, not a real-world
    outcome: in practice the University would have to publish them.
    """
    from core.agent import coverage_problem

    simulated = [r for r in rows if r["simulated"]]
    if not simulated:
        return None

    cache_key = (
        len(simulated),
        max(r["id"] for r in simulated),
        config.SERVICES_FILE.stat().st_mtime,
    )
    if cache_key in _LOOP_CACHE:
        return _LOOP_CACHE[cache_key]

    services, _ = router.load_catalogue()
    synthetic = {sid for sid, s in services.items() if s.get("provenance") == "synthetic"}
    introduced = frozenset(
        sid for sid in synthetic if services[sid].get("introduced_with_synthetic_data")
    )

    def decide(question: str, before: bool) -> tuple[str | None, str | None]:
        routed = router.route(question, exclude=introduced if before else frozenset())
        service = routed["service"]
        if not service:
            return "router could not place the enquiry", None
        if not service.get("documented") or (before and service["id"] in synthetic):
            return "no published procedure", service["id"]
        if coverage_problem(question, service):
            return "outside the coverage of the indexed data", service["id"]
        return None, service["id"]

    before_rows, after_rows = [], []
    closed: Counter = Counter()
    # Questions the old catalogue sent to the wrong service. "Is there financial
    # support for students in difficulty?" matched the ID card service on the
    # word "student" -- so the "before" register overstates ID card demand, and
    # the comparison has to say by how much rather than let the number stand.
    rerouted: Counter = Counter()
    rerouted_example: dict[tuple[str, str], str] = {}

    for row in simulated:
        reason_before, service_before = decide(row["question"], before=True)
        reason_after, answered_by = decide(row["question"], before=False)
        before_rows.append(
            {**row, "escalated": int(bool(reason_before)), "escalation_reason": reason_before,
             "service_id": service_before}
        )
        after_rows.append(
            {**row, "escalated": int(bool(reason_after)), "escalation_reason": reason_after,
             "service_id": answered_by}
        )
        if reason_before and not reason_after:
            closed[answered_by] += 1
        if service_before and answered_by and service_before != answered_by:
            rerouted[(service_before, answered_by)] += 1
            rerouted_example.setdefault((service_before, answered_by), row["question"])

    total = len(simulated)
    before_escalated = sum(r["escalated"] for r in before_rows)
    after_escalated = sum(r["escalated"] for r in after_rows)

    result = {
        "questions": total,
        "before": {
            "escalated": before_escalated,
            "rate": round(before_escalated / total, 4),
            "gaps": knowledge_gaps(before_rows),
        },
        "after": {
            "escalated": after_escalated,
            "rate": round(after_escalated / total, 4),
            "gaps": knowledge_gaps(after_rows),
        },
        "closed_by": [
            {
                "service_id": sid,
                "service": services[sid]["name"],
                "synthetic": sid in synthetic,
                "enquiries": count,
            }
            for sid, count in closed.most_common()
        ],
        "rerouted": [
            {
                "from": services[a]["name"],
                "to": services[b]["name"],
                "enquiries": count,
                "example": rerouted_example[(a, b)],
            }
            for (a, b), count in rerouted.most_common()
        ],
        "method": (
            "The same simulated semester routed against the catalogue before and "
            "after the synthetic procedures were added, using the seeder's rules."
        ),
    }

    _LOOP_CACHE.clear()
    _LOOP_CACHE[cache_key] = result
    return result


def deflection(rows: list[dict]) -> dict:
    """Share of enquiries answered without escalation, and the trend.

    Decision: is the assistant actually reducing front-desk load, or just
    producing a log? A flat or falling rate means the knowledge base is not
    keeping up with what students ask.
    """
    if not rows:
        return {"rate": 0.0, "answered": 0, "total": 0, "weeks": [], "series": []}

    answered = sum(1 for r in rows if not r["escalated"])

    by_week: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        by_week[_week(row["ts"])].append(0 if row["escalated"] else 1)

    weeks = sorted(by_week)
    return {
        "rate": round(answered / len(rows), 4),
        "answered": answered,
        "total": len(rows),
        "weeks": weeks,
        "series": [
            round(sum(by_week[w]) / len(by_week[w]), 4) for w in weeks
        ],
    }


def busiest_hours(rows: list[dict]) -> dict:
    """When enquiries arrive, hour by hour and day by day.

    Decision: when to put a second person on the desk, and when the quiet hours
    are. A weekly total says demand is high; this says it lands between 10 and
    noon, which is what a rota needs.
    """
    if not rows:
        return {"hours": [], "counts": [], "peak_hour": None, "weekdays": [], "weekday_counts": []}

    by_hour = Counter(int(row["ts"][11:13]) for row in rows)
    hours = list(range(24))
    counts = [by_hour.get(hour, 0) for hour in hours]

    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_day = Counter(datetime.fromisoformat(row["ts"]).weekday() for row in rows)

    busiest = max(by_hour, key=lambda h: by_hour[h])
    return {
        "hours": hours,
        "counts": counts,
        # The working window, for the sentence the panel leads with.
        "peak_hour": busiest,
        "peak_count": by_hour[busiest],
        "weekdays": names,
        "weekday_counts": [by_day.get(index, 0) for index in range(7)],
    }


def most_asked(rows: list[dict], limit: int = 8) -> list[dict]:
    """The questions that come back most often, however they were worded.

    Decision: what belongs on a FAQ page, a noticeboard or in the orientation
    pack. A question asked two hundred times in a semester is a leaflet, not a
    conversation.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["question"]:
            groups[_normalise_question(row["question"])].append(row)

    ranked = sorted(groups.values(), key=len, reverse=True)[:limit]
    services, _ = router.load_catalogue()

    out = []
    for members in ranked:
        declined = sum(1 for r in members if r["escalated"])
        service_id = next((r["service_id"] for r in members if r["service_id"]), None)
        out.append(
            {
                "question": members[0]["question"],
                "volume": len(members),
                "share": round(len(members) / max(len(rows), 1), 4),
                "declined": declined,
                "service": services.get(service_id, {}).get("name") if service_id else None,
                "category": members[0]["category"],
            }
        )
    return out


def repeat_rate(rows: list[dict]) -> dict:
    """How much of the load is the same few questions returning.

    Decision: whether publishing a handful of answers would remove most of the
    traffic, or whether demand is genuinely varied and needs staff instead.
    """
    if not rows:
        return {"distinct": 0, "total": 0, "repeated_share": 0.0, "top_five_share": 0.0}

    groups = Counter(_normalise_question(row["question"]) for row in rows if row["question"])
    if not groups:
        return {"distinct": 0, "total": len(rows), "repeated_share": 0.0, "top_five_share": 0.0}

    total = sum(groups.values())
    repeated = sum(count for count in groups.values() if count > 1)
    top_five = sum(count for _, count in groups.most_common(5))
    return {
        "distinct": len(groups),
        "total": total,
        "repeated_share": round(repeated / total, 4),
        "top_five_share": round(top_five / total, 4),
    }


def service_health(rows: list[dict]) -> dict:
    """How the assistant itself is performing, as a service.

    Decision: is it fast enough to be used at a counter, and is it answering or
    quietly refusing more of what it is asked?
    """
    times = sorted(row["elapsed_ms"] for row in rows if row.get("elapsed_ms"))
    answered = sum(1 for row in rows if not row["escalated"])

    weeks = sorted({_week(row["ts"]) for row in rows})
    recent, previous = (weeks[-1] if weeks else None), (weeks[-2] if len(weeks) > 1 else None)
    this_week = sum(1 for row in rows if _week(row["ts"]) == recent)
    last_week = sum(1 for row in rows if _week(row["ts"]) == previous) if previous else 0

    # The newest week is usually still running, so comparing it with a finished
    # one reads as a collapse in demand. Say which it is and let the panel
    # phrase it honestly.
    partial = recent == _week(datetime.now(timezone.utc).isoformat())

    return {
        "median_ms": times[len(times) // 2] if times else None,
        "p90_ms": times[int(len(times) * 0.9)] if times else None,
        "measured": len(times),
        "answered_share": round(answered / len(rows), 4) if rows else 0.0,
        "this_week": this_week,
        "last_week": last_week,
        # Positive means demand is rising into the coming week. Withheld while
        # the week is incomplete, because the comparison would not be like for like.
        "change": (
            round((this_week - last_week) / last_week, 4)
            if last_week and not partial
            else None
        ),
        "week": recent,
        "partial_week": partial,
    }


def office_load(rows: list[dict]) -> list[dict]:
    """Enquiries routed to each office.

    Decision: staffing and resource allocation across offices.
    """
    counts = Counter(r["office_id"] or "unrouted" for r in rows)
    total = sum(counts.values()) or 1

    import json as _json
    from core import config

    offices = {
        o["id"]: o
        for o in _json.loads(config.OFFICES_FILE.read_text(encoding="utf-8"))["offices"]
    }

    return [
        {
            "office_id": office_id,
            "office": offices.get(office_id, {}).get("name", "Not routed"),
            "enquiries": count,
            "share": round(count / total, 4),
        }
        for office_id, count in counts.most_common()
    ]


def source_freshness(rows: list[dict], stale_before: int = 2020) -> dict:
    """How much of what we tell students rests on old documents.

    Decision: which documents to prioritise for review. This metric exists
    because the College handbook we rely on is dated 2017 -- a student acting on
    a superseded procedure is a real failure mode, not a hypothetical one.
    """
    cited = 0
    stale = 0
    year_counts: Counter = Counter()

    for row in rows:
        years = json.loads(row["source_years"] or "[]")
        if not years:
            continue
        cited += 1
        for year in years:
            year_counts[year] += 1
        if any(y.isdigit() and int(y) < stale_before for y in years):
            stale += 1

    return {
        "answers_with_dated_sources": cited,
        "answers_citing_stale_sources": stale,
        "stale_share": round(stale / cited, 4) if cited else 0.0,
        "stale_before": stale_before,
        "by_year": dict(sorted(year_counts.items())),
    }


def forecast(rows: list[dict], horizon: int = 4) -> dict:
    """Project the next few weeks of demand.

    Decision: staff ahead of the next peak rather than after it.

    Deliberately a simple baseline -- a linear trend over recent weeks blended
    with the recent average. With one semester of history there is not enough
    data to fit anything seasonal honestly, and a sophisticated model on thin
    data would give false confidence. The report should say exactly this.
    """
    weekly = weekly_demand(rows)
    weeks, totals = weekly["weeks"], weekly["totals"]

    if len(totals) < 4:
        return {"weeks": [], "values": [], "method": "insufficient history", "basis_weeks": len(totals)}

    recent = totals[-8:]
    n = len(recent)
    mean_x = (n - 1) / 2
    mean_y = sum(recent) / n

    variance = sum((i - mean_x) ** 2 for i in range(n))
    slope = (
        sum((i - mean_x) * (y - mean_y) for i, y in enumerate(recent)) / variance
        if variance
        else 0.0
    )

    projected = []
    for step in range(1, horizon + 1):
        value = mean_y + slope * (n - 1 - mean_x + step)
        projected.append(max(0, round(value)))

    last_year, last_week = map(int, weeks[-1].split("-W"))
    labels = []
    for step in range(1, horizon + 1):
        week = last_week + step
        year = last_year + (1 if week > 52 else 0)
        labels.append(f"{year}-W{(week - 1) % 52 + 1:02d}")

    return {
        "weeks": labels,
        "values": projected,
        "method": "linear trend over the last 8 weeks",
        "basis_weeks": n,
        "caveat": "One semester of mostly simulated history. Treat as indicative only.",
    }


def dashboard() -> dict:
    """Everything the admin view needs, in one query pass."""
    rows = _rows()
    counts = store.count()

    return {
        "summary": {
            **counts,
            "categories": len({r["category"] for r in rows if r["category"]}),
            "date_range": [rows[0]["ts"], rows[-1]["ts"]] if rows else [],
        },
        "demand_by_category": demand_by_category(rows),
        "weekly_demand": weekly_demand(rows),
        "busiest_hours": busiest_hours(rows),
        "most_asked": most_asked(rows),
        "repeat_rate": repeat_rate(rows),
        "service_health": service_health(rows),
        "knowledge_gaps": knowledge_gaps(rows),
        "gap_loop": gap_loop(rows),
        "deflection": deflection(rows),
        "office_load": office_load(rows),
        "source_freshness": source_freshness(rows),
        "forecast": forecast(rows),
    }
