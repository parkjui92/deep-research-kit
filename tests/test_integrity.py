"""Retraction/correction checks, human comparability marks and the candidate text status."""
import httpx
import pytest

from deep_research import integrity, notebook
from deep_research import workflow as w
from deep_research.exports import export_zip, report
from ui.research import comparability, highlight, query_terms

RETRACTED = {"message": {"DOI": "10.1/a", "updated-by": [
    {"DOI": "10.1/notice", "type": "retraction", "label": "Retraction", "source": "retraction-watch",
     "updated": {"date-parts": [[2021, 12, 15]]}},
    {"DOI": "10.1/notice", "type": "retraction", "label": "Retraction", "source": "publisher",
     "updated": {"date-parts": [[2021, 12, 15]]}},
    {"DOI": "10.1/fix", "type": "correction", "label": "Correction", "source": "publisher",
     "updated": {"date-parts": [[2020, 3, 1]]}}]}}


def client(payload, status=200, seen=None):
    def handler(request):
        if seen is not None:
            seen.append(str(request.url))
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_crossref_notices_are_deduplicated_and_the_worst_status_wins():
    seen = []
    record = integrity.check_doi("https://doi.org/10.1/A", client(RETRACTED, seen=seen))
    assert seen == ["https://api.crossref.org/works/10.1/a"]  # only the DOI leaves the machine
    assert record["status"] == "retracted"
    assert [(n["type"], n["date"]) for n in record["notices"]] == [("retraction", "2021-12-15"), ("correction", "2020-03-01")]
    assert integrity.label(record) == "철회됨 (2021-12-15)"
    assert integrity.notice_links(record) == ["https://doi.org/10.1/notice", "https://doi.org/10.1/fix"]


def test_no_notice_is_not_called_safe_and_failures_are_not_clear():
    clear = integrity.check_doi("10.1/b", client({"message": {"DOI": "10.1/b"}}))
    assert clear["status"] == "clear" and "타당성을 뜻하지는 않습니다" in integrity.explain(clear)
    assert integrity.check_doi("10.1/c", client({}, status=404))["status"] == "unknown"  # neither index has it
    assert integrity.check_doi("10.1/d", client({}, status=503))["status"] == "unknown"
    assert integrity.check_doi("")["status"] == "no_doi"
    assert integrity.label(None) == "확인 안 함"


def test_openalex_flag_from_search_stays_until_crossref_is_checked():
    flag = integrity.from_search({"doi": "10.1/x", "retracted": True})
    assert flag["status"] == "retracted"
    assert integrity.from_search({"doi": "10.1/x", "retracted": False}) is None
    record = integrity.check_doi("10.1/x", client({"message": {}}), openalex_retracted=True)
    assert record["status"] == "retracted" and "OpenAlex" in record["via"]


def test_text_status_keeps_abstract_only_apart_from_full_text():
    catalog = {"s1": {"id": "s1", "page_count": 3, "text_pages": 3}, "s2": {"id": "s2", "page_count": 3, "text_pages": 0}}
    assert notebook.text_status({"source_id": "s1"}, catalog) == "full"
    assert notebook.text_status({"source_id": "s2"}, catalog) == "no_text"
    assert notebook.text_status({"abstract": "An abstract."}, catalog) == "abstract"
    assert notebook.text_status({}, catalog) == "none"


def test_highlight_escapes_text_and_marks_only_search_words():
    terms = query_terms(["generative AI AND productivity", "생성형 AI 생산성"])
    assert "AND" not in terms and "AI" not in terms and "생산성" in terms
    html = highlight("<b>Generative</b> tools raise productivity", terms)
    assert "&lt;b&gt;" in html and html.count("<mark") == 2


def _project(tmp_path):
    from test_ui import _project_with_value
    return _project_with_value(tmp_path, "19 percent longer")


