"""Turn source documents into clean text, preserving the structure citations need.

Readers for TXT/PDF/DOCX/PPTX are adapted from the earlier MiniGPT lab work.
The cleaning is deliberately *not* the same: MiniGPT lowercased everything and
collapsed newlines, which is right for training a language model and wrong here.
This system quotes its sources back to students, so case, punctuation and the
heading structure that section-aware chunking depends on all have to survive.
"""

from __future__ import annotations

import re
from pathlib import Path

# Headings are marked with this sentinel so chunking can split on sections
# without needing the original markup.
HEADING = "\n\n### "

_ENCODINGS = ("utf-8", "utf-8-sig", "cp1252", "cp850", "latin-1", "utf-16")


def read_txt(path: Path) -> str:
    """Read a text file, trying the encodings that actually show up in practice."""
    for encoding in _ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode {path.name} with any known encoding")


def read_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    parts = []
    with fitz.open(path) as pdf:
        for number, page in enumerate(pdf, start=1):
            text = page.get_text()
            if text.strip():
                # Page numbers are kept so a citation can point at a page.
                parts.append(f"\n\n[[page:{number}]]\n{text}")
    return "".join(parts)


def read_docx(path: Path) -> str:
    from docx import Document

    document = Document(str(path))
    parts = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        if paragraph.style.name.startswith("Heading"):
            parts.append(f"{HEADING}{text}\n")
        else:
            parts.append(text)
    return "\n".join(parts)


def read_pptx(path: Path) -> str:
    from pptx import Presentation

    presentation = Presentation(str(path))
    parts = []
    for number, slide in enumerate(presentation.slides, start=1):
        parts.append(f"{HEADING}Slide {number}\n")
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                parts.append(shape.text.strip())
    return "\n".join(parts)


def html_to_text(html: str) -> str:
    """Extract readable content from a page, keeping headings and list items.

    University pages are mostly navigation. We drop the chrome first, then walk
    the remaining block elements in document order so the output reads in the
    same sequence a person would.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")

    for tag in soup(
        ["script", "style", "nav", "header", "footer", "form", "noscript", "iframe"]
    ):
        tag.decompose()

    # Prefer the main content region when the page marks one -- but only if it
    # actually holds the content. The academic calendar marks an <article> that
    # is empty and builds its dates elsewhere, so preferring the tag by name
    # returned nothing at all and the page was written off as JavaScript-only.
    candidates = [
        c
        for c in (
            soup.find("main"),
            soup.find("article"),
            soup.find(attrs={"role": "main"}),
            soup.find("div", class_=re.compile(r"content|region-content", re.I)),
            soup.body,
            soup,
        )
        if c is not None
    ]
    sizes = [(c, len(c.get_text(" ", strip=True))) for c in candidates]
    widest = max(size for _, size in sizes) if sizes else 0
    # The marked-up region is the tidier choice, but only when it holds most of
    # the page. On the academic calendar it held the introduction and nothing
    # else, while the dates sat in plain divs beside it, so preferring it by
    # name lost the whole table.
    root = next(
        (c for c, size in sizes if size >= max(200, widest * 0.7)),
        soup.body or soup,
    )

    parts: list[str] = []
    seen: set[str] = set()

    for element in root.find_all(
        ["h1", "h2", "h3", "h4", "p", "li", "td", "th", "caption"]
    ):
        text = " ".join(element.get_text(" ", strip=True).split())
        if len(text) < 3:
            continue
        # University pages repeat menu labels in several places.
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)

        if element.name in {"h1", "h2", "h3", "h4"}:
            parts.append(f"{HEADING}{text}\n")
        elif element.name in {"li", "td", "th"}:
            parts.append(f"- {text}")
        else:
            parts.append(text)

    # Calendar rows. The academic calendar pairs a <time> with an activity
    # inside plain layout divs, so the walk above sees none of it: the page
    # extracted as its own introduction and nothing else. Each row becomes one
    # readable line, which is also how a student reads the table.
    for moment in root.find_all("time"):
        # Climb to the element that holds the activity as well as the date. The
        # calendar puts them in sibling columns, so the nearest parent is the
        # date column alone: stopping there produced rows of bare dates.
        row = None
        for ancestor in moment.parents:
            if ancestor.name not in {"div", "tr", "li", "section"}:
                continue
            whole = ancestor.get_text(" ", strip=True)
            dates = " ".join(t.get_text(" ", strip=True) for t in ancestor.find_all("time"))
            if len(whole) - len(dates) >= 10:
                row = ancestor
                break
        if row is None:
            continue
        whole = " ".join(row.get_text(" ", strip=True).split())
        dates = " to ".join(
            " ".join(t.get_text(" ", strip=True).split()) for t in row.find_all("time")
        )
        # Activity first, then its dates. Read the other way round, the model
        # paired "Matriculation" with the dates of the row below it.
        activity = whole
        for piece in (t.get_text(" ", strip=True) for t in row.find_all("time")):
            activity = activity.replace(" ".join(piece.split()), " ")
        activity = " ".join(activity.replace(" - ", " ").split())
        text = f"{activity}: {dates}" if activity and dates else whole

        key = text.lower()
        if len(text) < 8 or key in seen:
            continue
        seen.add(key)
        parts.append(f"- {text}")

    extracted = "\n".join(parts)

    # Some pages lay their content out in bare divs and spans, with none of the
    # block tags above. Walking the tags then yields almost nothing from a page
    # that plainly has text, so fall back to reading the region directly.
    if len(extracted) < 200:
        raw = root.get_text("\n", strip=True)
        if len(raw) > len(extracted):
            lines, previous = [], None
            for line in (" ".join(l.split()) for l in raw.splitlines()):
                if len(line) >= 3 and line != previous:
                    lines.append(line)
                    previous = line
            extracted = "\n".join(lines)

    return extracted


def clean_text(text: str) -> str:
    """Light normalisation only.

    Case and punctuation are load-bearing: "Room D2" and "GH₵30" have to come
    back out exactly as they went in, because students act on them.
    """
    if not text:
        return ""

    # Normalise the various unicode spaces and quotes that PDFs are full of.
    text = text.replace(" ", " ").replace("​", "")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')

    # Collapse runs of spaces/tabs, but keep paragraph breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    # Drop lines that are page furniture rather than content.
    lines = [
        line.rstrip()
        for line in text.split("\n")
        if not re.fullmatch(r"\s*(page\s*\d+(\s*of\s*\d+)?|\d+)\s*", line, re.I)
    ]

    return "\n".join(lines).strip()


def read_document(path: Path) -> str:
    """Dispatch on file type. Raises on an unsupported extension rather than
    returning empty text, so a silently-skipped source cannot reach the index."""
    suffix = path.suffix.lower()
    readers = {
        ".txt": read_txt,
        ".md": read_txt,
        ".pdf": read_pdf,
        ".docx": read_docx,
        ".pptx": read_pptx,
    }
    if suffix == ".html" or suffix == ".htm":
        return clean_text(html_to_text(read_txt(path)))
    if suffix not in readers:
        raise ValueError(f"No reader for {suffix} ({path.name})")
    return clean_text(readers[suffix](path))
