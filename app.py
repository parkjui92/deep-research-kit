"""Local review desk. All persistent operations use the same core as the skill/CLI."""
import os
from pathlib import Path

import streamlit as st

from deep_research.project import Project, read_json, write_json
from deep_research.providers import use_session_key
from ui import chrome as ui
from ui.pages import PAGES
from ui.start import is_example, start_page
from ui.workbench import workbench

st.set_page_config(page_title="Deep Research Kit · 근거 검토실", page_icon="📖", layout="wide")
ui.inject_css()

ROOT = Path(__file__).resolve().parent
PROJECTS = Path(os.environ.get("DRK_PROJECTS_DIR", ROOT / "projects")).expanduser().resolve()
PROJECTS.mkdir(parents=True, exist_ok=True)


def make_example(folder: str, title: str, with_table: bool):
    """Common case: three real papers. with_table=True also loads the prepared example responses so
    the first thing the person sees is a filled comparison table."""
    from deep_research.examples import apply_example_screening, create_example, load_reference
    target = PROJECTS / folder
    # This UI creates separate examples only. Mark their origin before downloading, so
    # a partly downloaded example never appears among the person's own research.
    if target.exists():
        raise ValueError("이미 있는 조사 폴더입니다. 시작 화면에서 새 예시 체험을 선택하세요.")
    target.mkdir(parents=True)
    write_json(target / "example-origin.json", {"schema": "drk-example-origin/1", "kind": "example"})
    with st.spinner("실제 논문 3편을 공식 자료원에서 내려받아 등록하는 중 · 약 20초"):
        project = create_example(target, title=title)
        if with_table:
            apply_example_screening(project)
            run_id = load_reference(project)
            st.session_state["wb_run"] = run_id
    st.session_state["open_project"] = folder
    if with_table:
        # Set before the sidebar's mode switch (key mode_pick) is drawn in the next run.
        st.session_state["mode"] = st.session_state["mode_pick"] = "작업 화면"
        st.session_state["flash"] = "논문 3편의 비교표입니다. 값을 누르면 오른쪽에 원문이 열립니다. 이상한 값 하나를 원문에서 확인해 고쳐 보고, 「항목 추가」로 비교 항목을 하나 더해 보세요."
    else:
        st.session_state["mode"] = st.session_state["mode_pick"] = "단계별(학습)"
        st.session_state["stage_value"] = ui.STAGES[1]
        st.session_state["flash"] = "논문 3편을 등록했습니다. 제목과 PDF를 확인하고 포함·제외를 판단하세요. AI 추출(3단계)은 Claude Code가 있으면 직접, 없으면 「수업용 예시 응답」으로 할 수 있습니다."
    st.rerun()


def show_start():
    st.query_params.pop("project", None)
    st.session_state["project_name"] = None
    st.session_state.pop("start_path", None)
    st.session_state["scroll_top"] = True


def select_project():
    name = st.session_state.get("project_name")
    if name:
        st.query_params["project"] = name
        st.session_state.pop("start_path", None)
        st.session_state["mode_pick"] = st.session_state.get("mode", "작업 화면")
        st.session_state["scroll_top"] = True
    else:
        st.query_params.pop("project", None)


def sidebar(existing):
    st.sidebar.markdown('<div class="drk-brand">DEEP RESEARCH KIT</div><div class="drk-brand-sub">근거 검토실</div>',
                        unsafe_allow_html=True)
    st.sidebar.button("＋ 새 조사", key="start_new", width="stretch", on_click=show_start)
    if target := st.session_state.pop("open_project", None):
        if target in existing:
            st.query_params["project"] = target
            st.session_state["mode_pick"] = st.session_state.get("mode", "작업 화면")
            st.session_state["scroll_top"] = True
    if not existing:
        return None
    # The URL is the explicit choice. A plain / always opens the start page, even
    # if a previous session or .last-project file happens to contain an example.
    wanted = st.query_params.get("project")
    if wanted and wanted not in existing:
        st.sidebar.warning("이 링크의 조사를 찾을 수 없습니다. 아래에서 저장된 조사를 선택하세요.")
        st.query_params.pop("project", None)
        wanted = None
    if st.session_state.get("project_name") != wanted:
        st.session_state["project_name"] = wanted
    name = st.sidebar.selectbox("조사 선택", existing, index=None, key="project_name",
                                placeholder="내 조사 또는 예시 선택",
                                format_func=lambda n: ("예시 · " if is_example(PROJECTS / n) else "내 조사 · ")
                                + read_json(PROJECTS / n / "project.json")["title"],
                                on_change=select_project)
    if not name:
        return None
    project = Project(PROJECTS / name)
    if st.session_state.get("mode_pick") not in {"작업 화면", "단계별(학습)"}:
        st.session_state["mode_pick"] = st.session_state.get("mode", "작업 화면")
    st.session_state["mode"] = st.session_state.get("mode_pick") or "작업 화면"
    if st.session_state["mode"] == "작업 화면":
        return project
    with st.sidebar.expander("도움말·보기 설정"):
        st.segmented_control("보기", ["작업 화면", "단계별(학습)"], key="mode_pick")
        st.caption("단계별 안내에서는 조사 설계부터 따라갈 수 있습니다.")
    # The marks change the option labels, which would reset a keyed radio on every rerun;
    # keep the chosen stage ourselves and hand the radio its index.
    current = st.session_state.get("stage_value", ui.STAGES[0])
    status = ui.stage_status(project, current)
    chosen = st.sidebar.radio("작업 단계", ui.STAGES, index=ui.STAGES.index(current),
                              format_func=lambda s: f"{ui.STAGE_MARK[status[s]]}  {s}")
    st.session_state["stage_value"] = chosen
    if chosen != current:
        # The ✓·●·○ marks were drawn for the previous stage; redraw once so ● follows the click.
        st.session_state["scroll_top"] = True
        st.rerun()
    st.sidebar.caption("✓ 저장된 것이 있음 · ● 지금 보는 단계 · ○ 아직 저장한 것 없음")
    st.sidebar.caption(f"폴더 `{name}` · 3·5단계의 AI 실행은 Claude Code 또는 수업용 예시 응답으로")
    return project


def main():
    # A key typed into this browser session applies to this run only (never saved, never shared).
    use_session_key(st.session_state.get("drk_openalex_key"))
    existing = sorted(p.name for p in PROJECTS.iterdir() if (p / "project.json").exists())
    project = sidebar(existing)
    if project is None:
        start_page(PROJECTS, make_example)
        return
    title = read_json(project.root / "project.json")["title"]
    if is_example(project.root):
        st.info("예시 조사입니다. 내 연구는 ‘＋ 새 조사’에서 시작하세요.",
                icon=":material/school:")
    if st.session_state.get("mode", "작업 화면") == "작업 화면":
        if message := st.session_state.pop("flash", None):
            st.success(message)
        workbench(project)
        return
    ui.app_header(project, title, st.session_state["stage_value"])
    if st.session_state.pop("scroll_top", False):
        ui.scroll_top()
    if message := st.session_state.pop("flash", None):
        st.success(message)
    ui.todo(project, st.session_state["stage_value"])
    PAGES[ui.STAGES.index(st.session_state["stage_value"])](project)


try:
    main()
except (ValueError, OSError, KeyError, TypeError) as exc:
    st.error(str(exc))
    st.caption("이미 저장한 문헌·실행·검토 기록은 프로젝트 폴더에 남아 있습니다. 화면을 새로 고치거나 왼쪽에서 다른 프로젝트·보기를 고르면 계속할 수 있습니다.")
