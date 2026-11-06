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


def test_key_order_session_then_env_then_file(monkeypatch, tmp_path):
    from deep_research import providers
    assert providers.openalex_key() == ("", None) and providers.openalex_key_params() == {}
    key_file = tmp_path / "openalex.key"
    key_file.write_text("  k-file \n", encoding="utf-8")
    monkeypatch.setattr(providers, "_key_files", lambda: [tmp_path / "missing.key", key_file])
    assert providers.openalex_key() == ("k-file", "file")
    monkeypatch.setenv("OPENALEX_API_KEY", "k-env")
    assert providers.openalex_key() == ("k-env", "env")
    providers.use_session_key(" k-session ")
    assert providers.openalex_key() == ("k-session", "session")
    assert providers.openalex_key_params() == {"api_key": "k-session"}
    providers.use_session_key("")
    assert providers.openalex_key()[1] == "env"


def test_hint_depends_on_whether_a_key_was_used(monkeypatch):
    from deep_research import providers
    assert providers.openalex_hint({"arXiv": "HTTP 503"}) == ""
    assert providers.openalex_hint({"OpenAlex": "한도 초과(HTTP 429)"}) == providers.RATE_LIMIT_HINT
    providers.use_session_key("k")
    assert providers.openalex_hint({"OpenAlex": "한도 초과(HTTP 429)"}) == providers.OWN_KEY_LIMIT_HINT
    assert providers.openalex_hint({"OpenAlex": "HTTP 401"}) == providers.BAD_KEY_HINT


def test_session_key_is_sent_but_never_logged(monkeypatch, tmp_path):
    from deep_research import providers
    from deep_research.project import Project
    p = Project(tmp_path / "p").initialize()
    seen = []
    def get(url, params=None, **kwargs):
        seen.append(params)
        return httpx.Response(200, json={"results": [], "meta": {"count": 0}}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx, "get", get)
    providers.use_session_key("k-secret")
    providers.search_literature(p, "ai productivity")
    assert seen[-1]["api_key"] == "k-secret"
    assert "k-secret" not in (tmp_path / "p" / "search-log.json").read_text(encoding="utf-8")


