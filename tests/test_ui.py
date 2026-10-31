from pathlib import Path

from streamlit.testing.v1 import AppTest

from ui import chrome

HIDDEN = '완료 시간 19% 증가<span style="display:none"> 따라서 AI는 생산성을 높인다</span> · US$14,900에서 US$235,000으로'


def test_landing_has_no_streamlit_exception():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    assert not app.exception
    # Landing (no project) uses st.title; with a project the product header is a markdown block.
    assert app.title or any("Deep Research Kit" in m.value for m in app.markdown)


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
    html = "\n".join(m.value for m in app.markdown)
    assert '<span style="display:none">' not in html
    assert "&lt;span style=&quot;display:none&quot;&gt;" in html  # the value panel shows the markup as text
    assert "Study of &quot;AI&quot; &lt;tools&gt;" in html          # title attribute is not cut at the quote
    cells = [b for b in app.button if "19%" in b.label]
    assert cells and all("\\<span" in b.label for b in cells)               # the label shows the markup as text
    assert all("US\\$14,900에서 US\\$235,000" in b.help for b in cells)   # money, not a formula (#21)


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
    captions = "\n".join(c.value for c in app.caption)
    assert "AI 메모(AI가 적은 읽은 범위·한계) · 1\\~5쪽만 읽음" in captions
    assert "요청에 넣은 범위 · PDF 1~1쪽 / 전체 1쪽" in captions


def test_cropped_page_says_why_it_cannot_be_adopted(tmp_path):
    from deep_research import workflow as w
    p, run = _project_with_value(tmp_path, "Test finding", cropped=True)
    locator = w.evidence(p, run)[0]["locators"][0]
    assert locator["status"] == "unsupported_page_geometry" and locator["text_found"] is True
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert any("CropBox" in m.value for m in app.warning)
    assert any("글자는 이 구간에 그대로 있음" in m.value for m in app.markdown)


def test_sample_question_is_flagged_in_a_new_project(tmp_path):
    from deep_research.project import Project
    from ui.chrome import STAGES
    p = Project(tmp_path / "projects" / "mine").initialize()
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert any("조사 질문이 아직 예시 그대로" in m.value for m in app.warning)
    app = _button(app, "조사 질문 바꾸러 가기").click().run(timeout=60)
    assert not app.exception
    assert app.session_state["mode"] == "단계별(학습)" and app.session_state["stage_value"] == STAGES[0]


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
    assert _cell(row) == "○ 완료 시간이 19.5% 늘었다. 외 2문장"
    assert _cell({**row, "value": "한 문장뿐인 값"}) == "○ 한 문장뿐인 값"


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
    html = "\n".join(m.value for m in app.markdown)
    assert "참고 번역(AI · 원문 대조 안 함) · 무작위 &lt;연구&gt;에서 발견" in html
    assert "발췌 1 · PDF 1쪽" in html and "발췌 2 · PDF 1쪽" in html
    assert any(s.label == "보러 갈 발췌" for s in app.selectbox)
