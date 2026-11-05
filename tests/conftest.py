"""Tests never pick up a real OpenAlex key from the machine they run on."""
import pytest


@pytest.fixture(autouse=True)
def _no_real_openalex_key(monkeypatch):
    from deep_research import providers
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    monkeypatch.setattr(providers, "_key_files", lambda: [])
    providers.use_session_key("")
    yield
    providers.use_session_key("")
