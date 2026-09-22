"""Hybrid retrieval over the indexed corpus, with the confidence gate.

Two searches, fused. Vector search catches paraphrase -- "take a year off" finds
deferment text that never uses the word. Keyword search catches the exact tokens
a student quotes and an embedding blurs: "Room D2", "STS", "GH₵60", "1996".
Neither alone is good enough for administrative text, which is full of literal
identifiers wrapped in natural language.

The confidence gate lives here rather than in the caller, because every path to
an answer has to pass through it. Below the threshold, no model is called at all.
"""

from __future__ import annotations

import json
import math
import re
import sys
from functools import lru_cache

from core import config
from core.embed import embed

# Reciprocal-rank fusion constant. 60 is the value from the original RRF paper and
# behaves well here: it keeps a strong hit in one ranker from being outvoted by a
# mediocre showing in the other.
RRF_K = 60


@lru_cache(maxsize=1)
def load_chunks() -> list[dict]:
    if not config.CHUNKS_FILE.exists():
        raise FileNotFoundError(
            f"{config.CHUNKS_FILE} not found - run tools/build_index.py first"
        )
    return json.loads(config.CHUNKS_FILE.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    client = chromadb.PersistentClient(path=str(config.CHROMA))
    return client.get_collection("ugbs_navigator")


def _tokenise(text: str) -> list[str]:
    return re.findall(r"[a-z0-9₵$]+", text.lower())


@lru_cache(maxsize=1)
def _keyword_stats() -> tuple[list[set[str]], dict[str, float]]:
    """Document token sets and IDF weights, computed once at first use."""
    chunks = load_chunks()
    tokensets = [set(_tokenise(c["embed_text"])) for c in chunks]

    frequency: dict[str, int] = {}
    for tokens in tokensets:
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1

    total = len(tokensets)
    idf = {
        token: math.log(1 + total / count)
        for token, count in frequency.items()
    }
    return tokensets, idf


def keyword_search(question: str, top_k: int) -> list[tuple[int, float]]:
    """IDF-weighted overlap. Rare tokens like "1996" or "D2" dominate, which is
    exactly what we want -- they are the terms that identify a specific procedure."""
    tokensets, idf = _keyword_stats()
    query = set(_tokenise(question))

    scored = []
    for index, tokens in enumerate(tokensets):
        shared = query & tokens
        if not shared:
            continue
        scored.append((index, sum(idf.get(t, 0.0) for t in shared)))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


_vector_error: str | None = None


def _report_vector_failure(exc: Exception) -> None:
    global _vector_error
    message = f"{type(exc).__name__}: {exc}"[:300]
    if message != _vector_error:
        print(
            f"WARNING: vector search failed; answering from keyword search only, "
            f"and the confidence gate is unreliable until fixed. {message}\n"
            f"Rebuild the index: python tools/build_index.py --from-chunks",
            file=sys.stderr,
        )
    _vector_error = message


def vector_status() -> tuple[bool, str]:
    """Whether vector search works right now. Used by /health and the evaluation,
    so a keyword-only system cannot pass for the full one."""
    global _vector_error
    try:
        vector_search("transcript", 1)
        _vector_error = None
        return True, ""
    except Exception as exc:  # noqa: BLE001
        _report_vector_failure(exc)
        return False, _vector_error or ""


def vector_search(question: str, top_k: int) -> list[tuple[str, float]]:
    """Cosine similarity over the Chroma index. Returns (chunk_id, similarity)."""
    vector = embed([question])[0].tolist()
    result = _collection().query(query_embeddings=[vector], n_results=top_k)

    ids = result["ids"][0]
    # Chroma returns cosine *distance*; similarity is the useful direction.
    distances = result["distances"][0]
    return [(chunk_id, 1.0 - dist) for chunk_id, dist in zip(ids, distances)]


def retrieve(question: str, top_k: int | None = None) -> dict:
    """Run both searches, fuse, and apply the confidence gate.

    Returns a dict with ``hits``, ``confidence`` and ``passed_gate``. When
    ``passed_gate`` is False the caller must not send anything to a language
    model -- there is nothing trustworthy to ground an answer in.
    """
    top_k = top_k or config.settings.retrieval_top_k
    chunks = load_chunks()
    by_id = {c["chunk_id"]: (i, c) for i, c in enumerate(chunks)}

    # Search wider than we return, so fusion has something to work with.
    pool = max(top_k * 4, 20)

    try:
        vector_hits = vector_search(question, pool)
    except Exception as exc:  # noqa: BLE001
        # No index yet, or Chroma failed to open. Keyword search alone still
        # answers, which keeps the pipeline usable rather than dead -- but it
        # must not be silent. From 19 September this path swallowed an
        # unreadable index for two days: every enquiry scored 1.0, the
        # confidence gate stopped firing, and nothing said so.
        _report_vector_failure(exc)
        vector_hits = []

    keyword_hits = keyword_search(question, pool)

    ranks: dict[str, float] = {}
    best_similarity = 0.0

    for rank, (chunk_id, similarity) in enumerate(vector_hits):
        ranks[chunk_id] = ranks.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
        best_similarity = max(best_similarity, similarity)

    if keyword_hits:
        top_keyword_score = keyword_hits[0][1] or 1.0
        for rank, (index, score) in enumerate(keyword_hits):
            chunk_id = chunks[index]["chunk_id"]
            ranks[chunk_id] = ranks.get(chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
            if not vector_hits:
                # Without vectors, normalised keyword score stands in for similarity.
                best_similarity = max(best_similarity, min(1.0, score / top_keyword_score))

    ordered = sorted(ranks.items(), key=lambda pair: pair[1], reverse=True)[:top_k]

    hits = []
    for chunk_id, fused in ordered:
        if chunk_id not in by_id:
            continue  # index and chunks.json out of step; rebuild fixes it
        _, chunk = by_id[chunk_id]
        similarity = next(
            (s for cid, s in vector_hits if cid == chunk_id), None
        )
        hits.append(
            {
                **{k: v for k, v in chunk.items() if k != "embed_text"},
                "fused_score": round(fused, 5),
                "similarity": round(similarity, 4) if similarity is not None else None,
            }
        )

    confidence = round(best_similarity, 4)
    threshold = config.settings.confidence_threshold

    return {
        "hits": hits,
        "confidence": confidence,
        "threshold": threshold,
        "passed_gate": bool(hits) and confidence >= threshold,
        "vector_available": bool(vector_hits),
    }
