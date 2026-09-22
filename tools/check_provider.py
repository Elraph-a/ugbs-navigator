"""Verify the configured LLM provider before relying on it.

    ..\\AI_Lab\\Scripts\\python.exe tools\\check_provider.py
    ..\\AI_Lab\\Scripts\\python.exe tools\\check_provider.py --provider groq

Answers three questions in order, because each one fails differently:

  1. Is a key configured at all?
  2. Does the key work, and which models does this account actually have?
  3. Does the configured model respond, and how fast?

Model ids move. Groq in particular retires and renames models, so this lists
what the account can really use rather than trusting a default written months
ago. The key is never printed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config

PROBE = (
    "Reply with exactly the word READY and nothing else."
)


def mask(key: str) -> str:
    if not key:
        return "(empty)"
    return f"{key[:4]}…{key[-4:]} ({len(key)} chars)"


def check_groq(model: str) -> int:
    from openai import OpenAI

    key = config.settings.groq_api_key
    print(f"  key            {mask(key)}")
    if not key:
        print("\n  No GROQ_API_KEY. Put it in .env:  GROQ_API_KEY=gsk_...")
        return 1

    client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")

    try:
        available = sorted(m.id for m in client.models.list().data)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  Key rejected or unreachable: {type(exc).__name__}: {exc}")
        return 1

    print(f"\n  {len(available)} models available to this account:\n")
    for name in available:
        marker = "  <- configured" if name == model else ""
        print(f"    {name}{marker}")

    if model not in available:
        print(
            f"\n  WARNING: GROQ_MODEL={model!r} is not in that list.\n"
            "  Set GROQ_MODEL in .env to one of the ids above."
        )
        return 1

    # Generous budget: a reasoning model spends tokens thinking before it writes
    # anything, so a tight cap returns empty content and looks like a dead key.
    extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}

    started = time.time()
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROBE}],
            temperature=0,
            max_tokens=300,
            **extra,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"\n  Model call failed: {type(exc).__name__}: {exc}")
        return 1

    elapsed = time.time() - started
    reply = (completion.choices[0].message.content or "").strip()
    used = completion.usage.completion_tokens

    print(f"\n  probe reply    {reply!r}")
    print(f"  tokens used    {used}")
    print(f"  round trip     {elapsed:.2f}s")

    if not reply:
        print("\n  Model answered with empty content — it spent the whole budget")
        print("  reasoning. Raise max_tokens or lower reasoning_effort.")
        return 1
    return 0


def check_gemini(model: str) -> int:
    from google import genai

    key = config.settings.gemini_api_key
    print(f"  key            {mask(key)}")
    if not key:
        print("\n  No GEMINI_API_KEY. Put it in .env:  GEMINI_API_KEY=...")
        return 1

    client = genai.Client(api_key=key)
    started = time.time()
    try:
        response = client.models.generate_content(model=model, contents=PROBE)
    except Exception as exc:  # noqa: BLE001
        print(f"\n  Model call failed: {type(exc).__name__}: {exc}")
        return 1

    print(f"\n  probe reply    {(response.text or '').strip()!r}")
    print(f"  round trip     {time.time() - started:.2f}s")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", help="override LLM_PROVIDER for this check")
    parser.add_argument("--model", help="override the model id for this check")
    args = parser.parse_args()

    provider = (args.provider or config.settings.llm_provider).lower()

    print(f"\nprovider         {provider}")

    if provider == "extractive":
        print("  Nothing to check: extractive calls no model.")
        return 0

    if provider == "groq":
        return check_groq(args.model or config.settings.groq_model)
    if provider == "gemini":
        return check_gemini(args.model or config.settings.gemini_model)

    if provider == "ollama":
        import ollama

        client = ollama.Client(host=config.settings.ollama_host)
        try:
            names = [m.get("model") for m in client.list().get("models", [])]
        except Exception as exc:  # noqa: BLE001
            print(f"  Ollama unreachable at {config.settings.ollama_host}: {exc}")
            return 1
        print(f"  models pulled  {names or 'none'}")
        return 0

    print(f"  Unknown provider {provider!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
