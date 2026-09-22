"""FastAPI service for the UGBS Service Navigator.

    ..\\AI_Lab\\Scripts\\python.exe -m uvicorn backend.app.main:app --reload --port 8000

Thin on purpose. The conversation, retrieval, routing and analytics all live in
core/ so the evaluation tool exercises exactly the same code this serves.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core import analytics, config, store
from core.chat import answer as run_answer
from core.chat import run_chat, should_log
from core.router import load_catalogue


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    # The whole conversation so far, oldest first, ending with the new message.
    # The server keeps no session: the conversation lives in the student's
    # browser tab and nowhere else, which is the privacy promise in CLAUDE.md.
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()
    purged = store.purge_expired()
    if purged:
        print(f"Purged {purged} enquiries past the {config.settings.retention_days}-day retention window")

    # Warm the embedding model now rather than inside the first request, so the
    # first question in a demo is not the one that pays for loading it.
    try:
        from core import embed
        from core.retrieve import load_chunks

        load_chunks()
        embed.warm()
        print("Embedding model and chunk index loaded")
    except Exception as exc:  # noqa: BLE001
        print(f"Warm-up skipped: {type(exc).__name__}: {exc}")
        print("Run tools/build_index.py if retrieval is expected to work.")

    available, reason = config.settings.provider_is_available
    print(f"LLM provider: {config.settings.llm_provider}" + ("" if available else f"  ({reason})"))

    # Same reasoning as the embedding warm-up: pay connection setup now, not
    # in front of an audience.
    from core.generate import warm

    print(f"Model: {warm()}")

    # The before/after analysis routes the whole simulated semester twice. Doing
    # it now caches it, so the dashboard opens instantly during a demo.
    try:
        analytics.dashboard()
        print("Analytics computed")
    except Exception as exc:  # noqa: BLE001
        print(f"Analytics warm-up skipped: {type(exc).__name__}: {exc}")

    yield


app = FastAPI(
    title="UGBS Service Navigator",
    description="A conversational assistant for University of Ghana Business School administrative procedures.",
    version="0.2.0",
    lifespan=lifespan,
)

# Local development and the hosted frontend are always allowed; CORS_ORIGINS
# adds more, comma-separated. Origins are public addresses, not secrets.
_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ugbs-navigator.vercel.app",
] + [
    o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Rate limiting
#
# A public deployment runs on a free-tier model key: anyone who finds the URL
# could spend its quota, and the host allows only 8,000 tokens a minute. Two
# sliding one-minute windows protect it: one per visitor, one for everyone.
#
# Visitors are told apart by a hash of their address, held in memory for at
# most a minute and never written anywhere -- the enquiry log still stores no
# identifier, which is the privacy promise in CLAUDE.md.
# ---------------------------------------------------------------------------

PER_VISITOR_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_VISITOR", "10"))
TOTAL_PER_MINUTE = int(os.environ.get("RATE_LIMIT_TOTAL", "40"))

_windows: dict[str, deque] = {}
_total: deque = deque()
_lock = threading.Lock()


def _visitor(request: Request) -> str:
    # Behind a proxy (Hugging Face, Vercel) the client is the first forwarded hop.
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",")[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(address.encode()).hexdigest()[:16]


def _allow(request: Request) -> bool:
    now = time.monotonic()
    key = _visitor(request)
    with _lock:
        for window in (_total, _windows.setdefault(key, deque())):
            while window and now - window[0] > 60:
                window.popleft()
        visitor = _windows[key]
        if len(visitor) >= PER_VISITOR_PER_MINUTE or len(_total) >= TOTAL_PER_MINUTE:
            return False
        visitor.append(now)
        _total.append(now)
        # Forget visitors whose window has emptied, so the table cannot grow.
        for stale in [k for k, w in _windows.items() if not w]:
            del _windows[stale]
    return True


def _check_rate(request: Request) -> None:
    if not _allow(request):
        raise HTTPException(
            status_code=429,
            detail="Too many questions in a short time. Please wait a minute and try again.",
        )


def _event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def _stream(messages: list[dict]) -> StreamingResponse:
    """Run one turn and stream it as server-sent events.

    The step events are the agent's real control flow and the delta events are
    the reply as it is written, so the interface shows what is actually
    happening rather than a progress animation timed to look busy.
    """

    def events():
        final: dict | None = None
        try:
            for event in run_chat(messages):
                if event["type"] == "done":
                    final = event["response"]
                yield _event(event)
        except FileNotFoundError as exc:
            yield _event(
                {
                    "type": "error",
                    "message": str(exc),
                    "hint": "Run tools/build_index.py to create the index.",
                }
            )
            return
        except Exception as exc:  # noqa: BLE001 - a stream must end with a reason
            yield _event(
                {
                    "type": "error",
                    "message": "Something went wrong while answering.",
                    "hint": f"{type(exc).__name__}: {exc}"[:300],
                }
            )
            return

        # Refusals are logged too -- they are the input to the knowledge-gap
        # register. Small talk is not.
        if final and should_log(final):
            store.log_enquiry(final, simulated=False)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
def health() -> dict:
    from core.retrieve import vector_status

    available, reason = config.settings.provider_is_available
    vectors, vector_note = vector_status()
    return {
        # "degraded" when retrieval has fallen back to keywords: it still
        # answers, but the confidence gate cannot be trusted.
        "status": "ok" if vectors else "degraded",
        "provider": config.settings.llm_provider,
        "provider_available": available,
        "provider_note": reason,
        "vector_search": vectors,
        "vector_note": vector_note,
        "enquiries": store.count(),
    }


@app.post("/chat/stream")
def chat_stream(request: ChatRequest, http: Request) -> StreamingResponse:
    """One turn of a conversation, streamed."""
    _check_rate(http)
    messages = [m.model_dump() for m in request.messages]
    if messages[-1]["role"] != "user":
        raise HTTPException(status_code=422, detail="The last message must be from the student.")
    return _stream(messages)


@app.post("/ask/stream")
def ask_stream(request: AskRequest, http: Request) -> StreamingResponse:
    """A single question with no history. Kept for demo links and older clients."""
    _check_rate(http)
    return _stream([{"role": "user", "content": request.question}])


@app.post("/ask")
def ask(request: AskRequest, http: Request) -> dict:
    """A single question, final response only."""
    _check_rate(http)
    try:
        response = run_answer(request.question)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"{exc}. Run tools/build_index.py to create the index.",
        ) from exc

    if should_log(response):
        store.log_enquiry(response, simulated=False)
    return response


@app.get("/analytics")
def get_analytics() -> dict:
    return analytics.dashboard()


@app.get("/services")
def services() -> dict:
    """The service catalogue, for the interface and the admin view."""
    catalogue, offices = load_catalogue()
    return {
        "services": [
            {
                "id": s["id"],
                "name": s["name"],
                "category": s["category"],
                "documented": s.get("documented", False),
                "office": offices.get(s["office"], {}).get("short_name"),
            }
            for s in catalogue.values()
        ],
        "offices": list(offices.values()),
    }
