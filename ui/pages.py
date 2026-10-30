"""The six stages. Every persistent operation goes through deep_research; pages only arrange and explain."""
from __future__ import annotations

import json

import streamlit as st
import yaml

from deep_research import workflow as flow
from deep_research.exports import compare, export_zip, matrix, report
from deep_research.project import read_json

from . import chrome as ui

DECISION_CHOICES = {"include": "포함", "exclude": "제외", "pending": "보류"}
REVIEW_CHOICES = {"accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외"}
REVIEW_FILTERS = {"all": "전체", "pending": "미검토", "kept": "채택", "parked": "보류·제외"}


def _run_picker(project, key: str):
    runs = project.runs()
    if not runs:
        ui.empty("아직 실행이 없습니다.", "문헌을 선별한 뒤 ‘3 · 원문 추출’에서 「새 추출 실행 만들기」를 누르세요.")
        return None
    return st.selectbox("실행 기록", runs, key=key, format_func=lambda r: _run_label(project, r))


def _run_label(project, run_id: str) -> str:
    run = flow.manifest(project, run_id)
    return f"{run_id} · {ui.word(ui.RUN_STATE, run['state'])} · {run['created_at'][:16].replace('T', ' ')}"


def plan_page(project):
    config = project.config()
    plan = config["plan"]
    ui.header("무엇을, 어떤 기준으로 조사할까요?",
              "질문·범위·포함 기준·추출 항목을 정합니다. 여기서 바꾼 기준은 다음 실행부터 적용되고, 실행마다 그때의 기준이 함께 저장됩니다.",
              [("추출 항목", len(config["fields"])), ("문헌당 읽을 쪽수", plan.get("max_pages_per_document", 20) or "전체"),
               ("한 실행의 문헌 상한", plan["max_documents"])])
    with st.form("plan-" + str(project.root)):
        st.markdown("**조사 질문과 범위**")
        question = st.text_input("조사 질문", plan["question"])
        purpose = st.text_area("조사 목적", plan.get("purpose", ""), height=85)
        scope = st.text_area("대상과 범위", plan.get("scope", ""), height=85)
        a, b = st.columns(2)
        inclusion = a.text_area("포함 기준", plan.get("inclusion", ""))
        exclusion = b.text_area("제외 기준", plan.get("exclusion", ""))
        st.markdown("**실행 범위**")
        a, b = st.columns(2)
        limit = a.number_input("한 실행에서 다룰 문헌 수 상한", 1, 100, plan["max_documents"])
        page_limit = b.number_input("문헌당 처음부터 읽을 PDF 쪽수 · 0은 전체", 0, 1000, plan.get("max_pages_per_document", 20))
        st.caption("기본은 첫 20쪽입니다. 긴 부록까지 읽으려면 0을 지정하세요. 읽은 범위는 근거와 보고서에 표시됩니다.")
        output = st.text_input("결과 형태", plan.get("output", ""))
        st.markdown("**추출 항목** — 항목 이름이 아니라 지침이 AI가 가져올 것을 정합니다. 한 항목의 지침을 바꾸고 새 실행과 비교해 보세요.")
        fields = st.data_editor(config["fields"], num_rows="dynamic", width="stretch", key="fields-" + str(project.root),
                                column_config={"id": st.column_config.TextColumn("id", help="영문·숫자·하이픈", width="small"),
                                               "name": st.column_config.TextColumn("이름", width="medium"),
                                               "instruction": st.column_config.TextColumn("추출 지침", width="large")})
        rules = st.text_area("종합 지침", config["synthesis_rules"], height=150)
        if st.form_submit_button("설계 저장", type="primary"):
            project.save_config({"question": question, "purpose": purpose, "scope": scope,
                                 "inclusion": inclusion, "exclusion": exclusion,
                                 "max_documents": int(limit), "max_pages_per_document": int(page_limit), "output": output}, fields, rules)
            st.success("설계를 저장했습니다. 질문·범위·선별 기준이 바뀌었다면 문헌 선별을 다시 확인하세요.")
    with st.expander("뜯어보기 · 실제 설정 파일"):
        st.code(str(project.root / "research-plan.yaml"))
        st.code(yaml.safe_dump(project.config(), allow_unicode=True, sort_keys=False), language="yaml")
        st.caption("config/extraction-fields.yaml, config/synthesis-rules.md도 직접 수정할 수 있습니다. UI와 스킬이 같은 파일을 읽습니다.")


