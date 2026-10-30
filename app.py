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


LAST = PROJECTS / ".last-project"


def remember(name: str):
    try:
        LAST.write_text(name, encoding="utf-8")
    except OSError:
        pass


def sidebar(existing):
    st.sidebar.markdown('<div class="drk-brand">DEEP RESEARCH KIT</div><div class="drk-brand-sub">근거 검토실 · AI가 PDF에서 뽑은 값을 사람이 원문으로 확인하는 문헌조사 도구</div>',
                        unsafe_allow_html=True)
    with st.sidebar.expander("프로젝트 만들기", expanded=not existing):
        name = st.text_input("폴더 이름 · 영문·숫자·하이픈", "my-research")
        title = st.text_input("프로젝트 제목", "나의 문헌조사", help="공통 사례도 여기 적은 제목으로 만들어집니다.")
        if st.button("빈 프로젝트 만들기", width="stretch"):
            Project(PROJECTS / safe_id(name)).initialize(title)
            st.session_state["project_name"] = safe_id(name)
            remember(safe_id(name))
            st.session_state["flash"] = "빈 프로젝트를 만들었습니다. 1단계에서 조사 질문과 기준을 적고, 2단계에서 PDF를 등록하세요."
            st.rerun()
        if st.button("공통 사례 만들기 · 실제 논문 3편 내려받음", width="stretch", help="약 20초 걸립니다. 수업용 공통 문헌 3편을 등록합니다."):
            from deep_research.examples import create_example
            target = PROJECTS / safe_id(name)
            with st.spinner("실제 논문 3편을 공식 자료원에서 내려받아 등록하는 중 · 약 20초"):
                create_example(target, title=title)
            st.session_state["project_name"] = safe_id(name)
            remember(safe_id(name))
            st.session_state["stage_value"] = ui.STAGES[1]
            st.session_state["flash"] = "논문 3편을 등록했습니다. 제목과 PDF를 확인하고 포함·제외를 판단하세요. AI 추출(3단계)은 Claude Code가 있으면 직접, 없으면 「수업용 예시 응답」으로 할 수 있습니다."
            st.rerun()
    if not existing:
        return None
    if "project_name" not in st.session_state:
        wanted = st.query_params.get("project") or (LAST.read_text(encoding="utf-8").strip() if LAST.exists() else "")
        st.session_state["project_name"] = wanted if wanted in existing else existing[0]
    name = st.sidebar.selectbox("프로젝트", existing, key="project_name")
    st.query_params["project"] = name
    remember(name)
    project = Project(PROJECTS / name)
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
        st.title("AI가 뽑은 값을, 사람이 원문으로 확인하는 문헌조사")
        st.markdown('<div class="drk-lead">조사 기준을 정하고 PDF를 모으면, AI가 문헌마다 값을 뽑고 그 자리를 PDF에 표시합니다. '
                    '사람이 원문을 읽고 채택한 근거만 종합과 보고서에 남습니다. AI 실행은 Claude Code(앤트로픽의 터미널 도구) 또는 수업용 예시 응답으로 합니다.</div>',
                    unsafe_allow_html=True)
        ui.empty("아직 프로젝트가 없습니다.", "왼쪽 「프로젝트 만들기」에서 시작하세요. 수업이라면 「공통 사례 만들기 · 실제 논문 3편」을 누르면 됩니다.")
        for column, step in zip(st.columns(6), ui.STAGES):
            with column:
                with st.container(border=True):
                    st.markdown(f"**{step}**")
                    st.caption(ui.STAGE_HINT[step])
        return
    title = read_json(project.root / "project.json")["title"]
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
    st.caption("이미 저장한 문헌·실행·검토 기록은 프로젝트 폴더에 남아 있습니다. 왼쪽에서 다른 단계를 고르면 계속할 수 있습니다.")
