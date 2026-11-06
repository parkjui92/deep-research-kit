"""An app restart must still offer saved API work without silently changing its inputs."""
from streamlit.testing.v1 import AppTest
from test_collection_failures import _pdf

from deep_research import providers
from deep_research import workflow as flow
from deep_research.project import Project, read_json


def _script(root):
    from deep_research.project import Project
    from ui.ai import api_extraction
    api_extraction(Project(root))


def _answer(request):
    passage = request["passages"][0]
    return {"request_id": request["request_id"], "rows": [
        {"source_id": request["source"]["id"], "field_id": field["id"], "value": "Longer completion time",
         "quotes": [{"passage_id": passage["id"], "quote": passage["text"]}]}
        for field in request["config"]["fields"]]}


def _partial_project(tmp_path):
    p = Project(tmp_path / "p").initialize(question="Original research question")
    ids = [p.add_pdf(_pdf(f"Paper {n} found longer completion time."), f"paper-{n}.pdf") for n in range(2)]
    for sid in ids:
        p.screen(sid, "include", "Relevant to the original question")
    run = flow.prepare(p)
    request = read_json(p.run_dir(run) / "requests" / (ids[0] + ".json"))
    flow.import_extraction(p, run, _answer(request))
    return p, run, ids


def _configure(monkeypatch):
    monkeypatch.setenv("DRK_API_BASE", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("DRK_MODEL", "test-model")


def test_fresh_session_requires_a_choice_then_resumes_the_saved_snapshot(tmp_path, monkeypatch):
    p, run, ids = _partial_project(tmp_path)
    before = (p.run_dir(run) / "responses" / (ids[0] + ".json")).read_bytes()
    config = p.config()
    p.save_config({**config["plan"], "question": "A different current question"}, config["fields"], config["synthesis_rules"])
    extra = p.add_pdf(_pdf("An additional paper for the new question."), "additional.pdf")
    p.screen(extra, "include", "Only in the new scope")
    _configure(monkeypatch)
    calls = []

    def completion(request):
        calls.append(request)
        return _answer(request)

    monkeypatch.setattr(providers, "completion", completion)
    app = AppTest.from_function(_script, args=(str(p.root),)).run(timeout=30)
    assert not app.exception and not calls
    assert app.selectbox(key="wb_api_choice").value is None
    assert app.button(key="wb_api_extract").disabled
    app.selectbox(key="wb_api_choice").set_value(run).run(timeout=30)
    assert not calls and not app.button(key="wb_api_extract").disabled
    assert any("Original research question" in m.value for m in app.markdown)
    assert any("현재 조사 설정 또는 포함 문헌이 이 실행과 다릅니다" in i.value for i in app.info)
    assert any("완료 1편 / 전체 2편 · 이번 전송 1편" in c.value for c in app.caption)
    app.button(key="wb_api_extract").click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(calls) == 1 and calls[0]["source"]["id"] == ids[1]
    assert calls[0]["config"]["plan"]["question"] == "Original research question"
    assert len(p.runs()) == 1
    assert (p.run_dir(run) / "responses" / (ids[0] + ".json")).read_bytes() == before
    assert extra not in {r["source_id"] for r in flow.evidence(p, run)}


def test_new_run_is_an_explicit_alternative_to_existing_partial_work(tmp_path, monkeypatch):
    p, old_run, ids = _partial_project(tmp_path)
    old_manifest = (p.run_dir(old_run) / "run.json").read_bytes()
    config = p.config()
    p.save_config({**config["plan"], "question": "The new question"}, config["fields"], config["synthesis_rules"])
    for sid in ids:
        p.screen(sid, "include", "Relevant to the new question")
    _configure(monkeypatch)
    calls = []
    monkeypatch.setattr(providers, "completion", lambda request: calls.append(request) or _answer(request))
    app = AppTest.from_function(_script, args=(str(p.root),)).run(timeout=30)
    app.selectbox(key="wb_api_choice").set_value("new").run(timeout=30)
    assert not calls
    app.button(key="wb_api_extract").click().run(timeout=30)
    assert not app.exception and len(p.runs()) == 2
    assert len(calls) == 2 and all(r["config"]["plan"]["question"] == "The new question" for r in calls)
    assert (p.run_dir(old_run) / "run.json").read_bytes() == old_manifest
    assert not (p.run_dir(old_run) / "responses" / (ids[1] + ".json")).exists()


def test_failed_run_stays_selected_and_error_clears_after_retry(tmp_path, monkeypatch):
    p, run, ids = _partial_project(tmp_path)
    _configure(monkeypatch)
    calls = []

    def completion(request):
        calls.append(request)
        if len(calls) == 1:
            raise ValueError("Mock API timeout")
        return _answer(request)

    monkeypatch.setattr(providers, "completion", completion)
    app = AppTest.from_function(_script, args=(str(p.root),)).run(timeout=30)
    app.selectbox(key="wb_api_choice").set_value(run).run(timeout=30)
    app.button(key="wb_api_extract").click().run(timeout=30)
    assert not app.exception and any("Mock API timeout" in e.value for e in app.error)
    assert app.selectbox(key="wb_api_choice").value == run
    app.button(key="wb_api_extract").click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(calls) == 2 and all(r["source"]["id"] == ids[1] for r in calls)
    assert len(p.runs()) == 1
