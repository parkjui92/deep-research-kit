"""Optional configured API, with the data destination visible before execution."""
import os
from urllib.parse import urlsplit

import streamlit as st

from deep_research import workflow as flow
from deep_research.providers import extract_with_api

from . import chrome as ui


def api_extraction(project):
    base, model = os.environ.get("DRK_API_BASE", ""), os.environ.get("DRK_MODEL", "")
    if not base or not model:
        st.info("연결된 API가 없습니다. 원문 검색·독서 노트는 연결 없이 사용할 수 있습니다.")
        st.caption("앱 실행 환경에 DRK_API_BASE·DRK_MODEL·필요 시 DRK_API_KEY를 설정합니다. Chat Completions와 JSON 응답을 지원하는 서버가 필요합니다. 설정 방법은 README의 ‘선택 API’를 참고하세요.")
        return
    try:
        host = urlsplit(base).hostname
    except ValueError:
        st.error("API 주소 형식을 확인하세요.")
        return
    local = host in {"localhost", "127.0.0.1", "::1"}
    st.markdown(f"**{'로컬 주소' if local else '외부 주소'}에 연결** · {ui.md(host or '주소 확인 필요')} · 모델 {ui.md(model)}")
    st.caption("이 주소로 지정한 원문과 조사 설정을 보냅니다. 로컬 주소라도 서버가 외부로 중계하는지는 해당 서버 설정을 확인하세요. 모델 설치·서버별 호환성은 자동으로 확인하지 않습니다. 외부 API 비용은 별도입니다.")
    resume = st.session_state.get("wb_api_pending")
    if resume and resume not in project.runs():
        st.session_state.pop("wb_api_pending", None)
        resume = None
    if resume:
        st.caption("미완료 실행을 이어갑니다. 이미 받은 문헌의 응답은 보존하며, 이 실행을 만든 당시의 조사 설정을 사용합니다.")
    if st.button("남은 문헌 API 추출 이어 하기" if resume else "이 API로 원문 전송·추출", key="wb_api_extract"):
        try:
            run_id = resume or flow.prepare(project)
            st.session_state["wb_api_pending"] = run_id
            with st.spinner("문헌별로 추출하는 중 · 완료된 응답은 저장됩니다"):
                extract_with_api(project, run_id)
        except ValueError as exc:
            st.error(ui.md(str(exc)))
        else:
            st.session_state.pop("wb_api_pending", None)
            st.session_state["wb_route_run"] = run_id
            st.session_state["wb_route"] = "근거 비교"
            st.session_state["flash"] = "추출을 마쳤습니다. 원문을 확인한 뒤 채택하세요."
            st.rerun()
