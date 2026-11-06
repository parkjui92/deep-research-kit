"""Korean reference translations: what counts as foreign, the request, the checked answer,
the headless Claude Code run and where the translation shows."""
import json

import pytest

from deep_research import translate
from deep_research.project import Project

EN = "Generative AI raised the productivity of customer support agents by 14 percent."
TITLE = "The Impact of Generative AI on Knowledge Work"


def _project(tmp_path):
    return Project(tmp_path / "projects" / "p").initialize()


def test_only_mostly_latin_text_needs_translation():
    assert translate.is_foreign(EN)
    assert not translate.is_foreign("생성형 AI는 상담원 생산성을 14% 높였다(GPT-4 기반).")
    assert not translate.is_foreign("OECD AI")  # a label, not a sentence
    assert translate.key(EN) == translate.key("  " + EN.replace(" ", "\n", 1))  # whitespace does not matter
    assert translate.missing({}, [EN, EN, "한국어 문장입니다", ""]) == [EN]


def test_prepare_batches_untranslated_text_and_drops_a_stale_answer(tmp_path):
    p = _project(tmp_path)
    translate.response_path(p).parent.mkdir(parents=True, exist_ok=True)
    translate.response_path(p).write_text("{}", encoding="utf-8")
    request = translate.prepare(p, [EN, TITLE, "이미 한국어"])
    assert [i["text"] for i in request["items"]] == [EN, TITLE]
    assert not translate.response_path(p).exists()
    assert json.loads(translate.request_path(p).read_text(encoding="utf-8"))["items"][0]["id"] == translate.key(EN)
    assert '"id"' in translate.prompt_text(request) and EN in translate.prompt_text(request)


def test_only_checked_answers_are_stored(tmp_path):
    p = _project(tmp_path)
    translate.prepare(p, [EN, TITLE])
    answer = {"items": [
        {"id": translate.key(EN), "ko": "생성형 AI는 고객 상담원의 생산성을 14% 높였다."},
        {"id": translate.key(TITLE), "ko": "Not Korean at all"},
        {"id": "never-asked", "ko": "요청하지 않은 항목"},
    ]}
    assert translate.import_answer(p, answer, "웹 AI") == 1
    cache = translate.load(p)
    assert translate.lookup(cache, EN).startswith("생성형 AI는")
    assert translate.lookup(cache, TITLE) == "" and "never-asked" not in cache
    assert cache[translate.key(EN)]["by"] == "웹 AI"
    with pytest.raises(ValueError, match="id"):
        translate.import_answer(p, {"items": [{"id": translate.key(TITLE), "ko": "가" * 5000}]}, "웹 AI")  # too long to be it
    with pytest.raises(ValueError, match="형식"):
        translate.import_answer(p, {"translations": []}, "웹 AI")


def test_a_web_ai_answer_in_prose_or_a_code_fence_is_read():
    raw = '번역입니다:\n```json\n{"items": [{"id": "a", "ko": "가"}]}\n```\n끝.'
    assert translate.parse_answer(raw) == {"items": [{"id": "a", "ko": "가"}]}
    with pytest.raises(ValueError, match="JSON"):
        translate.parse_answer("no json here")


def test_claude_code_gets_only_the_request_and_the_answer_file(tmp_path, monkeypatch):
    import shutil

    from deep_research import providers
    p = _project(tmp_path)
    request = translate.prepare(p, [EN])
    rid = request["request_id"]
    tools = providers.translate_tools(p, rid)
    assert tools == [f"Read(./projects/p/translate/requests/{rid}.json)", f"Edit(./projects/p/translate/responses/{rid}.json)",
                     f"Write(./projects/p/translate/responses/{rid}.json)"]
    assert "\n" not in providers.translate_prompt(p)
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "1", ""

    def fake_cli(args, timeout, cwd=None):
        seen["args"], seen["cwd"] = args, cwd
        translate.response_path(p, rid).write_text(json.dumps({"items": [{"id": translate.key(EN), "ko": "생성형 AI는 생산성을 높였다."}]}),
                                              encoding="utf-8")
        return Done()

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(providers, "_cli", fake_cli)
    assert providers.run_claude_translate(p) == 1
    assert seen["args"][seen["args"].index("--allowedTools") + 1:] == tools
    assert translate.lookup(translate.load(p), EN) == "생성형 AI는 생산성을 높였다."


