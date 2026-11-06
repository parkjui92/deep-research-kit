"""The manual note-to-paragraph flow stays local and keeps its source/revision trail."""
import io
import json
import zipfile

import pytest
from streamlit.testing.v1 import AppTest
from test_notebook import local_project

from deep_research import notebook, writing
from deep_research.project import Project, write_json


def note_fixture(tmp_path):
    p, sid = local_project(tmp_path)
    passage = p.index(sid)["passages"][0]
    note = notebook.save_note(p, sid, passage["id"], passage["text"], "Completion was slower", "주요 결과")
    return p, note


def test_old_note_can_be_revised_without_losing_quote_or_history(tmp_path):
    p, note = note_fixture(tmp_path)
    note.pop("revision")
    note.pop("history")
    write_json(p.root / "reading-notes.json", [note])
    saved = notebook.update_note(p, note["id"], "Only experienced workers were observed", "적용 한계", 1)
    assert saved["revision"] == 2
    assert saved["quote"] == note["quote"] and saved["locator"] == note["locator"]
    assert saved["history"][0]["memo"] == "Completion was slower"
    assert saved["review_status"] == "unreviewed_note" and not p.runs()
    assert notebook.notes(Project(p.root))[0] == saved
    with pytest.raises(ValueError, match="다른 화면"):
        notebook.update_note(p, note["id"], "Stale text", "기타", 1)
    with pytest.raises(ValueError):
        notebook.update_note(p, note["id"], " ", "기타", 2)
    assert notebook.notes(p)[0]["revision"] == 2


def test_note_search_combines_source_kind_and_terms(tmp_path):
    p, note = note_fixture(tmp_path)
    assert notebook.filter_notes(p, "local slower", "주요 결과", note["source_id"]) == [note]
    assert notebook.filter_notes(p, "randomized") == [note]
    assert notebook.filter_notes(p, "slower", "적용 한계") == []
    assert notebook.filter_notes(p, source_id="different") == []
    assert notebook.filter_notes(p, "slower missing") == []


def test_manual_paragraph_keeps_note_versions_and_has_no_ai_side_effect(tmp_path):
    from test_ui import _project_with_value

    from deep_research import workflow
    p, run = _project_with_value(tmp_path, "AI finding")
    before = workflow.evidence(p, run)
    source = p.catalog()[0]
    passage = p.index(source["id"])["passages"][0]
    note = notebook.save_note(p, source["id"], passage["id"], passage["text"], "My reading")
    first = writing.save_section(p, "A qualified claim", "Only in this setting", "Paragraph one.", [note["id"]], expected_revision=0)
    assert first["note_versions"] == {note["id"]: 1} and first["authorship"] == "human_draft"
    notebook.update_note(p, note["id"], "Interpretation revised", "적용 한계", 1)
    assert writing.changed_notes(first, notebook.notes(p)) == [note["id"]]
    assert "재확인 필요" in writing.markdown(p)
    second = writing.save_section(p, first["title"], first["claim"], "Paragraph revised.", [note["id"]], first["id"], 1)
    assert second["note_versions"] == {note["id"]: 2}
    assert writing.changed_notes(second, notebook.notes(p)) == []
    assert writing.load(p)["history"][-1]["previous"]["body"] == "Paragraph one."
    assert workflow.evidence(p, run) == before and workflow.accepted(p, run) == []


def test_draft_rejects_missing_notes_stale_edits_and_changed_original(tmp_path):
    p, note = note_fixture(tmp_path)
    with pytest.raises(ValueError, match="노트를 찾을"):
        writing.save_section(p, "Title", note_ids=["not-in-this-project"])
    assert writing.load(p)["sections"] == []
    section = writing.save_section(p, "Title", note_ids=[note["id"]])
    with pytest.raises(ValueError, match="다른 화면"):
        writing.save_section(p, "Stale title", section_id=section["id"], expected_revision=0)
    (p.source_dir(note["source_id"]) / "original.pdf").write_bytes(b"changed original")
    with pytest.raises(ValueError):
        writing.save_section(p, "Title", note_ids=[note["id"]])
    with pytest.raises(ValueError):
        writing.markdown(p)
    assert len(writing.load(p)["sections"]) == 1


