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


def _extracted_project(tmp_path):
    import io

    from reportlab.pdfgen import canvas

    from deep_research import workflow as w
    from deep_research.project import Project, read_json
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 750, "A randomized study found 19 percent longer completion time.")
    pdf.showPage()
    pdf.save()
    p = Project(tmp_path / "projects" / "research").initialize()
    sid = p.add_pdf(buf.getvalue(), "paper.pdf", "Test study")
    p.screen(sid, "include", "Observed task outcome")
    run = w.prepare(p)
    request = read_json(p.run_dir(run) / "requests" / (sid + ".json"))
    passage = request["passages"][0]
    w.import_extraction(p, run, {"request_id": request["request_id"], "rows": [
        {"source_id": sid, "field_id": f["id"], "value": "Test finding",
         "quotes": [{"passage_id": passage["id"], "quote": passage["text"]}]}
        for f in request["config"]["fields"]]})
    return p, run


def test_agent_tools_have_no_code_execution_or_review_writes(tmp_path):
    p, run = _extracted_project(tmp_path)
    tools = providers.agent_tools(p, run)
    assert not any("python" in t or t in {"Write", "Edit"} for t in tools)
    edits = [t for t in tools if t.startswith("Edit(")]
    assert edits == [f"Edit(./projects/research/runs/{run}/drafts/**)"]
    assert (p.run_dir(run) / "drafts").is_dir()


def _fake_claude(monkeypatch, effect):
    import shutil
    import subprocess
    monkeypatch.setattr(shutil, "which", lambda name: "claude")
    def run(args, **kwargs):
        effect()
        return subprocess.CompletedProcess(args, 0, stdout="3", stderr="")
    monkeypatch.setattr(subprocess, "run", run)


def test_agent_run_cannot_change_human_review_state(tmp_path, monkeypatch):
    from deep_research import workflow as w
    from deep_research.project import read_json, write_json
    p, run = _extracted_project(tmp_path)
    first = w.evidence(p, run)[0]["id"]
    w.review(p, run, first, "hold", "Needs the table", "Person")
    folder = p.run_dir(run)
    reviews_before = (folder / "reviews.json").read_text(encoding="utf-8")

    def tamper():
        rows = read_json(folder / "evidence.json")
        for row in rows:
            row["review"] = {"status": "accept", "note": "ok", "reviewer": "Person"}
        write_json(folder / "evidence.json", rows)
        write_json(folder / "reviews.json", [{"evidence_id": first, "status": "accept"}])
        manifest = read_json(folder / "run.json")
        manifest["review_revision"] += 5
        write_json(folder / "run.json", manifest)

    _fake_claude(monkeypatch, tamper)
    with pytest.raises(ValueError, match="검토 기록이 바뀌어"):
        providers.run_claude_code(p, run)
    rows = {e["id"]: e for e in w.evidence(p, run)}
    assert rows[first]["review"]["status"] == "hold"
    assert all(e["review"]["status"] == "pending" for i, e in rows.items() if i != first)
    assert (folder / "reviews.json").read_text(encoding="utf-8") == reviews_before
    assert w.manifest(p, run)["review_revision"] == 1
    assert w.accepted(p, run) == []


def test_agent_run_without_review_changes_passes(tmp_path, monkeypatch):
    p, run = _extracted_project(tmp_path)
    _fake_claude(monkeypatch, lambda: None)
    assert providers.run_claude_code(p, run) == "3"


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
    p, run = _extracted_project(tmp_path)
    _fake_cli(monkeypatch, lambda args: (1, "Not logged in · Please run /login"))
    with pytest.raises(ValueError, match="/login 한 뒤"):
        providers.run_claude_code(p, run)


def test_second_agent_run_on_same_project_is_refused(tmp_path, monkeypatch):
    p, run = _extracted_project(tmp_path)
    seen = {}
    def handler(args):
        seen["busy"] = providers.agent_busy(p)
        with pytest.raises(ValueError, match="이미 진행 중"):
            providers.run_claude_code(p, run)
        return 0, "done"
    _fake_cli(monkeypatch, handler)
    assert not providers.agent_busy(p)
    assert providers.run_claude_code(p, run) == "done"
    assert seen["busy"] is True and not providers.agent_busy(p)


def _prepared_project(tmp_path):
    """A run waiting for extraction: requests written, no responses yet."""
    import io

    from reportlab.pdfgen import canvas

    from deep_research import workflow as w
    from deep_research.project import Project
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 750, "A randomized study found 19 percent longer completion time.")
    pdf.showPage()
    pdf.save()
    p = Project(tmp_path / "projects" / "research").initialize()
    sid = p.add_pdf(buf.getvalue(), "paper.pdf", "Test study")
    p.screen(sid, "include", "Observed task outcome")
    return p, w.prepare(p)