def test_claude_code_that_saved_nothing_is_reported(tmp_path, monkeypatch):
    import shutil

    from deep_research import providers
    p = _project(tmp_path)
    translate.prepare(p, [EN])

    class Done:
        returncode, stdout, stderr = 0, "I need permission to write the file.", ""

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(providers, "_cli", lambda *a, **kw: Done())
    with pytest.raises(ValueError, match="I need permission"):
        providers.run_claude_translate(p)


def test_quote_shows_the_extraction_translation_first():
    from ui.chrome import quote_html
    locator = {"quote": EN, "page": 3, "status": "exact", "boxes": []}
    assert "참고 번역" not in quote_html(locator)
    assert "나중 번역" in quote_html(locator, translated="나중 번역")
    assert "추출 때 번역" in quote_html({**locator, "translation": "추출 때 번역"}, translated="나중 번역")


def _search_script(root, title, abstract):
    import streamlit as st

    from deep_research.project import Project
    from ui.workbench import search_results_panel
    st.session_state.setdefault("wb_results", [
        {"title": title, "abstract": abstract, "authors": ["A"], "year": 2025, "venue": "J", "cited_by": 1,
         "pdf_url": "", "oa": False, "doi": "10.1/x", "url": "https://example.com/x", "providers": ["OpenAlex"]}])
    st.session_state.setdefault("drk_claude_ready", True)
    search_results_panel(Project(root))


