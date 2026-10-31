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


def _project_with_value(tmp_path, value):
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
    sid = p.add_pdf(buf.getvalue(), "paper.pdf", 'Study of "AI" <tools>')
    p.screen(sid, "include", "Observed task outcome")
    run = w.prepare(p)
    request = read_json(p.run_dir(run) / "requests" / (sid + ".json"))
    passage = request["passages"][0]
    w.import_extraction(p, run, {"request_id": request["request_id"], "rows": [
        {"source_id": sid, "field_id": f["id"], "value": value,
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
