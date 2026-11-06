import io
import json
import zipfile

import pytest
from reportlab.pdfgen import canvas
from streamlit.testing.v1 import AppTest

from deep_research import notebook
from deep_research.project import Project


def local_project(tmp_path):
    project = Project(tmp_path / "reading").initialize("Reading", question="Does the intervention work?")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for line in ["A randomized study found 19 percent longer completion time.",
                 "The sample included sixteen experienced researchers."]:
        pdf.drawString(40, 750, line)
        pdf.showPage()
    pdf.save()
    sid = project.add_pdf(buffer.getvalue(), "paper.pdf", "A local study", "10.1/test")
    return project, sid


def test_new_question_has_no_sample_criteria(tmp_path):
    project, _ = local_project(tmp_path)
    plan = project.config()["plan"]
    assert plan["question"] == "Does the intervention work?"
    assert not plan["inclusion"] and not plan["exclusion"] and not plan["scope"]
    with pytest.raises(ValueError):
        Project(tmp_path / "blank").initialize(question="  ")
    assert not (tmp_path / "blank").exists()


def test_search_and_notes_work_without_ai_or_network(tmp_path, monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: pytest.fail("Unexpected network"))
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: pytest.fail("Unexpected AI request"))
    p, sid = local_project(tmp_path)
    hits = notebook.search_passages(p, "sample researchers")["hits"]
    assert len(hits) == 1 and hits[0]["page"] == 2
    assert notebook.search_passages(p, "completion sample")["total"] == 0
    assert notebook.search_passages(p, "sample", source_ids=set())["total"] == 0
    hit = hits[0]
    note = notebook.save_note(p, sid, hit["passage_id"], hit["text"], "Limited sample", "적용 한계")
    assert note["locator"]["page"] == 2 and note["locator"]["boxes"]
    assert note["review_status"] == "unreviewed_note" and not p.runs()
    assert notebook.save_note(p, sid, hit["passage_id"], hit["text"], "Limited sample", "적용 한계") == note
    assert len(notebook.notes(Project(p.root))) == 1
    with pytest.raises(ValueError, match="찾지 못"):
        notebook.save_note(p, sid, hit["passage_id"], "There were a thousand people", "Wrong quotation")
    with pytest.raises(ValueError):
        notebook.search_passages(p, " ")


def test_notes_do_not_change_existing_ai_review(tmp_path):
    from test_ui import _project_with_value

    from deep_research import workflow as flow
    p, run = _project_with_value(tmp_path, "A finding")
    before = flow.evidence(p, run)
    sid = p.catalog()[0]["id"]
    passage = p.index(sid)["passages"][0]
    notebook.save_note(p, sid, passage["id"], passage["text"], "My interpretation")
    assert flow.evidence(p, run) == before and flow.accepted(p, run) == []


def test_resaving_candidate_preserves_reading_and_acquired_pdf(tmp_path):
    p, sid = local_project(tmp_path)
    record = {"title": "A local study", "doi": "https://doi.org/10.1/TEST", "status": "saved", "search_query": "query one"}
    p.remember_candidate(record)
    notebook.update_reading(p, notebook.candidate_key(record), "later", "Check methods")
    p.remember_candidate({**record, "doi": "10.1/test", "status": "added", "source_id": sid})
    p.remember_candidate({**record, "status": "saved", "source_id": None, "search_query": "query two"})
    items = Project(p.root).collection()
    assert len(items) == 1 and items[0]["source_id"] == sid and items[0]["status"] == "added"
    assert items[0]["reading"]["reason"] == "Check methods"
    assert items[0]["discovered_in"] == ["query one", "query two"]


