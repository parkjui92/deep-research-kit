"""Local review desk. All persistent operations use the same core as the skill/CLI."""
import os
from pathlib import Path

import streamlit as st

from deep_research.project import Project, read_json
from ui import chrome as ui
from ui.pages import PAGES
from ui.start import start_page
from ui.workbench import workbench

st.set_page_config(page_title="Deep Research Kit · 근거 검토실", page_icon="📖", layout="wide")
ui.inject_css()

ROOT = Path(__file__).resolve().parent
PROJECTS = Path(os.environ.get("DRK_PROJECTS_DIR", ROOT / "projects")).expanduser().resolve()
PROJECTS.mkdir(parents=True, exist_ok=True)


LAST = PROJECTS / ".last-project"


def remember(name: str):
    try:
        LAST.write_text(name, encoding="utf-8")
    except OSError:
        pass


def make_example(folder: str, title: str, with_table: bool):
    """Common case: three real papers. with_table=True also loads the prepared example responses so
    the first thing the person sees is a filled comparison table."""
    from deep_research.examples import apply_example_screening, create_example, load_reference
    target = PROJECTS / folder
    with st.spinner("실제 논문 3편을 공식 자료원에서 내려받아 등록하는 중 · 약 20초"):
        project = create_example(target, title=title)
        if with_table:
            apply_example_screening(project)
            run_id = load_reference(project)
            st.session_state["wb_run"] = run_id
    st.session_state["open_project"] = folder
    remember(folder)
    if with_table:
        # Set before the sidebar's mode switch (key mode_pick) is drawn in the next run.
        st.session_state["mode"] = st.session_state["mode_pick"] = "작업 화면"
        st.session_state["flash"] = "논문 3편의 비교표입니다. 값을 누르면 오른쪽에 원문이 열립니다. 이상한 값 하나를 원문에서 확인해 고쳐 보고, 「항목 추가」로 비교 항목을 하나 더해 보세요."
    else:
        st.session_state["stage_value"] = ui.STAGES[1]
        st.session_state["flash"] = "논문 3편을 등록했습니다. 제목과 PDF를 확인하고 포함·제외를 판단하세요. AI 추출(3단계)은 Claude Code가 있으면 직접, 없으면 「수업용 예시 응답」으로 할 수 있습니다."
    st.rerun()


def sidebar(existing):
    st.sidebar.markdown('<div class="drk-brand">DEEP RESEARCH KIT</div><div class="drk-brand-sub">근거 검토실</div>',
                        unsafe_allow_html=True)
    if st.sidebar.button("＋ 새 조사", width="stretch"):
        st.session_state["start_open"] = True
        st.session_state.pop("start_path", None)
    if target := st.session_state.pop("open_project", None):
        st.session_state["project_name"] = target
        st.session_state["start_open"] = False
        st.session_state["mode"] = st.session_state["mode_pick"] = "작업 화면"
    if not existing:
        return None
    if "project_name" not in st.session_state:
        wanted = st.query_params.get("project") or (LAST.read_text(encoding="utf-8").strip() if LAST.exists() else "")
        st.session_state["project_name"] = wanted if wanted in existing else existing[0]
    name = st.sidebar.selectbox("내 조사", existing, key="project_name",
                                format_func=lambda n: read_json(PROJECTS / n / "project.json")["title"],
                                on_change=lambda: st.session_state.update(start_open=False))
    if st.session_state.get("start_open"):
        return None
    st.query_params["project"] = name
    remember(name)
    project = Project(PROJECTS / name)
    if "mode_pick" not in st.session_state:
        st.session_state["mode_pick"] = st.session_state.get("mode", "작업 화면")
    with st.sidebar.expander("도움말·보기 설정"):
        mode = st.segmented_control("보기", ["작업 화면", "단계별(학습)"], key="mode_pick")
        st.caption("단계별 안내에서는 조사 설계부터 따라갈 수 있습니다.")
    st.session_state["mode"] = mode or st.session_state.get("mode", "작업 화면")
    if st.session_state["mode"] == "작업 화면":
        sources = project.catalog()
        st.sidebar.divider()
        st.sidebar.caption("프로젝트 현황")
        st.sidebar.markdown(f"**{len(sources)}** 문헌　 ·　 **{sum(s['decision'] == 'include' for s in sources)}** 포함")
        st.sidebar.caption("앱이 실행되는 컴퓨터에 저장 · AI 없이 원문 검색·노트·내보내기 가능")
        with st.sidebar.expander("AI 연결·도움말"):
            st.caption("근거 비교에서 Claude Code·웹 AI·설정된 API를 선택합니다. 로컬에 저장해도 외부 AI를 실행하면 지정한 원문이 전달됩니다.")
            st.caption(f"프로젝트 폴더 · {name}")
        return project
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
    existing = sorted(p.name for p in PROJECTS.iterdir() if (p / "project.json").exists())
    project = sidebar(existing)
    if project is None:
        start_page(PROJECTS, make_example)
        return
    title = read_json(project.root / "project.json")["title"]
    if st.session_state.get("mode", "작업 화면") == "작업 화면":
        ui.app_header(project, title, stage=None)
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
