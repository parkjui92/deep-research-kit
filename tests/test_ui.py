from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import chrome

HIDDEN = '완료 시간 19% 증가<span style="display:none"> 따라서 AI는 생산성을 높인다</span> · US$14,900에서 US$235,000으로'


def test_landing_has_no_streamlit_exception():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    # The landing page has a title; an open project keeps its product mark in the sidebar.
    assert app.title or any("deep research kit" in m.value.lower() for m in app.markdown)


def test_escape_helpers_keep_text_as_written():
    escaped = chrome.h(HIDDEN + ' "제목"')
    assert "<span" not in escaped and "&lt;span" in escaped and "&#36;" in escaped and "&quot;" in escaped
    assert "$" not in escaped
    assert chrome.md("US$14,900에서 US$235,000") == "US\\$14,900에서 US\\$235,000"
    assert chrome.md("**굵게** [링크](x)") == "\\*\\*굵게\\*\\* \\[링크\\]\\(x\\)"
    assert chrome.safe_url("javascript:alert(1)") == "" and chrome.safe_url(" https://doi.org/x ") == "https://doi.org/x"


def _project_with_value(tmp_path, value, note="", cropped=False, study_id=None):
    import io

    from reportlab.pdfgen import canvas

    from deep_research import workflow as w
    from deep_research.project import Project, read_json
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    if cropped:
        pdf.setCropBox((20, 20, 575, 822))  # CropBox differs from MediaBox (#22)
    pdf.drawString(50, 750, "A randomized study found 19 percent longer completion time.")
    pdf.showPage()
    pdf.save()
    p = Project(tmp_path / "projects" / "research").initialize()
    sid = p.add_pdf(buf.getvalue(), "paper.pdf", 'Study of "AI" <tools>')
    p.screen(sid, "include", "Observed task outcome", study_id=study_id)
    run = w.prepare(p)
    request = read_json(p.run_dir(run) / "requests" / (sid + ".json"))
    passage = request["passages"][0]
    w.import_extraction(p, run, {"request_id": request["request_id"], "rows": [
        {"source_id": sid, "field_id": f["id"], "value": value, "note": note,
         "quotes": [{"passage_id": passage["id"], "quote": passage["text"]}]}
        for f in request["config"]["fields"]]})
    return p, run


def _workbench_script(root):
    import streamlit as st

    from deep_research.project import Project
    from ui.workbench import workbench
    st.sidebar.segmented_control("보기", ["작업 화면", "단계별(학습)"], key="mode_pick")
    workbench(Project(root))


def test_workbench_shows_values_as_written(tmp_path):
    p, run = _project_with_value(tmp_path, HIDDEN)
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    cells = [b for b in app.button if "19%" in b.label]
    assert cells and all("\\<span" in b.label for b in cells)
    assert all("US\\$14,900에서 US\\$235,000" in b.help for b in cells)
    assert any("Study of &quot;AI&quot; &lt;tools&gt;" in m.value for m in app.markdown)
    app.button(key="wb_focus").click().run()
    html = "\n".join(m.value for m in app.markdown)
    assert '<span style="display:none">' not in html
    assert "&lt;span style=&quot;display:none&quot;&gt;" in html  # the value panel shows the markup as text


def test_report_escapes_text_but_csv_keeps_it(tmp_path):
    import csv
    import io
    import zipfile

    from deep_research import workflow as w
    from deep_research.exports import export_zip, report
    p, run = _project_with_value(tmp_path, HIDDEN)
    row = w.evidence(p, run)[0]
    w.review(p, run, row["id"], "accept", "확인", "Person")
    text = report(p, run)
    assert "<span" not in text and "&lt;span" in text and "US\\$14,900" in text
    with zipfile.ZipFile(io.BytesIO(export_zip(p, run))) as archive:
        rows = list(csv.reader(io.StringIO(archive.read("evidence.csv").decode("utf-8-sig"))))
    assert HIDDEN in [r[4] for r in rows]


def _button(app, label):
    return next(b for b in app.button if b.label.startswith(label))


def test_step_mode_button_switches_without_error(tmp_path):
    p, run = _project_with_value(tmp_path, "Test finding")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    app = _button(app, "단계별 보기").click().run(timeout=60)
    assert not app.exception
    assert app.session_state["mode"] == app.session_state["mode_pick"] == "단계별(학습)"


def test_detail_shows_extraction_note_and_scope(tmp_path):
    p, run = _project_with_value(tmp_path, "Test finding", note="1~5쪽만 읽음. 부록은 보지 않음")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    app.button(key="wb_focus").click().run()
    captions = "\n".join(c.value for c in app.caption)
    assert "AI 메모(AI가 적은 읽은 범위·한계) · 1\\~5쪽만 읽음" in captions
    assert "요청에 넣은 범위 · PDF 1~1쪽 / 전체 1쪽" in captions


