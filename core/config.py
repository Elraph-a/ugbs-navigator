"""Project paths and settings, loaded once from the environment.

Secrets live in ``.env`` at the project root and nowhere else. Everything that
needs a path should import it from here rather than recomputing it, so moving a
directory is a one-line change.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA = PROJECT_ROOT / "data"
RAW = DATA / "raw"
SYNTHETIC = DATA / "synthetic"
STRUCTURED = DATA / "structured"
CHROMA = DATA / "chroma"
DB_PATH = DATA / "enquiries.db"
TMP = PROJECT_ROOT / ".tmp"
DOCS = PROJECT_ROOT / "docs"
TESTS = PROJECT_ROOT / "tests"

OFFICES_FILE = STRUCTURED / "offices.json"
SERVICES_FILE = STRUCTURED / "services.json"
CHUNKS_FILE = DATA / "chunks.json"
SOURCES_FILE = RAW / "SOURCES.md"


def _load_dotenv() -> None:
    """Read ``.env`` into os.environ without overriding real environment vars.

    We parse it by hand rather than depending on python-dotenv so that the tools
    still run on a machine where only the standard library is available.
    """
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # A real environment variable always wins over the file.
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _get(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    gemini_api_key: str
    gemini_model: str
    groq_api_key: str
    groq_model: str
    groq_fast_model: str
    ollama_model: str
    ollama_host: str
    embedding_model: str
    retrieval_top_k: int
    confidence_threshold: float
    retention_days: int
    # One shared password for the administrative dashboard. Not accounts: it
    # keeps the service data out of casual view, and the API checks it so the
    # page cannot simply be bypassed. Empty means the dashboard is unprotected,
    # which the API refuses to serve rather than assume is intentional.
    admin_password: str

    @property
    def provider_is_available(self) -> tuple[bool, str]:
        """Whether the configured provider can actually run, and why not."""
        if self.llm_provider == "gemini" and not self.gemini_api_key:
            return False, (
                "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty. "
                "Get a free key at https://aistudio.google.com/apikey, or set "
                "LLM_PROVIDER=extractive to run without any model."
            )
        if self.llm_provider == "groq" and not self.groq_api_key:
            return False, (
                "LLM_PROVIDER=groq but GROQ_API_KEY is empty. "
                "Get a free key at https://console.groq.com/keys, or set "
                "LLM_PROVIDER=extractive to run without any model."
            )
        if self.llm_provider not in {"gemini", "groq", "ollama", "extractive"}:
            return False, f"Unknown LLM_PROVIDER {self.llm_provider!r}"
        return True, ""


def load_settings() -> Settings:
    return Settings(
        llm_provider=_get("LLM_PROVIDER", "extractive").lower(),
        gemini_api_key=_get("GEMINI_API_KEY", ""),
        gemini_model=_get("GEMINI_MODEL", "gemini-2.5-flash"),
        groq_api_key=_get("GROQ_API_KEY", ""),
        # Confirm against `tools/check_provider.py` rather than trusting this
        # default: Groq retires and renames models fairly often.
        groq_model=_get("GROQ_MODEL", "openai/gpt-oss-120b"),
        # Triage (is this a question? rewrite the follow-up) is a short
        # classification, so it runs on the smaller model to keep the time before
        # the first word appears down.
        groq_fast_model=_get("GROQ_FAST_MODEL", "openai/gpt-oss-20b"),
        ollama_model=_get("OLLAMA_MODEL", "qwen2.5:3b"),
        ollama_host=_get("OLLAMA_HOST", "http://localhost:11434"),
        embedding_model=_get(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        ),
        retrieval_top_k=_get_int("RETRIEVAL_TOP_K", 6),
        # Tuned on tests/gold_questions.yaml: genuine enquiries retrieve at
        # 0.46-0.68, off-topic ones at 0.33-0.41. Raising this from 0.35 took
        # refusal precision from 70% to 100% at the cost of one in-scope answer.
        confidence_threshold=_get_float("CONFIDENCE_THRESHOLD", 0.42),
        retention_days=_get_int("RETENTION_DAYS", 180),
        admin_password=_get("ADMIN_PASSWORD", ""),
    )


settings = load_settings()


# The enquiry categories the router and analytics both work from. Kept here
# because the knowledge base, the router and the dashboard must agree on them.
CATEGORIES = [
    "registration",
    "transcripts",
    "examinations",
    "results_and_records",
    "graduation",
    "deferment_and_withdrawal",
    "fees_and_finance",
    "student_id",
    "admissions",
    "it_and_portals",
    "course_advising",
    "welfare_and_support",
]
