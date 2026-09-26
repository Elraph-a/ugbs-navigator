"""Fetch every source in data/sources.yaml into data/raw/ and record provenance.

Run from the project root:

    ..\\AI_Lab\\Scripts\\python.exe tools\\collect_sources.py
    ..\\AI_Lab\\Scripts\\python.exe tools\\collect_sources.py --only transcript_request
    ..\\AI_Lab\\Scripts\\python.exe tools\\collect_sources.py --refresh

Existing files are kept unless --refresh is passed, so a flaky connection does
not cost you the whole corpus. Failures are reported loudly and listed at the
end rather than skipped quietly -- a source that silently failed to download is
a hole in the knowledge base that nobody notices until the demo.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.ingest import clean_text, html_to_text

USER_AGENT = (
    "UGBS-Service-Navigator/0.1 (University of Ghana OMIS 404 student project; "
    "indexing published administrative procedures)"
)
TIMEOUT = 30


def fetch(url: str) -> tuple[bytes, str]:
    """Return (body, content_type). Raises on any non-200."""
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.content, response.headers.get("content-type", "").lower()


def fetch_rendered(url: str) -> str:
    """The page's HTML after its JavaScript has run.

    Several University pages return a shell to a plain HTTP request: the
    academic calendar and the general registration page both extracted as a
    navigation menu and were recorded as failures. A real browser sees what a
    student sees. Slower and heavier, so it is a fallback, never the first try.
    """
    result = subprocess.run(
        ["node", str(config.PROJECT_ROOT / "tools" / "render_page.mjs"), url],
        capture_output=True,
        timeout=120,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise ValueError(f"browser render failed: {result.stderr.strip()[:200]}")
    return result.stdout


def quality_problem(text: str) -> str:
    """Return a reason to reject this extraction, or "" if it looks like content.

    Some University pages return a shell whose only real markup is the site
    menu. Those extract as a short block of link labels: plausible-looking text
    that is pure navigation. Indexing it is worse than having nothing, because
    retrieval will happily match a student's question against a menu item and
    cite it as a source.
    """
    if len(text) < 400:
        return (
            f"only {len(text)} characters extracted - the page is probably "
            "JavaScript-rendered or an error page"
        )

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return "no text extracted"

    bullets = sum(1 for line in lines if line.startswith("- "))
    if bullets / len(lines) >= 0.9:
        return (
            f"{bullets}/{len(lines)} lines are list items - this is the site "
            "navigation menu, not article content"
        )

    return ""


def save_source(entry: dict, refresh: bool) -> dict:
    """Download one source. Returns a provenance record."""
    source_id = entry["id"]
    url = entry["url"]
    is_pdf = url.lower().endswith(".pdf")
    suffix = ".pdf" if is_pdf else ".txt"
    target = config.RAW / f"{source_id}{suffix}"

    record = {
        "id": source_id,
        "title": entry["title"],
        "url": url,
        "category": entry.get("category", "unknown"),
        "publisher": entry.get("publisher", ""),
        "authority": entry.get("authority", "secondary"),
        "published_date": entry.get("published_date"),
        "provenance": "real",
        "file": target.name,
    }

    if target.exists() and not refresh:
        record["access_date"] = record.get("access_date") or "unchanged"
        record["status"] = "cached"
        record["bytes"] = target.stat().st_size
        print(f"  cached   {source_id:<28} {target.name}")
        return record

    body, content_type = fetch(url)

    if is_pdf or "pdf" in content_type:
        target = config.RAW / f"{source_id}.pdf"
        target.write_bytes(body)
        record["file"] = target.name
        size = len(body)
    else:
        text = clean_text(html_to_text(body.decode("utf-8", errors="replace")))
        reject = quality_problem(text)
        if reject:
            # A shell rather than a page: try again with a browser before
            # recording a failure.
            print(f"  render   {source_id:<28} plain fetch gave a shell ({reject})")
            rendered = clean_text(html_to_text(fetch_rendered(url)))
            still_wrong = quality_problem(rendered)
            if still_wrong:
                raise ValueError(f"{reject}; after browser render: {still_wrong}")
            text = rendered
            record["fetched_with"] = "browser render"
        target.write_text(text, encoding="utf-8")
        size = len(text)

    record["access_date"] = date.today().isoformat()
    record["status"] = "fetched"
    record["bytes"] = size
    print(f"  fetched  {source_id:<28} {target.name}  ({size:,} bytes)")
    return record


def write_sources_md(records: list[dict], failures: list[tuple[str, str]]) -> None:
    """SOURCES.md is the provenance record the report cites."""
    lines = [
        "# Sources",
        "",
        "Every document in the knowledge base, where it came from, and when we fetched it.",
        "Generated by `tools/collect_sources.py` -- edit `data/sources.yaml`, not this file.",
        "",
        f"Last run: {date.today().isoformat()}",
        "",
        "| id | title | publisher | category | published | accessed | status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(records, key=lambda x: x["id"]):
        lines.append(
            f"| `{r['id']}` | {r['title']} | {r['publisher']} | {r['category']} | "
            f"{r['published_date'] or '_not stated_'} | {r.get('access_date', '')} | "
            f"{r['status']} |"
        )

    if failures:
        lines += [
            "",
            "## Could not be fetched",
            "",
            "These are listed so the gap is visible rather than silent.",
            "",
            "| id | reason |",
            "| --- | --- |",
        ]
        for source_id, reason in failures:
            lines.append(f"| `{source_id}` | {reason} |")

    undated = [r for r in records if not r["published_date"]]
    lines += [
        "",
        "## Freshness",
        "",
        f"- {len(records)} sources collected",
        f"- {len(undated)} state no publication date",
        "",
        "Several key sources date from 2017. That is carried into chunk metadata and "
        "surfaced on the dashboard as source-freshness exposure, because a student "
        "acting on a stale procedure is a real failure mode of this system.",
        "",
    ]
    config.SOURCES_FILE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="fetch a single source id")
    parser.add_argument(
        "--refresh", action="store_true", help="re-download sources already on disk"
    )
    args = parser.parse_args()

    manifest = yaml.safe_load((config.DATA / "sources.yaml").read_text(encoding="utf-8"))
    entries = manifest["sources"]
    if args.only:
        entries = [e for e in entries if e["id"] == args.only]
        if not entries:
            print(f"No source with id {args.only!r}", file=sys.stderr)
            return 1

    config.RAW.mkdir(parents=True, exist_ok=True)

    print(f"Collecting {len(entries)} sources into {config.RAW}\n")

    records: list[dict] = []
    failures: list[tuple[str, str]] = []

    for entry in entries:
        try:
            records.append(save_source(entry, refresh=args.refresh))
        except Exception as exc:  # noqa: BLE001 - we want every failure reported
            reason = f"{type(exc).__name__}: {exc}"
            failures.append((entry["id"], reason))
            print(f"  FAILED   {entry['id']:<28} {reason}")

    # Merge into the existing index rather than replacing it. With --only, a
    # straight overwrite would silently shrink the knowledge base to one document.
    index_path = config.RAW / "sources_index.json"
    merged: dict[str, dict] = {}
    if index_path.exists():
        for existing in json.loads(index_path.read_text(encoding="utf-8")):
            merged[existing["id"]] = existing
    for record in records:
        merged[record["id"]] = record

    # Drop anything no longer in the manifest, so a removed source really goes away.
    manifest_ids = {e["id"] for e in manifest["sources"]}
    final = [r for r in merged.values() if r["id"] in manifest_ids]

    index_path.write_text(json.dumps(final, indent=2), encoding="utf-8")
    write_sources_md(final, failures)

    print(f"\n{len(records)} collected, {len(failures)} failed")
    print(f"Provenance written to {config.SOURCES_FILE}")

    if failures:
        print("\nFailed sources are recorded in SOURCES.md. Fix the URL in")
        print("data/sources.yaml, or remove the entry if the page is gone.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
