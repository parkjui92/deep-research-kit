"""Finding open PDFs, and tying a PDF that arrives later to the search hit waiting for it."""
import io
import json
import os
import time

import httpx
import pytest
from reportlab.pdfgen import canvas

from deep_research import acquire
from deep_research.project import Project

PDF = b"%PDF-1.4 tiny"


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    monkeypatch.setattr(acquire, "PAUSE", 0)


def client(routes):
    """A fake web: {url: (status, body, headers)}; anything else is 404."""
    seen = []

    def handler(request):
        url = str(request.url).split("?")[0]
        seen.append(url)
        status, body, headers = routes.get(url, (404, b"", {}))
        return httpx.Response(status, content=body if isinstance(body, bytes) else body.encode(), headers=headers)
    c = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    c.seen = seen
    return c


def test_open_copies_are_tried_in_order_and_every_try_is_recorded():
    web = client({
        "https://publisher.test/a.pdf": (403, b"blocked", {}),
        "https://repo.test/a": (200, b"<html>not a pdf</html>", {}),
        "https://api.unpaywall.org/v2/10.1/abc": (200, json.dumps({"best_oa_location": {"url_for_pdf": "https://oa.test/a.pdf"},
                                                                   "oa_locations": []}), {}),
        "https://oa.test/a.pdf": (200, PDF, {}),
    })
    data, attempts = acquire.find_pdf({"pdf_url": "https://publisher.test/a.pdf", "pdf_urls": ["https://repo.test/a"],
                                       "doi": "10.1/abc", "url": "https://doi.org/10.1/abc"}, web)
    assert data == PDF
    assert [(a["route"], a["result"]) for a in attempts] == [
        ("검색 결과의 PDF 주소", "접근 거부(403)"), ("OpenAlex의 다른 원문 위치", "PDF 아님"), ("Unpaywall", "받음")]
    assert "https://doi.org/10.1/abc" not in web.seen  # stops at the first real PDF


def test_landing_page_pdf_address_is_followed():
    page = ('<html><head><meta content="/files/a.pdf" name="citation_pdf_url">'
            '<meta name="citation_title" content="x"></head></html>')
    web = client({
        "https://doi.org/10.1/abc": (302, b"", {"location": "https://journal.test/article/1"}),
        "https://journal.test/article/1": (200, page, {}),
        "https://journal.test/files/a.pdf": (200, PDF, {}),
        "https://api.unpaywall.org/v2/10.1/abc": (200, json.dumps({"best_oa_location": None, "oa_locations": []}), {}),
    })
    data, attempts = acquire.find_pdf({"doi": "10.1/abc"}, web)
    assert data == PDF
    assert attempts[-2:] == [{"route": "논문 페이지", "url": "https://doi.org/10.1/abc", "result": "PDF 주소 표시 있음"},
                             {"route": "논문 페이지의 citation_pdf_url", "url": "https://journal.test/files/a.pdf", "result": "받음"}]
    assert {"route": "Unpaywall", "url": "10.1/abc", "result": "오픈액세스 사본 없음"} in attempts


def test_arxiv_and_blocked_pages_and_size_limit(monkeypatch):
    web = client({"https://arxiv.org/pdf/2507.09089v2": (200, PDF, {})})
    assert acquire.find_pdf({"doi": "10.48550/arxiv.2507.09089v2"}, web)[0] == PDF
    blocked = client({"https://pnas.test/doi/1": (403, b"", {})})
    data, attempts = acquire.find_pdf({"url": "https://pnas.test/doi/1", "pdf_url": "javascript:alert(1)"}, blocked)
    assert data is None and attempts == [{"route": "논문 페이지", "url": "https://pnas.test/doi/1", "result": "접근 거부(403)"}]
    monkeypatch.setattr(acquire, "MAX_BYTES", 10)
    big = client({"https://big.test/a.pdf": (200, PDF + b"x" * 20, {})})
    assert acquire.find_pdf({"pdf_url": "https://big.test/a.pdf"}, big) == (None, [
        {"route": "검색 결과의 PDF 주소", "url": "https://big.test/a.pdf", "result": "100 MB 초과"}])


def test_citation_pdf_url_parsing():
    page = ("<META NAME='citation_pdf_url' CONTENT='https://x.test/a.pdf?download=1&amp;v=2'>"
            '<link rel="alternate" type="application/pdf" href="b.pdf">'
            '<meta name="citation_pdf_url" content="javascript:void(0)">')
    assert acquire.citation_pdf_urls(page, "https://x.test/article/") == [
        "https://x.test/a.pdf?download=1&v=2", "https://x.test/article/b.pdf"]


