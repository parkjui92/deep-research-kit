import json

import httpx
import pytest

from deep_research import providers


def test_api_parses_json_and_does_not_save_credentials(monkeypatch):
    monkeypatch.setenv("DRK_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("DRK_MODEL", "test-model")
    monkeypatch.setenv("DRK_API_KEY", "test-secret")
    def post(url, **kwargs):
        assert url == "https://example.test/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer test-secret"
        assert "test-secret" not in json.dumps(kwargs["json"])
        assert kwargs["json"]["response_format"] == {"type": "json_object"}
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"rows": []}'}}]},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    assert providers.completion({"instructions": "Return JSON"}) == {"rows": []}


def test_api_error_does_not_echo_provider_body_or_key(monkeypatch):
    monkeypatch.setenv("DRK_API_BASE", "https://example.test/v1")
    monkeypatch.setenv("DRK_MODEL", "test-model")
    def post(url, **kwargs):
        return httpx.Response(429, text="private provider details",
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(ValueError, match="HTTP 429") as error:
        providers.completion({"instructions": "Return JSON"})
    assert "private" not in str(error.value)