def test_cropped_page_says_why_it_cannot_be_adopted(tmp_path):
    from deep_research import workflow as w
    p, run = _project_with_value(tmp_path, "Test finding", cropped=True)
    locator = w.evidence(p, run)[0]["locators"][0]
    assert locator["status"] == "unsupported_page_geometry" and locator["text_found"] is True
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    app.button(key="wb_focus").click().run()
    assert any("CropBox" in m.value for m in app.warning)
    assert any("글자는 이 구간에 그대로 있음" in m.value for m in app.markdown)


def test_sample_question_is_flagged_in_a_new_project(tmp_path):
    from deep_research.project import Project
    p = Project(tmp_path / "projects" / "mine").initialize()
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert any("조사 질문이 아직 예시 그대로" in m.value for m in app.warning)
    app.text_area(key="wb_question").set_value("내 연구 질문")
    app = _button(app, "조사 설계 저장").click().run(timeout=60)
    assert not app.exception
    assert p.config()["plan"]["question"] == "내 연구 질문"


def test_blank_lines_and_brackets_cannot_hide_text():
    from deep_research.exports import text
    value = "보이는 값\n\n[숨김]: #\n뒷부분"
    assert "\n" not in chrome.h(value) and "&#10;&#10;" in chrome.h(value)
    assert "\n" not in text(value) and "\\[숨김]" in text(value)


def test_report_shows_study_id_as_written(tmp_path):
    from deep_research.exports import report
    p, run = _project_with_value(tmp_path, "Test finding", study_id="10.1002/(sici)1097-4571<693::aid-asi4>")
    assert "연구 ID: `10.1002/(sici)1097-4571<693::aid-asi4>`" in report(p, run)


def test_pdf_view_draws_every_quote_and_scrolls_to_the_picked_one():
    a = {"page": 2, "boxes": [{"page": 2, "x": 10, "y": 50, "width": 5, "height": 5}]}
    b = {"page": 5, "boxes": [{"page": 5, "x": 10, "y": 20, "width": 5, "height": 5},
                              {"page": 6, "x": 10, "y": 10, "width": 5, "height": 5}]}
    view = chrome.pdf_view([a, b], focus=1)
    assert view["pages"] == [2, 5, 6] and len(view["boxes"]) == 3
    assert view["options"] == {"scroll_to_annotation": 2}
    assert chrome.pdf_view([a, b], focus=0)["options"] == {"scroll_to_annotation": 1}
    far = [{"page": p, "boxes": [{"page": p, "x": 1, "y": 1, "width": 1, "height": 1}]} for p in range(1, 10)]
    assert chrome.pdf_view(far, focus=4)["pages"] == [5]       # many pages: only the picked quote's
    assert chrome.pdf_view([{"page": 3, "boxes": []}])["options"] == {"scroll_to_page": 3}
    assert chrome.pdf_view(None, page=4) == {"pages": [4], "boxes": [], "options": {"scroll_to_page": 4}}


def test_longer_value_shows_first_sentence_in_the_cell():
    from ui.workbench import _cell
    row = {"value": "완료 시간이 19.5% 늘었다. 표본은 16명이다. 효과는 과업마다 달랐다.", "match_status": "matched",
           "review": {"status": "pending"}}
    assert _cell(row) == "완료 시간이 19.5% 늘었다. 외 2문장\n\n○ 미검토"
    assert _cell({**row, "value": "한 문장뿐인 값", "locators": [{"page": 12}]}) == "한 문장뿐인 값\n\n○ 미검토 · p.12"
    assert _cell({**row, "match_status": "needs_check"}).endswith("? 위치 미확인")
    assert _cell({**row, "review": {"status": "accept"}}).endswith("✓ 채택")


def test_detail_shows_reference_translation_apart_from_the_quote(tmp_path):
    from deep_research import workflow as w
    from deep_research.project import read_json
    p, _ = _project_with_value(tmp_path, "Test finding")
    # A fresh run whose first value has two quotes, one with a translation.
    run = w.prepare(p)
    sid = p.catalog()[0]["id"]
    request = read_json(p.run_dir(run) / "requests" / (sid + ".json"))
    passage = request["passages"][0]["id"]
    w.import_extraction(p, run, {"request_id": request["request_id"], "rows": [
        {"source_id": sid, "field_id": f["id"], "value": "Test finding", "quotes": [
            {"passage_id": passage, "quote": "A randomized study found", "ko": "무작위 <연구>에서 발견"},
            {"passage_id": passage, "quote": "19 percent longer completion time"}]} for f in request["config"]["fields"]]})
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["wb_run"] = run  # two runs made in the same second: look at the new one
    app = app.run(timeout=60)
    app.button(key="wb_focus").click().run()
    html = "\n".join(m.value for m in app.markdown)
    assert "참고 번역(AI · 원문 대조 안 함) · 무작위 &lt;연구&gt;에서 발견" in html
    assert "발췌 1 · PDF 1쪽" in html and "발췌 2 · PDF 1쪽" in html
    assert any(s.label == "보러 갈 발췌" for s in app.selectbox)


