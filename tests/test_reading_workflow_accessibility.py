"""Candidate choice and source-note navigation remain usable without paid AI."""
import json

import pytest
from streamlit.proto.WidgetStates_pb2 import WidgetStates
from streamlit.testing.v1 import AppTest
from test_notebook import local_project
from test_ui import _workbench_script

from deep_research import notebook, providers


def _candidate_app(root):
    from deep_research.project import Project
    from ui.reading import candidate_queue
    candidate_queue(Project(root))


def _reading_app(root):
    from deep_research.project import Project
    from ui.reading import reading_room
    reading_room(Project(root))


def _app(script, project):
    app = AppTest.from_function(script, args=(str(project.root),))
    app.session_state["drk_claude_ready"] = False
    return app


@pytest.fixture(autouse=True)
def no_external_requests(monkeypatch):
    import httpx

    def unexpected(*args, **kwargs):
        pytest.fail("This reading workflow must not call an external service")

    monkeypatch.setattr(httpx.Client, "send", unexpected)


def _candidates(tmp_path):
    project, sid = local_project(tmp_path)
    records = [
        {"title": "Available study", "doi": "10.1/full", "source_id": sid, "status": "added"},
        {"title": "Later study", "doi": "10.1/later", "abstract": "A sample in another setting", "status": "saved"},
        {"title": "Unread methods", "doi": "10.1/methods", "status": "saved"},
        {"title": "Finished study", "doi": "10.1/done", "status": "saved"},
    ]
    for record in records:
        project.remember_candidate(record)
    notebook.update_reading(project, notebook.candidate_key(records[1]), "later", "Compare sample methods")
    notebook.update_reading(project, notebook.candidate_key(records[3]), "done", "Already read")
    return project, records


def _select_table_row(app, row):
    """AppTest has no dataframe click API; send the native row-selection event."""
    table_id = app.dataframe[0].proto.id
    states = WidgetStates()
    for widget in app._tree.get_widget_states().widgets:
        if widget.id != table_id:
            states.widgets.add().CopyFrom(widget)
    states.widgets.add(id=table_id, string_value=json.dumps({"selection": {"rows": [row], "columns": []}}))
    return app._run(states)


def test_candidate_filters_combine_and_empty_filter_can_be_reset_without_losing_candidates(tmp_path):
    project, records = _candidates(tmp_path)
    before = project.collection()
    app = _app(_candidate_app, project).run()
    app.text_input(key="wb_candidate_query").set_value("SAMPLE methods")
    app.selectbox(key="wb_candidate_reading").set_value("later")
    app.selectbox(key="wb_candidate_text").set_value("abstract").run()
    assert not app.exception
    assert app.dataframe[0].value["문헌"].tolist() == ["Later study"]
    assert app.selectbox(key="wb_candidate").value == notebook.candidate_key(records[1])
    assert app.text_area[0].value == "Compare sample methods"
    app.selectbox(key="wb_candidate_text").set_value("full").run()
    assert not app.exception and not app.dataframe
    assert any("조건에 맞는 후보" in info.value for info in app.info)
    app.button(key="wb_candidate_reset").click().run()
    assert len(app.dataframe[0].value) == 4
    assert app.text_input(key="wb_candidate_query").value == ""
    assert project.collection() == before


def test_candidate_table_selection_and_keyboard_picker_stay_in_sync(tmp_path):
    project, records = _candidates(tmp_path)
    app = _app(_candidate_app, project).run()
    # Row 1 is the second unread candidate, not the second insertion-order item.
    _select_table_row(app, 1)
    assert not app.exception
    assert app.selectbox(key="wb_candidate").value == notebook.candidate_key(records[2])
    assert any("선택한 후보 · Unread methods" in m.value for m in app.markdown)
    selected = app.dataframe[0].value.query("선택 == '선택됨'")["문헌"].tolist()
    assert selected == ["Unread methods"]
    old_table = app.dataframe[0].key
    app.selectbox(key="wb_candidate").set_value(notebook.candidate_key(records[1])).run()
    assert not app.exception
    assert app.dataframe[0].key != old_table
    assert any("선택한 후보 · Later study" in m.value for m in app.markdown)
    assert app.text_area[0].value == "Compare sample methods"
    _select_table_row(app, 0)
    assert app.selectbox(key="wb_candidate").value == notebook.candidate_key(records[0])


