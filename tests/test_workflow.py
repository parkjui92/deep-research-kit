import copy
import io
import json
import zipfile

import pytest
from reportlab.pdfgen import canvas

from deep_research import workflow as w
from deep_research.documents import locate_quote, normalize
from deep_research.exports import compare, export_zip, report
from deep_research.project import Project, read_json


def pdf_bytes(text="A randomized study found 19 percent longer completion time."):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 750, text)
    pdf.showPage()
    pdf.drawString(50, 750, "Repeated evidence phrase. Repeated evidence phrase.")
    pdf.showPage()
    pdf.showPage()  # no text layer
    pdf.save()
    return buf.getvalue()


@pytest.fixture
def project(tmp_path):
    p = Project(tmp_path / "research").initialize()
    sid = p.add_pdf(pdf_bytes(), "paper.pdf", "Test study", "10.1234/test")
    p.screen(sid, "include", "Observed task outcome")
    return p


def response(p, run):
    sid = p.catalog()[0]["id"]
    request = read_json(p.run_dir(run) / "requests" / (sid + ".json"))
    passage = request["passages"][0]
    return {"request_id": request["request_id"], "rows": [
        {"source_id": sid, "field_id": f["id"], "value": "Test finding",
         "quotes": [{"passage_id": passage["id"], "quote": passage["text"]}]}
        for f in request["config"]["fields"]]}


def extracted(p):
    run = w.prepare(p)
    w.import_extraction(p, run, response(p, run))
    return run


def test_real_pdf_quote_and_geometry(project):
    sid = project.catalog()[0]["id"]
    index = project.index(sid)
    first = index["passages"][0]
    result = locate_quote(index, first["id"], "19 percent longer completion time.")
    assert result["status"] == "exact_normalized"
    assert result["boxes"][0]["page"] == 1
    assert result["boxes"][0]["y"] < 110
    assert index["pages"][2]["status"] == "no_text_layer"
    second = index["passages"][1]
    assert locate_quote(index, second["id"], "Repeated evidence phrase.")["status"] == "ambiguous"
    assert locate_quote(index, first["id"], "invented positive conclusion")["status"] == "unmatched"
    assert locate_quote(index, "missing", first["text"])["status"] == "invalid_passage"
    assert normalize("한국어 근거\n확인") == "한국어근거확인"


def test_pdf_and_study_deduplication(project):
    old = project.catalog()[0]
    data = (project.source_dir(old["id"]) / "original.pdf").read_bytes()
    assert project.add_pdf(data, "renamed.pdf") == old["id"]
    assert len(project.catalog()) == 1
    sid = project.add_pdf(pdf_bytes("Different report of the same underlying study."), "version.pdf")
    project.screen(sid, "include", "Second report", study_id=old["study_id"])
    run = w.prepare(project)
    text = report(project, run)
    assert "문헌 2건 · 연구 1건" in text


def test_fabricated_quote_cannot_be_accepted(project):
    run = w.prepare(project)
    payload = response(project, run)
    payload["rows"][0]["quotes"][0]["quote"] = "This quotation was never in the paper."
    payload["rows"][0]["review"] = {"status": "accept"}  # model cannot set review state
    rows = w.import_extraction(project, run, payload)
    assert rows[0]["match_status"] == "needs_check"
    assert rows[0]["review"]["status"] == "pending"
    with pytest.raises(ValueError, match="원문 위치"):
        w.review(project, run, rows[0]["id"], "accept", "test", "Tester")
    assert "유효한 종합이 아직 없습니다" in report(project, run)
    assert "채택 근거 0/4" in report(project, run)


def test_missing_rows_and_foreign_requests_are_rejected(project):
    run = w.prepare(project)
    payload = response(project, run)
    incomplete = copy.deepcopy(payload)
    incomplete["rows"].pop()
    with pytest.raises(ValueError):
        w.import_extraction(project, run, incomplete)
    foreign = copy.deepcopy(payload)
    foreign["request_id"] = "other-run"
    with pytest.raises(ValueError):
        w.import_extraction(project, run, foreign)
    payload["rows"][0]["value"] = None
    payload["rows"][0]["quotes"] = []
    assert w.import_extraction(project, run, payload)[0]["match_status"] == "not_found"