def test_outline_can_be_reordered_and_prior_content_is_retained(tmp_path):
    p, _ = note_fixture(tmp_path)
    a = writing.save_section(p, "First")
    b = writing.save_section(p, "Second")
    writing.move_section(p, b["id"], -1, 2)
    assert [s["id"] for s in writing.load(p)["sections"]] == [b["id"], a["id"]]
    assert writing.load(p)["history"][-1]["previous_order"] == [a["id"], b["id"]]
    writing.move_section(p, b["id"], -1, 3)
    assert writing.load(p)["revision"] == 3
    with pytest.raises(ValueError):
        writing.move_section(p, a["id"], -1, 2)


def test_draft_export_keeps_citations_and_paragraph_breaks_without_hidden_markup(tmp_path):
    p, note = note_fixture(tmp_path)
    writing.save_section(p, "Evidence <title>", "A claim", "First paragraph.\n\n<script>Hidden</script> US$19", [note["id"], note["id"]])
    markdown = writing.markdown(p)
    assert "First paragraph.\n\n" in markdown
    assert "<script>" not in markdown and "&lt;script&gt;Hidden" in markdown
    assert "PDF 1쪽" in markdown and "19 percent" in markdown and "10.1/test" in markdown
    assert markdown.count(f"[^{note['id']}]:") == 1
    with zipfile.ZipFile(io.BytesIO(notebook.library_zip(p))) as archive:
        assert archive.read("report-draft.md").decode() == markdown
        document = json.loads(archive.read("report-draft.json"))
        assert document["sections"][0]["note_ids"] == [note["id"]]
        assert json.loads(archive.read("materials.json"))["report_draft"] == document


def _writing_app(root):
    from deep_research.project import Project
    from ui.writing import report_draft
    report_draft(Project(root))


def _notes_app(root):
    from deep_research.project import Project
    from ui.reading import notes_panel
    notes_panel(Project(root))


def test_writing_ui_selects_sources_before_save_and_keeps_unsaved_paragraph(tmp_path):
    p, note = note_fixture(tmp_path)
    app = AppTest.from_function(_writing_app, args=(str(p.root),)).run()
    assert not app.exception
    next(t for t in app.text_input if t.label == "논점 제목").set_value("The effect depends on context")
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("My paragraph with limitations.")
    app.multiselect[0].set_value([note["id"]]).run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "My paragraph with limitations."
    assert any("Completion was slower" in m.value for m in app.markdown)
    app.button(key="wb_draft_save").click().run()
    assert not app.exception
    section = writing.load(p)["sections"][0]
    assert section["note_ids"] == [note["id"]] and section["body"] == "My paragraph with limitations."
    app.button(key="wb_draft_read_" + note["id"]).click().run()
    assert app.session_state["wb_route"] == "문헌 모으기"
    assert app.session_state["wb_passage_" + note["source_id"]] == note["locator"]["passage_id"]


def test_notes_ui_edits_filters_and_sends_note_to_report(tmp_path):
    p, note = note_fixture(tmp_path)
    app = AppTest.from_function(_notes_app, args=(str(p.root),)).run()
    assert not app.exception
    next(t for t in app.text_area if t.label == "메모 수정").set_value("Changed interpretation")
    next(b for b in app.button if b.label == "메모 수정 저장").click().run()
    assert not app.exception
    assert notebook.notes(p)[0]["history"][0]["memo"] == "Completion was slower"
    app.text_input(key="wb_notes_query").set_value("notfound").run()
    assert any("조건에 맞는 노트" in i.value for i in app.info)
    app.text_input(key="wb_notes_query").set_value("changed").run()
    app.button(key="wb_note_link_" + note["id"]).click().run()
    assert app.session_state["wb_output_route"] == "내 보고서 초안"
    assert app.session_state["wb_report_note_to_link"] == note["id"]


def test_ui_warns_when_a_linked_note_was_revised(tmp_path):
    p, note = note_fixture(tmp_path)
    section = writing.save_section(p, "Claim", note_ids=[note["id"]])
    notebook.update_note(p, note["id"], "A narrower claim", "적용 한계", 1)
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    assert not app.exception
    assert any("연결 노트가 수정" in w.value for w in app.warning)
    assert any("A narrower claim" in m.value for m in app.markdown)


