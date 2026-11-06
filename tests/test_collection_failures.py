"""Bad PDFs must not discard the candidate or stop the rest of an upload batch."""
import io

from reportlab.pdfgen import canvas
from streamlit.testing.v1 import AppTest

from deep_research import acquire, notebook, providers
from deep_research.project import Project


def _pdf(text):
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer)
    document.drawString(30, 750, text)
    document.showPage()
    document.save()
    return buffer.getvalue()


def _candidate_script(root):
    from deep_research.project import Project
    from ui.reading import candidate_queue
    candidate_queue(Project(root))


def _upload_script(root):
    from deep_research.project import Project
    from ui.workbench import _import_popover
    _import_popover(Project(root))


class Upload:
    def __init__(self, name, data):
        self.name, self.data = name, data

    def getvalue(self):
        return self.data


def test_unavailable_pdf_keeps_failure_visible_and_offers_manual_import(tmp_path, monkeypatch):
    p = Project(tmp_path / "p").initialize(question="What works?")
    candidate = providers._candidate(title="Unavailable paper", doi="10.1/x", url="https://example.test/paper")
    p.remember_candidate(candidate)
    notebook.update_reading(p, notebook.candidate_key(candidate), "later", "Compare the method")
    monkeypatch.setattr(acquire, "find_pdf", lambda *a, **kw: (None, [
        {"route": "논문 페이지", "url": candidate["url"], "result": "접근 거부(403)"}]))
    app = AppTest.from_function(_candidate_script, args=(str(p.root),)).run(timeout=30)
    next(b for b in app.button if b.label == "공개 PDF 찾아 등록").click().run(timeout=30)
    assert not app.exception and not app.success
    assert any("공개 PDF를 확보하지 못했습니다" in item.value for item in app.warning)
    assert p.collection()[0]["reading"]["reason"] == "Compare the method"
    app.run()
    assert any("공개 PDF를 확보하지 못했습니다" in item.value for item in app.warning)
    app.button(key="wb_candidate_import").click().run()
    assert app.session_state["wb_library_route"] == "내 PDF"
    assert not p.catalog()


def test_candidate_corrupt_pdf_shows_error_and_can_retry_without_losing_notes(tmp_path, monkeypatch):
    p = Project(tmp_path / "p").initialize(question="What works?")
    candidate = providers._candidate(title="Candidate paper", doi="10.1/x", url="https://example.test/paper")
    p.remember_candidate(candidate)
    notebook.update_reading(p, notebook.candidate_key(candidate), "later", "Compare the research method")
    payload = [b"%PDF-1.4 broken"]
    monkeypatch.setattr(acquire, "find_pdf", lambda *a, **kw: (payload[0], []))
    app = AppTest.from_function(_candidate_script, args=(str(p.root),)).run(timeout=30)
    next(b for b in app.button if b.label == "공개 PDF 찾아 등록").click().run(timeout=30)
    assert not app.exception and not app.success
    assert any("등록하지 못했습니다" in error.value for error in app.error)
    assert not p.catalog()
    assert p.collection()[0]["reading"]["reason"] == "Compare the research method"
    payload[0] = _pdf("A valid replacement PDF containing research findings.")
    next(b for b in app.button if b.label == "공개 PDF 찾아 등록").click().run(timeout=30)
    assert not app.exception and not app.error
    assert len(p.catalog()) == 1 and p.collection()[0]["source_id"] == p.catalog()[0]["id"]
    assert p.collection()[0]["reading"]["state"] == "later"
    assert app.session_state["flash"] == "PDF를 등록했습니다."


def test_mixed_upload_continues_after_bad_pdf_and_retries_count_duplicates_truthfully(tmp_path, monkeypatch):
    import streamlit as st

    p = Project(tmp_path / "p").initialize(question="What works?")
    good = Upload("good.pdf", _pdf("First valid research document."))
    bad = Upload("broken.pdf", b"%PDF-1.4 broken")
    later = Upload("later.pdf", _pdf("Third valid research document."))
    files = [good, bad, later]
    monkeypatch.setattr(st, "file_uploader", lambda label, **kw: files if label.startswith("PDF") else None)
    app = AppTest.from_function(_upload_script, args=(str(p.root),)).run(timeout=30)
    app.button(key="wb_pdf_add").click().run(timeout=30)
    assert not app.exception and len(p.catalog()) == 2
    assert not app.success
    assert any("새 등록 2개 · 이미 등록 0개 · 실패 1개" in item.value for item in app.warning)
    assert any("broken.pdf" in item.value for item in app.error)
    before = {s["id"]: (p.source_dir(s["id"]) / "original.pdf").read_bytes() for s in p.catalog()}
    bad.data = _pdf("A repaired second research document.")
    app.button(key="wb_pdf_add").click().run(timeout=30)
    assert not app.exception and not app.error and not app.warning
    assert len(p.catalog()) == 3
    assert any("새 등록 1개 · 이미 등록 2개 · 실패 0개" in item.value for item in app.success)
    assert all((p.source_dir(sid) / "original.pdf").read_bytes() == data for sid, data in before.items())
    # A later, wholly failed batch must not leave the previous success banner on screen.
    files[:] = [Upload("still-broken.pdf", b"not a PDF")]
    app.button(key="wb_pdf_add").click().run(timeout=30)
    assert not app.exception and len(p.catalog()) == 3 and not app.success
    assert any("새 등록 0개 · 이미 등록 0개 · 실패 1개" in item.value for item in app.warning)
    assert any("등록한 파일이 없습니다" in item.value for item in app.caption)
