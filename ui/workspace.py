"""Question, library and evidence-linked results for the working view."""
from __future__ import annotations

import streamlit as st

from deep_research import workflow as flow
from deep_research.exports import citation, display_value
from deep_research.project import format_screen_quotes, parse_screen_quotes, read_json

from . import chrome as ui
from .research import coverage, review_counts

VIEWS = ["근거 비교", "문헌 모으기", "보고서에 쓰기"]


def scope_session(project):
    """Search hits, filters and drafts must not leak into another project's workspace."""
    identity = str(project.root)
    previous = st.session_state.get("wb_project")
    if previous is not None and previous != identity:
        for key in list(st.session_state):
            if key.startswith(("wb_", "cell-")) or key == "reviewer":
                del st.session_state[key]
    st.session_state["wb_project"] = identity


def navigate(view, evidence_id=None, field_id=None):
    st.session_state["wb_view"] = view
    if evidence_id:
        st.session_state["wb_next"] = evidence_id
        st.session_state["wb_filter"] = "전체"
        st.session_state["wb_find"] = ""
        if field_id:
            st.session_state["wb_columns"] = [field_id]
        else:
            st.session_state.pop("wb_columns", None)
        st.session_state["wb_layout"] = "집중 검토"


def question_panel(project, config, compact=False):
    plan = config["plan"]
    if not compact:
        st.markdown('<div class="drk-question"><span class="drk-eyebrow">RESEARCH QUESTION · 조사 질문</span>'
                    f'<div>{ui.h(plan["question"])}</div></div>', unsafe_allow_html=True)
    with st.expander("질문·선별 기준 편집", icon=":material/tune:"):
        with st.form("wb_design"):
            question = st.text_area("조사 질문", plan["question"], key="wb_question", height=80)
            a, b = st.columns(2)
            inclusion = a.text_area("포함 기준", plan.get("inclusion", ""), key="wb_inclusion")
            exclusion = b.text_area("제외 기준", plan.get("exclusion", ""), key="wb_exclusion")
            scope = st.text_input("조사 범위", plan.get("scope", ""), key="wb_scope")
            a, b = st.columns(2)
            limit = a.number_input("문헌 수 상한", 1, 100, plan["max_documents"], key="wb_doc_limit")
            pages = b.number_input("문헌당 읽을 쪽수 (0=전체)", 0, 1000,
                                   plan.get("max_pages_per_document", 20), key="wb_page_limit")
            st.caption("변경한 기준은 다음 추출부터 적용됩니다. 이미 만든 실행의 질문·추출값·검토 기록은 보존됩니다.")
            if st.form_submit_button("조사 설계 저장", type="primary"):
                try:
                    project.save_config({**plan, "question": question.strip(), "inclusion": inclusion,
                                         "exclusion": exclusion, "scope": scope,
                                         "max_documents": limit, "max_pages_per_document": pages},
                                        config["fields"], config["synthesis_rules"])
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["flash"] = "조사 설계를 저장했습니다. 다음 추출부터 적용됩니다."
                    st.rerun()


def library(project):
    sources = project.catalog()
    st.subheader("내 문헌")
    if not sources:
        ui.empty("아직 등록한 PDF가 없습니다.", "위에서 문헌을 검색해 담거나 「PDF 가져오기」로 시작하세요.")
        return
    pending = sum(s["decision"] == "pending" for s in sources)
    st.caption(f"등록 {len(sources)}편 · 포함 {sum(s['decision'] == 'include' for s in sources)}편 · 보류 {pending}편")
    a, b = st.columns([3, 1])
    query = a.text_input("내 문헌 검색", placeholder="제목·저자·DOI", key="wb_library_query")
    state = b.selectbox("선별 상태", ["전체", "include", "pending", "exclude"], key="wb_library_state",
                         format_func=lambda v: "전체" if v == "전체" else ui.word(ui.DECISION, v))
    visible = [project.with_bib(s) for s in sources if state == "전체" or s["decision"] == state]
    visible = [s for s in visible if all(t in (s["title"] + " " + s.get("doi", "") + " " +
               " ".join((s.get("bib") or {}).get("authors", []))).casefold() for t in query.casefold().split())]
    if not visible:
        st.info("조건에 맞는 문헌이 없습니다. 검색어나 선별 상태를 바꿔 보세요.")
        return
    st.dataframe([{"문헌": s["title"], "연도": (s.get("bib") or {}).get("year"),
                   "선별": ui.word(ui.DECISION, s["decision"]), "이유": s.get("reason", ""),
                   "PDF 쪽수": s.get("page_count")} for s in visible],
                 hide_index=True, width="stretch", height=min(80 + 36 * len(visible), 320))
    ids = [s["id"] for s in visible]
    if st.session_state.get("wb_library_pick") not in ids:
        st.session_state["wb_library_pick"] = ids[0]
    sid = st.selectbox("선별할 문헌", ids, key="wb_library_pick",
                       format_func=lambda i: next(s["title"] for s in visible if s["id"] == i))
    source = next(s for s in visible if s["id"] == sid)
    with st.container(key="drk-library-inspector"):
        left, right = st.columns([1, 1.35], gap="large")
    with left, st.container(border=True):
        st.markdown("**이 문헌을 조사에 사용할까요?**")
        st.caption("포함한 PDF가 다음 AI 추출 대상이 됩니다.")
        with st.form("wb_screen_" + sid):
            decision = st.radio("선별 판단", list(ui.DECISION),
                                index=list(ui.DECISION).index(source["decision"]),
                                format_func=lambda v: ui.word(ui.DECISION, v), horizontal=True)
            reason = st.text_area("선별 이유 (필수)", source.get("reason", ""), height=80)
            quotes = st.text_area("판단 근거 구절 (선택 · 한 줄에 하나)",
                                  format_screen_quotes(source.get("screen_quotes", [])), height=80)
            if st.form_submit_button("선별 저장", type="primary"):
                try:
                    project.screen(sid, decision, reason, quotes=parse_screen_quotes(quotes))
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.session_state["flash"] = "선별 판단을 저장했습니다. 이전 판단은 이력에 남습니다."
                    st.rerun()
        with st.expander("서지·인용 문구"):
            st.code(citation(source), language=None, wrap_lines=True)
    with right:
        ui.show_pdf(project, sid, source.get("screen_quotes", []), identity="library-" + sid)


