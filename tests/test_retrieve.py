"""A broken vector index must be loud, never silent.

From 19 September an unreadable Chroma index made every search fall back to
keywords without a word: confidence read 1.0 on every question and the gate
stopped declining off-topic ones. These tests pin the behaviour that replaced it.
"""

from core import retrieve


def _broken(*_args, **_kwargs):
    raise RuntimeError("index unreadable")


def test_fallback_warns_and_is_reported(monkeypatch, capsys):
    monkeypatch.setattr(retrieve, "vector_search", _broken)
    monkeypatch.setattr(retrieve, "_vector_error", None)

    result = retrieve.retrieve("how do I request a transcript")

    assert result["vector_available"] is False
    assert "vector search failed" in capsys.readouterr().err


def test_vector_status_reports_failure(monkeypatch):
    monkeypatch.setattr(retrieve, "vector_search", _broken)

    ok, note = retrieve.vector_status()

    assert ok is False
    assert "index unreadable" in note