def paper(title, doi=""):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(60, 760, title)
    if doi:
        pdf.drawString(60, 740, f"https://doi.org/{doi}.")
    pdf.drawString(60, 700, "Abstract. A study of something measurable.")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def waiting_project(tmp_path, *hits):
    p = Project(tmp_path / "projects" / "research").initialize()
    for hit in hits:
        p.remember_candidate({"title": hit[0], "doi": hit[1], "url": "https://doi.org/" + hit[1] if hit[1] else "",
                              "authors": ["Kim"], "year": 2025, "venue": "Journal", "status": "pdf_missing", "source_id": None})
    return p


def test_uploaded_pdf_is_tied_to_the_waiting_hit_by_doi(tmp_path):
    p = waiting_project(tmp_path, ("Measuring Developer Productivity with AI Tools", "10.1234/abc.5678"),
                        ("Another Waiting Paper on Something Else", "10.9/zzz"))
    source_id, hit, how = acquire.register(p, paper("Measuring Developer Productivity", "10.1234/ABC.5678"), "download (3).pdf")
    assert hit["doi"] == "10.1234/abc.5678" and how == "DOI"
    source = p.source(source_id)
    assert source["title"] == "Measuring Developer Productivity with AI Tools"  # was the file name
    assert source["doi"] == "10.1234/abc.5678" and source["study_id"] == "10.1234/abc.5678"
    assert source["bib"]["year"] == 2025
    record = next(c for c in p.collection() if c["doi"] == "10.1234/abc.5678")
    assert record["status"] == "added" and record["source_id"] == source_id and record["linked_by"] == "DOI"
    assert [c["title"] for c in acquire.waiting(p)] == ["Another Waiting Paper on Something Else"]


def test_title_match_and_no_guessing(tmp_path):
    p = waiting_project(tmp_path, ("The Ideation Execution Gap in Research", ""), ("Short", ""))
    _, hit, how = acquire.register(p, paper("The Ideation-Execution Gap in Research"), "a.pdf")
    assert hit["title"] == "The Ideation Execution Gap in Research" and how == "제목"
    q = waiting_project(tmp_path / "two", ("Same DOI first", "10.5/x"), ("Same DOI second", "10.5/x"))
    assert acquire.register(q, paper("Something", "10.5/x"), "b.pdf")[1] is None  # two fits: not guessed


def test_fill_metadata_keeps_what_a_person_typed(tmp_path):
    p = Project(tmp_path / "research").initialize()
    sid = p.add_pdf(paper("x"), "file.pdf")
    p.screen(sid, "pending", "제목만 고침", title="내가 고친 제목")
    p.fill_metadata(sid, "Index title", "https://doi.org/10.1/A", "https://x.test")
    source = p.source(sid)
    assert source["title"] == "내가 고친 제목" and source["doi"] == "10.1/a" and source["url"] == "https://x.test"


def test_downloads_folder_picks_only_new_finished_pdfs(tmp_path):
    since = time.time() - 60
    old = tmp_path / "old.pdf"
    old.write_bytes(PDF)
    os.utime(old, (since - 100, since - 100))
    (tmp_path / "half.pdf.crdownload").write_bytes(PDF)
    fresh = tmp_path / "fresh.pdf"
    fresh.write_bytes(PDF)
    done = tmp_path / "done.pdf"
    done.write_bytes(PDF)
    os.utime(done, (time.time() - 10, time.time() - 10))
    assert acquire.new_downloads(tmp_path, since, set()) == [done]           # fresh one is still settling
    assert acquire.new_downloads(tmp_path, since, {str(done)}, settle=0) == [fresh]
    assert acquire.new_downloads(tmp_path / "missing", since, set()) == []


def test_retry_waiting_registers_and_keeps_the_trail(tmp_path):
    p = waiting_project(tmp_path, ("Open Paper Found On Second Try", "10.1/open"), ("Closed Paper Nobody Shares", "10.1/closed"))
    web = client({"https://api.unpaywall.org/v2/10.1/open": (200, json.dumps({"best_oa_location": {"url_for_pdf": "https://oa.test/o.pdf"}}), {}),
                  "https://oa.test/o.pdf": (200, paper("Open Paper Found On Second Try"), {})})
    got = acquire.retry_waiting(p, web)
    assert [c["title"] for c in got] == ["Open Paper Found On Second Try"]
    closed = acquire.waiting(p)[0]
    assert closed["title"] == "Closed Paper Nobody Shares" and closed["attempts"]
    assert next(c for c in p.collection() if c["doi"] == "10.1/open")["status"] == "added"


def test_collect_records_attempts(tmp_path):
    from deep_research.providers import _candidate, collect
    p = Project(tmp_path / "projects" / "research").initialize()
    web = client({"https://x.test/a.pdf": (403, b"", {})})
    record = collect(p, _candidate(provider="Crossref", title="Blocked Paper", pdf_url="https://x.test/a.pdf"), web)
    assert record["status"] == "pdf_missing" and record["attempts"][0]["result"] == "접근 거부(403)"