FAKE_CLAUDE = """import json, os, sys
with open(os.environ["DRK_FAKE_LOG"], "w", encoding="utf-8") as log:
    json.dump({"argv": sys.argv[1:]}, log, ensure_ascii=False)
sys.stdout.buffer.write("요청을 받았지만 파일 쓰기 권한이 필요합니다.".encode("utf-8"))
sys.stderr.buffer.write(os.environ.get("DRK_FAKE_STDERR", "").encode("utf-8"))
sys.exit(int(os.environ.get("DRK_FAKE_EXIT", "0")))
"""


def _fake_executable(tmp_path, monkeypatch):
    """A real `claude` on PATH. On Windows it is a .cmd file, the way npm installs Claude Code,
    so the arguments pass through cmd.exe exactly as in a classroom PC (#32)."""
    import os
    import sys
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "fake_claude.py").write_text(FAKE_CLAUDE, encoding="utf-8")
    if os.name == "nt":
        (bindir / "claude.cmd").write_text(f'@"{sys.executable}" "%~dp0fake_claude.py" %*\r\n', encoding="utf-8")
    else:
        launcher = bindir / "claude"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$(dirname "$0")/fake_claude.py" "$@"\n', encoding="utf-8")
        launcher.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir) + os.pathsep + os.environ.get("PATH", ""))
    log = tmp_path / "fake-claude.json"
    monkeypatch.setenv("DRK_FAKE_LOG", str(log))
    return log


def test_prompt_is_one_line_and_every_option_reaches_claude(tmp_path, monkeypatch):
    from deep_research.project import read_json
    p, run = _prepared_project(tmp_path)
    log = _fake_executable(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="0편의 결과만 저장"):
        providers.run_claude_code(p, run)
    argv = read_json(log)["argv"]
    assert argv[0] == "-p" and argv[1].startswith("/deep-research ")
    assert all("\n" not in a for a in argv)
    assert f"프로젝트 「projects/research」 · 실행 「{run}」" in argv[1]
    assert "--allowedTools" in argv and "--add-dir" in argv and "--output-format" in argv
    assert f"Edit(./projects/research/runs/{run}/drafts/**)" in argv


def test_saved_nothing_is_not_reported_as_done(tmp_path, monkeypatch):
    p, run = _prepared_project(tmp_path)
    _fake_executable(tmp_path, monkeypatch)
    with pytest.raises(ValueError) as error:
        providers.run_claude_code(p, run)
    # The person sees Claude's last words, decoded, and the other way to continue.
    assert "파일 쓰기 권한이 필요합니다" in str(error.value)
    assert "웹 AI" in str(error.value)


def test_failure_output_is_read_as_utf8(tmp_path, monkeypatch):
    p, run = _prepared_project(tmp_path)
    _fake_executable(tmp_path, monkeypatch)
    monkeypatch.setenv("DRK_FAKE_EXIT", "1")
    monkeypatch.setenv("DRK_FAKE_STDERR", "한글 오류: 설정 파일을 읽지 못함")
    with pytest.raises(ValueError, match="한글 오류: 설정 파일을 읽지 못함"):
        providers.run_claude_code(p, run)


def test_cli_is_called_with_utf8_and_survives_missing_streams(tmp_path, monkeypatch):
    import shutil
    import subprocess
    p, run = _prepared_project(tmp_path)
    seen = {}
    monkeypatch.setattr(shutil, "which", lambda name: "claude")
    def run_cli(args, **kwargs):
        seen.update(kwargs)
        # What Korean Windows returns when the reader thread failed to decode (#25 comment).
        return subprocess.CompletedProcess(args, 1, stdout=None, stderr=None)
    monkeypatch.setattr(subprocess, "run", run_cli)
    with pytest.raises(ValueError, match="Claude Code 실행 실패"):
        providers.run_claude_code(p, run)
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace"
    assert providers.claude_code_status()["available"] is False


def test_synthesis_run_that_saved_nothing_is_a_failure(tmp_path, monkeypatch):
    from deep_research import workflow as w
    p, run = _extracted_project(tmp_path)
    first = w.evidence(p, run)[0]["id"]
    w.review(p, run, first, "accept", "Matches the sentence", "Person")
    w.prepare_synthesis(p, run)
    _fake_claude(monkeypatch, lambda: None)
    with pytest.raises(ValueError, match="종합 결과가 저장되지 않았습니다"):
        providers.run_claude_code(p, run, "synthesis")
