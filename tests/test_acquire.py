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
    """A fake web: {url: (status, body, headers)}; anything else is 404. Records each request."""
    seen = []

    def handler(request):
        url = str(request.url).split("?")[0]
        seen.append((url, request.headers.get("user-agent", ""), str(request.url)))
        status, body, headers = routes.get(url, (404, b"", {}))
        if isinstance(body, httpx.SyncByteStream):
            return httpx.Response(status, stream=body, headers=headers)
        return httpx.Response(status, content=body if isinstance(body, bytes) else body.encode(), headers=headers)
    c = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, headers=acquire.UA)
    c.seen = seen
    return c


def unpaywall(is_oa, pdf=None, page=None):
    best = {"url_for_pdf": pdf, "url_for_landing_page": page} if (pdf or page) else None
    return (200, json.dumps({"is_oa": is_oa, "best_oa_location": best, "oa_locations": []}), {})


def test_open_copies_are_tried_in_order_and_the_contact_goes_to_unpaywall_only():
    web = client({
        "https://oa-index.test/a.pdf": (403, b"blocked", {}),
        "https://repo.test/a": (200, b"<html>not a pdf</html>", {}),
        "https://api.unpaywall.org/v2/10.1/abc": unpaywall(True, pdf="https://oa.test/a.pdf"),
        "https://oa.test/a.pdf": (200, PDF, {}),
    })
    data, attempts = acquire.find_pdf({"provider": "OpenAlex", "pdf_url": "https://oa-index.test/a.pdf",
                                       "pdf_urls": ["https://repo.test/a"], "doi": "10.1/abc",
                                       "url": "https://doi.org/10.1/abc"}, web)
    assert data == PDF
    assert [(a["route"], a["result"]) for a in attempts] == [
        ("검색 결과의 PDF 주소", "접근 거부(403)"), ("OpenAlex의 다른 원문 위치", "PDF 아님"), ("Unpaywall", "받음")]
    assert "https://doi.org/10.1/abc" not in [u for u, _, _ in web.seen]  # stops at the first real PDF
    assert all(acquire.CONTACT not in agent for _, agent, _ in web.seen)
    assert [full for url, _, full in web.seen if "unpaywall" in url][0].endswith("email=" + acquire.CONTACT.replace("@", "%40"))


def test_open_landing_page_pdf_address_is_followed():
    page = '<html><head><meta content="/files/a.pdf" name="citation_pdf_url"></head></html>'
    web = client({
        "https://api.unpaywall.org/v2/10.1/abc": unpaywall(True, page="https://repo.test/record/1"),
        "https://repo.test/record/1": (302, b"", {"location": "https://repo.test/record/1/"}),
        "https://repo.test/record/1/": (200, page, {}),
        "https://repo.test/files/a.pdf": (200, PDF, {}),
    })
    data, attempts = acquire.find_pdf({"doi": "10.1/abc"}, web)
    assert data == PDF
    assert attempts[-2:] == [{"route": "논문 페이지", "url": "https://repo.test/record/1", "result": "PDF 주소 표시 있음"},
                             {"route": "논문 페이지의 citation_pdf_url", "url": "https://repo.test/files/a.pdf", "result": "받음"}]


def test_publisher_pages_stay_closed_unless_unpaywall_says_open():
    routes = {"https://api.unpaywall.org/v2/10.1/closed": unpaywall(False),
              "https://doi.org/10.1/closed": (200, b'<meta name="citation_pdf_url" content="https://pub.test/x.pdf">', {}),
              "https://pub.test/x.pdf": (200, PDF, {})}
    web = client(routes)
    hit = {"provider": "Crossref", "doi": "10.1/closed", "url": "http://dx.doi.org/10.1/closed", "pdf_url": "https://pub.test/x.pdf"}
    data, attempts = acquire.find_pdf(hit, web)
    assert data is None and [u for u, _, _ in web.seen] == ["https://api.unpaywall.org/v2/10.1/closed"]
    assert attempts[-1]["result"] == "오픈액세스가 아니라 열지 않음"
    # A captive portal answers Unpaywall with an HTML page: no crash, and still no publisher page.
    portal = client({"https://api.unpaywall.org/v2/10.1/closed": (200, b"<html>Wi-Fi login</html>", {})})
    data, attempts = acquire.find_pdf(hit, portal)
    assert data is None and [a["result"] for a in attempts] == ["응답 형식 오류", "오픈액세스 여부를 몰라 열지 않음"]
    # Open per Unpaywall: the publisher's own page may be read, once (dx.doi.org = doi.org).
    routes["https://api.unpaywall.org/v2/10.1/closed"] = unpaywall(True)
    routes["https://pub.test/x.pdf"] = (403, b"", {})
    web = client(routes)
    acquire.find_pdf(hit, web)
    assert [u for u, _, _ in web.seen].count("https://doi.org/10.1/closed") == 1


