"""Independent navigation regressions using temporary projects and no model calls."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest
from test_collection_failures import _pdf
from test_ui import _project_with_value

from deep_research import workflow as flow
from deep_research.project import Project


def _app(project, monkeypatch):
    monkeypatch.setenv("DRK_PROJECTS_DIR", str(project.root.parent))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.query_params["project"] = project.root.name
    return app.run(timeout=30)


def _clean(app):
    assert not app.exception
    assert not app.error


def test_sidebar_navigation_and_project_switch_clear_project_drafts(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "First project finding")
    other = Project(project.root.parent / "second").initialize(title="Second research", question="Second project question")
    app = _app(project, monkeypatch)
    _clean(app)
    assert app.radio(key="wb_view").value == "근거 비교"
    app.text_input(key="wb_find").set_value("First project").run()
    app.radio(key="wb_view").set_value("문헌 모으기").run()
    app.text_input(key="wb_q").set_value("First search draft").run()
    app.selectbox(key="project_name").set_value(other.root.name).run()
    _clean(app)
    assert app.radio(key="wb_view").value == "문헌 모으기"
    assert app.text_input(key="wb_q").value != "First search draft"
    assert any("Second project question" in item.value for item in app.markdown)
    assert app.session_state["wb_project"] == str(other.root)
    app.selectbox(key="project_name").set_value(project.root.name).run()
    app.radio(key="wb_view").set_value("근거 비교").run()
    _clean(app)
    assert app.radio(key="wb_view").value == "근거 비교"
    assert app.text_input(key="wb_find").value == ""
    assert app.session_state["wb_run"] == run
    assert len(project.runs()) == 1 and other.runs() == []


def test_step_mode_returns_to_workspace_and_progress_routes_correctly(tmp_path, monkeypatch):
    project, _ = _project_with_value(tmp_path, "Finding")
    app = _app(project, monkeypatch)
    next(button for button in app.button if button.label == "단계별 보기").click().run()
    _clean(app)
    assert app.session_state["mode"] == "단계별(학습)"
    app.segmented_control(key="mode_pick").set_value("작업 화면").run()
    _clean(app)
    assert app.radio(key="wb_view").value == "근거 비교"
    app.button(key="wb_progress_PDF").click().run()
    _clean(app)
    assert app.radio(key="wb_view").value == "문헌 모으기"
    assert app.segmented_control(key="wb_library_view").value == "내 PDF"
    app.button(key="wb_progress_채택").click().run()
    _clean(app)
    assert app.radio(key="wb_view").value == "보고서에 쓰기"


def test_focus_and_table_preserve_search_status_columns_and_selected_evidence(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "Longer completion time")
    app = _app(project, monkeypatch)
    fields = [field["id"] for field in project.config()["fields"]][1:3]
    app.text_input(key="wb_find").set_value("Longer").run()
    app.selectbox(key="wb_filter").set_value("미검토").run()
    app.multiselect(key="wb_columns").set_value(fields).run()
    target = next(row["id"] for row in flow.evidence(project, run) if row["field_id"] == fields[-1])
    app.button(key="cell-" + target).click().run()
    _clean(app)
    assert app.session_state["wb_layout"] == "집중 검토"
    assert any(expander.label == "비교표 도구·필터" for expander in app.expander)
    assert app.text_input(key="wb_find").value == "Longer"
    assert app.selectbox(key="wb_filter").value == "미검토"
    assert app.multiselect(key="wb_columns").value == fields
    app.button(key="wb_back_table").click().run()
    _clean(app)
    assert app.session_state["wb_layout"] == "비교표"
    assert app.session_state["wb_pick"] == target
    assert app.text_input(key="wb_find").value == "Longer"
    assert app.selectbox(key="wb_filter").value == "미검토"
    assert app.multiselect(key="wb_columns").value == fields


def test_new_field_is_visible_as_pending_without_changing_saved_run(tmp_path, monkeypatch):
    project, run = _project_with_value(tmp_path, "Finding")
    snapshot = (project.run_dir(run) / "run.json").read_bytes()
    app = _app(project, monkeypatch)
    app.text_input(key="wb_f_name").set_value("Sample size")
    app.text_input(key="wb_f_inst").set_value("Keep the exact number of participants").run()
    app.button(key="wb_f_add").click().run()
    _clean(app)
    new_field = next(field for field in project.config()["fields"] if field["name"] == "Sample size")
    assert new_field["id"] in app.multiselect(key="wb_columns").value
    assert any('drk-th' in item.value and "Sample size" in item.value for item in app.markdown)
    assert any('drk-td-empty' in item.value and "AI 추출 대기" in item.value for item in app.markdown)
    assert (project.run_dir(run) / "run.json").read_bytes() == snapshot
    assert len(project.runs()) == 1


def test_seventh_field_keeps_six_selected_columns_and_explains_how_to_show_it(tmp_path, monkeypatch):
    project, _ = _project_with_value(tmp_path, "Finding")
    config = project.config()
    fields = config["fields"] + [
        {"id": f"extra-{i}", "name": f"Extra {i}", "instruction": "Keep the exact value"}
        for i in range(2)
    ]
    project.save_config(config["plan"], fields, config["synthesis_rules"])
    selected = [field["id"] for field in fields]
    app = _app(project, monkeypatch)
    app.multiselect(key="wb_columns").set_value(selected).run()
    app.text_input(key="wb_f_name").set_value("Sample size")
    app.text_input(key="wb_f_inst").set_value("Keep the exact number of participants").run()
    app.button(key="wb_f_add").click().run()
    _clean(app)
    assert len(project.config()["fields"]) == 7
    assert app.multiselect(key="wb_columns").value == selected
    assert any("표시 항목" in item.value and "최대 6개" in item.value for item in app.success)


@pytest.mark.parametrize("has_empty_run", [False, True])
def test_fields_are_editable_before_first_answer_and_with_empty_run(tmp_path, monkeypatch, has_empty_run):
    project = Project(tmp_path / "projects" / "research").initialize(question="A research question")
    source_id = project.add_pdf(_pdf("A study found longer completion time."), "study.pdf")
    project.screen(source_id, "include", "Relevant source")
    old_run = flow.prepare(project) if has_empty_run else None
    app = _app(project, monkeypatch)
    app.radio(key="wb_view").set_value("근거 비교").run()
    _clean(app)
    assert any(button.key == "wb_f_add" for button in app.button), "No field editor before the first extraction response"
    app.text_input(key="wb_f_name").set_value("Sample size")
    app.text_input(key="wb_f_inst").set_value("Keep the exact number of participants").run()
    app.button(key="wb_f_add").click().run()
    _clean(app)
    assert any(field["name"] == "Sample size" for field in project.config()["fields"])
    app.button(key="wb_make_request").click().run()
    _clean(app)
    new_run = app.session_state["wb_pending_run"]
    assert new_run != old_run
    assert any(field["name"] == "Sample size" for field in flow.manifest(project, new_run)["config"]["fields"])
    assert not flow.evidence(project, new_run)
