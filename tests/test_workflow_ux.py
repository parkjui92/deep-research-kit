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


def test_comparison_cell_opens_review_and_returns_with_filters_preserved(tmp_path):
    p, run = _project_with_value(tmp_path, "19 percent longer")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    assert len(app.session_state["wb_columns"]) == 4
    assert not any(r.label == "이 값을" for r in app.radio)
    app.text_input(key="wb_find").input("19 percent").run()
    app.selectbox(key="wb_filter").set_value("미검토").run()
    target = w.evidence(p, run)[-1]["id"]
    app.button(key="cell-" + target).click().run()
    assert not app.exception
    assert app.session_state["wb_layout"] == "집중 검토"
    assert app.session_state["wb_pick"] == target
    assert any(r.label == "이 값을" for r in app.radio)
    assert any("원문의 앞뒤" in c.label for c in app.checkbox)
    assert len(app.get("component_instance")) >= 1  # actual PDF component
    assert not any(e.label == "원문 PDF 펼치기" for e in app.expander)
    assert any(e.label == "비교표 도구·필터" for e in app.expander)
    app.button(key="wb_back_table").click().run()
    assert not app.exception
    assert app.session_state["wb_layout"] == "비교표"
    assert not any(e.label == "비교표 도구·필터" for e in app.expander)
    assert app.text_input(key="wb_find").value == "19 percent"
    assert app.selectbox(key="wb_filter").value == "미검토"
    assert app.session_state["wb_pick"] == target


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


def test_context_shows_the_words_around_a_quote_and_escapes_them():
    from ui.chrome import context_html
    passage = "Before this. " * 30 + "Completion took 19 percent longer <when> AI was allowed." + " After that." * 30
    html = context_html("completion took 19 percent  longer <when> AI was allowed.", passage)
    assert html.startswith('<div class="drk-context">') and "앞뒤 문맥" in html
    assert "<b>Completion took 19 percent longer &lt;when&gt; AI was allowed</b>" in html  # bold ends at the last letter
    assert "…" in html and len(html) < 700
    assert context_html("not in the passage", passage) == ""
    assert context_html("whole passage", "whole passage") == ""  # nothing around it to show


def test_cell_colours_follow_the_design_rules():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "assets" / "styles.css").read_text(encoding="utf-8")
    rule = {k: next(line for line in css.splitlines() if f"st-key-tone-{k}-" in line and "background" in line) for k in ("stop", "wait", "edit")}
    assert "#FEF2F2" not in rule["stop"] and "#7F1D1D" not in rule["stop"]  # red is for errors only
    assert "#FFF7ED" in rule["wait"]  # hold is orange, like its badge
    assert "#FEFCE8" not in rule["edit"]  # not the yellow of quotes and search marks


def test_context_finds_a_quote_matched_across_a_line_end_hyphen():
    from ui.chrome import context_html
    passage = "We recruited 43 expert researchers to execute randomly-as- signed ideas, either written by experts. Then more."
    html = context_html("43 expert researchers to execute randomly-assigned ideas,", passage)
    assert "<b>43 expert researchers to execute randomly-as- signed ideas</b>, either" in html
