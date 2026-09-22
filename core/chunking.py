"""Split documents into retrievable passages that can still be cited.

Two constraints shape this. A chunk has to be small enough that retrieval is
precise, and large enough that a procedure survives intact -- splitting "pay at
the Cash Office" away from "submit the receipt at Room D2" produces an answer
that is individually true and collectively useless.

So we split on section headings first and only fall back to a sliding window
inside a section that is too long. Every chunk keeps the heading it came from,
because that heading is what the citation shows the student.
"""

from __future__ import annotations

import hashlib
import re

from core.ingest import HEADING

PAGE_MARKER = re.compile(r"\[\[page:(\d+)\]\]")

TARGET_WORDS = 320
MAX_WORDS = 450
OVERLAP_RATIO = 0.15
MIN_WORDS = 25


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Return [(heading, body)]. Text before the first heading keeps an empty one."""
    marker = HEADING.strip("\n")  # "###"
    parts = re.split(rf"\n*{re.escape(marker)}\s*", text)

    sections: list[tuple[str, str]] = []
    if parts and parts[0].strip():
        sections.append(("", parts[0].strip()))

    for part in parts[1:]:
        if not part.strip():
            continue
        heading, _, body = part.partition("\n")
        sections.append((heading.strip(), body.strip()))

    return sections or [("", text.strip())]


def _window(words: list[str]) -> list[list[str]]:
    """Slide over an over-long section, overlapping so a procedure is not cut."""
    if len(words) <= MAX_WORDS:
        return [words]

    step = max(1, int(TARGET_WORDS * (1 - OVERLAP_RATIO)))
    windows = []
    for start in range(0, len(words), step):
        window = words[start : start + TARGET_WORDS]
        if len(window) < MIN_WORDS and windows:
            # A short tail belongs with the previous window, not on its own.
            windows[-1] = windows[-1] + window
            break
        windows.append(window)
        if start + TARGET_WORDS >= len(words):
            break
    return windows


def _page_for(text: str, fallback: int | None) -> int | None:
    match = PAGE_MARKER.search(text)
    return int(match.group(1)) if match else fallback


def chunk_document(text: str, meta: dict) -> list[dict]:
    """Turn one document's text into chunk records carrying full provenance."""
    chunks: list[dict] = []
    current_page: int | None = None

    for heading, body in _split_sections(text):
        # Page markers are metadata, not content: record then remove them.
        current_page = _page_for(heading + "\n" + body, current_page)
        clean_body = PAGE_MARKER.sub(" ", body)
        clean_heading = PAGE_MARKER.sub(" ", heading).strip()

        words = clean_body.split()
        if len(words) < MIN_WORDS:
            # Too short to stand alone, but a heading plus a line can still be a
            # real fact ("Express Transcripts - requests before 11:00 AM").
            if not clean_heading or len(words) < 5:
                continue

        for window in _window(words):
            passage = " ".join(window).strip()
            if len(passage.split()) < 5:
                continue

            # The text sent to the embedder includes the heading, because
            # "Express Transcripts" is often the only place the key term appears.
            embed_text = f"{clean_heading}. {passage}" if clean_heading else passage

            digest = hashlib.sha1(
                f"{meta['doc_id']}|{clean_heading}|{passage[:200]}".encode("utf-8")
            ).hexdigest()[:12]

            chunks.append(
                {
                    "chunk_id": f"{meta['doc_id']}::{digest}",
                    "text": passage,
                    "embed_text": embed_text,
                    "section": clean_heading,
                    "page": current_page,
                    "doc_id": meta["doc_id"],
                    "doc_title": meta["title"],
                    "category": meta.get("category", "unknown"),
                    "provenance": meta.get("provenance", "real"),
                    "source_url": meta.get("url", ""),
                    "publisher": meta.get("publisher", ""),
                    "authority": meta.get("authority", "secondary"),
                    "published_date": meta.get("published_date") or "",
                    "access_date": meta.get("access_date", ""),
                }
            )

    return chunks