def test_archived_outline_point_can_be_restored_with_its_links_and_body(tmp_path):
    p, note = note_fixture(tmp_path)
    section = writing.save_section(p, "A superseded point", body="Keep this draft", note_ids=[note["id"]])
    writing.archive_section(p, section["id"], 1)
    assert writing.load(p)["sections"] == []
    assert "Keep this draft" not in writing.markdown(p)
    app = AppTest.from_function(_writing_app, args=(str(p.root),)).run()
    app.button(key="wb_draft_restore_" + section["id"]).click().run()
    assert not app.exception
    assert writing.load(p)["sections"][0] == section
    assert writing.load(p)["archived"] == []
    app.button(key="wb_draft_archive").click().run()
    assert not app.exception and writing.load(p)["sections"] == []


def test_retraction_warning_reaches_manual_draft_and_linked_note_ui(tmp_path):
    from deep_research import integrity
    p, note = note_fixture(tmp_path)
    p.set_integrity(note["source_id"], integrity.from_search({"doi": "10.1/test", "retracted": True}))
    section = writing.save_section(p, "Claim needing caution", note_ids=[note["id"]])
    assert "문헌 고지 · 인용 전 확인" in writing.markdown(p) and "철회됨" in writing.markdown(p)
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    assert any("철회됨" in e.value for e in app.error)


def test_ui_handles_reorder_conflict_without_exception(tmp_path, monkeypatch):
    p, _ = note_fixture(tmp_path)
    section = writing.save_section(p, "First")
    writing.save_section(p, "Second")
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    def conflict(*args, **kwargs):
        raise ValueError("다른 화면에서 초안이 수정되었습니다.")
    monkeypatch.setattr(writing, "move_section", conflict)
    app.button(key="wb_draft_down").click().run()
    assert not app.exception and any("다른 화면" in e.value for e in app.error)


def test_saved_note_to_draft_and_back_ignores_old_note_filters(tmp_path):
    from test_ui import _workbench_script
    p, _ = local_project(tmp_path)
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["drk_claude_ready"] = False
    app.session_state["wb_library_view"] = "원문 검색·노트"
    app.session_state["wb_notes_query"] = "an old unrelated filter"
    app.session_state["wb_notes_kind"] = "후속 질문"
    app.run()
    next(t for t in app.text_area if t.label == "내 메모").set_value("A useful contextual note")
    next(b for b in app.button if b.label == "발췌·메모 저장").click().run()
    assert not app.exception
    app.button(key="wb_saved_note_report").click().run()
    assert not app.exception
    assert app.session_state["wb_output_kind"] == "내 보고서 초안"
    note = notebook.notes(p)[0]
    assert app.multiselect[0].value == [note["id"]]
    next(t for t in app.text_input if t.label == "논점 제목").set_value("Context")
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("My linked paragraph")
    app.button(key="wb_draft_save").click().run()
    assert not app.exception
    assert writing.load(p)["sections"][0]["note_ids"] == [note["id"]]
    app.button(key="wb_draft_read_" + note["id"]).click().run()
    assert not app.exception
    assert app.session_state["wb_view"] == "문헌 모으기"
    app.button(key="wb_saved_note_list").click().run()
    assert not app.exception
    assert app.text_input(key="wb_notes_query").value == ""
    assert any("A useful contextual note" in m.value for m in app.markdown)


def test_unsaved_fields_survive_reordering_switching_and_archive_restore(tmp_path):
    p, note = note_fixture(tmp_path)
    first = writing.save_section(p, "First", body="Saved first", note_ids=[note["id"]])
    second = writing.save_section(p, "Second", body="Saved second")
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = first["id"]
    app.run()
    next(t for t in app.text_input if t.label == "논점 제목").set_value("Unsaved title")
    next(t for t in app.text_area if t.label == "핵심 주장").set_value("Unsaved claim")
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Unsaved body")
    app.multiselect[0].set_value([])
    app.button(key="wb_draft_down").click().run()
    assert not app.exception
    assert app.selectbox(key="wb_draft_section").value == first["id"]
    assert next(t for t in app.text_input if t.label == "논점 제목").value == "Unsaved title"
    assert next(t for t in app.text_area if t.label == "핵심 주장").value == "Unsaved claim"
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Unsaved body"
    assert app.multiselect[0].value == []
    app.selectbox(key="wb_draft_section").set_value(second["id"]).run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Second unsaved body")
    app.selectbox(key="wb_draft_section").set_value(first["id"]).run()
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Unsaved body"
    app.button(key="wb_draft_archive").click().run()
    app.button(key="wb_draft_restore_" + first["id"]).click().run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Unsaved body"
    assert next(s for s in writing.load(p)["sections"] if s["id"] == first["id"])["body"] == "Saved first"
    app.selectbox(key="wb_draft_section").set_value(second["id"]).run()
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Second unsaved body"


