"""Workbench flow: PDF beside the review, one-line table controls, synthesis paths,
index cache, batch PDF collection and moving on to the next undecided paper."""
import json

import pytest
from streamlit.testing.v1 import AppTest
from test_ui import _project_with_value, _workbench_script

from deep_research import workflow as w


def test_index_check_is_cached_but_a_changed_file_is_still_caught(tmp_path, monkeypatch):
    from deep_research import project as project_module
    p, run = _project_with_value(tmp_path, "19 percent longer")
    sid = p.catalog()[0]["id"]
    calls = []
    real = project_module.digest
    monkeypatch.setattr(project_module, "digest", lambda data: calls.append(len(data)) or real(data))
    p.index(sid)
    first = len(calls)
    p.index(sid)
    assert len(calls) == first  # unchanged files are not hashed again
    pdf = p.source_dir(sid) / "original.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"%tampered")
    with pytest.raises(ValueError, match="원본 파일이 변경"):
        p.index(sid)


def test_comparison_shows_more_columns_and_the_pdf_beside_the_review(tmp_path):
    p, run = _project_with_value(tmp_path, "19 percent longer")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    assert len(app.session_state["wb_columns"]) == 4
    assert app.toggle(key="wb_pdf_inline").value is True
    assert not any(e.label == "원문 PDF 펼치기" for e in app.expander)
    assert not any(e.label == "검색·검토 상태·표시 항목" for e in app.expander)


def _synthesis_script(root, run_id):
    import streamlit as st

    from deep_research.project import Project
    from ui.workbench import _synthesis_controls
    st.session_state.setdefault("drk_claude_ready", False)
    _synthesis_controls(Project(root), run_id)


def test_synthesis_through_a_web_ai_is_checked_and_stored(tmp_path):
    p, run = _project_with_value(tmp_path, "19 percent longer")
    row = w.evidence(p, run)[0]
    w.review(p, run, row["id"], "accept", "8쪽 대조", "Kim")
    app = AppTest.from_function(_synthesis_script, args=(str(p.root), run)).run(timeout=60)
    assert not app.exception
    assert next(b for b in app.button if b.label == "Claude Code로 종합").disabled
    app.button(key="wb_synth_make").click().run(timeout=60)
    request = json.loads(app.session_state["wb_synth_request"])
    answer = {"request_id": request["request_id"], "gaps": [],
              "claims": [{"text": "완료 시간이 19% 길었다.", "kind": "finding", "evidence_ids": [row["id"]]}]}
    app.text_area[0].input("응답입니다:\n```json\n" + json.dumps(answer, ensure_ascii=False) + "\n```")
    app.button[-1].click().run(timeout=60)
    assert not app.exception
    assert w.current_synthesis(p, run)["claims"][0]["evidence_ids"] == [row["id"]]
    assert any("종합문이 준비됐습니다" in s.value for s in app.success)


def test_a_web_ai_synthesis_with_an_unknown_evidence_id_is_refused(tmp_path):
    p, run = _project_with_value(tmp_path, "19 percent longer")
    row = w.evidence(p, run)[0]
    w.review(p, run, row["id"], "accept", "8쪽 대조", "Kim")
    app = AppTest.from_function(_synthesis_script, args=(str(p.root), run)).run(timeout=60)
    app.button(key="wb_synth_make").click().run(timeout=60)
    request = json.loads(app.session_state["wb_synth_request"])
    app.text_area[0].input(json.dumps({"request_id": request["request_id"], "gaps": [],
                                       "claims": [{"text": "지어낸 주장", "kind": "finding", "evidence_ids": ["e_made_up"]}]}))
    app.button[-1].click().run(timeout=60)
    assert any("채택한 근거 ID" in e.value for e in app.error)
    assert w.current_synthesis(p, run) is None


def _library_script(root):
    from deep_research.project import Project
    from ui.workspace import library
    library(Project(root))


def test_saving_a_screening_decision_moves_to_the_next_undecided_paper(tmp_path):
    p, run = _project_with_value(tmp_path, "19 percent longer")
    data = (p.source_dir(p.catalog()[0]["id"]) / "original.pdf").read_bytes()
    second = p.add_pdf(data + b"%2", "b.pdf", "Second paper")
    third = p.add_pdf(data + b"%3", "c.pdf", "Third paper")
    app = AppTest.from_function(_library_script, args=(str(p.root),)).run(timeout=60)
    app.selectbox(key="wb_library_pick").set_value(second).run(timeout=60)
    app.text_area[0].input("대상 과업이 다름")
    app.radio[0].set_value("exclude")
    next(b for b in app.button if b.label == "선별 저장").click().run(timeout=60)
    assert not app.exception
    assert app.session_state["wb_library_pick"] == third
    assert p.source(second)["decision"] == "exclude"


def test_candidates_without_pdf_are_collected_in_one_go(tmp_path, monkeypatch):
    from deep_research import providers
    p, run = _project_with_value(tmp_path, "19 percent longer")
    for n in range(3):
        p.remember_candidate({"title": f"Candidate {n}", "doi": f"10.1/c{n}", "url": "", "status": "saved"})
    seen = []

    def fake_collect(project, item, client=None):
        seen.append(item["title"])
        return {"source_id": "s-new" if item["title"] != "Candidate 1" else None}

    monkeypatch.setattr(providers, "collect", fake_collect)

    def script(root):
        from deep_research.project import Project
        from ui.reading import candidate_queue
        candidate_queue(Project(root))

    app = AppTest.from_function(script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    app.button(key="wb_collect_all").click().run(timeout=60)
    assert not app.exception
    assert sorted(seen) == ["Candidate 0", "Candidate 1", "Candidate 2"]
    assert "3편 가운데 2편의 PDF를 등록했습니다" in app.session_state["flash"]