def sources_page(project):
    sources = project.catalog()
    stale = [s for s in sources if s["decision"] != "pending" and s.get("criteria_hash") != project.criteria_hash()]
    ui.header("문헌을 모으고 선별 이유를 남깁니다",
              "직접 확보한 PDF를 등록하고, 원문을 보면서 포함·제외·보류와 그 이유를 기록합니다. 같은 연구의 여러 보고서는 같은 연구 ID로 묶습니다.",
              [("등록 문헌", len(sources)), ("포함", sum(s["decision"] == "include" for s in sources)),
               ("제외", sum(s["decision"] == "exclude" for s in sources)),
               ("보류·미판단", sum(s["decision"] == "pending" for s in sources)),
               ("재확인 필요", len(stale), "조사 질문·기준이 바뀐 뒤 아직 다시 저장하지 않은 판단")])
    with st.expander("PDF 등록", expanded=not sources):
        files = st.file_uploader("직접 확보한 원문 PDF", type="pdf", accept_multiple_files=True)
        if st.button("선택한 PDF 등록", disabled=not files):
            for file in files:
                with st.spinner(file.name + " 색인 중"):
                    project.add_pdf(file.getvalue(), file.name)
            st.success("등록했습니다. 같은 파일은 중복 등록되지 않습니다.")
    with st.expander("학술 자료 찾기 · Crossref"):
        st.caption("서지정보 탐색입니다. 원문 전문 검색이나 체계적 문헌고찰의 포괄성을 보장하지 않습니다.")
        query = st.text_input("검색어")
        if st.button("검색하고 기록 남기기"):
            from deep_research.providers import crossref_search
            st.session_state["search_results"] = crossref_search(project, query)
        if st.session_state.get("search_results"):
            st.dataframe(st.session_state["search_results"], width="stretch")
    if not sources:
        ui.empty("등록된 문헌이 없습니다.", "위의 「PDF 등록」으로 원문을 올리거나, 왼쪽 「프로젝트 만들기」에서 공통 사례를 준비하세요.")
        return
    st.dataframe([{"문헌": s["title"], "선별": ui.word(ui.DECISION, s["decision"]), "연구 ID": s["study_id"],
                   "쪽수": s["page_count"], "텍스트 쪽": s["text_pages"],
                   "기준 재확인": "필요" if s in stale else "-"} for s in sources],
                 hide_index=True, width="stretch",
                 column_config={"문헌": st.column_config.TextColumn(width="large"),
                                "쪽수": st.column_config.NumberColumn(format="%d"),
                                "텍스트 쪽": st.column_config.NumberColumn(format="%d")})
    source_id = st.selectbox("검토할 문헌", [s["id"] for s in sources],
                             format_func=lambda sid: f"{ui.short(project.source(sid)['title'], 70)} · {ui.word(ui.DECISION, project.source(sid)['decision'])}")
    source = project.source(source_id)
    left, right = st.columns([1, 1.8], gap="large")
    with left:
        with st.container(border=True):
            ui.badge(ui.DECISION, source["decision"])
            with st.form("screen-" + source_id):
                title = st.text_input("문헌 제목", source["title"])
                doi = st.text_input("DOI · 선택", source["doi"])
                url = st.text_input("출처 주소 · 선택", source["url"])
                study_id = st.text_input("연구 ID", source["study_id"], help="같은 연구의 사전공개본·출판본은 같은 연구 ID를 지정하세요.")
                decision = st.radio("선별 판단", list(DECISION_CHOICES), index=list(DECISION_CHOICES).index(source["decision"]),
                                    format_func=DECISION_CHOICES.get, horizontal=True)
                reason = st.text_area("판단 이유", source["reason"], help="포함·제외 기준 중 어느 것에 어떻게 해당하는지 적습니다.")
                if st.form_submit_button("선별 저장", type="primary"):
                    try:
                        project.screen(source_id, decision, reason, study_id, title, doi, url)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["flash"] = "선별을 저장했습니다."
                        st.rerun()
        if source in stale:
            st.warning("조사 질문·기준이 바뀐 뒤의 판단이 아닙니다. 현재 기준으로 다시 확인하고 저장하세요.")
        if source["text_pages"] < source["page_count"]:
            st.warning(f"텍스트가 없는 쪽이 {source['page_count'] - source['text_pages']}쪽 있습니다. 스캔 문서는 이 버전에서 자동 추출할 수 없습니다.")
        page = st.number_input("미리 볼 PDF 쪽", 1, max(1, source["page_count"]), 1)
    with right:
        ui.show_pdf(project, source_id, page=int(page))