def test_material_export_before_ai_preserves_sources_and_escapes(tmp_path, monkeypatch):
    p, sid = local_project(tmp_path)
    passage = p.index(sid)["passages"][0]
    notebook.save_note(p, sid, passage["id"], passage["text"], "<script>memo</script>")
    p.remember_candidate({"title": "A local study", "doi": "10.1/test", "authors": ["A\nB"], "status": "saved"})
    p.log_search({"query": "=DANGEROUS()", "provider": "Offline fixture", "returned": 1})
    monkeypatch.setenv("DRK_API_KEY", "secret-must-never-export")
    data = notebook.library_zip(p, include_pdfs=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert f"sources/{sid}.pdf" in z.namelist()
        assert z.read(f"sources/{sid}.pdf") == (p.source_dir(sid) / "original.pdf").read_bytes()
        assert "'=DANGEROUS()" in z.read("search-log.csv").decode("utf-8-sig")
        assert "<script>" not in z.read("reading-notes.md").decode()
        assert z.read("references.ris").decode().count("TY  - GEN") == 1
        assert "AU  - A B" in z.read("references.ris").decode()
        assert json.loads(z.read("materials.json"))["notes"][0]["locator"]["page"] == 1
        assert all(b"secret-must-never-export" not in z.read(name) for name in z.namelist())
    assert not p.runs()


def test_modified_original_cannot_silently_create_notes(tmp_path):
    p, sid = local_project(tmp_path)
    passage = p.index(sid)["passages"][0]
    (p.source_dir(sid) / "original.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError):
        notebook.save_note(p, sid, passage["id"], passage["text"], "Memo")
    assert notebook.notes(p) == []


def test_reading_note_to_report_and_back(tmp_path):
    from test_ui import _button, _workbench_script
    p, sid = local_project(tmp_path)
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state["drk_claude_ready"] = False
    app.session_state["wb_library_view"] = "원문 검색·노트"
    app = app.run()
    app.text_input(key="wb_local_query").set_value("sample")
    _button(app, "내 PDF 전체에서 검색").click().run()
    assert not app.exception
    next(t for t in app.text_area if t.label == "내 메모").set_value("Small sample matters")
    _button(app, "발췌·메모 저장").click().run()
    assert not app.exception
    note = notebook.notes(p)[0]
    assert note["locator"]["page"] == 2
    app.session_state["wb_view"] = "보고서에 쓰기"
    app.run()
    assert not app.exception
    assert any("Small sample matters" in m.value for m in app.markdown)
    _button(app, "이 원문 다시 읽기").click().run()
    assert not app.exception
    assert app.session_state["wb_view"] == "문헌 모으기"
    assert app.selectbox(key="wb_passage_" + sid).value == note["locator"]["passage_id"]


def test_api_not_called_until_user_executes(tmp_path, monkeypatch):
    from test_ui import _project_with_value, _workbench_script

    from deep_research import providers
    p, _ = _project_with_value(tmp_path, "A finding")
    monkeypatch.setenv("DRK_API_BASE", "http://127.0.0.1:9999/v1")
    monkeypatch.setenv("DRK_MODEL", "test-model")
    monkeypatch.setattr(providers, "extract_with_api", lambda *a: pytest.fail("Unrequested extraction"))
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    assert not app.exception
    assert any("로컬 주소" in m.value and "test-model" in m.value for m in app.markdown)
    assert any(b.key == "wb_api_extract" for b in app.button)


def test_review_edit_field_is_only_shown_for_edit(tmp_path):
    from test_ui import _project_with_value, _workbench_script
    p, _ = _project_with_value(tmp_path, "A finding")
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run()
    assert not any(t.label.startswith("수정한 값") for t in app.text_area)
    app.button(key="wb_focus").click().run()
    next(r for r in app.radio if r.label == "이 값을").set_value("edit").run()
    assert not app.exception
    assert next(t for t in app.text_area if t.label.startswith("수정한 값")).value == "A finding"


def test_start_opens_existing_app_with_user_question(tmp_path, monkeypatch):
    from pathlib import Path

    from test_ui import _button
    monkeypatch.setenv("DRK_PROJECTS_DIR", str(tmp_path / "projects"))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    _button(app, "PDF에서 시작").click().run()
    next(t for t in app.text_input if t.label == "이번에 알아볼 질문").set_value("My real question")
    _button(app, "PDF 가져오기로 이동").click().run()
    assert not app.exception
    assert app.session_state["wb_library_view"] == "내 PDF"
    p = Project(tmp_path / "projects" / app.session_state["project_name"])
    assert p.config()["plan"]["question"] == "My real question"
    assert "research-" in p.root.name
