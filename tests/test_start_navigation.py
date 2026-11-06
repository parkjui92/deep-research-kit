"""An explicit project choice, never a remembered example, opens the workbench."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from deep_research.project import Project, write_json

APP = str(Path(__file__).resolve().parents[1] / "app.py")
START_TITLE = "주제에 맞는 문헌을 찾고, 보고서에 쓸 근거로 정리하세요."


def _projects(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    sample = Project(root / "a-example").initialize("Example research", question="Example question")
    write_json(sample.root / "example-manifest.json", [])
    mine = Project(root / "my-research").initialize("My research", question="My question")
    monkeypatch.setenv("DRK_PROJECTS_DIR", str(root))
    return root, sample, mine


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def _app(project=None):
    app = AppTest.from_file(APP)
    if project:
        app.query_params["project"] = project
    return app.run(timeout=30)


def _clean(app):
    assert not app.exception
    assert not app.error


def _button(app, label):
    return next(button for button in app.button if button.label == label)


def test_intro_video_opens_on_demand_and_switching_does_not_change_research(tmp_path, monkeypatch):
    root, _, _ = _projects(tmp_path, monkeypatch)
    before = _snapshot(root)
    app = _app()
    assert not app.get("video")
    app.button(key="start_watch_video").click().run()
    _clean(app)
    assert app.radio(key="intro_video_choice").value == "90초 핵심 보기"
    short_url = app.get("video")[0].proto.url
    app.radio(key="intro_video_choice").set_value("전체 사용법 · 4분 57초").run()
    _clean(app)
    assert app.get("video")[0].proto.url != short_url
    app.button(key="start_watch_video").click().run()
    assert not app.get("video")
    assert not app.query_params.get("project")
    assert _snapshot(root) == before


def test_missing_video_keeps_guidance_and_start_actions_available(tmp_path, monkeypatch):
    from ui import onboarding

    _projects(tmp_path, monkeypatch)
    monkeypatch.setattr(onboarding, "VIDEO_DIR", tmp_path / "missing-videos")
    app = _app()
    app.button(key="start_watch_video").click().run()
    _clean(app)
    assert not app.get("video")
    assert any("영상 파일이 없습니다" in item.value for item in app.info)
    assert any("원문 발췌와 내 메모" in item.value for item in app.markdown)
    _button(app, "조사 질문에서 시작").click().run()
    _clean(app)
    assert any(field.label == "이번에 알아볼 질문" for field in app.text_input)


@pytest.mark.parametrize("remembered", ["a-example", "my-research", None])
def test_plain_url_always_starts_without_opening_or_modifying_a_project(tmp_path, monkeypatch, remembered):
    root, sample, mine = _projects(tmp_path, monkeypatch)
    if remembered:
        (root / ".last-project").write_text(remembered, encoding="utf-8")
    before = _snapshot(root)
    app = _app()
    _clean(app)
    assert [title.value for title in app.title] == [START_TITLE]
    assert app.selectbox(key="project_name").value is None
    assert app.selectbox(key="start_resume").value is None
    assert app.selectbox(key="start_example").value is None
    assert app.button(key="start_resume_go").disabled
    assert app.button(key="start_example_go").disabled
    assert not app.query_params.get("project")
    assert not any(radio.key == "wb_view" for radio in app.radio)
    assert all("Example research" not in option for option in app.selectbox(key="start_resume").options)
    assert all("My research" not in option for option in app.selectbox(key="start_example").options)
    assert _snapshot(root) == before


@pytest.mark.parametrize("example", [False, True])
def test_explicit_project_link_opens_the_selected_project_and_labels_examples(tmp_path, monkeypatch, example):
    root, sample, mine = _projects(tmp_path, monkeypatch)
    selected = sample if example else mine
    before = _snapshot(root)
    app = _app(selected.root.name)
    _clean(app)
    assert [title.value for title in app.title] == [app.radio(key="wb_view").value] == ["문헌 모으기"]
    assert START_TITLE not in [title.value for title in app.title]
    assert app.session_state["wb_project"] == str(selected.root)
    assert app.query_params["project"] == selected.root.name
    assert any("예시 조사입니다" in item.value for item in app.info) is example
    assert _snapshot(root) == before


@pytest.mark.parametrize("example", [False, True])
def test_start_lists_resume_only_the_explicitly_selected_project(tmp_path, monkeypatch, example):
    root, sample, mine = _projects(tmp_path, monkeypatch)
    before = _snapshot(root)
    app = _app()
    key = "start_example" if example else "start_resume"
    selected = sample if example else mine
    app.selectbox(key=key).set_value(selected.root.name).run()
    assert [title.value for title in app.title] == [START_TITLE]
    assert not app.query_params.get("project")
    app.button(key=key + "_go").click().run()
    _clean(app)
    assert app.session_state["wb_project"] == str(selected.root)
    assert app.query_params["project"] == selected.root.name
    assert _snapshot(root) == before


def test_new_research_clears_example_url_and_refresh_stays_on_start(tmp_path, monkeypatch):
    root, sample, _ = _projects(tmp_path, monkeypatch)
    before = _snapshot(root)
    app = _app(sample.root.name)
    app.button(key="start_new").click().run()
    _clean(app)
    assert [title.value for title in app.title] == [START_TITLE]
    assert not app.query_params.get("project")
    assert app.selectbox(key="project_name").value is None
    refreshed = _app()
    _clean(refreshed)
    assert [title.value for title in refreshed.title] == [START_TITLE]
    assert not refreshed.query_params.get("project")
    assert _snapshot(root) == before


def test_plain_url_overrides_a_stale_selection_in_the_same_session(tmp_path, monkeypatch):
    _, sample, _ = _projects(tmp_path, monkeypatch)
    app = _app(sample.root.name)
    app.query_params.clear()
    app.run()
    _clean(app)
    assert [title.value for title in app.title] == [START_TITLE]
    assert app.selectbox(key="project_name").value is None
    assert not app.query_params.get("project")


def test_missing_project_link_returns_to_start_without_falling_back_to_example(tmp_path, monkeypatch):
    root, sample, _ = _projects(tmp_path, monkeypatch)
    (root / ".last-project").write_text(sample.root.name, encoding="utf-8")
    before = _snapshot(root)
    app = _app("missing-research")
    _clean(app)
    assert [title.value for title in app.title] == [START_TITLE]
    assert app.selectbox(key="project_name").value is None
    assert not app.query_params.get("project")
    assert any("이 링크의 조사를 찾을 수 없습니다" in item.value for item in app.warning)
    assert _snapshot(root) == before


def test_resume_preserves_step_mode_but_new_research_opens_the_workbench(tmp_path, monkeypatch):
    root, sample, mine = _projects(tmp_path, monkeypatch)
    original = _snapshot(root)
    app = _app(mine.root.name)
    _button(app, "단계별 보기").click().run()
    assert app.session_state["mode"] == "단계별(학습)"
    stage = "2 · 문헌 선별"
    next(radio for radio in app.radio if radio.label == "작업 단계").set_value(stage).run()
    assert app.session_state["mode"] == "단계별(학습)"
    app.button(key="start_new").click().run()
    assert app.session_state["mode"] == "단계별(학습)"
    app.selectbox(key="start_resume").set_value(mine.root.name).run()
    app.button(key="start_resume_go").click().run()
    _clean(app)
    assert app.session_state["mode"] == "단계별(학습)"
    assert app.session_state["stage_value"] == stage
    app.button(key="start_new").click().run()
    _button(app, "PDF에서 시작").click().run()
    next(field for field in app.text_input if field.label == "이번에 알아볼 질문").set_value("A new real question")
    _button(app, "PDF 가져오기로 이동").click().run()
    _clean(app)
    name = app.session_state["project_name"]
    assert name not in {sample.root.name, mine.root.name}
    assert app.query_params["project"] == name
    assert app.session_state["mode"] == "작업 화면"
    assert app.session_state["wb_library_view"] == "내 PDF"
    assert Project(root / name).config()["plan"]["question"] == "A new real question"
    assert not (root / name / "example-origin.json").exists()
    assert all(_snapshot(root)[path] == data for path, data in original.items())


def test_sidebar_selection_can_open_research_from_start_without_changing_mode(tmp_path, monkeypatch):
    _, _, mine = _projects(tmp_path, monkeypatch)
    app = _app()
    app.selectbox(key="project_name").set_value(mine.root.name).run()
    _clean(app)
    assert app.session_state["wb_project"] == str(mine.root)
    assert app.query_params["project"] == mine.root.name
    assert app.session_state["mode"] == "작업 화면"


@pytest.mark.parametrize("entry,submit", [("조사 질문에서 시작", "문헌 검색 시작"),
                                         ("PDF에서 시작", "PDF 가져오기로 이동")])
def test_question_focus_is_requested_on_open_and_error_but_does_not_interrupt_typing(tmp_path, monkeypatch, entry, submit):
    from ui import chrome

    root, _, _ = _projects(tmp_path, monkeypatch)
    original = _snapshot(root)
    requested = []
    monkeypatch.setattr(chrome, "focus_after_render", lambda selector, **kwargs: requested.append(selector))
    app = _app()
    assert not requested
    _button(app, entry).click().run()
    assert requested == ['[data-testid="stForm"] input']
    _button(app, submit).click().run()
    assert any("이번 조사 질문을 입력하세요" in error.value for error in app.error)
    assert requested == ['[data-testid="stForm"] input'] * 2
    next(field for field in app.text_input if field.label == "이번에 알아볼 질문").set_value("작성 중인 질문").run()
    _clean(app)
    assert len(requested) == 2
    assert _snapshot(root) == original


@pytest.mark.parametrize("fail_download", [False, True])
def test_example_creation_requires_a_click_and_partial_examples_remain_separate(tmp_path, monkeypatch, fail_download):
    from deep_research import examples

    root, _, _ = _projects(tmp_path, monkeypatch)
    original = _snapshot(root)
    created = []

    def create(target, title):
        project = Project(target).initialize(title, question="Example question")
        created.append(project)
        if fail_download:
            raise ValueError("Mock download failed")
        write_json(project.root / "example-manifest.json", [])
        return project

    monkeypatch.setattr(examples, "create_example", create)
    monkeypatch.setattr(examples, "apply_example_screening", lambda project: None)
    monkeypatch.setattr(examples, "load_reference", lambda project: None)
    app = _app()
    assert not created
    app.button(key="start_example_new").click().run()
    assert len(created) == 1
    project = created[0]
    assert (project.root / "example-origin.json").exists()
    if fail_download:
        assert any("Mock download failed" in item.value for item in app.error)
    else:
        _clean(app)
        assert app.session_state["wb_project"] == str(project.root)
        assert any("예시 조사입니다" in item.value for item in app.info)
    fresh = _app()
    assert len(fresh.selectbox(key="start_resume").options) == 1
    assert len(fresh.selectbox(key="start_example").options) == 2
    assert all(_snapshot(root)[path] == data for path, data in original.items())
