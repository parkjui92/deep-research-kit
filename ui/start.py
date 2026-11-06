"""Start with a research question or documents, without asking for an internal folder name."""
import uuid

import streamlit as st

from deep_research.project import Project, read_json

from . import chrome as ui
from .onboarding import start_help


def is_example(root):
    """Existing examples and interrupted UI example downloads share this label."""
    return (root / "example-manifest.json").exists() or (root / "example-origin.json").exists()


def _resume(projects, names, *, example=False):
    if not names:
        return
    key = "start_example" if example else "start_resume"
    if st.session_state.get(key) not in names:
        st.session_state[key] = None
    metadata = {name: read_json(projects / name / "project.json") for name in names}
    chosen = st.selectbox("저장된 예시" if example else "이어서 볼 내 조사", names, index=None,
                          key=key, placeholder="예시를 선택하세요" if example else "조사를 선택하세요",
                          format_func=lambda name: metadata[name]["title"] + " · "
                          + ui.local_time(metadata[name]["created_at"]))
    if st.button("선택한 예시 열기" if example else "내 조사 이어하기", key=key + "_go",
                 disabled=not chosen, width="stretch"):
        st.session_state["open_project"] = chosen
        st.session_state.pop("start_path", None)
        st.rerun()


def start_page(projects, make_example):
    st.markdown('<div class="drk-wordmark">Deep Research Kit</div>', unsafe_allow_html=True)
    st.title("주제에 맞는 문헌을 찾고, 보고서에 쓸 근거로 정리하세요.", anchor=False)
    if st.session_state.pop("scroll_top", False):
        ui.scroll_top(focus_main=True)
    st.markdown("읽을 문헌을 고르는 순간부터, 인용할 내용을 원문에서 확인하는 순간까지.")
    existing = sorted(path.name for path in projects.iterdir() if (path / "project.json").exists())
    examples = [name for name in existing if is_example(projects / name)]
    mine = [name for name in existing if name not in examples]
    st.header("내 조사 이어하기", anchor=False)
    if mine:
        _resume(projects, mine)
    else:
        st.caption("아직 직접 시작한 조사가 없습니다. 아래에서 질문이나 PDF로 시작하세요.")
    st.header("새 조사 시작", anchor=False)
    focus_question = False
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.subheader("주제로 문헌 찾기", anchor=False)
        st.caption("학술 자료원을 검색하고, 먼저 읽을 이유와 후보를 저장합니다.")
        if st.button("조사 질문에서 시작", type="primary", width="stretch"):
            st.session_state["start_path"] = "문헌 검색"
            focus_question = True
    with b, st.container(border=True):
        st.subheader("내 문헌 비교하기", anchor=False)
        st.caption("PDF를 가져와 원문을 찾고 메모합니다. AI 추출은 선택할 수 있습니다.")
        if st.button("PDF에서 시작", width="stretch"):
            st.session_state["start_path"] = "내 PDF"
            focus_question = True
    path = st.session_state.get("start_path")
    if path:
        st.header("조사 질문 입력", anchor=False)
        with st.form("start_research"):
            question = st.text_input("이번에 알아볼 질문", placeholder="예: 생성형 AI가 지식업무의 생산성에 미치는 영향은?")
            title = st.text_input("조사 제목 (선택)", placeholder="비워 두면 질문을 제목으로 사용합니다.")
            st.caption("질문이 넓으면 엉뚱한 문헌이 많이 섞입니다. 아는 만큼만 좁혀 주세요. 대상·분야·검색어는 비워도 됩니다.")
            a, b = st.columns(2)
            target = a.text_input("대상·맥락 (선택)", placeholder="예: 공공기관 사무직 / 국내 중소기업")
            field = b.text_input("분야·학문 (선택)", placeholder="예: 행정학 / 노동경제학")
            a, b = st.columns([3, 1])
            keywords = a.text_input("검색어 (선택 · 영문 권장)", placeholder="예: generative AI knowledge work productivity",
                                    help="학술 자료원은 영문 논문이 대부분입니다. 비우면 질문을 그대로 검색어로 넣습니다.")
            since = b.number_input("발행연도 이후 (0=전체)", 0, 2100, 0)
            if st.form_submit_button("문헌 검색 시작" if path == "문헌 검색" else "PDF 가져오기로 이동", type="primary"):
                if not question.strip():
                    st.error("이번 조사 질문을 입력하세요.")
                    focus_question = True
                else:
                    name = "research-" + uuid.uuid4().hex[:10]
                    project = Project(projects / name).initialize(title.strip() or question.strip()[:70], question=question)
                    scope = " · ".join(f"{label}: {value.strip()}" for label, value in
                                       (("대상·맥락", target), ("분야", field), ("발행연도", f"{since}년 이후" if since else ""))
                                       if value.strip())
                    if scope:
                        config = project.config()
                        project.save_config({**config["plan"], "scope": scope}, config["fields"], config["synthesis_rules"])
                    st.session_state["open_project"] = name
                    st.session_state["start_destination"] = path
                    st.session_state["start_query"] = keywords.strip()
                    st.session_state["start_year"] = int(since or 0)
                    st.session_state["mode"] = st.session_state["mode_pick"] = "작업 화면"
                    st.rerun()
        if focus_question:
            ui.focus_after_render('[data-testid="stForm"] input')
    start_help()
    st.caption("PDF·노트·검토 기록은 앱이 실행되는 컴퓨터에 저장됩니다. 외부 검색에는 검색어가, AI 실행에는 지정한 원문이 전달됩니다.")
    with st.expander("예시 체험 · 내 조사와 별도"):
        st.caption("예시는 사용자가 선택할 때만 열립니다. 저장된 연습 기록은 아래에서 다시 열 수 있습니다.")
        _resume(projects, examples, example=True)
        st.write("자료 등록·원문 검색·독서 노트·내보내기는 AI 없이 사용할 수 있습니다. 외부 검색 자료원의 한도와 AI 제공자의 비용·이용 조건은 별도입니다.")
        st.caption("새 예시 체험은 공개 논문 PDF를 내려받고 별도의 연습 조사를 만듭니다. 자동으로 AI를 실행하지 않습니다.")
        if st.button("논문 3편 예제 체험 · 바로 비교표 보기", key="start_example_new", width="stretch"):
            make_example("example-" + uuid.uuid4().hex[:8], "AI와 지식업무 · 논문 3편 예제", with_table=True)