def test_search_box_offers_key_field_and_keyless_retry(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from test_ui import _button, _workbench_script

    from deep_research import providers
    from deep_research.project import Project
    p = Project(tmp_path / "search").initialize()
    calls = []
    def limited(*a, **kw):
        calls.append("OpenAlex")
        request = httpx.Request("GET", providers.OPENALEX)
        raise httpx.HTTPStatusError("429", request=request, response=httpx.Response(429, request=request))
    def keyless(name):
        def search(*a, **kw):
            calls.append(name)
            return 1, [providers._candidate(provider=name, title=f"{name} hit", doi=f"10.1/{name.lower()}")]
        return search
    monkeypatch.setitem(providers.PROVIDERS, "OpenAlex", limited)
    monkeypatch.setitem(providers.PROVIDERS, "Crossref", keyless("Crossref"))
    monkeypatch.setitem(providers.PROVIDERS, "arXiv", keyless("arXiv"))
    app = AppTest.from_function(_workbench_script, args=(str(p.root),)).run(timeout=60)
    assert not app.exception
    assert any(t.label == "OpenAlex 키" for t in app.text_input)
    app.text_input(key="wb_q").set_value("ai productivity")
    _button(app, "문헌 검색").click().run(timeout=60)
    assert not app.exception and calls == ["OpenAlex"]
    assert any("검색 창의 「OpenAlex 개인 키」" in e.value for e in app.error)
    app.button(key="wb_fallback_go").click().run(timeout=60)
    assert not app.exception and calls[1:] == ["Crossref", "arXiv"]
    assert st_results(app) == 2
    app.text_input(key="wb_openalex_key_input").input("k-mine").run(timeout=60)
    assert not app.exception
    assert any("지금: 이 창에 넣은 키" in e.label for e in app.expander)
    assert "k-mine" not in (p.root / "search-log.json").read_text(encoding="utf-8")


def st_results(app):
    return len(app.session_state["wb_results"])


@pytest.mark.parametrize('legacy', [None, 'OpenAlex 검색 결과', 'Crossref · OpenAlex'])
def test_rechecking_preserves_openalex_warning_and_source_history(tmp_path, legacy):
    p, run = _project(tmp_path)
    sid = w.evidence(p, run)[0]['source_id']
    p.fill_metadata(sid, doi='10.1/a')
    flag = integrity.from_search({'doi': '10.1/a', 'retracted': True})
    if legacy:
        flag = {'doi': '10.1/a', 'via': legacy, 'status': 'retracted', 'notices': [],
                'checked_at': '2020-01-01T00:00:00Z'}
    p.set_integrity(sid, flag)
    with client({'message': {}}) as http:
        for _ in range(3):
            integrity.check_sources(p, client=http)
            record = p.source(sid)['integrity']
            assert record['status'] == 'retracted'
            assert record['providers']['OpenAlex']['status'] == 'retracted'
            assert record['providers']['Crossref']['status'] == 'clear'
    assert len(record['checks']) == (5 if legacy == 'Crossref · OpenAlex' else 4)
    if legacy:
        assert record['providers']['OpenAlex']['checked_at'].startswith('2020-01-01')
    # Reading/migrating and checking must not mutate the caller's original snapshot.
    if legacy:
        assert flag['via'] == legacy
    else:
        assert len(flag['checks']) == 1


def test_failed_recheck_keeps_known_notices_and_reports_failure():
    original = integrity.check_doi('10.1/a', client(RETRACTED))
    failed = integrity.check_doi('10.1/a', client({}, status=503), previous=original)
    assert failed['status'] == 'retracted'
    assert failed['notices'] == original['notices']
    assert failed['check_status'] == 'unknown' and failed['retained_warning']
    assert failed['providers']['Crossref']['last_check']['status'] == 'unknown'
    assert '최근 조회 실패' in integrity.explain(failed)
    assert len(failed['checks']) == 2 and len(original['checks']) == 1
    # A later empty index response does not silently revoke the recorded retraction notice.
    empty = integrity.check_doi('10.1/a', client({'message': {}}), previous=failed)
    assert empty['status'] == 'retracted' and empty['check_status'] == 'clear'
    assert '이전 고지를 유지' in integrity.explain(empty)
    assert integrity.notice_links(empty) == integrity.notice_links(original)


def test_failed_check_is_not_misreported_as_previously_clear():
    clear = integrity.check_doi('10.1/a', client({'message': {}}))
    failed = integrity.check_doi('10.1/a', client({}, status=503), previous=clear)
    assert failed['status'] == 'unknown'
    assert failed['checks'][0]['status'] == 'clear'
    assert failed['checks'][1]['status'] == 'unknown'


def test_legacy_crossref_warning_is_not_misattributed_to_openalex():
    legacy = {'doi': '10.1/a', 'via': 'Crossref', 'status': 'corrected', 'checked_at': '2020-01-01',
              'notices': [{'type': 'correction', 'notice_doi': '10.1/fix', 'label': 'Correction', 'date': '2020-01-01'}]}
    checked = integrity.check_doi('10.1/a', client({'message': {}}), previous=legacy)
    assert checked['status'] == 'corrected'
    assert set(checked['providers']) == {'Crossref'}
    assert checked['providers']['Crossref']['checked_at'] == '2020-01-01'


def test_changed_doi_does_not_inherit_another_papers_warning():
    previous = integrity.from_search({'doi': '10.1/a', 'retracted': True})
    checked = integrity.check_doi('https://doi.org/10.1/B', client({'message': {}}), previous=previous)
    assert checked['status'] == 'clear' and checked['doi'] == '10.1/b'
    assert len(checked['checks']) == 1 and 'OpenAlex' not in checked['providers']


@pytest.mark.parametrize('payload', [{}, {'message': []}])
def test_malformed_crossref_metadata_is_unknown_not_clear(payload):
    assert integrity.check_doi('10.1/a', client(payload))['status'] == 'unknown'


def test_openalex_only_does_not_claim_corrections_were_checked():
    def handler(request):
        return httpx.Response(404, json={}) if 'crossref' in request.url.host else httpx.Response(200, json={'is_retracted': False})
    record = integrity.check_doi('10.1/a', httpx.Client(transport=httpx.MockTransport(handler)))
    assert record['coverage'] == 'retraction_only'
    assert '정정·우려 고지는 확인하지 못했습니다' in integrity.explain(record)
    assert record['providers']['Crossref']['status'] == 'not_found'
    assert record['providers']['OpenAlex']['status'] == 'clear'


def test_missing_openalex_flag_is_unknown_not_false():
    def handler(request):
        return httpx.Response(404, json={}) if 'crossref' in request.url.host else httpx.Response(200, json={})
    record = integrity.check_doi('10.1/a', httpx.Client(transport=httpx.MockTransport(handler)))
    assert record['status'] == 'unknown'


def test_merging_older_candidate_preserves_catalog_check_and_deduplicates_history():
    older = {'doi': '10.1/a', 'status': 'clear', 'via': 'Crossref', 'notices': [], 'checked_at': '2020-01-01'}
    newer = integrity.check_doi('10.1/a', client(RETRACTED), previous=older)
    combined = integrity.merge_records('10.1/a', newer, older, newer)
    assert combined['status'] == 'retracted'
    assert len(combined['checks']) == len(newer['checks']) == 2
    assert combined['providers']['Crossref']['status'] == 'retracted'
    assert integrity.merge_records('10.1/a', None, None) is None


def test_fresh_candidate_warning_is_visible_over_catalog_clear():
    clear = integrity.check_doi('10.1/a', client({'message': {}}))
    candidate = {'doi': '10.1/a', 'source_id': 's1', 'retracted': True}
    record = notebook.candidate_integrity(candidate, {'s1': {'doi': '10.1/a', 'integrity': clear}})
    assert record['status'] == 'retracted'
    assert record['providers']['OpenAlex']['status'] == 'retracted'
    assert record['providers']['Crossref']['status'] == 'clear'


@pytest.mark.parametrize('pdf_available', [True, False])
def test_recollect_does_not_erase_newer_checks(tmp_path, monkeypatch, pdf_available):
    from deep_research import acquire, providers
    p, run = _project(tmp_path)
    sid = w.evidence(p, run)[0]['source_id']
    p.fill_metadata(sid, doi='10.1/a')
    known = integrity.check_doi('10.1/a', client(RETRACTED))
    p.set_integrity(sid, known)
    old = {'doi': '10.1/a', 'status': 'clear', 'via': 'Crossref', 'notices': [], 'checked_at': '2020-01-01'}
    candidate = {'doi': '10.1/a', 'title': 'Paper', 'url': '', 'integrity': old}
    p.remember_candidate({**candidate, 'integrity': known, 'source_id': sid, 'status': 'added'})
    data = (p.source_dir(sid) / 'original.pdf').read_bytes() if pdf_available else None
    monkeypatch.setattr(acquire, 'find_pdf', lambda candidate, client=None: (data, []))
    providers.collect(p, candidate)
    assert p.source(sid)['integrity']['status'] == 'retracted'
    assert p.collection()[0]['integrity']['status'] == 'retracted'
    assert p.collection()[0]['integrity']['providers']['Crossref']['status'] == 'retracted'


def test_partial_check_reaches_report_and_report_screen(tmp_path):
    from streamlit.testing.v1 import AppTest
    from test_ui import _workbench_script
    p, run = _project(tmp_path)
    row = w.evidence(p, run)[0]
    w.review(p, run, row['id'], 'accept', 'Checked context', 'Reviewer')
    partial = {'doi': '10.1/a', 'status': 'clear', 'via': 'OpenAlex(Crossref에 없는 DOI · 정정 고지는 확인 못 함)',
               'notices': [], 'checked_at': '2020-01-01'}
    p.set_integrity(row['source_id'], partial)
    assert '정정·우려 고지는 확인하지 못했습니다' in report(p, run)
    app = AppTest.from_function(_workbench_script, args=(str(p.root),))
    app.session_state['drk_claude_ready'] = False
    app.session_state['cc_status'] = {'available': False, 'reason': 'test'}
    app.run(timeout=60)
    app.button(key='wb_progress_채택').click().run(timeout=60)
    assert not app.exception
    assert any('철회 표시만 확인했습니다. 정정·우려 고지는 미확인입니다' in m.value for m in app.markdown)


def test_other_source_observation_does_not_hide_a_failed_check(monkeypatch):
    monkeypatch.setattr(integrity, 'now', lambda: '2026-01-01T00:00:00Z')
    initial = integrity.from_search({'doi': '10.1/a', 'retracted': True})
    monkeypatch.setattr(integrity, 'now', lambda: '2026-01-02T00:00:00Z')
    failed = integrity.check_doi('10.1/a', client({}, status=503), previous=initial)
    monkeypatch.setattr(integrity, 'now', lambda: '2026-01-03T00:00:00Z')
    candidate = {'doi': '10.1/a', 'source_id': 's1', 'retracted': True}
    combined = notebook.candidate_integrity(candidate, {'s1': {'doi': '10.1/a', 'integrity': failed}})
    assert combined['status'] == 'retracted' and combined['check_status'] == 'unknown'
    assert 'Crossref HTTPStatusError' in combined['error']
    assert '최근 조회 실패' in integrity.explain(combined)
    recovered = integrity.check_doi('10.1/a', client({'message': {}}), previous=combined)
    assert recovered['status'] == 'retracted' and recovered['check_status'] == 'clear'
    assert 'error' not in recovered
    assert all('checks' not in c and 'providers' not in c and 'last_check' not in c for c in recovered['checks'])


def test_result_json_preserves_current_integrity_beside_frozen_sources(tmp_path):
    import io
    import json
    import zipfile
    p, run = _project(tmp_path)
    row = w.evidence(p, run)[0]
    frozen = w.manifest(p, run)['sources']
    assert not frozen[0].get('integrity')
    w.review(p, run, row['id'], 'accept', 'Checked context', 'Reviewer')
    warning = integrity.check_doi('10.1/a', client(RETRACTED))
    failed = integrity.check_doi('10.1/a', client({}, status=503), previous=warning)
    p.set_integrity(row['source_id'], failed)
    with zipfile.ZipFile(io.BytesIO(export_zip(p, run))) as archive:
        exported = json.loads(archive.read('research.json'))
        assert exported['run']['sources'] == frozen
        assert exported['current_sources'][0]['integrity'] == failed
        assert exported['exported_at']
        assert '최근 조회 실패' in archive.read('research.md').decode()
        assert 'current_sources' in archive.read('README.txt').decode()
    assert w.manifest(p, run)['sources'] == frozen


@pytest.mark.parametrize('optional', [{}, {'doi': None, 'url': None}])
def test_collect_can_register_pdf_without_doi_or_landing_url(tmp_path, monkeypatch, optional):
    from deep_research import acquire, providers
    from deep_research.project import Project
    p, run = _project(tmp_path)
    sid = w.evidence(p, run)[0]['source_id']
    data = (p.source_dir(sid) / 'original.pdf').read_bytes()
    fresh = Project(tmp_path / 'fresh').initialize()
    candidate = {'title': 'A PDF without a DOI', 'pdf_url': 'https://example.test/paper.pdf', **optional}
    monkeypatch.setattr(acquire, 'find_pdf', lambda candidate, client=None: (data, []))
    result = providers.collect(fresh, candidate)
    assert result['status'] == 'added'
    assert fresh.source(result['source_id'])['doi'] == ''
    assert fresh.collection()[0]['source_id'] == result['source_id']


def test_collect_without_retrieval_metadata_returns_clear_missing_result(tmp_path):
    from deep_research import providers
    from deep_research.project import Project
    p = Project(tmp_path / 'no-address').initialize()
    def unexpected(request):
        raise AssertionError('A title-only candidate must not make an invented network request')
    result = providers.collect(p, {'title': 'Title only'}, httpx.Client(transport=httpx.MockTransport(unexpected)))
    assert result['status'] == 'pdf_missing' and result['source_id'] is None
    assert 'PDF를 직접 가져오세요' in result['attempts'][0]['result']
    assert p.collection()[0]['title'] == 'Title only'
