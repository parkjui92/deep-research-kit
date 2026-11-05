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
    translate.prepare(p, [EN])
    tools = providers.translate_tools(p)
    assert tools == ["Read(./projects/p/translate/request.json)", "Edit(./projects/p/translate/response.json)",
                     "Write(./projects/p/translate/response.json)"]
    assert "\n" not in providers.translate_prompt(p)
    seen = {}

    class Done:
        returncode, stdout, stderr = 0, "1", ""

    def fake_cli(args, timeout, cwd=None):
        seen["args"], seen["cwd"] = args, cwd
        translate.response_path(p).write_text(json.dumps({"items": [{"id": translate.key(EN), "ko": "생성형 AI는 생산성을 높였다."}]}),
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

    def fake_run(project):
        request = json.loads(translate.request_path(project).read_text(encoding="utf-8"))
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