def extraction_page(project):
    runs = project.runs()
    latest = flow.manifest(project, runs[0]) if runs else None
    ui.header("지금의 기준으로 원문을 다시 읽습니다",
              "새 실행은 설계와 문헌 목록을 그 시점에 고정합니다. 이전 실행과 검토 기록은 그대로 남아 비교 기준이 됩니다.",
              [("실행", len(runs)),
               ("최근 실행 상태", ui.word(ui.RUN_STATE, latest["state"]) if latest else "-"),
               ("최근 실행 응답", f"{sum((project.run_dir(runs[0]) / 'responses' / (r['source_id'] + '.json')).exists() for r in latest['requests'])}/{len(latest['requests'])}" if latest else "-")])
    a, b = st.columns([1, 2], gap="large")
    with a:
        if st.button("새 추출 실행 만들기", type="primary", width="stretch"):
            try:
                run_id = flow.prepare(project)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["extract_run"] = run_id
                st.session_state["flash"] = f"원문에서 새 요청을 만들었습니다 · {run_id}"
                st.rerun()
    with b:
        with st.expander("공통 사례 · 사전 작성 예시로 구조 살펴보기"):
            st.caption("새 AI 실행이 아닙니다. 같은 원본·기본 설계에서만 불러오며, 모든 근거는 미검토 상태로 들어옵니다.")
            if st.button("기준 추출 예시 불러오기"):
                from deep_research.examples import load_reference
                try:
                    st.session_state["extract_run"] = load_reference(project)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.rerun()
    run_id = _run_picker(project, "extract_run")
    if not run_id:
        return
    folder = project.run_dir(run_id)
    run = flow.manifest(project, run_id)
    with st.container(border=True):
        ui.badge(ui.RUN_STATE, run["state"])
        st.markdown(f"**실행 `{run_id}`** · 시작 {run['created_at'][:19].replace('T', ' ')} UTC · "
                    f"문헌 {len(run['requests'])}건 · 읽기 범위 문헌당 첫 {run['config']['plan'].get('max_pages_per_document', 20) or '전체'}쪽")
        st.markdown("**기본 실행 · Claude Code에서 이 저장소를 열고 다음 요청을 붙여 넣으세요.**")
        st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {run_id}\nrequests/의 원문을 읽고 모든 문헌을 추출해 import-extraction으로 가져와 줘. 사람의 검토 상태는 바꾸지 마.")
        st.caption("스킬은 AI 모델을 이용합니다. 별도 API 키 없이 기존 Claude Code 세션에서 실행할 수 있으며 해당 서비스의 사용량이 적용됩니다.")
        for req in run["requests"]:
            imported = (folder / "responses" / (req["source_id"] + ".json")).exists()
            request = read_json(folder / "requests" / (req["source_id"] + ".json"))
            with st.expander(("✓ 응답 있음 · " if imported else "○ 응답 대기 · ") + ui.short(project.source(req["source_id"])["title"], 80)):
                st.caption(f"원문 구간 {len(request['passages'])}개 · 요청 ID `{req['request_id']}`")
                for warning in request["warnings"]:
                    st.warning(warning)
                st.download_button("요청 JSON", json.dumps(request, ensure_ascii=False, indent=2), req["source_id"] + "-request.json", key="req-" + req["request_id"])
    a, b = st.columns(2, gap="large")
    with a:
        with st.expander("응답 파일 직접 가져오기"):
            responses = st.file_uploader("모델이 작성한 응답 JSON", type="json", accept_multiple_files=True)
            if st.button("원문과 대조하여 가져오기", disabled=not responses):
                for file in responses:
                    flow.import_extraction(project, run_id, json.loads(file.getvalue()))
                st.rerun()
    with b:
        with st.expander("선택 · 직접 API로 실행"):
            st.caption("DRK_API_BASE, DRK_MODEL, 필요시 DRK_API_KEY 환경변수를 설정합니다. 포함 문헌의 텍스트가 해당 서버로 전송됩니다.")
            consent = st.checkbox("선택한 API 서버에 이 문헌 텍스트를 전송합니다.")
            if st.button("API 추출 실행 / 이어서 실행", disabled=not consent):
                from deep_research.providers import extract_with_api
                with st.spinner("문헌별 추출 중 · 완료한 문헌은 저장됩니다"):
                    extract_with_api(project, run_id)
                st.rerun()
    if st.button("저장된 응답 새로 읽기", icon=":material/refresh:"):
        st.rerun()