def search_history(project):
    records = read_json(project.root / "search-log.json")
    if not records:
        return
    with st.expander(f"검색 이력 · {len(records)}회", icon=":material/history:"):
        st.caption("검색 당시의 검색어·자료원·조건을 보존합니다. 재검색하면 결과가 달라질 수 있습니다.")
        for i, item in reversed(list(enumerate(records))[-10:]):
            left, right = st.columns([5, 1])
            left.markdown(f"**{ui.md(item.get('query', ''))}**")
            since = (item.get("filters") or {}).get("year_from")
            left.caption(f"{ui.md(item.get('provider', ''))} · {item.get('returned', 0)}건 · "
                         f"{str(since) + '년 이후' if since else '전체 연도'} · {ui.local_time(item.get('at', ''))}")
            right.button("조건 불러오기", key=f"wb_history_{i}",
                         on_click=_restore_search, args=(item,))


def _restore_search(item):
    st.session_state["wb_q"] = item.get("query", "")
    st.session_state["wb_prov"] = [p for p in item.get("provider", "").split("+")
                                  if p in {"OpenAlex", "arXiv", "Crossref"}] or ["OpenAlex"]
    st.session_state["wb_year"] = (item.get("filters") or {}).get("year_from") or 0
    st.session_state["wb_limit"] = max(5, min(50, item.get("limit", 20)))


def results_panel(project, run_id, export_controls, synthesis_controls=None):
    run = flow.manifest(project, run_id)
    rows = flow.evidence(project, run_id)
    counts = review_counts(rows)
    sources = {s["id"]: project.with_bib(s) for s in run["sources"]}
    fields = {f["id"]: f["name"] for f in run["config"]["fields"]}
    st.subheader("검토한 근거로 연구 결과 만들기")
    a, b, c = st.columns(3)
    a.metric("채택한 근거", f"{counts['kept']}건")
    b.metric("남은 검토", f"{counts['pending'] + counts['held']}건")
    c.metric("원문 위치 미확인", f"{counts['unlocated']}건")
    st.caption("미검토·보류·제외한 값은 결론에 사용하지 않습니다. 위치 확인은 의미적 지지를 뜻하지 않습니다.")
    overview, synthesis, downloads = st.tabs(["근거 현황", "종합·출처", "내보내기"])
    with overview:
        st.markdown("**항목별 근거 현황**")
        st.dataframe(coverage(rows, run["sources"], run["config"]["fields"]),
                     hide_index=True, width="stretch")
        st.caption("미발견은 읽은 범위에서 값을 찾지 못했다는 뜻이며, 효과가 없거나 학술적 연구 공백이라는 뜻이 아닙니다. 미발견은 검토 상태와 중복 집계됩니다.")
        approved = [r for r in rows if r["review"]["status"] in {"accept", "edit"}]
        if not approved:
            ui.empty("아직 채택한 근거가 없습니다.", "근거 비교에서 원문을 읽고 판단을 저장하면 여기에 모입니다.")
        for row in approved:
            with st.container(border=True):
                st.markdown(f"**{ui.md(fields[row['field_id']])}** · {ui.md(sources[row['source_id']]['title'])}")
                st.write(ui.md(display_value(row)))
                st.button("원문·검토 기록 보기", key="wb_kept_" + row["id"],
                          on_click=navigate, args=(VIEWS[0], row["id"], row["field_id"]))
    with synthesis:
        if synthesis_controls:
            synthesis_controls()
        current = flow.current_synthesis(project, run_id)
        if not current:
            stale = (project.run_dir(run_id) / "synthesis.json").exists()
            st.info("검토가 바뀌어 이전 종합문이 만료됐습니다. 채택 근거로 다시 종합하세요." if stale
                    else "아직 종합문이 없습니다. 채택 근거로 종합을 요청할 수 있습니다.")
        else:
            row_map = {r["id"]: r for r in rows}
            kinds = {"finding": "주요 발견", "agreement": "일치", "contrast": "차이·상충", "interpretation": "해석"}
            for i, claim in enumerate(current["claims"]):
                with st.container(border=True):
                    st.caption(kinds.get(claim["kind"], claim["kind"]))
                    st.markdown(ui.md(claim["text"]))
                    for j, eid in enumerate(claim["evidence_ids"]):
                        row = row_map[eid]
                        source = sources[row["source_id"]]
                        st.button(f"[{j + 1}] {ui.md(ui.short(source['title'], 65))} · {ui.md(fields[row['field_id']])}",
                                  key=f"wb_claim_{i}_{j}", on_click=navigate, args=(VIEWS[0], eid, row["field_id"]))
            if current.get("gaps"):
                st.markdown("**AI가 제안한 남은 질문 · 연구자가 확인하세요**")
                for gap in current["gaps"]:
                    st.markdown("- " + ui.md(gap))
    with downloads:
        export_controls()
