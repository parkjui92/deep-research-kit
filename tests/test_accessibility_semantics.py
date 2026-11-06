"""Native-control paths and meaningful names, using only temporary local sources.

AppTest checks emitted labels and state transitions, not browser focus, computed
accessible names, screen-reader output, or responsive rendering. Those need a
separate real-browser check.
"""
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest
from test_ui import _project_with_value

from deep_research import acquire, notebook, providers, writing
from deep_research import workflow as flow
from deep_research.exports import report
from ui import chrome


@pytest.fixture(autouse=True)
def _no_external_execution(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("Accessibility tests must not call external services or AI")

    monkeypatch.setattr(httpx.Client, "request", refused)
    monkeypatch.setattr(providers, "completion", refused)
    monkeypatch.setattr(providers, "run_claude_code", refused)
    monkeypatch.setattr(providers, "run_claude_translate", refused)
    monkeypatch.setattr(providers, "claude_code_status", lambda: {
        "available": False, "reason": "No model execution in this test"})


def _app(project, monkeypatch):
    monkeypatch.setenv("DRK_PROJECTS_DIR", str(project.root.parent))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.query_params["project"] = project.root.name
    return app.run(timeout=30)


def _screen(app):
    assert not app.exception
    assert not app.error
    assert len(app.title) == 1, "Each work view needs one native main heading"
    for kind in ("button", "checkbox", "toggle", "radio", "segmented_control", "selectbox",
                 "multiselect", "text_input", "text_area", "number_input", "slider"):
        for widget in getattr(app, kind):
            assert widget.label.strip(), f"Unnamed {kind}: {widget.key}"


def _button(app, text):
    return next(button for button in app.button if button.label.startswith(text))


def test_search_can_save_one_candidate_without_editing_the_result_grid(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "Longer completion time")
    evidence_before = flow.evidence(project, run)
    original = (project.source_dir(project.catalog()[0]["id"]) / "original.pdf").read_bytes()
    items = [{"title": title, "doi": f"10.1000/accessibility-{index}",
              "url": f"https://example.test/paper/{index}", "pdf_url": "", "oa": False,
              "authors": ["Test Author"], "year": 2026, "venue": "Test Journal",
              "abstract": "A randomized study found longer completion time.", "cited_by": 0}
             for index, title in enumerate(("A different study", "The selected study"))]
    monkeypatch.setitem(providers.PROVIDERS, "OpenAlex",
                        lambda query, limit, year_from=None: (2, items))
    monkeypatch.setattr(acquire, "find_pdf", lambda candidate, client=None: (original, []))

    app = _app(project, monkeypatch)
    app.radio(key="wb_view").set_value("문헌 모으기").run()
    app.text_input(key="wb_q").set_value("completion time")
    _button(app, "문헌 검색").click().run()
    _screen(app)
    # This selector/button path does not require the data editor's canvas or cells.
    next(box for box in app.selectbox if (box.key or "").startswith("wb_result_pick_")).set_value(1).run()
    assert app.button(key="wb_collect_one").label == "이 문헌을 후보함에 담기"
    app.button(key="wb_collect_one").click().run()
    _screen(app)
    assert [candidate["title"] for candidate in project.collection()] == ["The selected study"]
    assert app.segmented_control(key="wb_library_view").value == "읽기 후보"
    next(area for area in app.text_area if area.label == "읽을 이유·메모").set_value("Same outcome, inspect conditions")
    _button(app, "후보 메모 저장").click().run()
    _button(app, "공개 PDF 찾아 등록").click().run()
    _screen(app)
    assert project.collection()[0].get("source_id")
    _button(app, "내 PDF에서 읽기").click().run()
    _screen(app)
    assert app.segmented_control(key="wb_library_view").value == "원문 검색·노트"
    assert any("19 percent longer completion time" in item.value for item in app.text)

    next(area for area in app.text_area if area.label == "내 메모").set_value("Effect depends on the measured task")
    _button(app, "발췌·메모 저장").click().run()
    note = notebook.notes(project)[0]
    app.button(key="wb_saved_note_report").click().run()
    _screen(app)
    assert app.segmented_control(key="wb_output_kind").value == "내 보고서 초안"
    next(field for field in app.text_input if field.label == "논점 제목").set_value("Task-specific effect")
    next(area for area in app.text_area if area.label == "내가 쓸 문단").set_value("The result concerns the measured task.")
    app.button(key="wb_draft_save").click().run()
    _screen(app)
    section = writing.load(project)["sections"][0]
    assert section["note_ids"] == [note["id"]]
    assert "PDF 1쪽" in writing.markdown(project)
    # A reading note/report connection must not turn into an accepted AI finding.
    assert flow.evidence(project, run) == evidence_before
    next(area for area in app.text_area if area.label == "내가 쓸 문단").set_value("Unsaved qualified wording").run()
    app.button(key="wb_draft_read_" + note["id"]).click().run()
    _screen(app)
    app.button(key="wb_return_to_draft").click().run()
    _screen(app)
    assert next(area for area in app.text_area if area.label == "내가 쓸 문단").value == "Unsaved qualified wording"

    app.radio(key="wb_view").set_value("문헌 모으기").run()
    app.segmented_control(key="wb_library_view").set_value("문헌 검색").run()
    next(box for box in app.selectbox if (box.key or "").startswith("wb_result_pick_")).set_value(1).run()
    _screen(app)
    assert app.button(key="wb_collect_one").disabled
    assert app.button(key="wb_collect_one").label == "이미 후보함에 있음"
    assert len(project.collection()) == 1


def test_identical_comparison_values_name_the_paper_and_field_and_review_exports(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "The same finding")
    app = _app(project, monkeypatch)
    _screen(app)
    source = project.catalog()[0]
    fields = {field["id"]: field for field in project.config()["fields"]}
    rows = flow.evidence(project, run)
    labels = []
    for row in rows:
        label = app.button(key="cell-" + row["id"]).label
        assert chrome.md(source["title"]) in label
        assert chrome.md(fields[row["field_id"]]["name"]) in label
        labels.append(label)
    assert len(set(labels)) == len(rows), "Equal values must still have distinct button names"
    target = rows[0]
    app.button(key="cell-" + target["id"]).click().run()
    _screen(app)
    assert app.session_state["wb_pick"] == target["id"]
    app.radio(key="wb_decision_" + target["id"]).set_value("accept").run()
    next(box for box in app.checkbox if "원문의 앞뒤 문맥" in box.label).check()
    next(field for field in app.text_input if field.label.startswith("이유 한 줄")).set_value("Checked PDF 1 and surrounding passage")
    next(field for field in app.text_input if field.label.startswith("검토자")).set_value("Test reviewer")
    _button(app, "저장하고 다음 미검토로").click().run()
    _screen(app)
    assert [row["id"] for row in flow.accepted(project, run)] == [target["id"]]
    app.radio(key="wb_view").set_value("보고서에 쓰기").run()
    app.segmented_control(key="wb_output_kind").set_value("AI 근거 결과").run()
    _screen(app)
    assert "Test reviewer" in report(project, run)
    assert "Checked PDF 1 and surrounding passage" in report(project, run)


def test_native_paper_list_retains_filters_and_preference_across_review_and_report(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "The same finding")
    source = project.catalog()[0]
    app = _app(project, monkeypatch)
    app.text_input(key="wb_find").set_value("same finding").run()
    app.selectbox(key="wb_filter").set_value("미검토").run()
    fields = project.config()["fields"][:2]
    app.multiselect(key="wb_columns").set_value([field["id"] for field in fields]).run()
    app.toggle(key="wb_list_view").set_value(True).run()
    _screen(app)
    rows = [row for row in flow.evidence(project, run) if row["field_id"] in {field["id"] for field in fields}]
    assert not any((button.key or "").startswith("cell-") for button in app.button)
    labels = [app.button(key="list-cell-" + row["id"]).label for row in rows]
    target = rows[-1]
    app.button(key="list-cell-" + target["id"]).click().run()
    _screen(app)
    assert app.session_state["wb_pick"] == target["id"]
    app.button(key="wb_back_table").click().run()
    _screen(app)
    assert app.toggle(key="wb_list_view").value is True
    assert app.text_input(key="wb_find").value == "same finding"
    assert app.selectbox(key="wb_filter").value == "미검토"
    assert app.multiselect(key="wb_columns").value == [field["id"] for field in fields]
    app.radio(key="wb_view").set_value("보고서에 쓰기").run()
    app.radio(key="wb_view").set_value("근거 비교").run()
    _screen(app)
    assert app.toggle(key="wb_list_view").value is True
    for row, label in zip(rows, labels):
        assert chrome.md(chrome.short(source["title"], 65)) in label
        assert chrome.md(next(field["name"] for field in fields if field["id"] == row["field_id"])) in label


def _pdf_app(root, source_id, locators, focus=0):
    from deep_research.project import Project
    from ui.chrome import show_pdf

    show_pdf(Project(root), source_id, locators, page=1, identity="accessibility-test", focus=focus)


@pytest.mark.parametrize("with_quote", [True, False], ids=["matched-quote", "page-without-highlight"])
def test_pdf_moves_only_after_opt_in_and_keeps_the_same_text_and_highlights(tmp_path, monkeypatch, with_quote):
    project, run = _project_with_value(tmp_path, "A checked finding")
    source_id = project.catalog()[0]["id"]
    locators = flow.evidence(project, run)[0]["locators"] if with_quote else []
    calls = []
    monkeypatch.setattr(chrome, "pdf_viewer", lambda data, **options: calls.append((data, options)))
    app = AppTest.from_function(_pdf_app, args=(str(project.root), source_id, locators)).run()
    assert not app.exception
    choice = app.checkbox(key="pdf-auto-scroll-" + source_id)
    assert choice.label == "발췌 위치로 자동 이동" and choice.value is False
    original_data, original_options = calls[-1]
    assert "scroll_to_annotation" not in original_options
    assert "scroll_to_page" not in original_options
    assert original_options["render_text"] is True
    assert bool(original_options["annotations"]) is with_quote

    choice.check().run()
    assert not app.exception
    moved_data, moved_options = calls[-1]
    expected_scroll = "scroll_to_annotation" if with_quote else "scroll_to_page"
    assert moved_options[expected_scroll] == 1
    assert moved_options["scroll_behavior"] == "instant"
    assert moved_data == original_data
    for name in ("annotations", "pages_to_render", "render_text", "zoom_level", "key"):
        assert moved_options[name] == original_options[name]

    app.checkbox(key="pdf-auto-scroll-" + source_id).uncheck().run()
    assert not app.exception
    restored_data, restored_options = calls[-1]
    assert restored_data == original_data
    assert restored_options == original_options


def test_pdf_without_auto_scroll_renders_the_selected_later_page(tmp_path, monkeypatch):
    import io

    from reportlab.pdfgen import canvas

    from deep_research.project import Project

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for page in range(1, 4):
        pdf.drawString(50, 750, f"Local source passage on page {page}.")
        pdf.showPage()
    pdf.save()
    project = Project(tmp_path / "later-page").initialize()
    source_id = project.add_pdf(buffer.getvalue(), "three-pages.pdf", "Local three-page source")
    locators = [
        {"page": 1, "boxes": [{"page": 1, "x": 50, "y": 80, "width": 100, "height": 12}]},
        {"page": 3, "boxes": [{"page": 3, "x": 50, "y": 80, "width": 100, "height": 12},
                               {"page": 3, "x": 50, "y": 95, "width": 80, "height": 12}]},
    ]
    calls = []
    monkeypatch.setattr(chrome, "pdf_viewer", lambda data, **options: calls.append(options))
    app = AppTest.from_function(_pdf_app, args=(str(project.root), source_id, locators, 1)).run()
    assert not app.exception
    assert app.checkbox(key="pdf-auto-scroll-" + source_id).value is False
    options = calls[-1]
    assert options["pages_to_render"] == [3]
    assert "scroll_to_annotation" not in options and "scroll_to_page" not in options
    assert options["zoom_level"] == "auto"
    assert [(box["page"], box["x"], box["y"]) for box in options["annotations"]] == [
        (3, 50, 80), (3, 50, 95)]