def test_arxiv_numbers_old_and_new():
    web = client({"https://arxiv.org/pdf/2507.09089v2": (200, PDF, {}), "https://arxiv.org/pdf/hep-th/9901001": (200, PDF, {})})
    assert acquire.find_pdf({"doi": "10.48550/arxiv.2507.09089v2"}, web)[0] == PDF
    assert acquire.find_pdf({"url": "https://arxiv.org/abs/hep-th/9901001"}, web)[0] == PDF


def test_size_limit_and_unsafe_addresses(monkeypatch):
    blocked = client({"https://pnas.test/doi/1": (403, b"", {})})
    data, attempts = acquire.find_pdf({"url": "https://pnas.test/doi/1", "pdf_url": "javascript:alert(1)"}, blocked)
    assert data is None and attempts == [{"route": "논문 페이지", "url": "https://pnas.test/doi/1", "result": "접근 거부(403)"}]
    monkeypatch.setattr(acquire, "MAX_BYTES", 10)
    big = client({"https://big.test/a.pdf": (200, PDF + b"x" * 20, {})})
    assert acquire.find_pdf({"pdf_url": "https://big.test/a.pdf"}, big) == (None, [
        {"route": "검색 결과의 PDF 주소", "url": "https://big.test/a.pdf", "result": "100 MB 초과"}])


class Trickle(httpx.SyncByteStream):
    def __iter__(self):
        for _ in range(30):
            time.sleep(0.1)
            yield b"x"


def test_a_slow_server_cannot_hold_a_hit_past_its_budget(monkeypatch):
    monkeypatch.setattr(acquire, "BUDGET", 0.5)
    web = client({"https://slow.test/a.pdf": (200, Trickle(), {}), "https://api.unpaywall.org/v2/10.1/s": unpaywall(True)})
    start = time.monotonic()
    data, attempts = acquire.find_pdf({"pdf_url": "https://slow.test/a.pdf", "doi": "10.1/s"}, web)
    assert data is None and time.monotonic() - start < 1.5
    assert attempts[0]["result"] == "시간 한도" and attempts[-1]["route"] == "시간 한도"
    assert not any("unpaywall" in u for u, _, _ in web.seen)  # nothing is sent after the budget


def test_citation_pdf_url_parsing():
    page = ("<META NAME='citation_pdf_url' CONTENT='https://x.test/a.pdf?download=1&amp;v=2'>"
            '<link rel="alternate" type="application/pdf" href="b.pdf">'
            '<meta name="citation_pdf_url" content="javascript:void(0)">')
    assert acquire.citation_pdf_urls(page, "https://x.test/article/") == [
        "https://x.test/a.pdf?download=1&v=2", "https://x.test/article/b.pdf"]


def waiting_project(tmp_path, *hits):
    p = Project(tmp_path / "projects" / "research").initialize()
    for title, doi in hits:
        p.remember_candidate({"title": title, "doi": doi, "url": "https://doi.org/" + doi if doi else "",
                              "authors": ["Kim"], "year": 2025, "venue": "Journal", "status": "pdf_missing", "source_id": None})
    return p


QJE = ("The Returns to Early Childhood Education in Developing Countries", "10.1093/qje/qjae044")
REVIEW = ("A Review of Program Evaluations in Education", "10.5555/my.review.2026")


def test_a_paper_is_tied_by_its_own_doi_not_by_the_ones_it_cites(tmp_path):
    p = waiting_project(tmp_path, QJE)
    draft = "My Draft on School Programs\nhttps://doi.org/10.5555/my.review.2026\nAs shown in [1] doi:10.1093/qje/qjae044, ..."
    assert acquire.match_waiting(p, draft) == (None, "")
    own = "Journal header\nhttps://doi.org/10.1093/qje/qjae044\nThe Returns to Early Childhood Education ..."
    assert acquire.match_waiting(p, own)[1] == "DOI"


def test_title_rules(tmp_path):
    p = waiting_project(tmp_path, ("Machine Learning", ""), ("The Ideation Execution Gap in Research", ""))
    assert acquire.match_waiting(p, "We apply machine learning to many problems.") == (None, "")
    assert acquire.match_waiting(p, "The Ideation-Execution Gap\nin Research\nAuthors ...")[1] == "제목"
    assert acquire.match_waiting(p, "Supplementary Information for\nThe Ideation Execution Gap in Research") == (None, "보충자료로 보임")
    q = waiting_project(tmp_path / "q", ("A Shared Title For Two Different Papers", "10.1000/one"),
                        ("A Shared Title For Two Different Papers", "10.1000/two"))
    assert acquire.match_waiting(q, "A Shared Title for Two Different Papers\nby someone") == (None, "후보가 여럿")
    r = waiting_project(tmp_path / "r", REVIEW)
    assert acquire.match_waiting(r, "Front matter 10.1000/xyz.1\nA Review of Program Evaluations in Education\nhttps://doi.org/10.5555/my.review.2026")[1] == "제목·DOI"