def _filtered(rows, choice):
    if choice == "pending":
        return [r for r in rows if r["review"]["status"] == "pending"]
    if choice == "kept":
        return [r for r in rows if r["review"]["status"] in {"accept", "edit"}]
    if choice == "parked":
        return [r for r in rows if r["review"]["status"] in {"hold", "reject"}]
    return rows


def review_page(project):
    ui.header("추출값 옆에서 실제 원문을 확인합니다",
              "왼쪽은 AI가 낸 값과 발췌, 오른쪽은 그 자리가 표시된 원본 PDF입니다. 앞뒤 문맥을 읽고 채택·수정 후 채택·보류·제외를 이유와 함께 남깁니다.")
    run_id = _run_picker(project, "review_run")
    if not run_id:
        return
    rows = flow.evidence(project, run_id)
    if not rows:
        ui.empty("이 실행에는 아직 추출 응답이 없습니다.", "‘3 · 원문 추출’에서 스킬 요청을 실행하거나 응답 파일을 가져온 뒤 돌아오세요.")
        return
    fields = {f["id"]: f["name"] for f in flow.manifest(project, run_id)["config"]["fields"]}
    counts = {k: sum(r["review"]["status"] == k for r in rows) for k in ui.REVIEW}
    reviewed = len(rows) - counts["pending"]
    for column, (label, value) in zip(st.columns(4), [("근거", len(rows)), ("채택", counts["accept"] + counts["edit"]),
                                                      ("보류·제외", counts["hold"] + counts["reject"]), ("미검토", counts["pending"])]):
        column.metric(label, value, border=True)
    st.progress(reviewed / len(rows), text=f"검토 진행 {reviewed}/{len(rows)}")
    choice = st.segmented_control("보기", list(REVIEW_FILTERS), default="all", format_func=REVIEW_FILTERS.get,
                                  key="review_filter", label_visibility="collapsed") or "all"
    shown = _filtered(rows, choice)
    if not shown:
        ui.empty(f"‘{REVIEW_FILTERS[choice]}’에 해당하는 근거가 없습니다.", "다른 보기를 고르세요.")
        return
    ids = [r["id"] for r in shown]
    # "저장하고 다음": the previous save left the next pending evidence here before the widget existed.
    if (jump := st.session_state.pop("review_next", None)) in ids:
        st.session_state["review_pick"] = jump
    if st.session_state.get("review_pick") not in ids:
        st.session_state["review_pick"] = ids[0]
    selected = st.selectbox("검토할 근거", ids, key="review_pick", format_func=lambda eid: next(
        f"{ui.short(project.source(r['source_id'])['title'], 44)} · {fields[r['field_id']]} · {ui.word(ui.REVIEW, r['review']['status'])}"
        for r in rows if r["id"] == eid))
    row = next(r for r in rows if r["id"] == selected)
    left, right = st.columns([1, 1.8], gap="large")
    with left:
        with st.container(border=True):
            a, b = st.columns(2)
            with a:
                ui.badge(ui.MATCH, row["match_status"])
            with b:
                ui.badge(ui.REVIEW, row["review"]["status"])
            st.markdown(f"**{fields[row['field_id']]}** · {ui.short(project.source(row['source_id'])['title'], 60)}")
            st.markdown("**AI 추출값**")
            st.markdown(f'<div class="drk-value">{row["value"] or "자료에서 찾지 못함"}</div>', unsafe_allow_html=True)
            if row["match_status"] == "matched":
                st.caption("발췌 문자열의 원문 위치를 찾았습니다. 위치가 맞다는 뜻이지 값이 옳다는 뜻은 아닙니다.")
            else:
                st.warning("원문 위치를 찾지 못했거나 미발견입니다. 채택할 수 없으며 보류·제외로 기록할 수 있습니다.")
            for locator in row["locators"]:
                joined = " · 줄끝 하이픈을 이어 대조" if locator.get("dehyphenated") else ""
                st.markdown(f'<div class="drk-quote">{locator["quote"]}</div>'
                            f'<div class="drk-meta">PDF {locator["page"]}쪽 · {locator["status"]}{joined}</div>', unsafe_allow_html=True)
            if row["note"]:
                st.caption("AI 메모 · " + row["note"])
            st.caption(f"근거 ID `{row['id']}` · 읽기 범위 PDF {row['page_scope']['from']}~{row['page_scope']['to']}쪽 / 전체 {row['page_scope']['total']}쪽")
        with st.container(border=True):
            st.markdown("**내 판단**")
            with st.form("review-" + run_id + selected):
                previous_status = row["review"]["status"] if row["review"]["status"] in REVIEW_CHOICES else "hold"
                status = st.radio("판정", list(REVIEW_CHOICES), index=list(REVIEW_CHOICES).index(previous_status),
                                  format_func=REVIEW_CHOICES.get, horizontal=True)
                value = st.text_area("수정 후 채택할 값", row["review"].get("edited_value") or row["value"] or "",
                                     help="‘수정 후 채택’일 때만 저장됩니다. 원래 AI 추출값은 그대로 보존됩니다.")
                note = st.text_area("판단 이유·조건·한계", row["review"].get("note", ""))
                reviewer = st.text_input("검토자", st.session_state.get("reviewer", ""))
                checked = st.checkbox("원문 문맥을 읽고 추출값을 뒷받침하는지 판단했습니다.")
                if st.form_submit_button("판단 저장", type="primary", help="저장하면 다음 미검토 근거로 이동합니다."):
                    # Keep the PDF on screen: report the problem next to the form instead of failing the page.
                    if status in {"accept", "edit"} and not checked:
                        st.error("채택하려면 ‘원문 문맥을 읽고 판단했습니다’에 표시하세요.")
                    else:
                        try:
                            flow.review(project, run_id, selected, status, note, reviewer, value)
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["reviewer"] = reviewer
                            pending_after = [r["id"] for r in rows if r["review"]["status"] == "pending" and r["id"] != selected]
                            st.session_state["review_next"] = pending_after[0] if pending_after else selected
                            st.session_state["flash"] = ("판단을 저장했습니다. 다음 미검토 근거로 이동했습니다." if pending_after
                                                         else "판단을 저장했습니다. 미검토 근거가 없습니다. ‘5 · 종합’으로 이동하세요.")
                            st.rerun()
            st.caption("저장하면 다음 미검토 근거로 이동합니다. 판단을 바꾸면 그 실행의 이전 종합은 만료되고, 원래 추출값과 검토 이력은 보존됩니다.")
    with right:
        if row["locators"]:
            pick = st.selectbox("보여줄 발췌", range(len(row["locators"])), format_func=lambda i: f"{i + 1} · PDF {row['locators'][i]['page']}쪽")
            locator = row["locators"][pick]
            ui.show_pdf(project, row["source_id"], [locator], page=locator["page"] or 1, identity=selected)
        else:
            ui.show_pdf(project, row["source_id"], identity=selected)