def test_unsaved_paragraph_survives_source_reading_roundtrip(tmp_path):
    from test_ui import _workbench_script
    p, note = note_fixture(tmp_path)
    section = writing.save_section(p, "Keep my place", body="Saved body", note_ids=[note["id"]])
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["drk_claude_ready"] = False
    app.session_state["wb_view"] = "보고서에 쓰기"
    app.session_state["wb_output_kind"] = "내 보고서 초안"
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Remember my unsaved paragraph")
    app.button(key="wb_draft_read_" + note["id"]).click().run()
    assert app.session_state["wb_view"] == "문헌 모으기"
    app.button(key="wb_return_to_draft").click().run()
    assert not app.exception
    assert app.selectbox(key="wb_draft_section").value == section["id"]
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Remember my unsaved paragraph"
    assert writing.load(p)["sections"][0]["body"] == "Saved body"
    app.button(key="wb_draft_save").click().run()
    assert writing.load(p)["sections"][0]["body"] == "Remember my unsaved paragraph"


def test_external_saved_change_keeps_local_draft_and_blocks_overwrite(tmp_path):
    p, _ = note_fixture(tmp_path)
    section = writing.save_section(p, "Title", body="Initial saved body")
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Local unsaved body").run()
    writing.save_section(p, "Title", body="Saved from another window", section_id=section["id"])
    app.run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Local unsaved body"
    assert app.button(key="wb_draft_save").disabled
    assert any("저장본이 바뀌었습니다" in w.value for w in app.warning)
    app.button(key="wb_draft_reload").click().run()
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Saved from another window"


def two_note_fixture(tmp_path):
    from reportlab.pdfgen import canvas
    p, first = note_fixture(tmp_path)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(40, 750, "A separate study measured accuracy in a different population.")
    pdf.showPage()
    pdf.save()
    sid = p.add_pdf(buffer.getvalue(), "second.pdf", "A second study", "10.1/second")
    passage = p.index(sid)["passages"][0]
    second = notebook.save_note(p, sid, passage["id"], passage["text"], "Accuracy in another population", "적용 한계")
    return p, first, second


def test_source_panel_shows_one_note_and_keeps_unsaved_text_when_switching(tmp_path):
    p, first, second = two_note_fixture(tmp_path)
    section = writing.save_section(p, "Compare settings", note_ids=[first["id"], second["id"]])
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    assert len([b for b in app.button if b.label == "원문에서 확인"]) == 1
    assert app.button(key="wb_draft_read_" + first["id"])
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Keep writing while checking notes")
    app.selectbox(key="wb_draft_note_pick_" + section["id"]).set_value(second["id"]).run()
    assert not app.exception
    assert len([b for b in app.button if b.label == "원문에서 확인"]) == 1
    assert app.button(key="wb_draft_read_" + second["id"])
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Keep writing while checking notes"
    app.multiselect[0].set_value([first["id"]]).run()
    assert not app.exception
    assert app.selectbox(key="wb_draft_note_pick_" + section["id"]).value == first["id"]
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Keep writing while checking notes"


def test_link_search_and_source_filter_keep_existing_links_and_unsaved_paragraph(tmp_path):
    p, first, second = two_note_fixture(tmp_path)
    section = writing.save_section(p, "Keep selected sources", note_ids=[first["id"]])
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("Unfinished paragraph")
    app.text_input(key="wb_draft_link_query").set_value("accuracy")
    app.selectbox(key="wb_draft_link_source").set_value(second["source_id"]).run()
    assert not app.exception
    assert app.multiselect[0].value == [first["id"]]
    assert len(app.multiselect[0].options) == 2  # kept selection + matching add candidate
    app.multiselect[0].set_value([first["id"], second["id"]]).run()
    app.text_input(key="wb_draft_link_query").set_value("no result here").run()
    assert app.multiselect[0].value == [first["id"], second["id"]]
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "Unfinished paragraph"
    app.button(key="wb_draft_save").click().run()
    assert not app.exception
    assert writing.load(p)["sections"][0]["note_ids"] == [first["id"], second["id"]]


