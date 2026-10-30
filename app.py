"""Local review desk. All persistent operations use the same core as the skill/CLI."""
from pathlib import Path

import streamlit as st

from deep_research.project import Project, read_json, safe_id
from ui import chrome as ui
from ui.pages import PAGES

st.set_page_config(page_title="Deep Research Kit · 근거 검토실", page_icon="📖", layout="wide")
ui.inject_css()

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)


def sidebar(existing):
    st.sidebar.markdown('<div class="drk-brand">DEEP RESEARCH KIT</div><div class="drk-brand-sub">근거 검토실</div>',
                        unsafe_allow_html=True)
    with st.sidebar.expander("프로젝트 만들기", expanded=not existing):
        name = st.text_input("폴더 이름 · 영문·숫자·하이픈", "my-research")
        title = st.text_input("프로젝트 제목", "나의 문헌조사")
        if st.button("빈 프로젝트 만들기", width="stretch"):
            Project(PROJECTS / safe_id(name)).initialize(title)
            st.session_state["project_name"] = name
            st.rerun()
        if st.button("공통 사례 준비 · 실제 논문 3편", width="stretch"):
            from deep_research.examples import create_example
            target = PROJECTS / safe_id(name)
            with st.spinner("공식 자료원에서 PDF를 준비하고 있습니다"):
                create_example(target)
            st.session_state["project_name"] = name
            st.rerun()
    if not existing:
        return None
    name = st.sidebar.selectbox("프로젝트", existing, key="project_name")
    project = Project(PROJECTS / name)
    # The marks change the option labels, which would reset a keyed radio on every rerun;
    # keep the chosen stage ourselves and hand the radio its index.
    current = st.session_state.get("stage_value", ui.STAGES[0])
    status = ui.stage_status(project, current)
    chosen = st.sidebar.radio("작업 단계", ui.STAGES, index=ui.STAGES.index(current),
                              format_func=lambda s: f"{ui.STAGE_MARK[status[s]]}  {s}")
    st.session_state["stage_value"] = chosen
    st.sidebar.caption("✓ 저장된 것이 있음 · ● 지금 보는 단계 · ○ 아직 없음")
    st.sidebar.caption(str(project.root))
    return project


def main():
    existing = sorted(p.name for p in PROJECTS.iterdir() if (p / "project.json").exists())
    project = sidebar(existing)
    if project is None:
        st.title("찾은 자료를, 확인한 근거로.")
        st.markdown('<div class="drk-lead">조사 기준을 정하고, 실제 PDF의 근거를 읽고, 판단을 남기는 문헌조사 작업 공간입니다.</div>',
                    unsafe_allow_html=True)
        ui.empty("아직 프로젝트가 없습니다.", "왼쪽 「프로젝트 만들기」에서 빈 프로젝트 또는 공통 사례(실제 논문 3편)를 만드세요.")
        for column, (step, what) in zip(st.columns(6), [("1 · 조사 설계", "질문·기준·추출 항목"), ("2 · 문헌 선별", "포함·제외와 이유"),
                                                        ("3 · 원문 추출", "실행 고정 · AI 응답"), ("4 · 근거 검토", "PDF 옆에서 판단"),
                                                        ("5 · 종합", "채택 근거만으로 답"), ("6 · 비교·내보내기", "전후 비교 · ZIP")]):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{step}**")
                    st.caption(what)
        return
    st.title(read_json(project.root / "project.json")["title"])
    if message := st.session_state.pop("flash", None):
        st.success(message)
    PAGES[ui.STAGES.index(st.session_state["stage_value"])](project)


try:
    main()
except (ValueError, OSError, KeyError, TypeError) as exc:
    st.error(str(exc))
    st.caption("이미 저장한 문헌·실행·검토 기록은 프로젝트 폴더에 남아 있습니다. 왼쪽에서 다른 단계를 고르면 계속할 수 있습니다.")