def synthesis_page(project):
    ui.header("채택한 근거만 연결해 답을 만듭니다",
              "미검토·보류·제외 근거는 종합에 들어가지 않습니다. 종합문은 AI 초안이며 주장마다 근거 ID가 붙습니다.")
    run_id = _run_picker(project, "synthesis_run")
    if not run_id:
        return
    rows = flow.evidence(project, run_id)
    approved = flow.accepted(project, run_id)
    current = flow.current_synthesis(project, run_id)
    for column, (label, value) in zip(st.columns(3), [("채택한 근거", len(approved)), ("미검토·보류·제외", len(rows) - len(approved)),
                                                      ("종합", "유효" if current else "없음·만료")]):
        column.metric(label, value, border=True)
    if not rows:
        ui.empty("이 실행에는 추출 응답이 없습니다.", "‘3 · 원문 추출’에서 응답을 가져온 뒤 돌아오세요.")
        return
    st.markdown("**문헌 × 항목 · 채택한 값만**")
    st.dataframe(matrix(project, run_id), width="stretch", hide_index=True)
    with st.container(border=True):
        if st.button("검토 결과로 종합 요청 만들기", type="primary", disabled=not approved):
            flow.prepare_synthesis(project, run_id)
            st.success("종합 요청을 저장했습니다. 아래 요청 문장을 Claude Code에 붙여 넣으세요.")
        if not approved:
            st.caption("채택한 근거가 하나 이상 있어야 종합을 요청할 수 있습니다.")
        request_path = project.run_dir(run_id) / "synthesis-request.json"
        if request_path.exists():
            st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {run_id}\nsynthesis-request.json의 채택 근거를 종합하고 import-synthesis로 가져와 줘.")
            a, b = st.columns(2, gap="large")
            with a:
                with st.expander("종합 JSON 직접 가져오기"):
                    response = st.file_uploader("종합 응답", type="json", key="synthesis_upload")
                    if st.button("종합 가져오기", disabled=response is None):
                        try:
                            flow.import_synthesis(project, run_id, json.loads(response.getvalue()))
                        except (ValueError, TypeError) as exc:
                            st.error(str(exc))
                        else:
                            st.rerun()
            with b:
                with st.expander("선택 · 직접 API 종합"):
                    consent = st.checkbox("채택 근거를 설정한 API 서버로 전송합니다.")
                    if st.button("API 종합 실행", disabled=not consent or not approved):
                        from deep_research.providers import synthesize_with_api
                        with st.spinner("채택 근거를 종합하고 있습니다"):
                            synthesize_with_api(project, run_id)
                        st.rerun()
        if st.button("종합 결과 새로 읽기", icon=":material/refresh:"):
            st.rerun()
    with st.container(border=True):
        # The report carries our own <a id> anchors for evidence links; nothing user-supplied is HTML.
        st.markdown(report(project, run_id), unsafe_allow_html=True)


