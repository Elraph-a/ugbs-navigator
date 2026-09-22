"""Enquiry log. SQLite, because the analytics are aggregation queries.

What is stored is deliberately narrow: the redacted question, how it was routed,
how confident the system was, and whether it could answer. There is no session
id, no IP address and no student identifier, so there is nothing to join back to
a person even if someone wanted to -- see CLAUDE.md section 8.

`simulated` marks the seeded semester of history apart from real usage. The
dashboard shows the split rather than blending them, because a chart that mixes
generated data with observed data and says nothing about it is dishonest.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from core import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS enquiries (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    ts                   TEXT    NOT NULL,
    question             TEXT    NOT NULL,
    category             TEXT,
    service_id           TEXT,
    office_id            TEXT,
    routing_confidence   REAL,
    retrieval_confidence REAL,
    answered             INTEGER NOT NULL,
    escalated            INTEGER NOT NULL,
    escalation_reason    TEXT,
    provider             TEXT,
    elapsed_ms           INTEGER,
    pii_kinds            TEXT,
    source_years         TEXT,
    simulated            INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_enquiries_ts       ON enquiries(ts);
CREATE INDEX IF NOT EXISTS idx_enquiries_category ON enquiries(category);
CREATE INDEX IF NOT EXISTS idx_enquiries_escal    ON enquiries(escalated);
"""


@contextmanager
def connect():
    config.DATA.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(config.DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)


def log_enquiry(response: dict, *, simulated: bool = False, ts: str | None = None) -> int:
    """Record one enquiry. `response` is the dict returned by core.agent.answer."""
    init()

    service_id = next(
        (s["service"]["id"] for s in response["sections"] if s.get("service")), None
    )
    # A conversational reply cites once for the whole answer; the older per-
    # section shape cited per procedure. Read both so the freshness metric counts
    # every source a student was actually shown.
    cited = list(response.get("citations") or []) + [
        citation for section in response["sections"] for citation in section.get("citations", [])
    ]
    source_years = sorted(
        {c["published_date"][:4] for c in cited if c.get("published_date")}
    )

    with connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO enquiries (
                ts, question, category, service_id, office_id,
                routing_confidence, retrieval_confidence, answered, escalated,
                escalation_reason, provider, elapsed_ms, pii_kinds, source_years, simulated
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                ts or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                response["question"],
                response.get("category"),
                service_id,
                (response.get("office") or {}).get("id"),
                response.get("routing_confidence"),
                response.get("retrieval_confidence"),
                0 if response["escalated"] else 1,
                1 if response["escalated"] else 0,
                response.get("escalation_reason"),
                response.get("provider"),
                response.get("elapsed_ms"),
                json.dumps(response.get("pii_redacted", [])),
                json.dumps(source_years),
                1 if simulated else 0,
            ),
        )
        return cursor.lastrowid


def purge_expired() -> int:
    """Delete enquiries past the retention window. Retention is a promise, not a
    setting, so this runs on startup rather than waiting to be called."""
    init()
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=config.settings.retention_days)
    ).isoformat(timespec="seconds")

    with connect() as connection:
        cursor = connection.execute(
            "DELETE FROM enquiries WHERE simulated = 0 AND ts < ?", (cutoff,)
        )
        return cursor.rowcount


def fetch_all(include_simulated: bool = True) -> list[dict]:
    init()
    query = "SELECT * FROM enquiries"
    if not include_simulated:
        query += " WHERE simulated = 0"
    query += " ORDER BY ts"

    with connect() as connection:
        return [dict(row) for row in connection.execute(query)]


def count() -> dict:
    init()
    with connect() as connection:
        row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(simulated)        AS simulated,
                   SUM(escalated)        AS escalated
            FROM enquiries
            """
        ).fetchone()
    return {
        "total": row["total"] or 0,
        "simulated": row["simulated"] or 0,
        "live": (row["total"] or 0) - (row["simulated"] or 0),
        "escalated": row["escalated"] or 0,
    }