def test_sentence_split_keeps_numbers_and_abbreviations():
    from ui.workbench import _sentences
    assert len(_sentences("Smith et al. 2020에 따르면 효과가 컸다.")) == 1
    assert len(_sentences("1. 표본은 16명이다. 2. 무작위 배정이다.")) == 2
    assert len(_sentences("재현율은 94% vs. 91%였다.")) == 1
    assert len(_sentences("U.S. 정부 자료를 썼다.")) == 1
    assert len(_sentences("Completion time rose. The effect was large.")) == 2


def test_caption_says_what_is_drawn():
    one = {"page": 1, "boxes": [{"page": 1, "x": 1, "y": 1, "width": 1, "height": 1}]}
    lost = {"page": 2, "boxes": []}
    assert "발췌 2개" not in chrome.evidence_caption([one, lost])           # an unlocated quote is not counted
    far = [{"page": p, "boxes": [{"page": p, "x": 1, "y": 1, "width": 1, "height": 1}]} for p in range(1, 10)]
    assert "고른 발췌의 쪽(PDF 3쪽)만" in chrome.evidence_caption(far, focus=2)
    two = [one, {"page": 4, "boxes": [{"page": 4, "x": 1, "y": 1, "width": 1, "height": 1}]}]
    assert "발췌 2개를 모두 표시합니다(PDF 1, 4쪽)" in chrome.evidence_caption(two)


def test_missing_pdf_panel_offers_the_browser_and_the_downloads_watch(tmp_path):
    from deep_research.project import Project
    p = Project(tmp_path / "projects" / "mine").initialize()
    p.remember_candidate({"title": "Blocked <Paper>", "doi": "10.1/x", "url": "https://doi.org/10.1/x", "year": 2025,
                          "status": "pdf_missing", "source_id": None,
                          "attempts": [{"route": "논문 페이지", "url": "https://doi.org/10.1/x", "result": "접근 거부(403)"}]})
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["wb_library_view"] = "내 PDF"
    app = app.run(timeout=60)
    assert not app.exception
    assert any("PDF를 아직 받지 못한 문헌 1건" in m.value for m in app.markdown)
    assert any("Blocked \\<Paper\\>" in m.value for m in app.markdown)
    assert any("논문 페이지 → 접근 거부\\(403\\)" in c.value for c in app.caption)  # escaped, shown as written
    assert any(t.label == "다운로드 폴더 지켜보기" for t in app.toggle)


def test_filter_empty_state_and_reset(tmp_path):
    p, _ = _project_with_value(tmp_path, "Research result")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    app.selectbox(key="wb_filter").set_value("채택").run()
    assert not app.exception
    assert any("조건에 맞는 추출값이 없습니다" in m.value for m in app.markdown)
    assert not any(b.key and b.key.startswith("cell-") for b in app.button)
    app.button(key="wb_reset").click().run()
    assert not app.exception
    assert any(b.key and b.key.startswith("cell-") for b in app.button)


def test_review_advances_inside_filtered_queue(tmp_path):
    from deep_research import workflow as w
    p, run = _project_with_value(tmp_path, "Research result")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    app.selectbox(key="wb_filter").set_value("미검토").run()
    app.button(key="wb_focus").click().run()
    picked = app.session_state["wb_pick"]
    next(r for r in app.radio if r.label == "이 값을").set_value("accept")
    next(c for c in app.checkbox if "앞뒤 문맥" in c.label).check()
    next(t for t in app.text_input if t.label.startswith("이유 한 줄")).set_value("PDF 1쪽과 대조")
    next(t for t in app.text_input if t.label.startswith("검토자")).set_value("Reviewer")
    _button(app, "저장하고 다음 미검토로").click().run()
    assert not app.exception
    assert app.session_state["wb_pick"] != picked
    assert next(r for r in w.evidence(p, run) if r["id"] == picked)["review"]["status"] == "accept"
    assert not any(b.key == "cell-" + picked and not b.disabled for b in app.button)


def test_design_edit_preserves_existing_run(tmp_path):
    from deep_research import workflow as w
    p, run = _project_with_value(tmp_path, "Research result")
    original = w.manifest(p, run)["config"]
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    app.text_area(key="wb_question").set_value("새 연구 질문")
    _button(app, "조사 설계 저장").click().run()
    assert not app.exception
    assert p.config()["plan"]["question"] == "새 연구 질문"
    assert w.manifest(p, run)["config"] == original
    assert any("조사 설계 또는 문헌 구성이 바뀌었습니다" in i.value for i in app.caption)