def _config_changes(before: dict, after: dict) -> list[dict]:
    """Flatten two frozen configs into the lines that differ."""
    changes = []
    for key in sorted(set(before["plan"]) | set(after["plan"])):
        if before["plan"].get(key) != after["plan"].get(key):
            changes.append({"항목": f"설계 · {key}", "이전": before["plan"].get(key, "-"), "이후": after["plan"].get(key, "-")})
    left = {f["id"]: f for f in before["fields"]}
    right = {f["id"]: f for f in after["fields"]}
    for fid in sorted(set(left) | set(right)):
        x, y = left.get(fid), right.get(fid)
        if x != y:
            changes.append({"항목": f"추출 항목 · {fid}",
                            "이전": f"{x['name']}: {x['instruction']}" if x else "-",
                            "이후": f"{y['name']}: {y['instruction']}" if y else "-"})
    if before["synthesis_rules"] != after["synthesis_rules"]:
        changes.append({"항목": "종합 지침", "이전": before["synthesis_rules"], "이후": after["synthesis_rules"]})
    return changes


def export_page(project):
    ui.header("바뀐 판단을 비교하고 다음 작업으로 가져갑니다",
              "9주차 결과는 10주차 위키의 재료가 됩니다. 근거 ID·원문 위치·검토 상태를 함께 보존해 내보냅니다.")
    run_id = _run_picker(project, "export_run")
    if not run_id:
        return
    with st.container(border=True):
        st.markdown("**내보내기**")
        include_pdfs = st.checkbox("원본 PDF도 ZIP에 포함", help="내보낸 원문의 이용 조건은 원저작물의 조건을 따릅니다.")
        a, b = st.columns(2)
        a.download_button("Markdown + JSON + CSV 내려받기", export_zip(project, run_id, include_pdfs), f"{run_id}.zip", type="primary", width="stretch")
        b.download_button("조사 보고서 Markdown", report(project, run_id), f"{run_id}.md", width="stretch")
    runs = project.runs()
    fields = {f["id"]: f["name"] for f in flow.manifest(project, run_id)["config"]["fields"]}
    if len(runs) > 1:
        with st.container(border=True):
            st.markdown("**실행 비교** — 무엇을 바꿨고, 어떤 값이 새로 나왔고, 판단이 어떻게 달라졌나")
            baseline = st.selectbox("비교 기준 실행", [r for r in runs if r != run_id], format_func=lambda r: _run_label(project, r))
            result = compare(project, baseline, run_id)
            st.markdown("**① 설계 변경**")
            changes = _config_changes(result["config_before"], result["config_after"])
            if changes:
                st.dataframe(changes, width="stretch", hide_index=True)
            else:
                st.caption("설계는 같습니다.")
            st.markdown("**② 추출값·검토 상태 변경**")
            if result["differences"]:
                table = []
                for d in result["differences"]:
                    x, y = d["before"] or {}, d["after"] or {}
                    table.append({"문헌": ui.short(project.source(d["source_id"])["title"], 44),
                                  "항목": fields.get(d["field_id"], d["field_id"]),
                                  "이전 값": x.get("value") or "-", "이후 값": y.get("value") or "-",
                                  "이전 검토": ui.word(ui.REVIEW, x["review"]) if x else "없음",
                                  "이후 검토": ui.word(ui.REVIEW, y["review"]) if y else "없음"})
                st.dataframe(table, width="stretch", hide_index=True)
            else:
                st.info("추출값과 검토 상태의 차이가 없습니다. 변경이 반드시 개선을 뜻하지는 않습니다.")
            st.markdown("**③ 종합**")
            a, b = st.columns(2)
            for column, label, synth in ((a, "기준 실행", result["synthesis_before"]), (b, "이번 실행", result["synthesis_after"])):
                with column:
                    st.caption(label)
                    if synth:
                        for claim in synth["claims"]:
                            st.markdown(f"- **{claim['kind']}** {claim['text']}")
                    else:
                        st.caption("유효한 종합 없음")
            st.download_button("비교 JSON", json.dumps(result, ensure_ascii=False, indent=2), "comparison.json")
    else:
        ui.empty("비교할 다른 실행이 없습니다.", "설계에서 추출 항목 하나를 바꾸고 ‘3 · 원문 추출’에서 새 실행을 만들면 여기서 전후를 비교할 수 있습니다.")
    with st.expander("개선 이슈 작성"):
        template = f"## 재현 환경\nDeep Research Kit 0.2.0\n\n## 바꾼 기준\n\n## 기대한 결과\n\n## 실제 결과\n\n## 재현 방법\n실행: {run_id}\n\n## 제안\n\n※ 원문·개인정보·API 키를 공개 이슈에 붙이지 마세요.\n"
        issue = st.text_area("원 저장소의 Issues에 남길 초안", template, height=280)
        st.download_button("이슈 초안 저장", issue, "issue.md")


PAGES = [plan_page, sources_page, extraction_page, review_page, synthesis_page, export_page]
