"""Start with a research question or documents, without asking for an internal folder name."""
import uuid

import streamlit as st

from deep_research.project import Project


def start_page(projects, make_example):
    st.markdown('<div class="drk-wordmark">Deep Research Kit</div>', unsafe_allow_html=True)
    st.title("주제에 맞는 문헌을 찾고, 보고서에 쓸 근거로 정리하세요.")
    st.markdown("읽을 문헌을 고르는 순간부터, 인용할 내용을 원문에서 확인하는 순간까지.")
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.subheader("주제로 문헌 찾기")
        st.caption("학술 자료원을 검색하고, 먼저 읽을 이유와 후보를 저장합니다.")
        if st.button("조사 질문에서 시작", type="primary", width="stretch"):
            st.session_state["start_path"] = "문헌 검색"
    with b, st.container(border=True):
        st.subheader("내 문헌 비교하기")
        st.caption("PDF를 가져와 원문을 찾고 메모합니다. AI 추출은 선택할 수 있습니다.")
        if st.button("PDF에서 시작", width="stretch"):
            st.session_state["start_path"] = "내 PDF"
    path = st.session_state.get("start_path")
    if path:
        with st.form("start_research"):
            question = st.text_input("이번에 알아볼 질문", placeholder="예: 생성형 AI가 지식업무의 생산성에 미치는 영향은?")
            title = st.text_input("조사 제목 (선택)", placeholder="비워 두면 질문을 제목으로 사용합니다.")
            if st.form_submit_button("문헌 검색 시작" if path == "문헌 검색" else "PDF 가져오기로 이동", type="primary"):
                if not question.strip():
                    st.error("이번 조사 질문을 입력하세요.")
                else:
                    name = "research-" + uuid.uuid4().hex[:10]
                    Project(projects / name).initialize(title.strip() or question.strip()[:70], question=question)
                    st.session_state["open_project"] = name
                    st.session_state["start_destination"] = path
                    st.session_state["mode"] = "작업 화면"
                    st.rerun()
    st.markdown("**문헌 모으기 → 근거 비교 → 보고서에 쓰기**")
    st.caption("PDF·노트·검토 기록은 앱이 실행되는 컴퓨터에 저장됩니다. 외부 검색에는 검색어가, AI 실행에는 지정한 원문이 전달됩니다.")
    with st.expander("예제로 살펴보기 · 비용과 데이터 안내"):
        st.write("자료 등록·원문 검색·독서 노트·내보내기는 AI 없이 사용할 수 있습니다. 외부 검색 자료원의 한도와 AI 제공자의 비용·이용 조건은 별도입니다.")
        if st.button("논문 3편 예제 체험 · 바로 비교표 보기", width="stretch"):
            make_example("example-" + uuid.uuid4().hex[:8], "AI와 지식업무 · 논문 3편 예제", with_table=True)