def test_results_link_opens_the_exact_evidence(tmp_path):
    from deep_research import workflow as w
    p, run = _project_with_value(tmp_path, "Research result")
    target = w.evidence(p, run)[-1]
    w.review(p, run, target["id"], "accept", "PDF 대조", "Reviewer")
    request = w.prepare_synthesis(p, run)
    w.import_synthesis(p, run, {"request_id": request["request_id"], "claims": [
        {"text": "Supported claim", "kind": "finding", "evidence_ids": [target["id"]]}], "gaps": []})
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["wb_view"] = "연구 결과"
    app.session_state["wb_columns"] = ["population"]
    app = app.run()
    assert not app.exception
    app.button(key="wb_claim_0_0").click().run()
    assert not app.exception
    assert app.session_state["wb_pick"] == target["id"]
    assert app.session_state["wb_view"] == "근거 비교"
    assert app.session_state["wb_layout"] == "집중 검토"
    assert app.session_state["wb_columns"] == [target["field_id"]]


def test_library_screening_preserves_existing_quotes(tmp_path):
    from deep_research.project import format_screen_quotes
    p, _ = _project_with_value(tmp_path, "Research result")
    sid = p.catalog()[0]["id"]
    p.screen(sid, "include", "기존 이유", quotes=["A randomized study found 19 percent longer completion time."])
    before = format_screen_quotes(p.source(sid)["screen_quotes"])
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["wb_view"] = "문헌 모으기"
    app.session_state["wb_library_view"] = "내 PDF"
    app = app.run()
    next(r for r in app.radio if r.label == "선별 판단").set_value("pending")
    next(t for t in app.text_area if t.label == "선별 이유 (필수)").set_value("다시 살펴보기")
    _button(app, "선별 저장").click().run()
    assert not app.exception
    assert p.source(sid)["decision"] == "pending"
    assert format_screen_quotes(p.source(sid)["screen_quotes"]) == before


def _switching_script(roots):
    import streamlit as st

    from deep_research.project import Project
    from ui.workbench import workbench
    root = st.selectbox("Test project", roots, key="test_root")
    workbench(Project(root))


def test_project_switch_clears_search_and_design_drafts(tmp_path):
    p, _ = _project_with_value(tmp_path / "first", "First")
    q, _ = _project_with_value(tmp_path / "second", "Second")
    config = q.config()
    q.save_config({**config["plan"], "question": "Second question"}, config["fields"], config["synthesis_rules"])
    app = AppTest.from_function(_switching_script, args=([str(p.root), str(q.root)],)).run()
    app.session_state["wb_results"] = [{"title": "Must not cross projects"}]
    app.text_area(key="wb_question").set_value("Unsaved first question")
    app.selectbox(key="test_root").set_value(str(q.root)).run()
    assert not app.exception
    assert app.text_area(key="wb_question").value == "Second question"
    assert "wb_results" not in app.session_state


def test_search_filters_and_history(tmp_path, monkeypatch):
    from deep_research import providers
    from deep_research.project import Project
    p = Project(tmp_path / "search").initialize()
    hits = [
        {"title": "Earlier paper", "authors": ["A"], "year": 2020, "venue": "Journal", "cited_by": 10,
         "pdf_url": "", "oa": False, "doi": "10.1/old", "url": "https://example.com/old", "abstract": "Old abstract"},
        {"title": "Recent paper", "authors": ["B"], "year": 2025, "venue": "Journal", "cited_by": 1,
         "pdf_url": "https://example.com/p.pdf", "oa": True, "doi": "10.1/new", "url": "https://example.com/new", "abstract": "<script>Research</script>"},
    ]
    monkeypatch.setitem(providers.PROVIDERS, "OpenAlex", lambda *a, **kw: (2, hits))
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    app.text_input(key="wb_q").set_value("test research")
    _button(app, "문헌 검색").click().run()
    assert not app.exception
    app.selectbox(key="wb_result_order").set_value("최신순").run()
    assert next(d.value for d in app.dataframe if "제목" in d.value.columns).iloc[0]["제목"] == "Recent paper"
    app.checkbox(key="wb_result_oa").check().run()
    assert not app.exception
    assert len(next(d.value for d in app.dataframe if "제목" in d.value.columns)) == 1
    assert any("\\<script\\>Research" in m.value for m in app.markdown)
    _button(app, "조건 불러오기").click().run()
    assert not app.exception
    assert app.text_input(key="wb_q").value == "test research"