def test_comparison_mark_is_human_only_and_reaches_the_record(tmp_path):
    p, run = _project(tmp_path)
    rows = w.evidence(p, run)
    with pytest.raises(ValueError):
        w.review(p, run, rows[0]["id"], "accept", "8쪽 대조", "Kim", comparison="maybe")
    w.review(p, run, rows[0]["id"], "accept", "8쪽 대조", "Kim", comparison="conditions")
    w.review(p, run, rows[1]["id"], "hold", "더 확인", "Kim", comparison="same")  # ignored when not adopted
    rows = w.evidence(p, run)
    assert rows[0]["review"]["comparison"] == "conditions" and rows[1]["review"]["comparison"] is None
    fields = w.manifest(p, run)["config"]["fields"]
    table = {r["항목"]: r for r in comparability(rows, fields)}
    first = table[next(f["name"] for f in fields if f["id"] == rows[0]["field_id"])]
    assert first["채택"] == 1 and first["조건이 다름"] == 1
    assert "다른 문헌과 비교(검토자 표시): 조건이 다름" in report(p, run)


def test_report_warns_about_retracted_adopted_sources(tmp_path):
    import io
    import zipfile
    p, run = _project(tmp_path)
    row = w.evidence(p, run)[0]
    assert "철회·정정 여부를 확인하지 않았습니다" not in report(p, run)  # nothing adopted yet
    w.review(p, run, row["id"], "accept", "대조", "Kim")
    assert "1편은 철회·정정 여부를 확인하지 않았거나 확인하지 못했습니다" in report(p, run)
    p.set_integrity(row["source_id"], integrity.check_doi("10.1/a", client(RETRACTED)))
    text = report(p, run)
    assert "## 철회·정정 확인" in text and "**[철회됨 (2021-12-15)]**" in text
    csv_text = zipfile.ZipFile(io.BytesIO(export_zip(p, run))).read("evidence.csv").decode("utf-8-sig")
    assert "철회됨 (2021-12-15)" in csv_text


def test_workspace_shows_progress_strip_and_report_view(tmp_path):
    from streamlit.testing.v1 import AppTest
    from test_ui import _workbench_script
    p, run = _project(tmp_path)
    row = w.evidence(p, run)[0]
    w.review(p, run, row["id"], "accept", "대조", "Kim", comparison="same")
    p.set_integrity(row["source_id"], integrity.check_doi("10.1/a", client(RETRACTED)))
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    labels = [b.label for b in app.button]
    assert any(label.startswith("추출 1편") for label in labels)
    assert any(label.startswith("채택 1건") for label in labels)
    assert "⚠ 철회·정정 1편" in labels
    app.button(key="wb_progress_채택").click().run(timeout=60)
    assert not app.exception
    text = " ".join(m.value for m in app.markdown)
    assert "채택 근거의 문헌 가운데 1편에 철회·정정·우려 고지가 있습니다." in text
    tables = [t.value for t in app.dataframe]
    assert any("같은 지표·단위" in getattr(t, "columns", []) for t in tables)


def test_doi_outside_crossref_falls_back_to_openalex_flag():
    def handler(request):
        if "crossref" in request.url.host:
            return httpx.Response(404, json={})
        assert request.url.path == "/works/doi:10.48550/arxiv.1"
        return httpx.Response(200, json={"is_retracted": False})
    record = integrity.check_doi("10.48550/arXiv.1", httpx.Client(transport=httpx.MockTransport(handler)))
    assert record["status"] == "clear" and "정정 고지는 확인 못 함" in record["via"]


def test_openalex_rate_limit_is_named_and_key_is_sent(monkeypatch, tmp_path):
    from deep_research import providers
    from deep_research.project import Project
    p = Project(tmp_path / "p").initialize()
    seen = []
    def get(url, params=None, **kwargs):
        seen.append(params)
        return httpx.Response(429, json={}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    with pytest.raises(ValueError, match="OPENALEX_API_KEY"):
        providers.search_literature(p, "ai productivity")
    assert "api_key" not in seen[0]
    monkeypatch.setenv("OPENALEX_API_KEY", "k-test")
    with pytest.raises(ValueError, match="429"):
        providers.search_literature(p, "ai productivity")
    assert seen[-1]["api_key"] == "k-test"
    assert "k-test" not in (tmp_path / "p" / "search-log.json").read_text(encoding="utf-8")
