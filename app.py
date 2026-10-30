"""Local review desk. All persistent operations use the same core as the skill/CLI."""
from pathlib import Path

import streamlit as st

from deep_research.project import Project, read_json, safe_id
from ui import chrome as ui
from ui.pages import PAGES
from ui.workbench import workbench

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
    st.session_state["project_name"] = folder
    remember(folder)
    if with_table:
        st.session_state["mode"] = "작업 화면"
        st.session_state["flash"] = "논문 3편의 비교표입니다. 값을 누르면 오른쪽에 원문이 열립니다. 이상한 값 하나를 원문에서 확인해 고쳐 보고, 「항목 추가」로 비교 항목을 하나 더해 보세요."
    else:
        st.session_state["stage_value"] = ui.STAGES[1]
        st.session_state["flash"] = "논문 3편을 등록했습니다. 제목과 PDF를 확인하고 포함·제외를 판단하세요. AI 추출(3단계)은 Claude Code가 있으면 직접, 없으면 「수업용 예시 응답」으로 할 수 있습니다."
    st.rerun()


def sidebar(existing):
    st.sidebar.markdown('<div class="drk-brand">DEEP RESEARCH KIT</div><div class="drk-brand-sub">근거 검토실</div>',
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
            make_example(safe_id(name), title, with_table=False)
    if not existing:
        return None
    if "project_name" not in st.session_state:
        wanted = st.query_params.get("project") or (LAST.read_text(encoding="utf-8").strip() if LAST.exists() else "")
        st.session_state["project_name"] = wanted if wanted in existing else existing[0]
    name = st.sidebar.selectbox("프로젝트", existing, key="project_name")
    st.query_params["project"] = name
    remember(name)
    project = Project(PROJECTS / name)
    if "mode_pick" not in st.session_state:
        st.session_state["mode_pick"] = st.session_state.get("mode", "작업 화면")
    mode = st.sidebar.segmented_control("보기", ["작업 화면", "단계별(학습)"], key="mode_pick",
                                        help="작업 화면 = 비교표와 원문을 바로 보며 일합니다. 단계별 = 조사 설계부터 한 단계씩 따라갑니다(수업용).")
    st.session_state["mode"] = mode or st.session_state.get("mode", "작업 화면")
    if st.session_state["mode"] == "작업 화면":
        st.sidebar.caption(f"폴더 `{name}` · AI 실행은 Claude Code가 있으면 바로, 없으면 요청문 복사 또는 예제 응답")
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
        st.markdown('<div class="drk-wordmark" style="font-size:1.1rem;margin-top:.5rem">Deep Research Kit</div>', unsafe_allow_html=True)
        st.title("여러 논문을 내 질문에 맞는 비교표로 정리하세요.")
        st.markdown('<div class="drk-lead" style="font-size:1.1rem">필요한 항목을 자동 추출하고, 원문을 확인해 고치고, 인용과 함께 가져가세요. '
                    'AI 실행은 Claude Code(앤트로픽의 터미널 도구)를 앱이 직접 부르거나, 수업용 예제 응답으로 합니다. 소프트웨어는 무료입니다.</div>',
                    unsafe_allow_html=True)
        a, b = st.columns(2)
        if a.button("내 문헌으로 시작", type="primary", width="stretch"):
            Project(PROJECTS / "my-research").initialize("나의 문헌조사")
            st.session_state["project_name"] = "my-research"
            remember("my-research")
            st.session_state["mode"] = "작업 화면"
            st.session_state["flash"] = "빈 프로젝트를 만들었습니다. 「문헌 찾기」로 검색해 담거나 「PDF 가져오기」로 올린 뒤 「AI로 추출」을 누르세요."
            st.rerun()
        if b.button("논문 3편 예제 체험 · 바로 비교표 보기", width="stretch"):
            make_example("class-example", "AI와 지식업무 · 논문 3편 예제", with_table=True)
        for column, (head, body) in zip(st.columns(3), [
                ("내가 정한 항목으로 여러 논문을 한 번에 비교", "대상·방법·결과·한계 같은 항목을 정하면 AI가 문헌마다 값을 뽑아 표로 놓습니다."),
                ("표의 값을 누르면 원문이 열리고, 수정한 판단이 남는다", "AI가 값을 뽑아낸 문장이 PDF에 표시됩니다. 채택·수정·보류가 기록으로 남고 채택한 값만 결과에 들어갑니다."),
                ("논문·항목을 추가해도 기록은 보존", "실행마다 기준과 값이 보존되고 전후를 비교합니다. 바뀐 부분만 다시 처리하는 기능은 다음 판의 목표입니다.")]):
            with column, st.container(border=True):
                st.markdown(f"**{head}**")
                st.caption(body)
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