def test_arxiv_number_on_the_page(tmp_path):
    p = waiting_project(tmp_path, ("Measuring the Impact of Early-2025 AI", "10.48550/arxiv.2507.09089"))
    assert acquire.match_waiting(p, "arXiv:2507.09089v2 [cs.AI] 25 Jul 2025\nMeasuring the impact")[1] == "arXiv 번호"


def paper(title, doi=""):
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf)
    pdf.drawString(60, 780, "Journal of Tests")
    if doi:
        pdf.drawString(60, 765, f"https://doi.org/{doi}.")
    pdf.drawString(60, 740, title)
    pdf.drawString(60, 700, "Abstract. A study of something measurable.")
    pdf.showPage()
    pdf.save()
    return buf.getvalue()


def test_uploaded_pdf_is_tied_and_fills_what_the_upload_lacked(tmp_path):
    p = waiting_project(tmp_path, ("Measuring Developer Productivity with AI Tools", "10.1234/abc.5678"), REVIEW)
    source_id, hit, how = acquire.register(p, paper("Measuring Developer Productivity", "10.1234/ABC.5678"), "download (3).pdf")
    assert hit["doi"] == "10.1234/abc.5678" and how == "DOI"
    source = p.source(source_id)
    assert source["title"] == "Measuring Developer Productivity with AI Tools"  # was the file name
    assert source["doi"] == "10.1234/abc.5678" and source["study_id"] == "10.1234/abc.5678" and source["bib"]["year"] == 2025
    record = next(c for c in p.collection() if c["doi"] == "10.1234/abc.5678")
    assert record["status"] == "added" and record["source_id"] == source_id and record["linked_by"] == "DOI"
    assert [c["title"] for c in acquire.waiting(p)] == [REVIEW[0]]


def test_fill_metadata_keeps_what_a_person_typed(tmp_path):
    p = Project(tmp_path / "research").initialize()
    sid = p.add_pdf(paper("x"), "file.pdf")
    p.screen(sid, "pending", "제목만 고침", title="내가 고친 제목")
    p.fill_metadata(sid, "Index title", "https://doi.org/10.1/A", "https://x.test")
    source = p.source(sid)
    assert source["title"] == "내가 고친 제목" and source["doi"] == "10.1/a" and source["url"] == "https://x.test"


def test_downloads_are_files_that_were_not_there_when_watching_began(tmp_path):
    before = tmp_path / "before.pdf"
    before.write_bytes(PDF)
    known = acquire.pdfs_in(tmp_path)
    (tmp_path / "half.pdf.crdownload").write_bytes(PDF)
    old_date = tmp_path / "server-dated.pdf"  # a browser kept the server's 2019 date
    old_date.write_bytes(PDF)
    os.utime(old_date, (1546300800, 1546300800))
    fresh = tmp_path / "fresh.pdf"  # still being written in place
    fresh.write_bytes(PDF)
    assert acquire.new_downloads(tmp_path, known) == [old_date]
    assert acquire.new_downloads(tmp_path, known | {str(old_date)}, settle=0) == [fresh]
    with pytest.raises(OSError):
        acquire.new_downloads(tmp_path / "missing", set())


def test_retry_waiting_registers_and_keeps_the_trail(tmp_path):
    p = waiting_project(tmp_path, ("Open Paper Found On Second Try", "10.1000/open"), ("Closed Paper Nobody Shares", "10.1000/closed"))
    web = client({"https://api.unpaywall.org/v2/10.1000/open": unpaywall(True, pdf="https://oa.test/o.pdf"),
                  "https://oa.test/o.pdf": (200, paper("Open Paper Found On Second Try"), {}),
                  "https://api.unpaywall.org/v2/10.1000/closed": unpaywall(False)})
    got = acquire.retry_waiting(p, web)
    assert [c["title"] for c in got] == ["Open Paper Found On Second Try"]
    closed = acquire.waiting(p)[0]
    assert closed["title"] == "Closed Paper Nobody Shares" and closed["attempts"][-1]["result"] == "오픈액세스가 아니라 열지 않음"
    assert next(c for c in p.collection() if c["doi"] == "10.1000/open")["status"] == "added"


def test_collect_records_attempts(tmp_path):
    from deep_research.providers import _candidate, collect
    p = Project(tmp_path / "projects" / "research").initialize()
    web = client({})
    record = collect(p, _candidate(provider="Crossref", title="Blocked Paper", doi="10.1/x", pdf_url="https://pub.test/a.pdf"), web)
    assert record["status"] == "pdf_missing"
    assert [a["result"] for a in record["attempts"]] == ["HTTP 404", "오픈액세스 여부를 몰라 열지 않음"]
    assert "https://pub.test/a.pdf" not in [u for u, _, _ in web.seen]  # a publisher link is not opened blind