def test_review_revision_invalidates_synthesis(project):
    run = extracted(project)
    row = w.evidence(project, run)[0]
    w.review(project, run, row["id"], "accept", "Read source context", "Tester")
    request = w.prepare_synthesis(project, run)
    payload = {"request_id": request["request_id"], "claims": [{"text": "Bounded conclusion",
               "kind": "finding", "evidence_ids": [row["id"]]}], "gaps": ["Only one study"]}
    w.import_synthesis(project, run, payload)
    assert w.current_synthesis(project, run)
    w.review(project, run, row["id"], "hold", "Reconsider interpretation", "Tester")
    assert w.current_synthesis(project, run) is None
    with pytest.raises(ValueError, match="변경"):
        w.import_synthesis(project, run, payload)
    assert len(read_json(project.run_dir(run) / "reviews.json")) == 2


def test_synthesis_rejects_unreviewed_evidence(project):
    run = extracted(project)
    rows = w.evidence(project, run)
    w.review(project, run, rows[0]["id"], "edit", "Narrowed population", "Tester", "Narrow result")
    request = w.prepare_synthesis(project, run)
    with pytest.raises(ValueError, match="채택한 근거"):
        w.import_synthesis(project, run, {"request_id": request["request_id"], "claims": [
            {"text": "Unsafe conclusion", "kind": "finding", "evidence_ids": [rows[1]["id"]]}]})


def test_rerun_preserves_baseline_and_reextracts_changed_fields(project):
    first = extracted(project)
    baseline = (project.run_dir(first) / "evidence.json").read_bytes()
    config = project.config()
    config["fields"].append({"id": "measurement", "name": "측정", "instruction": "Extract measurement unit"})
    project.save_config(config["plan"], config["fields"], config["synthesis_rules"])
    second = w.prepare(project)
    assert w.evidence(project, second) == []
    with pytest.raises(ValueError):
        w.import_extraction(project, second, response(project, first))
    w.import_extraction(project, second, response(project, second))
    assert (project.run_dir(first) / "evidence.json").read_bytes() == baseline
    changes = compare(project, first, second)
    assert any(d["field_id"] == "measurement" for d in changes["differences"])
    config["plan"]["inclusion"] = "Changed eligibility"
    project.save_config(config["plan"], config["fields"], config["synthesis_rules"])
    with pytest.raises(ValueError, match="다시 선별"):
        w.prepare(project)


def test_source_tampering_blocks_review_and_export(project):
    run = extracted(project)
    source = project.catalog()[0]
    (project.source_dir(source["id"]) / "original.pdf").write_bytes(pdf_bytes("Tampered"))
    with pytest.raises(ValueError, match="변경"):
        export_zip(project, run)
    before = project.runs()
    with pytest.raises(ValueError, match="변경"):
        w.prepare(project)
    assert project.runs() == before


def test_portable_export_preserves_evidence_and_locators(project):
    run = extracted(project)
    row = w.evidence(project, run)[0]
    w.review(project, run, row["id"], "accept", "Context checked", "Tester")
    data = export_zip(project, run, include_pdfs=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        exported = json.loads(archive.read("research.json"))
        assert exported["evidence"][0]["id"] == row["id"]
        assert exported["evidence"][0]["locators"][0]["boxes"]
        assert exported["evidence"][0]["review"]["reviewer"] == "Tester"
        assert "sources/" + row["source_id"] + ".pdf" in archive.namelist()
        assert not any("key" in name for name in archive.namelist())


def test_restart_and_repeated_import(project):
    run = extracted(project)
    restarted = Project(project.root)
    assert len(w.evidence(restarted, run)) == 4
    with pytest.raises(ValueError, match="이미 가져온"):
        w.import_extraction(restarted, run, response(restarted, run))


def test_explicit_page_scope_rejects_out_of_scope_quote(project):
    config = project.config()
    config["plan"]["max_pages_per_document"] = 1
    project.save_config(config["plan"], config["fields"], config["synthesis_rules"])
    run = w.prepare(project)
    payload = response(project, run)
    sid = project.catalog()[0]["id"]
    payload["rows"][0]["quotes"] = [{"passage_id": project.index(sid)["passages"][1]["id"],
                                    "quote": "Repeated evidence phrase."}]
    with pytest.raises(ValueError, match="조사 범위"):
        w.import_extraction(project, run, payload)


def test_rotated_and_cropped_pages_are_not_false_verified(tmp_path):
    import pdfplumber

    from deep_research.documents import index_pdf
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.setPageRotation(90)
    pdf.drawString(50, 100, "Rotated source evidence remains unverified.")
    pdf.save()
    path = tmp_path / "rotation.pdf"
    path.write_bytes(buf.getvalue())
    index = index_pdf(path, "rotation")
    assert index["pages"][0]["rotation"] == 90
    passage = index["passages"][0]
    assert locate_quote(index, passage["id"], passage["text"])["status"] == "unsupported_page_geometry"
    with pdfplumber.open(path) as document:
        assert document.pages[0].rotation == 90


def test_line_end_hyphen_is_joined_only_as_fallback(tmp_path):
    from deep_research.documents import index_pdf
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 750, "Developers using AI tools showed lower produc-")
    pdf.drawString(50, 735, "tivity in the field trial with well- known tasks.")
    pdf.save()
    path = tmp_path / "hyphen.pdf"
    path.write_bytes(buf.getvalue())
    index = index_pdf(path, "hyphen")
    pid = index["passages"][0]["id"]
    joined = locate_quote(index, pid, "showed lower productivity in the field")
    assert joined["status"] == "exact_normalized" and joined["dehyphenated"]
    assert len(joined["boxes"]) == 2  # one box per printed line
    printed = locate_quote(index, pid, "showed lower produc- tivity in the field")
    assert printed["status"] == "exact_normalized" and not printed["dehyphenated"]
    # A hyphen inside a line is not a line break and is never joined.
    assert locate_quote(index, pid, "trial with wellknown tasks")["status"] == "unmatched"


