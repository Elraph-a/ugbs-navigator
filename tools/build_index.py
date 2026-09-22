"""Build the retrieval index: raw documents -> chunks -> embeddings -> Chroma.

    ..\\AI_Lab\\Scripts\\python.exe tools\\build_index.py
    ..\\AI_Lab\\Scripts\\python.exe tools\\build_index.py --dry-run   # chunk only, no embedding

Embedding runs on CPU and is the slow step -- a few minutes for the full corpus
on the demo laptop. It is a build cost, not a request cost: at query time only
the question is embedded, which takes tens of milliseconds.

Run this after `tools/collect_sources.py`, and again whenever a source or a
synthetic procedure changes.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.chunking import chunk_document
from core.ingest import read_document

COLLECTION = "ugbs_navigator"


def _load_manifest_extracts() -> dict[str, dict]:
    """`extract` blocks live in sources.yaml, next to the URL they apply to."""
    manifest = yaml.safe_load((config.DATA / "sources.yaml").read_text(encoding="utf-8"))
    return {
        entry["id"]: entry["extract"]
        for entry in manifest["sources"]
        if entry.get("extract")
    }


manifest_extract = _load_manifest_extracts()


def apply_extract(text: str, spec: dict | None, doc_id: str) -> str:
    """Keep only the slice of a document named by an `extract` block in the manifest.

    The College of Humanities handbook covers every school in the college. Only
    the UGBS section is in scope, and indexing 1.1M characters of Law and
    Performing Arts course descriptions would swamp retrieval with passages a
    Business School student will never ask about.

    Both markers are matched at the start of a line so a passing mention in
    prose cannot move the boundary.
    """
    if not spec:
        return text

    start_marker = spec.get("start", "")
    end_marker = spec.get("end", "")

    start = 0
    if start_marker:
        match = re.search(rf"^{re.escape(start_marker)}$", text, re.M)
        if not match:
            print(f"  WARNING  {doc_id}: extract start {start_marker!r} not found, keeping whole document")
            return text
        start = match.start()

    stop = len(text)
    if end_marker:
        match = re.search(rf"^{re.escape(end_marker)}$", text[start:], re.M)
        if match:
            stop = start + match.start()
        else:
            print(f"  WARNING  {doc_id}: extract end {end_marker!r} not found, keeping to end")

    return text[start:stop]


def load_real_documents() -> list[tuple[str, dict]]:
    """Read the provenance index written by collect_sources.py."""
    index_path = config.RAW / "sources_index.json"
    if not index_path.exists():
        print("No data/raw/sources_index.json - run tools/collect_sources.py first.")
        return []

    records = json.loads(index_path.read_text(encoding="utf-8"))
    documents = []

    for record in records:
        path = config.RAW / record["file"]
        if not path.exists():
            print(f"  missing  {record['id']:<28} {record['file']}")
            continue
        try:
            text = read_document(path)
        except Exception as exc:  # noqa: BLE001 - report, never skip silently
            print(f"  FAILED   {record['id']:<28} {type(exc).__name__}: {exc}")
            continue

        meta = dict(record)
        meta["doc_id"] = record["id"]
        meta["provenance"] = "real"

        before = len(text)
        text = apply_extract(text, manifest_extract.get(record["id"]), record["id"])
        if len(text) != before:
            print(
                f"  scoped   {record['id']:<28} {before:,} -> {len(text):,} chars "
                "(UGBS section only)"
            )

        documents.append((text, meta))

    return documents


def load_synthetic_documents() -> list[tuple[str, dict]]:
    """Read authored procedures, which must declare their front matter."""
    documents = []
    for path in sorted(config.SYNTHETIC.glob("*.md")):
        raw = path.read_text(encoding="utf-8")

        if not raw.startswith("---"):
            print(f"  SKIPPED  {path.name}: no front matter, provenance unknown")
            continue

        _, _, rest = raw.partition("---")
        front_matter, _, body = rest.partition("---")
        meta = yaml.safe_load(front_matter) or {}

        if meta.get("provenance") != "synthetic":
            print(f"  SKIPPED  {path.name}: front matter must set provenance: synthetic")
            continue

        meta["doc_id"] = meta.get("id", path.stem)
        meta.setdefault("title", path.stem.replace("_", " ").title())
        meta.setdefault("url", "")
        meta.setdefault("publisher", "Authored by the project team")
        meta.setdefault("authority", "synthetic")
        documents.append((body.strip(), meta))

    return documents


def build_chunks() -> list[dict]:
    print("Reading documents\n")
    documents = load_real_documents() + load_synthetic_documents()

    chunks: list[dict] = []
    for text, meta in documents:
        produced = chunk_document(text, meta)
        chunks.extend(produced)
        flag = "" if meta["provenance"] == "real" else "  [synthetic]"
        print(f"  {meta['doc_id']:<28} {len(text):>9,} chars -> {len(produced):>4} chunks{flag}")

    return chunks


def embed_and_store(chunks: list[dict]) -> None:
    import chromadb

    from core.embed import embed

    # A stale collection silently serves deleted documents, so rebuild cleanly.
    if config.CHROMA.exists():
        shutil.rmtree(config.CHROMA)
    config.CHROMA.mkdir(parents=True, exist_ok=True)

    texts = [c["embed_text"] for c in chunks]
    print(f"\nEmbedding {len(texts):,} chunks with {config.settings.embedding_model} (ONNX, CPU)")

    started = time.time()
    vectors = embed(texts)
    elapsed = time.time() - started
    print(f"Embedded in {elapsed:.0f}s ({len(texts)/max(elapsed,1):.0f} chunks/s)")

    client = chromadb.PersistentClient(path=str(config.CHROMA))
    collection = client.get_or_create_collection(
        COLLECTION, metadata={"hnsw:space": "cosine"}
    )

    # Chroma metadata values must be scalars.
    metadatas = [
        {
            k: ("" if v is None else v)
            for k, v in c.items()
            if k not in {"text", "embed_text"} and isinstance(v, (str, int, float, bool)) or v is None
        }
        for c in chunks
    ]

    step = 500
    for start in range(0, len(chunks), step):
        stop = start + step
        collection.add(
            ids=[c["chunk_id"] for c in chunks[start:stop]],
            documents=[c["text"] for c in chunks[start:stop]],
            embeddings=vectors[start:stop].tolist(),
            metadatas=metadatas[start:stop],
        )

    print(f"Stored {collection.count():,} chunks in {config.CHROMA}")


def report(chunks: list[dict]) -> None:
    print(f"\n{'-' * 62}")
    print(f"{len(chunks):,} chunks from {len({c['doc_id'] for c in chunks})} documents\n")

    print("By category")
    for category, count in Counter(c["category"] for c in chunks).most_common():
        print(f"  {category:<28} {count:>5}")

    provenance = Counter(c["provenance"] for c in chunks)
    print("\nBy provenance")
    for kind, count in provenance.most_common():
        print(f"  {kind:<28} {count:>5}")

    dated = Counter(
        (c["published_date"] or "not stated")[:4] for c in chunks
    )
    print("\nBy publication year")
    for year, count in sorted(dated.items()):
        print(f"  {year:<28} {count:>5}")

    stale = sum(v for k, v in dated.items() if k.isdigit() and int(k) < 2020)
    if stale:
        print(
            f"\n  {stale:,} chunks ({stale/len(chunks):.0%}) come from sources published "
            "before 2020.\n  This is surfaced in the UI and measured on the dashboard."
        )


def write_provenance(chunks: list[dict]) -> None:
    """Write the real-vs-synthetic statement the report has to make.

    Generated from the index itself rather than maintained by hand, so it cannot
    drift away from what the system is actually answering from.
    """
    import json as _json

    by_doc: dict[str, dict] = {}
    for chunk in chunks:
        entry = by_doc.setdefault(
            chunk["doc_id"],
            {
                "title": chunk["doc_title"],
                "provenance": chunk["provenance"],
                "publisher": chunk["publisher"],
                "url": chunk.get("source_url", ""),
                "published": chunk.get("published_date", ""),
                "chunks": 0,
            },
        )
        entry["chunks"] += 1

    real = {k: v for k, v in by_doc.items() if v["provenance"] == "real"}
    synthetic = {k: v for k, v in by_doc.items() if v["provenance"] == "synthetic"}
    real_chunks = sum(v["chunks"] for v in real.values())
    syn_chunks = sum(v["chunks"] for v in synthetic.values())
    total = real_chunks + syn_chunks or 1

    services = _json.loads(config.SERVICES_FILE.read_text(encoding="utf-8"))["services"]
    syn_services = [s for s in services if s.get("provenance") == "synthetic"]

    lines = [
        "# Data provenance",
        "",
        "What this system answers from, and which parts the project team wrote.",
        "Generated by `tools/build_index.py` — do not edit by hand.",
        "",
        f"- **{len(real)} real documents**, {real_chunks} passages "
        f"({real_chunks / total:.0%} of the corpus)",
        f"- **{len(synthetic)} synthetic documents**, {syn_chunks} passages "
        f"({syn_chunks / total:.0%} of the corpus)",
        "",
        "## Real sources",
        "",
        "Published by the University of Ghana or UGBS, downloaded and indexed.",
        "Full URLs and access dates in `data/raw/SOURCES.md`.",
        "",
        "| Document | Publisher | Published | Passages |",
        "| --- | --- | --- | --- |",
    ]
    for entry in sorted(real.values(), key=lambda e: -e["chunks"]):
        lines.append(
            f"| {entry['title']} | {entry['publisher']} | "
            f"{entry['published'] or '_not stated_'} | {entry['chunks']} |"
        )

    lines += [
        "",
        "## Synthetic sources",
        "",
        "**Written by the project team, not by the University.** No published",
        "procedure was found for these, and the prototype needs them to demonstrate",
        "an end-to-end answer. Every passage carries `provenance: synthetic` and is",
        "badged in the interface wherever it is cited. They are illustrative and",
        "must not be relied on by a student.",
        "",
        "| Document | Covers | Passages |",
        "| --- | --- | --- |",
    ]
    for doc_id, entry in sorted(synthetic.items(), key=lambda kv: -kv[1]["chunks"]):
        lines.append(f"| {entry['title']} | `{doc_id}` | {entry['chunks']} |")

    lines += [
        "",
        "### Services answered from synthetic procedures",
        "",
        "| Service | Category |",
        "| --- | --- |",
    ]
    for service in syn_services:
        lines.append(f"| {service['name']} | {service['category']} |")

    lines += [
        "",
        "Everything else in `data/structured/services.json` — offices, rooms, fees,",
        "contacts, turnarounds — is hand-transcribed from a published source and",
        "cites it.",
        "",
    ]

    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / "data-provenance.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Provenance written to {config.DOCS / 'data-provenance.md'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="chunk and report without embedding"
    )
    parser.add_argument(
        "--from-chunks",
        action="store_true",
        help="embed the existing data/chunks.json instead of re-reading data/raw. "
        "Used by the deployment build, which does not carry the raw documents.",
    )
    args = parser.parse_args()

    if args.from_chunks:
        if not config.CHUNKS_FILE.exists():
            print(f"{config.CHUNKS_FILE} not found - run a full build locally first.")
            return 1
        chunks = json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))
        print(f"Loaded {len(chunks):,} chunks from {config.CHUNKS_FILE}")
        embed_and_store(chunks)
        return 0

    chunks = build_chunks()
    if not chunks:
        print("\nNo chunks produced. Run tools/collect_sources.py first.")
        return 1

    config.CHUNKS_FILE.write_text(
        json.dumps(chunks, indent=1, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nChunks written to {config.CHUNKS_FILE}")

    report(chunks)
    write_provenance(chunks)

    if args.dry_run:
        print("\n--dry-run: skipped embedding")
        return 0

    embed_and_store(chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
