"""Talk to the language model. One interface, four providers.

The model writes the reply; it never supplies University facts. Offices, rooms,
fees, dates and steps reach it as MATERIAL assembled by `core.chat` from the
service catalogue and retrieved passages -- see CLAUDE.md section 3.

Callers never branch on the provider. If provider-specific logic appears outside
this module, that is the bug. The one decision callers do make is what to say
when there is no model: they pass a `fallback`, and this module decides whether
it is needed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache

from core import config


def llm_available() -> bool:
    """True when a generative model is configured and has what it needs to run."""
    available, _ = config.settings.provider_is_available
    return available and config.settings.llm_provider != "extractive"


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _groq_client():
    """Groq, through its OpenAI-compatible endpoint.

    Deliberately not the `groq` SDK: the `openai` package is already in the lab
    environment and Groq speaks the same protocol, so this adds a provider
    without adding a dependency every teammate has to install.

    Cached, so every call reuses one connection pool. Building a new client per
    call paid a fresh TLS handshake to Groq each time -- measured at 6.7s on a
    cold first call, against 0.8s once the connection is open.
    """
    from openai import OpenAI

    return OpenAI(
        api_key=config.settings.groq_api_key,
        base_url="https://api.groq.com/openai/v1",
    )


def _groq_extra(model: str) -> dict:
    # gpt-oss reasons before it writes, and those tokens come out of the same
    # budget as the reply. Measured at 4.62s by default against 0.50s on "low"
    # for an identical answer: the model is phrasing material it was handed, not
    # solving a problem. Only gpt-oss accepts the parameter.
    return {"reasoning_effort": "low"} if "gpt-oss" in model else {}


def _gemini_parts(messages: list[dict]):
    from google.genai import types

    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in messages
        if m["role"] != "system"
    ]
    return system, contents


def _stream_provider(
    messages: list[dict], max_tokens: int, temperature: float, fast: bool = False
) -> Iterator[str]:
    provider = config.settings.llm_provider

    if provider == "groq":
        from openai import RateLimitError

        primary = config.settings.groq_fast_model if fast else config.settings.groq_model
        spare = config.settings.groq_fast_model

        # The free tier allows 8,000 tokens a minute per model -- two or three
        # answers. By default the SDK meets a 429 by silently waiting and
        # retrying, which in the evaluation showed up as 10-15s stalls. The two
        # models have separate budgets, so a throttled large model hands over
        # to the small one at once instead of making the student wait.
        client = _groq_client().with_options(max_retries=0)

        def open_stream(model: str):
            return client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
                **_groq_extra(model),
            )

        try:
            stream = open_stream(primary)
        except RateLimitError:
            if primary == spare:
                raise
            stream = open_stream(spare)

        for chunk in stream:
            if not chunk.choices:
                continue
            # Reasoning arrives on a separate field and is deliberately dropped.
            piece = getattr(chunk.choices[0].delta, "content", None)
            if piece:
                yield piece
        return

    if provider == "gemini":
        from google import genai
        from google.genai import types

        system, contents = _gemini_parts(messages)
        client = genai.Client(api_key=config.settings.gemini_api_key)
        for chunk in client.models.generate_content_stream(
            model=config.settings.gemini_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system or None,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        ):
            if chunk.text:
                yield chunk.text
        return

    if provider == "ollama":
        import ollama

        client = ollama.Client(host=config.settings.ollama_host)
        for part in client.chat(
            model=config.settings.ollama_model,
            messages=messages,
            stream=True,
            options={"temperature": temperature, "num_predict": max_tokens},
        ):
            message = part["message"] if isinstance(part, dict) else part.message
            piece = message["content"] if isinstance(message, dict) else message.content
            if piece:
                yield piece
        return

    raise RuntimeError(f"No generative model behind LLM_PROVIDER={provider!r}")


def warm() -> str:
    """Open the model connection before the first student arrives.

    Called at server start-up. The first call to a hosted model pays for DNS,
    TLS and connection setup; paying it here means the first question in a
    demo is as fast as the tenth. Returns a short status line, never raises.

    Both models are warmed. Warming only the fast one left the answer model
    cold: in the held-out evaluation the first answer took 44 seconds and every
    later one took under 4 -- which in a demo is the opening question.
    """
    if not llm_available():
        return "no model to warm"

    warmed, failures = [], []
    # Only Groq splits triage and answers across two models; elsewhere one call
    # warms the single model both paths use.
    for fast in ((True, False) if config.settings.llm_provider == "groq" else (True,)):
        try:
            complete([{"role": "user", "content": "Reply with OK."}], fast=fast, max_tokens=20)
            warmed.append("triage" if fast else "answers")
        except Exception as exc:  # noqa: BLE001 - start-up must not depend on the network
            failures.append(f"{'triage' if fast else 'answers'}: {type(exc).__name__}")

    if not warmed:
        return f"warm-up failed ({'; '.join(failures)}); first question will be slower"
    note = f"; {' and '.join(failures)} still cold" if failures else ""
    return f"{config.settings.llm_provider} connection open for {' and '.join(warmed)}{note}"


def complete(
    messages: list[dict],
    *,
    fast: bool = False,
    max_tokens: int = 400,
    temperature: float = 0.0,
) -> str:
    """One non-streaming call. Used for triage, where nothing is shown to the
    student until the answer is known anyway."""
    if config.settings.llm_provider == "groq":
        model = config.settings.groq_fast_model if fast else config.settings.groq_model
        # No silent retries: every caller of complete() has a deterministic
        # fallback, and using it beats waiting out a rate limit.
        completion = _groq_client().with_options(max_retries=0).chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **_groq_extra(model),
        )
        return (completion.choices[0].message.content or "").strip()

    return "".join(_stream_provider(messages, max_tokens, temperature)).strip()


def reply_stream(
    messages: list[dict],
    fallback: str,
    *,
    meta: dict,
    max_tokens: int = 1500,
    temperature: float = 0.3,
    fast: bool = False,
) -> Iterator[str]:
    """Yield the reply as it is written.

    With no model configured, or if the model fails before writing anything, the
    `fallback` text is yielded instead -- a misconfigured key or a dropped
    connection in the middle of a demo must degrade, not crash. `meta["provider"]`
    records which one the student actually got.
    """
    if not llm_available():
        meta["provider"] = "extractive"
        yield fallback
        return

    written = False
    try:
        for piece in undash_stream(_stream_provider(messages, max_tokens, temperature, fast)):
            written = True
            yield piece
        if not written:
            # A reasoning model that spends its whole budget thinking returns no
            # content at all. Treat that as a failure, not as an empty answer.
            raise RuntimeError("model returned no content")
        meta["provider"] = config.settings.llm_provider
    except Exception as exc:  # noqa: BLE001 - every failure must degrade
        if written:
            meta["provider"] = f"{config.settings.llm_provider} (interrupted)"
            yield (
                "\n\n_The connection to the language model dropped, so this answer "
                "may be incomplete._"
            )
        else:
            meta["provider"] = f"extractive (fell back: {type(exc).__name__})"
            yield fallback


# --------------------------------------------------------------------------
# Punctuation
#
# Replies should read as natural sentences, without em dashes. The prompt says
# so, but models copy the punctuation of the text they are given -- the corpus
# holds a hundred em dashes -- and lists come back as "**Label** – text". So
# the model's words are cleaned on the way out. Only model output: quoted
# passages and the no-model fallback are never altered.
# --------------------------------------------------------------------------

_DASHES = "–—"

# The model does not always put an ordinary space beside a dash: gpt-oss often
# uses a narrow no-break space (U+202F), which slipped past patterns written
# with [ \t] alone and reached the interface checks. S matches any of them.
_S = "[ \t    ]"

_BOLD_DASH = re.compile(rf"\*\*{_S}*[–—]{_S}*")     # "**Label** – text"
# A range: "10 – 12", "8am – 5pm", "Monday – Friday". Read as "to", not a pause.
# A tight en dash ("1–3") is the ordinary way to write a range and stays.
_RANGE_DASH = re.compile(
    rf"(\d|[ap]\.?m\.?|day)"
    rf"(?:{_S}+[–—]{_S}*|{_S}*[–—]{_S}+|—)"
    r"(\d|mon|tue|wed|thu|fri|sat|sun)",
    re.IGNORECASE,
)
_LINE_DASH = re.compile(rf"(?m)^({_S}*)[–—]{_S}+")    # a dash used as a bullet
_SPACED_DASH = re.compile(rf"{_S}*[–—]{_S}+|{_S}+[–—]{_S}*")
_TIGHT_EM = re.compile(r"(\w)—(\w)")                        # "fees—including"


def undash(text: str) -> str:
    """Turn dashes used as punctuation into the punctuation they stand for.

    Number ranges written without spaces ("1–3") are left alone.
    """
    text = _BOLD_DASH.sub("**: ", text)
    text = _RANGE_DASH.sub(r"\1 to \2", text)
    text = _LINE_DASH.sub(r"\1- ", text)
    text = _SPACED_DASH.sub(", ", text)
    return _TIGHT_EM.sub(r"\1, \2", text)


def _safe_cut(text: str) -> int:
    """The last point where the stream can be cut without splitting a dash
    pattern: just after whitespace, where the next character is not a dash and
    the last visible character before it is neither a dash nor bold markup."""
    for i in range(len(text) - 1, 0, -1):
        if not text[i - 1].isspace() or text[i].isspace() or text[i] in _DASHES:
            continue
        before = text[:i].rstrip()
        if before and before[-1] not in _DASHES and before[-1] != "*":
            return i
    return 0


def undash_stream(pieces: Iterator[str]) -> Iterator[str]:
    """`undash`, applied to a stream. Holds back only the few characters after
    the last safe cut, so the reply still appears word by word."""
    pending = ""
    for piece in pieces:
        pending += piece
        cut = _safe_cut(pending)
        if cut:
            yield undash(pending[:cut])
            pending = pending[cut:]
    if pending:
        yield undash(pending)


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------

# Some models emit their own citation syntax regardless of instruction. gpt-oss
# reaches for the OpenAI browsing forms, both 【1†L1-L4】 and a bare 【2】, so the
# dagger section is optional. Rewriting to [1] keeps one format on screen and
# lets the parser below find the references at all.
_ODD_CITATION = re.compile(r"【\s*(\d+)\s*(?:†[^】]*)?】")


def normalise_citations(text: str) -> str:
    text = _ODD_CITATION.sub(lambda m: f"[{m.group(1)}]", text)
    # Collapse the runs that substitution leaves behind: "[1][2]" -> "[1] [2]".
    return re.sub(r"\]\s*\[", "] [", text)


def used_citations(text: str, passages: list[dict]) -> list[dict]:
    """Return only the passages the reply actually cites.

    Listing every retrieved passage as a "source" would be dishonest -- most did
    not contribute. If nothing was cited, the top passage stands in so the
    student still has something to check the answer against.
    """
    referenced = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    chosen = [passages[i - 1] for i in sorted(referenced) if 1 <= i <= len(passages)]

    if not chosen and passages:
        chosen = passages[:1]

    return [
        {
            "index": passages.index(hit) + 1,
            "doc_title": hit["doc_title"],
            "section": hit.get("section") or "",
            "page": hit.get("page"),
            "source_url": hit.get("source_url", ""),
            "provenance": hit.get("provenance", "real"),
            "published_date": hit.get("published_date", ""),
            "publisher": hit.get("publisher", ""),
            "similarity": hit.get("similarity"),
        }
        for hit in chosen
    ]