def test_other_linked_source_warning_stays_visible_when_its_note_is_not_selected(tmp_path):
    from deep_research import integrity
    p, first, second = two_note_fixture(tmp_path)
    p.set_integrity(second["source_id"], integrity.from_search({"doi": "10.1/second", "retracted": True}))
    section = writing.save_section(p, "Compare cautiously", note_ids=[first["id"], second["id"]])
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    assert app.selectbox(key="wb_draft_note_pick_" + section["id"]).value == first["id"]
    assert any("철회됨" in w.value and "A second study" in w.value for w in app.warning)
    app.selectbox(key="wb_draft_note_pick_" + section["id"]).set_value(second["id"]).run()
    assert any("철회됨" in e.value for e in app.error)


def test_outline_buttons_preserve_each_paragraph_draft(tmp_path):
    p, _ = note_fixture(tmp_path)
    first = writing.save_section(p, "First outline point")
    second = writing.save_section(p, "Second outline point")
    app = AppTest.from_function(_writing_app, args=(str(p.root),))
    app.session_state["wb_draft_section"] = first["id"]
    app.run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("First unsaved paragraph")
    app.button(key="wb_draft_outline_" + second["id"]).click().run()
    assert app.selectbox(key="wb_draft_section").value == second["id"]
    assert "미저장" in app.button(key="wb_draft_outline_" + first["id"]).label
    app.button(key="wb_draft_outline_" + first["id"]).click().run()
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "First unsaved paragraph"


def test_selected_source_note_survives_reading_return(tmp_path):
    from test_ui import _workbench_script
    p, first, second = two_note_fixture(tmp_path)
    section = writing.save_section(p, "Keep source selection", note_ids=[first["id"], second["id"]])
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["drk_claude_ready"] = False
    app.session_state["wb_view"] = "보고서에 쓰기"
    app.session_state["wb_output_kind"] = "내 보고서 초안"
    app.session_state["wb_draft_section"] = section["id"]
    app.run()
    app.selectbox(key="wb_draft_note_pick_" + section["id"]).set_value(second["id"]).run()
    next(t for t in app.text_area if t.label == "내가 쓸 문단").set_value("A paragraph in progress")
    app.button(key="wb_draft_read_" + second["id"]).click().run()
    app.button(key="wb_return_to_draft").click().run()
    assert not app.exception
    assert app.selectbox(key="wb_draft_note_pick_" + section["id"]).value == second["id"]
    assert next(t for t in app.text_area if t.label == "내가 쓸 문단").value == "A paragraph in progress"


@pytest.mark.parametrize("has_ai_result", [False, True])
def test_saved_draft_opens_first_but_explicit_output_choice_survives_navigation(tmp_path, has_ai_result):
    from test_ui import _project_with_value, _workbench_script

    if has_ai_result:
        project, _ = _project_with_value(tmp_path, "19 percent longer")
    else:
        project, _ = note_fixture(tmp_path)
    writing.save_section(project, "Existing manual draft", body="A saved paragraph")
    app = AppTest.from_function(_workbench_script, args=(str(project.root),))
    app.session_state["drk_claude_ready"] = False
    app.run()
    app.radio(key="wb_view").set_value("보고서에 쓰기").run()
    assert not app.exception
    assert app.segmented_control(key="wb_output_kind").value == "내 보고서 초안"
    assert any(h.value == "노트로 내 보고서 쓰기" for h in app.header)

    app.segmented_control(key="wb_output_kind").set_value("독서 노트·자료").run()
    assert any(h.value == "출처가 붙은 독서 노트" for h in app.header)
    app.radio(key="wb_view").set_value("문헌 모으기").run()
    assert not app.exception
    app.radio(key="wb_view").set_value("보고서에 쓰기").run()
    assert not app.exception
    assert app.segmented_control(key="wb_output_kind").value == "독서 노트·자료"
    assert any(h.value == "출처가 붙은 독서 노트" for h in app.header)
    assert writing.load(project)["sections"][0]["body"] == "A saved paragraph"