def test_search_results_translate_on_click_and_show_beside_the_original(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from deep_research import providers
    p = _project(tmp_path)

    def fake_run(project, request_id=None):
        request = translate.read_request(project, request_id)
        assert [i["text"] for i in request["items"]] == [TITLE, EN]
        return translate.import_answer(project, {"items": [
            {"id": translate.key(TITLE), "ko": "생성형 AI가 지식 노동에 미치는 영향"},
            {"id": translate.key(EN), "ko": "생성형 AI는 고객 상담원의 생산성을 14% 높였다."}]}, "Claude Code")

    monkeypatch.setattr(providers, "run_claude_translate", fake_run)
    app = AppTest.from_function(_search_script, args=(str(p.root), TITLE, EN)).run(timeout=60)
    assert not app.exception
    button = next(b for b in app.button if b.label.startswith("보이는 결과의 영문 제목·초록 한글 번역"))
    assert button.label.endswith("2건")
    button.click().run(timeout=60)
    assert not app.exception
    assert any("번역 2건을 저장했습니다" in s.value for s in app.success)
    table = next(d.value for d in app.dataframe if "제목" in d.value.columns)
    assert table.iloc[0]["제목 번역(참고)"] == "생성형 AI가 지식 노동에 미치는 영향"
    shown = " ".join(m.value for m in app.markdown)
    assert "참고 번역(AI · 원문 대조 안 함) · 생성형 AI는 고객 상담원의" in shown
    assert not any(b.label.startswith("보이는 결과의 영문") for b in app.button)  # nothing left to translate


def test_requests_survive_later_batches_and_reply_order(tmp_path):
    p = _project(tmp_path)
    a = translate.prepare(p, [EN], context="search")
    a_path = translate.request_path(p, a["request_id"])
    before = a_path.read_bytes()
    b = translate.prepare(p, [TITLE], context="grid")
    assert a["request_id"] != b["request_id"]
    assert a_path.read_bytes() == before
    assert translate.import_answer(p, {"request_id": b["request_id"], "items": [
        {"id": translate.key(TITLE), "ko": "생성형 AI와 지식 노동"}]}, "웹 AI") == 1
    # A predates B, but its valid answer still belongs to A, even without an echoed request_id.
    assert translate.import_answer(p, {"items": [{"id": translate.key(EN), "ko": "생산성이 14% 높아졌다."}]},
                                   "웹 AI", request_id=a["request_id"]) == 1
    assert translate.lookup(translate.load(p), EN) == "생산성이 14% 높아졌다."
    assert not translate.pending_requests(p, "search")


def test_partial_answers_can_resume_and_replay_cannot_replace_cached_text(tmp_path):
    p = _project(tmp_path)
    request = translate.prepare(p, [EN, TITLE], context="search")
    rid = request["request_id"]
    first = {"items": [{"id": translate.key(EN), "ko": "생산성이 14% 높아졌다."}]}
    assert translate.import_answer(p, first, "웹 AI", rid) == 1
    assert [i["text"] for i in translate.remaining(p, request)] == [TITLE]
    assert [r["request_id"] for r in translate.pending_requests(p, "search")] == [rid]
    assert translate.import_answer(p, {"items": [{"id": translate.key(EN), "ko": "이미 저장한 번역을 바꾸려는 응답"}]}, "웹 AI", rid) == 0
    assert translate.lookup(translate.load(p), EN) == "생산성이 14% 높아졌다."
    assert translate.import_answer(p, {"items": [{"id": translate.key(TITLE), "ko": "생성형 AI와 지식 노동"}]}, "웹 AI", rid) == 1
    assert not translate.remaining(p, request)
    assert not translate.pending_requests(p, "search")


def test_mismatched_request_and_other_project_are_rejected(tmp_path):
    p = _project(tmp_path)
    other = Project(tmp_path / "other").initialize()
    a = translate.prepare(p, [EN])
    b = translate.prepare(p, [TITLE])
    reply = {"request_id": a["request_id"], "items": [{"id": translate.key(EN), "ko": "한국어 번역"}]}
    with pytest.raises(ValueError, match="request_id"):
        translate.import_answer(p, reply, "웹 AI", b["request_id"])
    with pytest.raises(ValueError, match="이 프로젝트"):
        translate.import_answer(other, reply, "웹 AI")
    with pytest.raises(ValueError, match="ID"):
        translate.import_answer(p, {**reply, "request_id": "../../project"}, "웹 AI")
    assert not translate.load(p) and not translate.load(other)


def test_legacy_request_and_response_files_remain_readable(tmp_path):
    from deep_research.project import write_json
    p = _project(tmp_path)
    write_json(translate.request_path(p), {"instructions": translate.INSTRUCTIONS, "items": [{"id": translate.key(EN), "text": EN}]})
    write_json(translate.response_path(p), {"items": [{"id": translate.key(EN), "ko": "기존 요청의 한국어 응답"}]})
    assert translate.import_response_file(p) == 1
    assert translate.lookup(translate.load(p), EN) == "기존 요청의 한국어 응답"


def test_oversized_text_is_not_truncated_and_cached_as_a_full_translation(tmp_path):
    p = _project(tmp_path)
    with pytest.raises(ValueError, match="구간을 나눠"):
        translate.prepare(p, ["Long source text. " * translate.MAX_CHARS])
    assert not translate.request_path(p).exists()


def test_claude_runner_keeps_its_request_when_another_is_prepared(tmp_path, monkeypatch):
    import shutil

    from deep_research import providers
    p = _project(tmp_path)
    a = translate.prepare(p, [EN])
    class Done:
        returncode, stdout, stderr = 0, "1", ""
    def fake_cli(args, timeout, cwd=None):
        translate.prepare(p, [TITLE])
        assert a["request_id"] in args[args.index("-p") + 1]
        translate.response_path(p, a["request_id"]).write_text(json.dumps({
            "request_id": a["request_id"], "items": [{"id": translate.key(EN), "ko": "첫 요청의 번역"}]}), encoding="utf-8")
        return Done()
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    monkeypatch.setattr(providers, "_cli", fake_cli)
    assert providers.run_claude_translate(p, request_id=a["request_id"]) == 1
    assert translate.lookup(translate.load(p), EN) == "첫 요청의 번역"
    assert not translate.lookup(translate.load(p), TITLE)


def _translation_script(roots):
    import streamlit as st

    from deep_research.project import Project
    from ui import translation
    st.session_state["drk_claude_ready"] = False
    root = st.selectbox("프로젝트", roots)
    page = st.radio("화면", ["first", "second"], horizontal=True)
    text = "Generative AI raised the productivity of customer support agents by 14 percent." if page == "first" else "The Impact of Generative AI on Knowledge Work"
    translation.control(Project(root), [text], page)


def _make_request(app):
    next(b for b in app.button if b.label == "요청문 만들기").click().run(timeout=60)
    assert not app.exception


def test_ui_returns_to_earlier_request_and_keeps_projects_separate(tmp_path):
    from streamlit.testing.v1 import AppTest
    p = _project(tmp_path)
    other = Project(tmp_path / "other").initialize()
    app = AppTest.from_function(_translation_script, args=([str(p.root), str(other.root)],)).run(timeout=60)
    _make_request(app)
    original_prompt = app.code[0].value
    app.radio[0].set_value("second").run(timeout=60)
    _make_request(app)
    assert TITLE in app.code[0].value and EN not in app.code[0].value
    app.radio[0].set_value("first").run(timeout=60)
    assert app.code[0].value == original_prompt
    app.selectbox[0].set_value(str(other.root)).run(timeout=60)
    assert not app.code  # same control key, different project: no old prompt or response form
    app.selectbox[0].set_value(str(p.root)).run(timeout=60)
    assert app.code[0].value == original_prompt
    app.text_area[0].set_value(json.dumps({"items": [{"id": translate.key(EN), "ko": "생산성이 14% 높아졌다."}]}))
    next(b for b in app.button if b.label == "번역 저장").click().run(timeout=60)
    assert not app.exception and not app.error
    assert translate.lookup(translate.load(p), EN) == "생산성이 14% 높아졌다."
    assert not translate.load(other)
    app.radio[0].set_value("second").run(timeout=60)
    assert TITLE in app.code[0].value  # the other outstanding request was not removed


def test_a_legacy_request_is_frozen_before_a_runner_can_read_it(tmp_path):
    from deep_research.project import write_json
    p = _project(tmp_path)
    legacy = {"instructions": "legacy instructions", "items": [{"id": translate.key(EN), "text": EN}]}
    write_json(translate.request_path(p), legacy)
    frozen = translate.freeze_request(p)
    translate.prepare(p, [TITLE])
    stored = translate.read_request(p, frozen["request_id"])
    assert stored["instructions"] == legacy["instructions"] and stored["items"] == legacy["items"]


def _batch_script(root):
    import streamlit as st

    from deep_research.project import Project
    from ui import translation
    st.session_state["drk_claude_ready"] = False
    title = "The Impact of Generative AI on Knowledge Work"
    finding = "Generative AI raised the productivity of customer support agents by 14 percent."
    group = st.radio("검색 결과", ["two", "one"])
    translation.control(Project(root), [finding, title] if group == "two" else [title], "search")


def test_ui_selects_earlier_batch_and_resumes_partial_reply(tmp_path):
    from streamlit.testing.v1 import AppTest
    p = _project(tmp_path)
    app = AppTest.from_function(_batch_script, args=(str(p.root),)).run(timeout=60)
    _make_request(app)
    first = translate.pending_requests(p, "search")[0]
    app.radio[0].set_value("one").run(timeout=60)
    _make_request(app)
    pending = next(s for s in app.selectbox if s.label == "응답을 저장할 번역 요청")
    pending.set_value(first["request_id"]).run(timeout=60)
    assert EN in app.code[0].value
    app.text_area[0].set_value(json.dumps({"items": [{"id": translate.key(EN), "ko": "생산성이 14% 높아졌다."}]}))
    next(b for b in app.button if b.label == "번역 저장").click().run(timeout=60)
    assert not app.exception and not app.error
    assert any("1건이 남았습니다" in item.value for item in app.success)
    assert EN in app.code[0].value  # original request stays selected for its remaining reply
    app.text_area[0].set_value(json.dumps({"items": [{"id": translate.key(TITLE), "ko": "생성형 AI와 지식 노동"}]}))
    next(b for b in app.button if b.label == "번역 저장").click().run(timeout=60)
    assert not app.exception and not app.error
    assert not app.code and not translate.pending_requests(p, "search")