def test_evidence_ids_are_scoped_to_their_run(project):
    first, second = extracted(project), extracted(project)
    ids = lambda run: {(e["source_id"], e["field_id"]): e["id"] for e in w.evidence(project, run)}  # noqa: E731
    assert ids(first).keys() == ids(second).keys()
    assert not set(ids(first).values()) & set(ids(second).values())
    assert compare(project, first, second)["differences"] == []


def test_task_file_matches_skill_draft_location(project):
    run = w.prepare(project)
    task = (project.run_dir(run) / "TASK.md").read_text(encoding="utf-8")
    assert "drafts/" in task and "responses/는 코어가 관리" in task


def test_text_files_are_read_and_written_as_utf8():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    for path in [root / "app.py", *(root / "deep_research").glob("*.py"), *(root / "ui").glob("*.py")]:
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"\.(read|write)_text\((?![^)]*encoding)", source), path.name


def test_curly_quotes_and_dashes_fold_to_ascii(tmp_path):
    from deep_research.documents import index_pdf
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(50, 750, "AI’s impact in the February–June 2025 “field” trial — measured.")
    pdf.save()
    path = tmp_path / "typography.pdf"
    path.write_bytes(buf.getvalue())
    index = index_pdf(path, "typography")
    pid = index["passages"][0]["id"]
    assert normalize("’“”–—") == "'\"\"--"
    printed = locate_quote(index, pid, "AI’s impact in the February–June 2025 “field” trial")
    ascii_quote = locate_quote(index, pid, "AI's impact in the February-June 2025 \"field\" trial - measured")
    assert printed["status"] == ascii_quote["status"] == "exact_normalized"
    assert normalize("한국어 ‘따옴표’") == "한국어'따옴표'"


def test_blank_field_id_gets_korean_message():
    with pytest.raises(ValueError, match="id"):
        Project.validate_config({"question": "q", "max_documents": 3},
                                [{"id": None, "name": "x", "instruction": "y"}])


def test_locate_anywhere_unique_ambiguous_unmatched(project):
    from deep_research.documents import locate_anywhere
    sid = project.catalog()[0]["id"]
    index = project.index(sid)
    hit = locate_anywhere(index, "19 percent longer completion time.")
    assert hit["status"] == "exact_normalized" and hit["page"] == 1 and hit["boxes"]
    twice = locate_anywhere(index, "Repeated evidence phrase.")
    assert twice["status"] == "multiple" and len(twice["occurrences"]) == 2 and twice["page"] == 2
    assert locate_anywhere(index, "invented positive conclusion")["status"] == "unmatched"
    assert locate_anywhere(index, "short")["status"] == "too_short"


def test_screen_quotes_are_located_and_kept_in_history(project):
    sid = project.catalog()[0]["id"]
    project.screen(sid, "include", "Measured outcome", quotes=[
        {"text": "19 percent longer completion time.", "criterion": "inclusion"},
        "not printed anywhere in this pdf"])
    source = project.source(sid)
    statuses = [q["status"] for q in source["screen_quotes"]]
    assert statuses == ["exact_normalized", "unmatched"]
    assert source["screen_quotes"][0]["page"] == 1 and source["screen_quotes"][0]["criterion"] == "inclusion"
    assert source["history"][-1]["quotes"][1]["status"] == "unmatched"
    with pytest.raises(ValueError):
        project.screen(sid, "include", "x", quotes=[{"text": "19 percent", "criterion": "maybe"}])
    with pytest.raises(ValueError):
        project.screen(sid, "include", "x", quotes=["   "])