def test_bulk_pdf_action_respects_filters_and_excludes_finished_candidates(tmp_path, monkeypatch):
    project, records = _candidates(tmp_path)
    requested = []

    def collect(project, item):
        requested.append(item["title"])
        return {"source_id": None}

    monkeypatch.setattr(providers, "collect", collect)
    app = _app(_candidate_app, project).run()
    app.selectbox(key="wb_candidate_reading").set_value("later").run()
    app.button(key="wb_collect_all").click().run()
    assert not app.exception and requested == [records[1]["title"]]
    app.selectbox(key="wb_candidate_reading").set_value("done").run()
    assert not any(b.key == "wb_collect_all" for b in app.button)
    assert project.collection()[1]["reading"]["reason"] == "Compare sample methods"


def test_bulk_pdf_action_continues_after_a_file_error(tmp_path, monkeypatch):
    project, _ = _candidates(tmp_path)
    requested = []

    def collect(project, item):
        requested.append(item["title"])
        if len(requested) == 1:
            raise OSError("Temporary PDF write failure")
        return {"source_id": None}

    monkeypatch.setattr(providers, "collect", collect)
    before = project.collection()
    app = _app(_candidate_app, project).run()
    app.button(key="wb_collect_all").click().run()
    assert not app.exception
    assert requested == ["Unread methods", "Later study"]
    assert "2편 가운데 0편" in app.session_state["flash"]
    assert project.collection() == before


def test_closing_search_keeps_the_current_source_and_page(tmp_path):
    project, sid = local_project(tmp_path)
    app = _app(_reading_app, project).run()
    first_passage = app.selectbox(key="wb_passage_" + sid).value
    app.text_input(key="wb_local_query").set_value("sample")
    next(b for b in app.button if b.label == "내 PDF 전체에서 검색").click().run()
    result = app.session_state["wb_local_results"]["hits"][0]
    assert result["page"] == 2 and result["passage_id"] != first_passage
    app.button(key="wb_local_clear").click().run()
    assert not app.exception
    assert app.selectbox(key="wb_read_source").value == sid
    assert app.selectbox(key="wb_passage_" + sid).value == result["passage_id"]
    assert next(t for t in app.text_area if t.label == "원문에서 남길 발췌").value == result["text"]


def test_note_source_roundtrip_restores_filters_and_contextual_action_labels(tmp_path):
    project, sid = local_project(tmp_path)
    passages = project.index(sid)["passages"]
    for passage, memo, kind in zip(passages, ["Completion time", "Sample limitation"], ["주요 결과", "적용 한계"]):
        notebook.save_note(project, sid, passage["id"], passage["text"], memo, kind)
    target = notebook.notes(project)[1]
    app = _app(_workbench_script, project)
    app.session_state["wb_view"] = "보고서에 쓰기"
    app.session_state["wb_output_kind"] = "독서 노트·자료"
    app.run()
    labels = [b.label for b in app.button if b.key and b.key.startswith("wb_note_go_")]
    assert len(labels) == len(set(labels)) == 2
    assert all("A local study" in label and "쪽" in label for label in labels)
    app.text_input(key="wb_notes_query").set_value("sample")
    app.selectbox(key="wb_notes_kind").set_value("적용 한계")
    app.selectbox(key="wb_notes_source").set_value(sid).run()
    app.button(key="wb_note_go_" + target["id"]).click().run()
    assert not app.exception
    assert app.selectbox(key="wb_passage_" + sid).value == target["locator"]["passage_id"]
    app.button(key="wb_return_to_notes").click().run()
    assert not app.exception
    assert app.text_input(key="wb_notes_query").value == "sample"
    assert app.selectbox(key="wb_notes_kind").value == "적용 한계"
    assert app.selectbox(key="wb_notes_source").value == sid
    assert any("Sample limitation" in m.value for m in app.markdown)
    assert not project.runs()
