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


def _fake_cli(monkeypatch, handler):
    import shutil
    import subprocess
    calls = []
    monkeypatch.setattr(shutil, "which", lambda name: "claude")
    def run(args, **kwargs):
        calls.append((args, kwargs))
        code, out = handler(args)
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def test_child_env_drops_parent_session_but_keeps_user_settings(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "parent-session")
    monkeypatch.setenv("CLAUDE_CODE_GIT_BASH_PATH", r"D:\Git\bin\bash.exe")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/home/me/.claude-work")
    env = providers.claude_env()
    assert "CLAUDECODE" not in env and "CLAUDE_CODE_SESSION_ID" not in env
    assert env["CLAUDE_CODE_GIT_BASH_PATH"] == r"D:\Git\bin\bash.exe"
    assert env["CLAUDE_CONFIG_DIR"] == "/home/me/.claude-work"


def test_status_check_does_not_call_the_model(monkeypatch):
    calls = _fake_cli(monkeypatch, lambda args: (0, "2.1.309 (Claude Code)"))
    assert providers.claude_code_status() == {"available": True, "reason": ""}
    assert calls[0][0][1:] == ["--version"] and "-p" not in calls[0][0]


def test_signed_out_run_says_how_to_log_in(tmp_path, monkeypatch):
    from deep_research.project import Project
    p = Project(tmp_path / "projects" / "research").initialize()
    _fake_cli(monkeypatch, lambda args: (1, "Not logged in · Please run /login"))
    with pytest.raises(ValueError, match="/login 한 뒤"):
        providers.run_claude_code(p, "r_1")


def test_second_agent_run_on_same_project_is_refused(tmp_path, monkeypatch):
    from deep_research.project import Project
    p = Project(tmp_path / "projects" / "research").initialize()
    seen = {}
    def handler(args):
        seen["busy"] = providers.agent_busy(p)
        with pytest.raises(ValueError, match="이미 진행 중"):
            providers.run_claude_code(p, "r_2")
        return 0, "done"
    _fake_cli(monkeypatch, handler)
    assert not providers.agent_busy(p)
    assert providers.run_claude_code(p, "r_1") == "done"
    assert seen["busy"] is True and not providers.agent_busy(p)
