"""Regressions reproduced while following a fresh GitHub installation."""
import os
import subprocess
from pathlib import Path

import pytest
from test_benchmark_navigation import _app, _clean

from deep_research import providers
from deep_research.project import Project


def test_search_survives_navigation_and_same_title_versions_select_independently(tmp_path, monkeypatch):
    # Identical project titles must not silently select the other research either.
    project = Project(tmp_path / "projects" / "first").initialize(question="A research question")
    other = Project(project.root.parent / "second").initialize(question="Another question")
    results = [providers._candidate(title="Same title", year=2023, doi=f"10.1234/{version}")
               for version in ("working-paper", "journal")]
    calls = []

    def search(*args, **kwargs):
        calls.append((args, kwargs))
        return len(results), results

    monkeypatch.setitem(providers.PROVIDERS, "Crossref", search)
    app = _app(project, monkeypatch)
    assert len(set(app.selectbox(key="project_name").options)) == 2
    app.text_input(key="wb_q").set_value("customer support")
    app.multiselect(key="wb_prov").set_value(["Crossref"])
    app.number_input(key="wb_year").set_value(2020)
    app.number_input(key="wb_limit").set_value(10)
    next(button for button in app.button if button.label == "문헌 검색").click().run()
    assert not app.error, [error.value for error in app.error]
    _clean(app)
    picker = next(item for item in app.selectbox if item.label == "살펴볼 문헌")
    assert len(set(picker.options)) == 2
    assert "10.1234/journal" in picker.options[1]
    picker.set_value(1).run()
    app.button(key="wb_collect_one").click().run()
    _clean(app)
    assert project.collection()[0]["doi"] == "10.1234/journal"
    assert app.segmented_control(key="wb_library_view").value == "읽기 후보"
    app.segmented_control(key="wb_library_view").set_value("내 PDF").run()
    app.segmented_control(key="wb_library_view").set_value("문헌 검색").run()
    _clean(app)
    assert app.text_input(key="wb_q").value == "customer support"
    assert app.multiselect(key="wb_prov").value == ["Crossref"]
    assert app.number_input(key="wb_year").value == 2020
    assert app.number_input(key="wb_limit").value == 10
    assert next(item for item in app.selectbox if item.label == "살펴볼 문헌").value == 1
    assert app.button(key="wb_collect_one").disabled
    assert len(calls) == 1
    app.selectbox(key="project_name").set_value(other.root.name).run()
    _clean(app)
    assert app.text_input(key="wb_q").value != "customer support"
    assert not other.collection()


def test_resume_choices_disambiguate_identical_titles_and_creation_minutes(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from deep_research.project import read_json, write_json

    root = tmp_path / "projects"
    first = Project(root / "first").initialize(title="같은 제목", question="First question")
    second = Project(root / "second").initialize(title="같은 제목", question="Second question")
    metadata = read_json(second.root / "project.json")
    metadata["created_at"] = read_json(first.root / "project.json")["created_at"]
    write_json(second.root / "project.json", metadata)
    monkeypatch.setenv("DRK_PROJECTS_DIR", str(root))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert len(set(app.selectbox(key="start_resume").options)) == 2
    app.selectbox(key="start_resume").set_value("first").run()
    app.button(key="start_resume_go").click().run()
    _clean(app)
    assert app.session_state["wb_project"] == str(first.root)


@pytest.mark.parametrize("sync_status", [0, 1])
def test_mac_launcher_handles_spaces_and_noninteractive_install_failure(tmp_path, sync_status):
    root = tmp_path / "새 사용자 설치"
    root.mkdir()
    launcher = root / "start.command"
    launcher.write_bytes((Path(__file__).resolve().parents[1] / "start.command").read_bytes())
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_uv = bin_dir / "uv"
    fake_uv.write_text('#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "$DRK_TEST_LOG"\n'
                       'if [ "$1" = sync ]; then exit "$DRK_SYNC_STATUS"; fi\n', encoding="utf-8")
    fake_uv.chmod(0o755)
    log = tmp_path / "calls.log"
    env = {**os.environ, "PATH": str(bin_dir) + os.pathsep + os.environ["PATH"],
           "DRK_TEST_LOG": str(log), "DRK_SYNC_STATUS": str(sync_status)}
    result = subprocess.run(["sh", str(launcher)], cwd=tmp_path, env=env, input="",
                            text=True, capture_output=True, timeout=5)
    assert result.returncode == sync_status
    calls = log.read_text().splitlines()
    assert calls[0] == f"{root}|sync --frozen"
    if sync_status:
        assert len(calls) == 1
        assert "설치를 마치지 못했습니다" in result.stdout
    else:
        assert calls[1] == f"{root}|run --frozen streamlit run app.py --server.address 127.0.0.1"