def test_parse_and_format_screen_quotes():
    from deep_research.project import format_screen_quotes, parse_screen_quotes
    parsed = parse_screen_quotes("포함: first sentence.\n\n제외: second one\nplain third\ninclusion: fourth")
    assert [q["criterion"] for q in parsed] == ["inclusion", "exclusion", "", "inclusion"]
    assert parsed[0]["text"] == "first sentence." and parsed[2]["text"] == "plain third"
    stored = [{"quote": "a b", "criterion": "inclusion"}, {"quote": "c", "criterion": ""}]
    assert format_screen_quotes(stored) == "포함: a b\nc"
    assert parse_screen_quotes(format_screen_quotes(stored)) == [{"text": "a b", "criterion": "inclusion"}, {"text": "c", "criterion": ""}]


def test_report_lists_screening_quotes(project):
    sid = project.catalog()[0]["id"]
    project.screen(sid, "include", "Measured outcome", quotes=["19 percent longer completion time."])
    run = extracted(project)
    text = report(project, run)
    assert "## 선별 판단과 근거 구절" in text
    assert "[기준 미표시 · PDF 1쪽 · 글자 그대로 일치] 19 percent longer completion time." in text


def test_example_screening_keeps_human_decisions(tmp_path):
    from deep_research.examples import SCREENING, apply_example_screening
    from deep_research.project import write_json
    p = Project(tmp_path / "ex").initialize()
    sid = p.add_pdf(pdf_bytes(), "metr.pdf", "Fake METR")
    sha = p.source(sid)["sha256"]
    write_json(p.root / "example-manifest.json", [{"key": "metr-2025-v2", "sha256": sha}])
    # Untouched paper gets the example screening (quotes will not match this fake PDF, and that is recorded).
    apply_example_screening(p)
    assert p.source(sid)["decision"] == "include" and p.source(sid)["reason"] == SCREENING["metr-2025-v2"]["reason"]
    # A person's own decision and quotes survive a second load.
    p.screen(sid, "exclude", "My own reason", quotes=["19 percent longer completion time."])
    apply_example_screening(p)
    assert p.source(sid)["decision"] == "exclude" and p.source(sid)["reason"] == "My own reason"
    assert p.source(sid)["screen_quotes"][0]["quote"] == "19 percent longer completion time."
    # Explicit reset is still possible.
    apply_example_screening(p, keep_human_decisions=False)
    assert p.source(sid)["decision"] == "include"


def test_reference_parsers_and_citation(project):
    from deep_research.exports import bibliography, citation
    from deep_research.providers import parse_bibtex, parse_ris
    ris = "TY  - JOUR\nTI  - A test paper\nAU  - Kim, A\nAU  - Lee, B\nPY  - 2024\nJO  - Journal X\nDO  - 10.1000/xyz\nER  - \n"
    assert parse_ris(ris)[0]["doi"] == "10.1000/xyz" and parse_ris(ris)[0]["authors"] == ["Kim, A", "Lee, B"]
    bib = "@article{k, title={Another {Test}}, author={Kim, A and Lee, B}, year={2023}, journal={J}, doi={10.1/ABC}}"
    item = parse_bibtex(bib)[0]
    assert item["title"] == "Another Test" and item["doi"] == "10.1/abc" and item["year"] == 2023
    sid = project.catalog()[0]["id"]
    project.set_bibliography(sid, ["Kim, A", "Lee, B", "Park, C"], 2024, "Journal X")
    source = project.source(sid)
    line = citation(source)
    assert line.startswith("Kim, A 외, 2024. Test study.") and "https://doi.org/10.1234/test" in line and "Journal X" in line
    run = extracted(project)
    row = w.evidence(project, run)[0]
    assert "PDF 1쪽" in citation(source, row) and "원문:" in citation(source, row)
    assert bibliography(project, run).startswith("1. Kim, A 외, 2024. Test study.")
    assert "## 참고문헌" in report(project, run)


def test_collection_keeps_metadata_only_candidates(project):
    from deep_research.providers import collect
    record = collect(project, {"title": "No PDF here", "authors": ["Z"], "year": 2020, "venue": "", "doi": "10.9/none",
                               "url": "", "pdf_url": "", "oa": False, "provider": "test"})
    assert record["status"] == "pdf_missing" and record["source_id"] is None
    assert project.collection()[0]["doi"] == "10.9/none"
    # Same DOI again replaces the earlier row instead of duplicating it.
    collect(project, {"title": "No PDF here v2", "authors": [], "year": 2021, "venue": "", "doi": "10.9/none", "url": "", "pdf_url": "", "oa": False, "provider": "test"})
    assert len(project.collection()) == 1 and project.collection()[0]["title"] == "No PDF here v2"
