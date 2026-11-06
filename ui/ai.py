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
    # Saved request/response files are the authority after a refresh or app restart.
    incomplete = {}
    for run_id in project.runs():
        run = flow.manifest(project, run_id)
        total = len(run["requests"])
        done = sum((project.run_dir(run_id) / "responses" / (item["source_id"] + ".json")).exists()
                   for item in run["requests"])
        if total and done < total:
            incomplete[run_id] = {"run": run, "done": done, "total": total}
    options = ["new", *incomplete]
    next_run = st.session_state.pop("wb_api_select_next", None)
    if next_run in incomplete:
        st.session_state["wb_api_choice"] = next_run
    elif st.session_state.get("wb_api_choice") not in options:
        previous = st.session_state.get("wb_api_pending")
        st.session_state["wb_api_choice"] = previous if previous in incomplete else (None if incomplete else "new")
    def choice_label(value):
        if value == "new":
            return "새 실행 · 현재 조사 설정과 포함 문헌"
        saved = incomplete[value]
        run = saved["run"]
        return f"이어 하기 · {ui.local_time(run['created_at'])} · {saved['done']}/{saved['total']}편 완료 · {ui.short(run['config']['plan']['question'], 50)}"
    selection = st.selectbox("API로 진행할 작업", options, index=None, key="wb_api_choice", format_func=choice_label,
                             placeholder="새 실행 또는 저장된 실행을 선택하세요")
    resume = selection if selection in incomplete else None
    if incomplete:
        st.caption("저장된 미완료 실행을 선택하면 이미 받은 응답은 다시 요청하지 않습니다. 다른 AI 경로에서 만든 실행도 이어갈 수 있습니다.")
    if resume:
        saved = incomplete[resume]
        run = saved["run"]
        st.markdown("**선택한 실행의 질문** · " + ui.md(run["config"]["plan"]["question"]))
        st.caption(f"{ui.local_time(run['created_at'])} 저장 · 완료 {saved['done']}편 / 전체 {saved['total']}편 · "
                   f"이번 전송 {saved['total'] - saved['done']}편. 당시의 질문·비교 항목·읽기 범위를 사용합니다.")
        current_ids = {s["id"] for s in project.catalog() if s["decision"] == "include"}
        if run["config"] != project.config() or current_ids != {s["id"] for s in run["sources"]}:
            st.info("현재 조사 설정 또는 포함 문헌이 이 실행과 다릅니다. 이어 하기는 아래에 보이는 저장 당시의 문헌과 설정을 사용합니다. 현재 기준을 쓰려면 새 실행을 선택하세요.")
        with st.expander("이 실행의 문헌·비교 항목 확인"):
            for source in run["sources"]:
                done = (project.run_dir(resume) / "responses" / (source["id"] + ".json")).exists()
                st.caption(("완료 · " if done else "남음 · ") + ui.md(source["title"]))
            st.caption("비교 항목 · " + " · ".join(ui.md(f["name"]) for f in run["config"]["fields"]))
            pages = run["config"]["plan"].get("max_pages_per_document", 20)
            st.caption("읽기 범위 · " + (f"문헌당 처음 {pages}쪽" if pages else "문헌 전체"))
    error = st.session_state.get("wb_api_error")
    if error and error["run_id"] == resume:
        st.error(ui.md(error["message"]))
    label = "남은 문헌 API 추출 이어 하기" if resume else ("새 실행으로 원문 전송·추출" if selection == "new" else "API 추출 실행")
    if st.button(label, key="wb_api_extract", disabled=selection is None):
        run_id = resume
        try:
            run_id = resume or flow.prepare(project)
            st.session_state["wb_api_pending"] = run_id
            with st.spinner("문헌별로 추출하는 중 · 완료된 응답은 저장됩니다"):
                extract_with_api(project, run_id)
        except ValueError as exc:
            if run_id:
                st.session_state["wb_api_select_next"] = run_id
                st.session_state["wb_api_error"] = {"run_id": run_id, "message": str(exc)}
                st.rerun()
            st.error(ui.md(str(exc)))
        else:
            st.session_state.pop("wb_api_pending", None)
            st.session_state.pop("wb_api_error", None)
            st.session_state["wb_route_run"] = run_id
            st.session_state["wb_route"] = "근거 비교"
            st.session_state["flash"] = "추출을 마쳤습니다. 원문을 확인한 뒤 채택하세요."
            st.rerun()
