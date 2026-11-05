"""The default working screen: a literature × item comparison table first, the PDF next to it.

Rayyan/Covidence/Elicit all put the thing the researcher is making (the table) in the middle and
tuck the process (search, runs, settings) into actions around it. The six stage pages remain as the
step-by-step learning mode; everything here calls the same core."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import streamlit as st

from deep_research import integrity
from deep_research import workflow as flow
from deep_research.exports import bibliography, citation, display_value, export_zip, report
from deep_research.project import (
    DEFAULT_FIELDS,
    DEFAULT_LENGTH,
    DEFAULT_PLAN,
    DEFAULT_RULES,
    LENGTH_CHOICES,
    has_no_text,
    length_of,
    no_text_note,
    read_json,
    with_length,
)

from . import chrome as ui
from . import reading, workspace
from .research import FILTERS, SORTS, filter_evidence, review_counts, search_view

CELL_TONE = {"accept": "go", "edit": "edit", "hold": "wait", "reject": "stop", "pending": "todo"}

GLYPH = {"pending": "○", "accept": "✓", "edit": "✎", "hold": "⏸", "reject": "✗"}
REVIEW_CHOICES = {"accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외"}
LEGEND = "○ 미검토 · ✓ 채택 · ✎ 수정 후 채택 · ⏸ 보류 · ✗ 제외 · — 읽은 범위에서 못 찾음 · ? 원문 위치 미확인"
REVIEW_GUIDE = ("**채택** 원문과 맞아 그대로 씀 · **수정 후 채택** 원문 기준으로 고쳐 씀(AI 값도 보존) · "
                "**보류** 더 확인이 필요함 · **제외** 원문과 다르거나 쓸 수 없음")
OUTPUTS = ("끝까지 하면 결과 ZIP이 남습니다: 보고서(research.md) · 비교표(comparison.csv, 문헌×항목) · "
           "근거 기록(evidence.csv, 값마다 원문 쪽·검토자·이유) · 전체 기록(research.json).")


def _answered_runs(project):
    return [r for r in project.runs() if any((project.run_dir(r) / "responses").glob("*.json"))]


def _cell(row):
    if row is None:
        return ""
    if row["value"] is None:
        return "—"
    mark = GLYPH.get(row["review"]["status"], "○")
    if row["match_status"] != "matched" and row["review"]["status"] == "pending":
        mark = "?"
    sentences = _sentences(display_value(row) or "")
    if len(sentences) > 1:  # a longer value (#29): the first sentence, the rest in the detail panel
        return f"{mark} {ui.short(sentences[0], 46)} 외 {len(sentences) - 1}문장"
    return f"{mark} {ui.short(display_value(row) or '', 60)}"


def _sentences(text):
    """Split after a Korean sentence end ('…했다. ') or after an English word of three or more
    lower-case letters followed by a capital or Hangul ('… time. The'). Numbers, list markers and
    abbreviations (1. · 19.5 · et al. · vs. · U.S.) stay inside the sentence."""
    pattern = r"(?<=[가-힣][.!?])\s+|(?<=[a-z]{3}[.!?])\s+(?=[A-Z가-힣])|(?<=。)\s*"
    return [s for s in re.split(pattern, text.strip()) if s]


def _slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "item-" + str(abs(hash(name)) % 10000)


def _say(message):
    """Success feedback where the person is looking: toast (bottom-right) plus the top banner."""
    st.session_state["flash"] = message
    st.toast(message, icon=":material/check_circle:")


def workbench(project):
    workspace.scope_session(project)
    runs = _answered_runs(project)
    all_runs = project.runs()
    for key in ("wb_run", "wb_pending_run", "wb_resp_run"):
        if st.session_state.get(key) and st.session_state[key] not in all_runs:
            st.session_state.pop(key, None)
    sources = project.catalog()
    included = [s for s in sources if s["decision"] == "include"]
    config = project.config()
    if target_run := st.session_state.pop("wb_route_run", None):
        if target_run in runs:
            st.session_state["wb_run"] = target_run
    if st.session_state.pop("wb_clear_reply", False):
        st.session_state.pop("wb_pack_reply", None)
    if route := st.session_state.pop("wb_route", None):
        st.session_state["wb_view"] = route
    legacy = {"비교·검토": "근거 비교", "문헌 탐색": "문헌 모으기", "연구 결과": "보고서에 쓰기"}
    if st.session_state.get("wb_view") in legacy:
        st.session_state["wb_view"] = legacy[st.session_state["wb_view"]]
    if destination := st.session_state.pop("start_destination", None):
        st.session_state["wb_view"] = "문헌 모으기"
        st.session_state["wb_library_route"] = destination
        st.session_state["wb_q"] = st.session_state.pop("start_query", "") or config["plan"]["question"]
        st.session_state["wb_year"] = st.session_state.pop("start_year", 0)
    st.session_state.setdefault("wb_view", workspace.VIEWS[0] if runs else workspace.VIEWS[1])
    st.markdown(f'<div class="drk-work-question">{ui.h(config["plan"]["question"])}</div>', unsafe_allow_html=True)
    if runs and st.session_state.get("wb_run") not in runs:
        st.session_state["wb_run"] = runs[0]
    workspace.progress_strip(project, st.session_state.get("wb_run") if runs else None)
    nav, settings = st.columns([4, 1])
    view = nav.segmented_control("작업 공간", [workspace.VIEWS[1], workspace.VIEWS[0], workspace.VIEWS[2]], key="wb_view", width="stretch",
                                 label_visibility="collapsed") or workspace.VIEWS[0]
    with settings, st.popover("조사 설정", icon=":material/tune:", width="stretch"):
        workspace.question_panel(project, config, compact=True)
        with st.expander("비교 항목 추가·편집"):
            _fields_popover(project, config)
        if runs:
            if st.session_state.get("wb_run") not in runs:
                st.session_state["wb_run"] = runs[0]
            st.selectbox("이전 추출 결과", runs, key="wb_run",
                         format_func=lambda r: ui.local_time(flow.manifest(project, r)["created_at"]) + " · " + r[-6:])
        st.button("단계별 보기", icon=":material/school:", on_click=open_steps)
    if view == workspace.VIEWS[1]:
        if path := st.session_state.pop("wb_library_route", None):
            st.session_state["wb_library_view"] = path
        section = st.segmented_control("문헌 작업", ["문헌 검색", "읽기 후보", "내 PDF", "원문 검색·노트"],
                                       key="wb_library_view", default="문헌 검색", width="stretch") or "문헌 검색"
        if section == "문헌 검색":
            if not runs:
                _question_notice(project, config, "wb_question_go_empty")
            st.subheader("질문에서 시작하는 문헌 탐색")
            with st.container(border=True, key="drk-search"):
                _search_popover(project)
            search_results_panel(project)
            workspace.search_history(project)
        elif section == "읽기 후보":
            reading.candidate_queue(project)
        elif section == "원문 검색·노트":
            reading.reading_room(project)
        else:
            a, b = st.columns(2)
            with a, st.popover("PDF·서지 가져오기", icon=":material/upload_file:", width="stretch"):
                _import_popover(project)
            with b, st.popover("AI로 비교표 만들기", icon=":material/auto_awesome:", width="stretch"):
                _extract_popover(project, runs, included, config)
            missing_pdfs_panel(project)
            if note := no_text_note([s for s in sources if s["decision"] != "exclude"]):
                st.warning(note, icon=":material/scanner:")
            workspace.library(project)
        return
    if view == workspace.VIEWS[2]:
        section = st.segmented_control("결과 종류", ["독서 노트·자료", "AI 근거 결과"],
                                       default="AI 근거 결과" if runs else "독서 노트·자료", key="wb_output_kind")
        if section == "AI 근거 결과" and runs:
            run_id = st.session_state.get("wb_run", runs[0])
            workspace.results_panel(project, run_id, lambda: _export_popover(project, runs),
                                    lambda: _synthesis_controls(project, run_id))
        elif section == "AI 근거 결과":
            st.info("아직 추출한 비교표가 없습니다. 독서 노트와 자료는 AI 없이도 내보낼 수 있습니다.")
        else:
            reading.notes_panel(project)
            reading.materials_export(project)
        return
    with st.expander("비교표 새로 만들기 · AI 연결·실행 범위"):
        _extract_popover(project, runs, included, config)
    if not runs:
        _onboarding(project, sources, included)
        return
    _comparison(project, st.session_state.get("wb_run", runs[0]), included, config)


def _comparison(project, run_id, included, config):
    run = flow.manifest(project, run_id)
    rows = flow.evidence(project, run_id)
    run_fields = run["config"]["fields"]
    run_field_ids = {f["id"] for f in run_fields}
    all_fields = run_fields + [f for f in config["fields"] if f["id"] not in run_field_ids]
    run_source_ids = {s["id"] for s in run["sources"]}
    new_sources = [s for s in included if s["id"] not in run_source_ids]
    by_key = {(r["source_id"], r["field_id"]): r for r in rows}
    counts = review_counts(rows)
    if not rows:
        ui.empty("이 실행에는 추출값이 없습니다.", "「AI로 추출」에서 응답을 가져오세요.")
        return
    st.markdown('<div class="drk-section-title">문헌 비교표 <span>값을 선택해 원문을 확인하세요</span></div>', unsafe_allow_html=True)
    summary, progress = st.columns([2, 1])
    summary.caption(f"문헌 {len(run['sources'])}편 · 항목 {len(run_fields)}개 · 채택 {counts['kept']} · 미검토 {counts['pending']} · 보류 {counts['held']}")
    progress.progress(counts["resolved"] / counts["total"], text=f"검토 확정 {counts['resolved']}/{counts['total']} · 보류 제외")
    if run["config"] != config or new_sources:
        st.caption("ⓘ 조사 설계 또는 문헌 구성이 바뀌었습니다. 현재 표에는 선택한 실행의 기준이 적용됩니다."
                   + (f" 새 문헌 {len(new_sources)}편 · 새 항목 {len(all_fields) - len(run_fields)}개는 추출 대기 중입니다."
                      if new_sources or len(all_fields) > len(run_fields) else ""))
        if run["config"]["plan"]["question"] != config["plan"]["question"]:
            st.caption("이 실행의 질문 · " + ui.md(run["config"]["plan"]["question"]))
    with st.expander("검색·검토 상태·표시 항목"):
        a, b, c = st.columns([2, 1, 1.2])
        query = a.text_input("비교표 검색", placeholder="제목·저자·추출값·원문 구절", key="wb_find")
        status = b.selectbox("검토 상태", FILTERS, key="wb_filter")
        st.session_state.setdefault("wb_layout", "비교표")
        layout = c.segmented_control("검토 방식", ["비교표", "집중 검토"], key="wb_layout") or "비교표"
        field_ids = [f["id"] for f in all_fields]
        if "wb_columns" in st.session_state:
            valid_columns = [f for f in st.session_state["wb_columns"] if f in field_ids]
            if valid_columns != st.session_state["wb_columns"]:
                st.session_state["wb_columns"] = valid_columns
        else:
            st.session_state["wb_columns"] = [f for f in field_ids if f in {"finding", "limitations"}] or field_ids[:2]
        with st.expander("표시 항목 선택", icon=":material/view_column:"):
            selected_fields = st.multiselect("비교할 항목 (한 번에 최대 6개)", field_ids,
                                             max_selections=6, key="wb_columns",
                                             format_func=lambda fid: next(f["name"] for f in all_fields if f["id"] == fid))
    fields = [f for f in all_fields if f["id"] in selected_fields]
    sources = [project.with_bib(s) for s in run["sources"]]
    visible = filter_evidence(rows, sources, query, status, set(selected_fields))
    ids = [r["id"] for r in visible]
    if not ids:
        ui.empty("조건에 맞는 추출값이 없습니다.", "검색어·검토 상태·표시 항목을 바꾸거나 필터를 초기화하세요.")
        st.button("필터 초기화", key="wb_reset", on_click=_reset_filters)
        return
    if (jump := st.session_state.pop("wb_next", None)) in ids:
        st.session_state["wb_pick"] = jump
    if st.session_state.get("wb_pick") not in ids:
        st.session_state["wb_pick"] = next((r["id"] for r in visible if r["review"]["status"] == "pending"), ids[0])
    visible_ids = set(ids)
    matched_sources = {r["source_id"] for r in visible}
    shown_sources = [s for s in sources if s["id"] in matched_sources]
    st.caption(f"조건에 맞는 문헌 {len(shown_sources)}편 · 근거 {len(visible)}건 / 전체 {len(rows)}건")
    with st.container(key="drk-comparison-workspace"):
        if layout == "비교표":
            table, detail = st.columns([1.15, 1], gap="large")
            with table:
                pages = max(1, (len(shown_sources) + 7) // 8)
                if st.session_state.get("wb_table_page", 1) > pages:
                    st.session_state["wb_table_page"] = 1
                if pages > 1:
                    page = st.selectbox("비교표 페이지 · 8편씩", list(range(1, pages + 1)), key="wb_table_page")
                    shown_sources = shown_sources[(page - 1) * 8:page * 8]
                _comparison_grid(project, shown_sources, fields, by_key, visible_ids,
                                 new_sources if not query and status == "전체" else [])
                st.caption("셀 선택 → 옆에서 원문 확인 · ○ 미검토 · ✓ 채택 · ✎ 수정 · ⏸ 보류")
            with detail:
                row = next(r for r in visible if r["id"] == st.session_state["wb_pick"])
                source = next(s for s in run["sources"] if s["id"] == row["source_id"])
                field = next(f["name"] for f in fields if f["id"] == row["field_id"])
                st.button("PDF와 나란히 크게 검토", key="wb_focus", on_click=_focus)
                _detail(project, run_id, row, source, field, visible)
                with st.expander("원문 PDF 펼치기"):
                    _evidence_pdf(project, row)
        else:
            index = ids.index(st.session_state["wb_pick"])
            a, b, c = st.columns([1, 3, 1])
            a.button("← 이전 근거", disabled=index == 0, key="wb_prev", on_click=_pick, args=(ids[max(0, index - 1)],))
            b.caption(f"원문 근거 {index + 1} / {len(ids)} · 위치 확인과 사람의 판단은 별도입니다.")
            c.button("다음 근거 →", disabled=index == len(ids) - 1, key="wb_forward", on_click=_pick, args=(ids[min(len(ids) - 1, index + 1)],))
            with st.container(key="drk-inspector"):
                _inspector(project, run_id, run, visible, fields)


def _focus():
    st.session_state["wb_layout"] = "집중 검토"


def _pick(evidence_id):
    st.session_state["wb_pick"] = evidence_id


def _reset_filters():
    st.session_state["wb_find"] = ""
    st.session_state["wb_filter"] = "전체"
    st.session_state.pop("wb_columns", None)


def _comparison_grid(project, shown_sources, fields, by_key, visible_ids, new_sources):
    widths = [1.3] + [1.0] * len(fields)
    with st.container(key="drk-grid", height=360 if len(shown_sources) > 3 else "content"):
        head = st.columns(widths, gap="small")
        head[0].markdown('<div class="drk-th">문헌</div>', unsafe_allow_html=True)
        for col, field in zip(head[1:], fields):
            col.markdown(f'<div class="drk-th" title="{ui.h(field["instruction"])}">{ui.h(field["name"])}</div>', unsafe_allow_html=True)
        for source in shown_sources:
            cols = st.columns(widths, gap="small")
            bib = project.with_bib(source).get("bib") or {}
            meta = " · ".join(x for x in (ui.short(", ".join(bib.get("authors", [])[:2]), 30), str(bib.get("year") or "")) if x)
            cols[0].markdown(f'<div class="drk-td-title" title="{ui.h(source["title"])}">{ui.h(ui.short(source["title"], 56))}<span>{ui.h(meta)}</span></div>', unsafe_allow_html=True)
            for col, field in zip(cols[1:], fields):
                cell = by_key.get((source["id"], field["id"]))
                if cell is None:
                    col.markdown('<div class="drk-td-empty">AI 추출 대기</div>', unsafe_allow_html=True)
                    continue
                selected = cell["id"] == st.session_state["wb_pick"]
                tone = "none" if cell["value"] is None else CELL_TONE.get(cell["review"]["status"], "todo")
                with col.container(key=f"tone-{tone}-{cell['id']}"):
                    if st.button(ui.md(_cell(cell) or "—"), key="cell-" + cell["id"], width="stretch", type="primary" if selected else "secondary", disabled=cell["id"] not in visible_ids,
                                 help=ui.md(cell["value"] or "읽은 범위에서 찾지 못함") + f"\n\n검토: {ui.word(ui.REVIEW, cell['review']['status'])}"):
                        st.session_state["wb_pick"] = cell["id"]
                        st.rerun()
        for source in new_sources:
            cols = st.columns(widths, gap="small")
            cols[0].markdown(f'<div class="drk-td-title" title="{ui.h(source["title"])}">{ui.h(ui.short(source["title"], 56))}<span>새 문헌 · 포함</span></div>', unsafe_allow_html=True)
            for col in cols[1:]:
                col.markdown('<div class="drk-td-empty">AI 추출 대기</div>', unsafe_allow_html=True)


def _inspector(project, run_id, run, rows, fields):
    row = next(r for r in rows if r["id"] == st.session_state["wb_pick"])
    source = project.with_bib(next(s for s in run["sources"] if s["id"] == row["source_id"]))
    field_name = next(f["name"] for f in fields if f["id"] == row["field_id"])
    left, right = st.columns([1, 1.5], gap="large")
    with left:
        _detail(project, run_id, row, source, field_name, rows)
    with right:
        _evidence_pdf(project, row)


def _evidence_pdf(project, row):
    if row["locators"]:
        pick = st.selectbox("보러 갈 발췌", range(len(row["locators"])), format_func=lambda i: f"발췌 {i + 1} · PDF {row['locators'][i]['page']}쪽",
                            key="wb_loc_" + row["id"]) if len(row["locators"]) > 1 else 0
        locator = row["locators"][pick]
        ui.show_pdf(project, row["source_id"], row["locators"], page=locator["page"] or 1, identity="wb-" + row["id"], focus=pick,
                    caption="이 쪽은 강조 위치를 그릴 수 없습니다(회전·잘린 쪽). 원문을 직접 보며 확인하세요."
                    if locator["status"] == "unsupported_page_geometry" else ui.evidence_caption(row["locators"], pick))
    else:
        ui.show_pdf(project, row["source_id"], identity="wb-" + row["id"], caption="이 항목은 읽은 범위에서 찾지 못했습니다. 원문을 넘기며 직접 확인하세요.")


def _detail(project, run_id, row, source, field_name, rows):
    with st.container(border=True):
        a, b = st.columns(2)
        with a:
            ui.badge(ui.MATCH, row["match_status"])
        with b:
            ui.badge(ui.REVIEW, row["review"]["status"])
        st.markdown(f"**{ui.md(field_name)}** · {ui.md(ui.short(source['title'], 60))}")
        if (source.get("integrity") or {}).get("status") in integrity.FLAGGED:
            ui.integrity_note(source["integrity"], "철회·정정 · ")
        st.markdown(f'<div class="drk-value">{ui.h(display_value(row) or "읽은 범위에서 찾지 못함")}</div>', unsafe_allow_html=True)
        if row["review"]["status"] == "edit":
            with st.expander("수정 전 AI 추출값"):
                st.markdown(ui.md(row["value"]))
        many = len(row["locators"]) > 1
        for i, locator in enumerate(row["locators"], 1):
            st.markdown(ui.quote_html(locator, i if many else None), unsafe_allow_html=True)
        if geometry := ui.geometry_note(row):
            st.warning(geometry, icon=":material/crop_rotate:")
        # What the model was given and what it wrote about its own reading are different things (#20).
        scope = row["page_scope"]
        if row["note"]:
            st.caption("AI 메모(AI가 적은 읽은 범위·한계) · " + ui.md(row["note"]))
        st.caption(f"요청에 넣은 범위 · PDF {scope['from']}~{scope['to']}쪽 / 전체 {scope['total']}쪽"
                   + (". 범위 밖에 있을 수 있습니다 — 「1 · 조사 설계」에서 읽을 쪽수를 0(전체)으로 두고 다시 추출하면 확인됩니다."
                      if row["value"] is None and scope["to"] < scope["total"] else ""))
        previous = row["review"]["status"] if row["review"]["status"] in REVIEW_CHOICES else None
        status = st.radio("이 값을", list(REVIEW_CHOICES), index=list(REVIEW_CHOICES).index(previous) if previous else None,
                          key="wb_decision_" + row["id"], format_func=REVIEW_CHOICES.get, horizontal=True,
                          help="채택 = 원문과 맞아 그대로 씀 · 수정 후 채택 = 고쳐 씀(원래 값 보존) · 보류 = 더 확인 · 제외 = 원문과 다르거나 쓸 수 없음")
        with st.form("wb-review-" + row["id"]):
            checked = st.checkbox("원문의 앞뒤 문맥을 읽고 판단했습니다 (채택·수정 후 채택에 필수)")
            value = row["review"].get("edited_value") or row["value"] or ""
            if status == "edit":
                value = st.text_area("수정한 값 (수정 후 채택일 때)", value, height=90,
                                     help="원문에 맞게 고칩니다. AI의 원래 추출값도 보존됩니다.")
            if status in {"accept", "edit"}:
                marks = [None, *flow.COMPARISON]
                comparison = st.radio("다른 문헌의 같은 항목과 비교하면 (선택)", marks,
                                      index=marks.index(row["review"].get("comparison")), horizontal=True,
                                      format_func=lambda k: "표시 안 함" if k is None else flow.COMPARISON[k],
                                      help="같은 지표·단위 = 나란히 비교 가능 · 조건이 다름 = 대상·기간·방법이 달라 비교에 단서가 필요 · "
                                           "비교 불가 = 다른 지표라 합치면 안 됨. 보고서에 쓰기의 근거 현황에 집계됩니다.")
            else:
                comparison = None
            note = st.text_input("이유 한 줄 (필수)", row["review"].get("note", ""),
                                 placeholder="예: 8쪽 발췌와 수치 일치, 앞뒤 문맥상 조건 누락 없음 / 단위가 빠져 보완",
                                 help="무엇과 대조했는지(쪽·표·문장)와 판단을 짧게 적습니다. 이 이유가 보고서·CSV의 근거 기록에 남습니다.")
            reviewer = st.text_input("검토자 (필수 · 한 번 적으면 이 프로젝트에 기억)", st.session_state.get("reviewer") or project.reviewer(),
                                     help="이름이나 이니셜. 보고서·CSV의 검토자 칸에 남습니다.")
            if st.form_submit_button("저장하고 다음 미검토로", type="primary", icon=":material/check:"):
                missing = []
                if status is None:
                    missing.append("판정(채택·수정 후 채택·보류·제외 중 하나)")
                if status in {"accept", "edit"} and not checked:
                    missing.append("원문 확인 표시")
                if not note.strip():
                    missing.append("이유")
                if not reviewer.strip():
                    missing.append("검토자")
                if missing:
                    st.error("저장하려면 다음을 채우세요: " + " · ".join(missing))
                else:
                    try:
                        flow.review(project, run_id, row["id"], status, note, reviewer, value, comparison)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["reviewer"] = reviewer
                        project.remember_reviewer(reviewer)
                        after = [r["id"] for r in rows if r["review"]["status"] == "pending" and r["id"] != row["id"]]
                        st.session_state["wb_next"] = after[0] if after else row["id"]
                        _say(f"저장했습니다 · {ui.md(field_name)} → {REVIEW_CHOICES[status]}" + ("" if after else " · 미검토가 없습니다. 내보내기로 가세요."))
                        st.rerun()
        with st.expander("인용 문장 복사", icon=":material/format_quote:"):
            st.code(citation(source, row), language=None)
            st.caption("저자·연도·게재지는 DOI로 받아 온 서지 정보입니다. 쪽수는 PDF 파일 기준이라 인쇄 쪽과 다를 수 있습니다.")


def _onboarding(project, sources, included):
    _question_notice(project, project.config(), "wb_question_go_empty")
    with st.container(border=True):
        st.markdown("**비교표를 만들 준비를 해 주세요.** AI 추출 결과는 원문과 대조한 뒤 채택합니다.")
        st.caption(OUTPUTS)
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**① 문헌 모으기**  \n검색에서 후보를 담거나 「내 PDF」에서 파일을 가져옵니다.  \n지금 {len(sources)}편")
        c2.markdown(f"**② 쓸 문헌 고르기**  \n「문헌 모으기 → 내 PDF」에서 포함·제외와 이유를 정합니다.  \n지금 포함 {len(included)}편")
        c3.markdown("**③ 비교표 만들기**  \n위 AI 연결에서 실행 방법과 읽을 범위를 확인하세요.")
        st.caption("AI를 연결하지 않아도 ‘원문 검색·노트’에서 읽고, ‘보고서에 쓰기’에서 발췌·서지·검색 이력을 내려받을 수 있습니다.")
        if sources and not included:
            if st.button("등록한 문헌을 모두 포함으로 두고 시작 (나중에 바꿀 수 있음)"):
                readable = [s for s in sources if s["decision"] == "pending" and not has_no_text(s)]
                for s in readable:
                    project.screen(s["id"], "include", "작업 화면에서 일괄 포함. 선별 이유는 2단계에서 보완.")
                skipped = sum(s["decision"] == "pending" and has_no_text(s) for s in sources)
                st.session_state["flash"] = (f"{len(readable)}편을 포함으로 두었습니다. 「AI로 추출」을 누르세요."
                                             + (f" 글자 없는 PDF {skipped}편은 보류로 남겼습니다." if skipped else ""))
                st.rerun()


# ---------------------------------------------------------------------------
# Action bar: everything that is not the table lives behind one of these buttons.
# ---------------------------------------------------------------------------
def _action_bar(project, runs, included, config):
    c1, c2, c3, c4 = st.columns([1, 1, 1.2, 1])
    with c1, st.popover("PDF 가져오기", icon=":material/upload_file:", width="stretch"):
        _import_popover(project)
    with c2, st.popover("항목 추가·편집", icon=":material/view_column:", width="stretch"):
        _fields_popover(project, config)
    with c3, st.popover("AI로 추출", icon=":material/auto_awesome:", width="stretch"):
        _extract_popover(project, runs, included, config)
    with c4:
        st.button("단계별 보기", icon=":material/school:", width="stretch",
                  help="조사 설계·선별·검토를 한 단계씩 따라가는 학습 모드", on_click=open_steps)


def open_steps(stage=None):
    """Switch to the step-by-step mode, optionally at one stage. This runs as a button callback:
    the sidebar's mode switch (key mode_pick) is already drawn when the button body runs, and
    Streamlit refuses to change a drawn widget's value then (#19)."""
    st.session_state["mode"] = st.session_state["mode_pick"] = "단계별(학습)"
    if stage:
        st.session_state["stage_value"] = stage
        st.session_state["scroll_top"] = True


def _example_question(project, config):
    """The research question is still the sample one, in a project of the person's own."""
    return (not (project.root / "example-manifest.json").exists()
            and config["plan"].get("question") == DEFAULT_PLAN["question"])


def _question_notice(project, config, key):
    if not _example_question(project, config):
        return
    st.warning("조사 질문이 아직 예시 그대로입니다. 「조사 설정 → 질문·선별 기준 편집」에서 내 질문을 먼저 적어 주세요.", icon=":material/edit_note:")


def _apply_key():
    from deep_research.providers import use_session_key
    key = (st.session_state.get("wb_openalex_key_input") or "").strip()
    st.session_state["drk_openalex_key"] = key
    use_session_key(key)


def _clear_key():
    from deep_research.providers import use_session_key
    st.session_state["wb_openalex_key_input"] = ""
    st.session_state.pop("drk_openalex_key", None)
    use_session_key("")


def _key_box():
    """Each person may bring a free OpenAlex key; it lives in this browser session only."""
    from deep_research.providers import KEY_SOURCE, openalex_key
    _, source = openalex_key()
    with st.expander(f"OpenAlex 개인 키 (선택) · 지금: {KEY_SOURCE[source]}", icon=":material/key:"):
        st.caption("키 없이도 검색되지만, 같은 와이파이를 쓰는 사람들과 하루 무료 한도를 나눠 써서 금방 막힙니다. "
                   "[openalex.org](https://openalex.org/settings/api)에서 무료 키를 받아 넣으면 내 한도로 검색합니다. "
                   "넣은 키는 이 브라우저 창에서만 쓰고 파일·검색 기록·내보내기에 저장하지 않습니다.")
        st.text_input("OpenAlex 키", type="password", key="wb_openalex_key_input", on_change=_apply_key,
                      placeholder="키를 붙여 넣고 Enter")
        if source == "session":
            st.button("이 창의 키 지우기", key="wb_key_clear", on_click=_clear_key)


def _run_search(project, query, providers, limit, year_from):
    from deep_research.providers import openalex_hint, search_literature
    st.session_state.pop("wb_results", None)
    st.session_state.pop("wb_results_query", None)
    st.session_state.pop("wb_fallback", None)
    retry = {"query": query, "limit": limit, "year_from": year_from}
    try:
        with st.spinner("학술 자료원을 검색하고 중복 문헌을 합치는 중"):
            results = search_literature(project, query, providers, limit, year_from or None)
    except ValueError as exc:
        st.error(str(exc))
        # search_literature logs every search before it raises; an empty query is refused before that.
        log = read_json(project.root / "search-log.json")[-1] if query.strip() else {}
        if openalex_hint(log.get("errors")):
            st.session_state["wb_fallback"] = retry
        return
    st.session_state["wb_results"] = results
    st.session_state["wb_results_query"] = query
    for key in ("wb_results_editor", "wb_result_pick", "wb_result_find", "wb_result_oa", "wb_result_order"):
        st.session_state.pop(key, None)
    if not results:
        st.info("검색 결과가 없습니다. 검색어를 줄이거나 연도 범위를 넓혀 보세요.")
    log = read_json(project.root / "search-log.json")[-1]
    if results and not log.get("errors"):
        st.rerun()  # the progress strip above counts this search too
    if log.get("errors"):
        hint = openalex_hint(log["errors"])
        st.warning("일부 자료원에서 결과를 받지 못했습니다: " + ", ".join(f"{k} {v}" for k, v in log["errors"].items())
                   + ". 나머지 결과를 표시합니다." + (" " + hint if hint else ""))
        if hint and not {"Crossref", "arXiv"} <= set(providers):
            st.session_state["wb_fallback"] = retry


def _search_popover(project):
    st.caption("학술 자료원에 검색어를 보냅니다. 내 PDF·노트는 전송하지 않습니다.")
    _key_box()
    with st.form("wb_search_form"):
        query = st.text_input("검색어", key="wb_q", placeholder="연구 주제를 입력하세요 · 예: generative AI knowledge work productivity")
        a, b, c = st.columns([2, 1, 1])
        providers = a.multiselect("학술 자료원", ["OpenAlex", "arXiv", "Crossref"], default=["OpenAlex"], key="wb_prov")
        year_from = b.number_input("발행연도 이후 (0=전체)", 0, 2100, 0, key="wb_year")
        limit = c.number_input("자료원별 최대 건수", 5, 50, 20, key="wb_limit")
        submitted = st.form_submit_button("문헌 검색", type="primary", icon=":material/search:")
    if submitted:
        _run_search(project, query, providers or ["OpenAlex"], limit, year_from)
    fallback = st.session_state.get("wb_fallback")
    if fallback and st.button("Crossref·arXiv로 다시 검색", key="wb_fallback_go", icon=":material/refresh:",
                              help="키 없이 쓸 수 있는 자료원입니다. 초록이 없는 문헌이 많고, arXiv는 프리프린트만 있습니다."):
        _run_search(project, fallback["query"], ["Crossref", "arXiv"], fallback["limit"], fallback["year_from"])
    st.caption("OpenAlex · arXiv · Crossref에서 검색합니다. 관련도순은 각 자료원이 반환한 순서이며 자료원 간 통합 점수가 아닙니다.")


def search_results_panel(project):
    results = st.session_state.get("wb_results") or []
    if not results:
        return
    with st.container(border=True):
        st.markdown(f"**검색 결과 {len(results)}건** · {ui.md(st.session_state.get('wb_results_query', ''))}")
        a, b, c = st.columns([2, 1, 1])
        query = a.text_input("결과 내 검색", placeholder="제목·저자·초록·DOI", key="wb_result_find")
        order = b.selectbox("정렬", SORTS, key="wb_result_order",
                            help="피인용 수는 얼마나 자주 인용됐는지일 뿐 품질·신뢰도 순위가 아닙니다.")
        oa = c.checkbox("오픈액세스만", key="wb_result_oa")
        visible = search_view(results, query, oa, order)
        st.caption(f"{len(visible)} / {len(results)}건 표시 · OA 표시는 공개 이용 가능 메타데이터이며 PDF 확보를 보장하지 않습니다.")
        if not visible:
            st.info("조건에 맞는 결과가 없습니다. 결과 내 검색어나 OA 필터를 바꿔 보세요.")
            return
        # A new key for every ordered set prevents checkboxes moving to a different paper.
        signature = flow.fingerprint(visible)[:12]
        records = [{"담기": False, "제목": ("[철회] " if r.get("retracted") else "") + r["title"], "저자": ", ".join(r.get("authors", [])[:3]),
                    "연도": r.get("year"), "학술지": r.get("venue", ""), "피인용": r.get("cited_by"),
                    "공개 원문": "OA" if r.get("pdf_url") or r.get("oa") else "확인 필요",
                    "자료원": ", ".join(r.get("providers", []))} for r in visible]
        edited = st.data_editor(records, hide_index=True, width="stretch", key="wb_results_editor_" + signature,
                                disabled=[k for k in records[0] if k != "담기"], height=min(80 + 36 * len(visible), 420),
                                column_config={"담기": st.column_config.CheckboxColumn(width="small"),
                                               "제목": st.column_config.TextColumn(width="large")})
        chosen = [visible[i] for i, r in enumerate(edited) if r.get("담기")]
        if st.button(f"선택한 {len(chosen)}건 후보함에 담기", disabled=not chosen, key="wb_collect", type="primary", icon=":material/library_add:"):
            for cand in chosen:
                project.remember_candidate({**cand, "status": "saved",
                                            "search_query": st.session_state.get("wb_results_query", "")})
            st.session_state["wb_library_route"] = "읽기 후보"
            _say(f"후보 {len(chosen)}편을 저장했습니다. 읽을 이유를 적고 필요한 PDF만 가져오세요.")
            st.rerun()
        with st.expander("초록·출처 미리보기", expanded=True):
            pick = st.selectbox("살펴볼 문헌", range(len(visible)), key="wb_result_pick_" + signature,
                                format_func=lambda i: visible[i]["title"])
            cand = visible[pick]
            if cand.get("retracted"):
                st.error("OpenAlex가 철회된 문헌으로 표시합니다. 담더라도 근거로 쓰기 전에 철회 고지를 확인하세요.", icon=":material/block:")
            st.markdown(ui.md(cand.get("abstract") or "이 자료원에서 초록을 제공하지 않았습니다. 원문 링크에서 확인하세요."))
            link = ui.safe_url(cand.get("url") or ("https://doi.org/" + cand["doi"] if cand.get("doi") else ""))
            if link:
                st.link_button("원문·출처 열기", link, icon=":material/open_in_new:")
            if cand.get("doi"):
                st.caption("DOI · " + ui.md(cand["doi"]))


WATCH_MINUTES = 20


def missing_pdfs_panel(project):
    """Hits whose PDF no open source handed over. The person opens each in their own browser
    (their subscriptions and logins, their bot checks), and the app picks the file up."""
    from deep_research import acquire
    pending = acquire.waiting(project)
    if not pending:
        st.session_state.pop("wb_watch", None)
        return
    with st.container(border=True, key="drk-missing"):
        st.markdown(f"**PDF를 아직 받지 못한 문헌 {len(pending)}건** — 바로 받을 수 있는 공개 사본이 없거나, 사이트가 자동 접근을 막았습니다. "
                    "「원문 열기」로 내 브라우저에서 열어 PDF를 내려받으면 「다운로드 폴더 지켜보기」가 등록하고 이 문헌과 묶습니다. "
                    "기관 구독·로그인이 필요한 곳은 내 계정으로 받습니다.")
        for i, cand in enumerate(pending[:15]):
            link = ui.safe_url(cand.get("url") or ("https://doi.org/" + cand["doi"] if cand.get("doi") else ""))
            left, right = st.columns([5, 1.2])
            left.markdown(f"{ui.md(ui.short(cand['title'], 90))} · {cand.get('year') or ''}")
            if cand.get("attempts"):
                left.caption("시도한 곳 · " + ui.md(acquire.attempts_summary(cand["attempts"])))
            if link:
                right.link_button("원문 열기", link, icon=":material/open_in_new:", width="stretch")
        a, b = st.columns(2)
        if a.button("PDF 다시 찾기 (자동)", key="wb_retry_pdfs", icon=":material/refresh:", width="stretch",
                    help="공개 사본을 다시 찾습니다: 검색 결과의 주소, OpenAlex의 다른 위치, arXiv, Unpaywall, 논문 페이지의 PDF 주소 표시"):
            with st.spinner("공개 사본을 다시 찾는 중 · 문헌당 최대 40초"):
                got = acquire.retry_waiting(project)
            _say(f"PDF {len(got)}건을 받았습니다." if got else "새로 받은 PDF가 없습니다. 내 브라우저에서 내려받아 주세요.")
            st.rerun()
        watching = b.toggle("다운로드 폴더 지켜보기", key="wb_watch_on",
                            help=f"켜 둔 동안({WATCH_MINUTES}분까지) 새로 내려받은 PDF 가운데 위 문헌과 DOI·제목이 맞는 것만 등록합니다.")
        if watching:
            folder = st.text_input("다운로드 폴더", str(acquire.downloads_folder()), key="wb_watch_dir",
                                   help="브라우저가 PDF를 저장하는 폴더. macOS는 처음에 이 폴더 접근을 허용할지 물을 수 있습니다.")
            state = st.session_state.get("wb_watch")
            if not state or state["folder"] != folder:
                # What is already in the folder is not a new download, whatever its date says.
                try:
                    known = acquire.pdfs_in(folder)
                except OSError as exc:
                    st.warning(f"이 폴더를 읽지 못했습니다({type(exc).__name__}). 경로를 확인하세요. "
                               "macOS는 시스템 설정 → 개인정보 보호 및 보안 → 파일 및 폴더에서 터미널의 다운로드 폴더 접근을 허용해야 할 수 있습니다.")
                    known = None
                st.session_state["wb_watch"] = {"folder": folder, "since": time.time(), "seen": known, "linked": [], "unmatched": []} if known is not None else None
            if st.session_state.get("wb_watch"):
                _watch_downloads(project)
        else:
            st.session_state.pop("wb_watch", None)
        _manual_link(project, pending)


@st.fragment(run_every=3)
def _watch_downloads(project):
    from deep_research import acquire
    state = st.session_state.get("wb_watch")
    if not state:
        return
    if time.time() - state["since"] > WATCH_MINUTES * 60:
        st.caption(f"{WATCH_MINUTES}분이 지나 지켜보기를 멈췄습니다. 다시 하려면 껐다 켜세요.")
        return
    changed = False
    try:
        arrived = acquire.new_downloads(state["folder"], state["seen"])
    except OSError as exc:
        st.warning(f"다운로드 폴더를 읽지 못해 지켜보기를 멈췄습니다({type(exc).__name__}). 경로·접근 권한을 확인하고 다시 켜세요.")
        return
    for path in arrived:
        state["seen"].add(str(path))
        data = acquire.read_download(path)
        if data is None:
            continue
        candidate, how = acquire.match_file(project, path)
        if candidate:
            source_id = project.add_pdf(data, path.name)
            acquire.link(project, source_id, candidate, how + " · 다운로드 폴더")
            state["linked"].append(candidate["title"])
            changed = True
        else:
            state["unmatched"].append(str(path))
    st.caption(f"지켜보는 중 · {ui.md(state['folder'])} · 묶은 PDF {len(state['linked'])}건")
    for name in list(state["unmatched"]):
        left, right = st.columns([5, 1.4])
        left.caption(f"맞는 문헌을 찾지 못한 새 PDF · {ui.md(Path(name).name)}")
        if right.button("그래도 등록", key="wb_watch_add_" + flow.fingerprint(name)[:12]):
            state["unmatched"].remove(name)
            data = acquire.read_download(name)
            try:
                if data is None:
                    raise ValueError("PDF로 읽을 수 없는 파일입니다.")
                acquire.register(project, data, Path(name).name)
            except ValueError as exc:
                st.error(f"{ui.md(Path(name).name)}: {ui.md(str(exc))}")
            else:
                changed = True
    if changed:
        st.rerun()


def _manual_link(project, pending):
    """When neither DOI nor title gave a single match: the person says which PDF is which."""
    from deep_research import acquire
    linked = {c.get("source_id") for c in project.collection() if c.get("source_id")}
    sources = [s for s in project.catalog() if s["id"] not in linked]
    if not sources:
        return
    with st.expander("올린 PDF와 직접 묶기"):
        a, b = st.columns(2)
        keys = {(c.get("doi") or c.get("title") or ""): c for c in pending}  # a stable value, not a list position
        picked = a.selectbox("PDF를 기다리는 문헌", list(keys), key="wb_link_cand",
                             format_func=lambda k: ui.short(keys[k]["title"], 60))
        source_id = b.selectbox("등록된 PDF", [s["id"] for s in sources], key="wb_link_src",
                                format_func=lambda sid: ui.short(next(s["title"] for s in sources if s["id"] == sid), 60))
        if st.button("묶기", key="wb_link_btn", disabled=picked not in keys):
            acquire.link(project, source_id, keys[picked], "직접")
            _say(f"「{ui.md(ui.short(keys[picked]['title'], 40))}」과 묶었습니다.")
            st.rerun()


def _import_popover(project):
    from deep_research.providers import collect, parse_bibtex, parse_ris
    st.markdown("**내 PDF 올리기**")
    files = st.file_uploader("PDF (여러 개 가능)", type="pdf", accept_multiple_files=True, key="wb_pdfs")
    if st.button("등록", disabled=not files, key="wb_pdf_add"):
        from deep_research.acquire import register
        linked = 0
        for file in files:
            with st.spinner(file.name + " 색인 중"):
                linked += register(project, file.getvalue(), file.name)[1] is not None
        _say(f"PDF {len(files)}건을 등록했습니다." + (f" PDF를 기다리던 문헌 {linked}건과 묶었습니다." if linked else "")
             + " 「문헌 탐색 → 내 문헌」에서 포함·제외를 정하세요.")
        st.rerun()
    st.markdown("**Zotero·EndNote에서 내보낸 목록(.ris / .bib)**")
    ref = st.file_uploader("RIS 또는 BibTeX", type=["ris", "bib", "txt"], key="wb_ref")
    if ref is not None:
        text = ref.getvalue().decode("utf-8", errors="replace")
        cands = parse_ris(text) if ref.name.lower().endswith(".ris") or "TY  -" in text else parse_bibtex(text)
        st.caption(f"{len(cands)}건 읽음 · 담으면 DOI로 오픈액세스 PDF를 찾아 등록하고, 못 찾으면 서지만 남깁니다.")
        if st.button(f"{len(cands)}건 담기", disabled=not cands, key="wb_ref_add"):
            from deep_research.providers import openalex_search
            added = 0
            with st.spinner("오픈액세스 PDF를 찾는 중"):
                for cand in cands:
                    if cand["doi"] and not cand["pdf_url"]:
                        try:
                            _, hits = openalex_search(cand["doi"], 1)
                            if hits and hits[0]["doi"] == cand["doi"]:
                                cand["pdf_url"] = hits[0]["pdf_url"]
                                cand["venue"] = cand["venue"] or hits[0]["venue"]
                        except Exception:  # network is optional here
                            pass
                    added += collect(project, cand)["status"] == "added"
            _say(f"{len(cands)}건 중 PDF 등록 {added}건, 서지만 {len(cands) - added}건.")
            st.rerun()


CUSTOM_LENGTH = "직접 입력"


def _length_picker(prefix, current=DEFAULT_LENGTH):
    """Length choices plus free text (#29). Returns None while the free text is still empty."""
    options = LENGTH_CHOICES + [CUSTOM_LENGTH]
    choice = st.selectbox("분량", options, index=options.index(current) if current in options else len(options) - 1,
                          key=f"{prefix}_len_{current}", help="값을 몇 문장으로 받을지. 「기본」 말고 다른 분량을 고르면 추출 지침 끝에 [분량: …]으로 붙고, "
                                                    "문장마다 근거 발췌를 요구합니다.")
    if choice != CUSTOM_LENGTH:
        return choice
    custom = st.text_input("분량 직접 입력", "" if current in options else current, key=f"{prefix}_len_text_{current}",
                           placeholder="예: 3문장 이내 / 단락 1개")
    return custom.strip() or None


def _fields_popover(project, config):
    st.markdown("**비교 항목** — 이름이 아니라 지침이 AI가 가져올 것을 정합니다. 표에서 고치거나 줄을 지우고 「항목 저장」.")
    edited_fields = st.data_editor([{**f, "length": length_of(f["instruction"])} for f in config["fields"]],
                                   num_rows="dynamic", width="stretch", key="wb_fields_editor", disabled=["length"],
                                   column_config={"id": st.column_config.TextColumn("id", width="small", help="영문·숫자·하이픈"),
                                                  "name": st.column_config.TextColumn("이름", width="medium"),
                                                  "instruction": st.column_config.TextColumn("추출 지침", width="large"),
                                                  "length": st.column_config.TextColumn("분량", width="small",
                                                                                        help="아래 「분량 바꾸기」에서 고릅니다")})
    if st.button("항목 저장", key="wb_fields_save"):
        cleaned = [{"id": _slug(f.get("id") or f.get("name") or ""), "name": (f.get("name") or "").strip(), "instruction": (f.get("instruction") or "").strip()}
                   for f in edited_fields if (f.get("name") or "").strip()]
        try:
            project.save_config(config["plan"], cleaned, config["synthesis_rules"])
        except ValueError as exc:
            st.error(str(exc))
        else:
            _say(f"항목 {len(cleaned)}개를 저장했습니다. 바뀐 항목은 다음 「AI로 추출」부터 적용됩니다.")
            st.rerun()
    st.divider()
    name = st.text_input("새 항목 이름", key="wb_f_name", placeholder="예: 표본 크기")
    instruction = st.text_input("추출 지침", key="wb_f_inst", placeholder="예: 참가자 수와 모집 방법을 숫자 그대로 적는다")
    length = _length_picker("wb_f_new")
    if st.button("항목 추가", disabled=not (name.strip() and instruction.strip() and length), key="wb_f_add"):
        fields = config["fields"] + [{"id": _slug(name), "name": name.strip(), "instruction": with_length(instruction.strip(), length)}]
        project.save_config(config["plan"], fields, config["synthesis_rules"])
        _say(f"항목 「{ui.md(name.strip())}」을 추가했습니다. 표에 'AI 추출 대기' 열로 보이며, 「AI로 추출」을 다시 실행하면 채워집니다.")
        st.rerun()
    st.divider()
    st.markdown("**분량 바꾸기** — 기존 항목의 분량만 바꿉니다. 바꾼 분량은 다음 「AI로 추출」부터 적용되고, 이전 실행과 전후를 비교할 수 있습니다.")
    ids = [f["id"] for f in config["fields"]]
    target = st.selectbox("항목", ids, key="wb_f_len_target", format_func=lambda i: next(f["name"] for f in config["fields"] if f["id"] == i))
    field = next(f for f in config["fields"] if f["id"] == target)
    length = _length_picker("wb_f_len_" + target, length_of(field["instruction"]))
    if st.button("분량 적용", disabled=not length or length == length_of(field["instruction"]), key="wb_f_len_apply"):
        fields = [{**f, "instruction": with_length(f["instruction"], length)} if f["id"] == target else f for f in config["fields"]]
        project.save_config(config["plan"], fields, config["synthesis_rules"])
        _say(f"「{ui.md(field['name'])}」의 분량을 「{ui.md(length)}」로 바꿨습니다. 다음 「AI로 추출」부터 적용됩니다.")
        st.rerun()
    st.caption("질문·범위·포함 기준·읽을 쪽수는 화면 위 「질문·선별 기준 편집」에서 바꿉니다.")


def _extract_popover(project, runs, included, config):
    from deep_research.providers import agent_busy, claude_code_status, run_claude_code
    st.markdown(f"**AI로 추출** — 포함 문헌 {len(included)}편 × 항목 {len(config['fields'])}개")
    plan = config["plan"]
    st.caption(f"한 실행의 문헌 상한 {plan['max_documents']}편 · 문헌당 처음 {plan.get('max_pages_per_document', 20) or '전체'}쪽을 읽음 "
               "(「단계별 보기 → 1 · 조사 설계」에서 바꿈)")
    example = (project.root / "example-manifest.json").exists()
    if not included:
        st.warning("포함으로 둔 문헌이 없습니다. 문헌을 담은 뒤 다시 누르세요.")
        return
    st.caption("Claude Code·웹 AI에는 지정한 쪽의 원문과 조사 설정이 전달됩니다. AI 이용료와 한도는 제공자 조건을 따릅니다.")
    with st.expander("설정된 API로 추출 · 로컬 모델 또는 외부 API"):
        from .ai import api_extraction
        api_extraction(project)
    if len(included) > plan["max_documents"]:
        st.warning(f"포함 문헌 {len(included)}편이 한 실행의 상한 {plan['max_documents']}편보다 많습니다. 일부를 제외하거나 상한을 올리세요.")
        st.button("상한 바꾸러 가기 · 1 · 조사 설계", key="wb_limit_go", on_click=open_steps, args=(ui.STAGES[0],))
    _question_notice(project, config, "wb_question_go")
    if "cc_status" not in st.session_state:
        st.session_state["cc_status"] = claude_code_status()
    status = st.session_state["cc_status"]
    if status["available"]:
        st.caption("이 컴퓨터의 Claude Code를 앱이 직접 부릅니다. 문헌 3편이면 보통 3~8분.")
        busy = agent_busy(project)
        if busy:
            st.info("이 프로젝트에서 AI 실행이 진행 중입니다. 끝나면 「저장된 응답 새로 읽기」로 결과를 확인하세요.", icon=":material/hourglass_top:")
        if st.button("AI로 추출 실행", type="primary", key="wb_run_ai", width="stretch", icon=":material/auto_awesome:", disabled=busy):
            try:
                run_id = flow.prepare(project)
            except ValueError as exc:
                st.error(str(exc))
                return
            with st.spinner("Claude Code가 원문을 읽고 있습니다 · 문헌 3편이면 보통 3~8분"):
                try:
                    run_claude_code(project, run_id, "extraction")
                except ValueError as exc:
                    st.session_state["wb_pending_run"] = run_id
                    st.session_state["wb_ai_error"] = str(exc)
                    if any((project.run_dir(run_id) / "responses").glob("*.json")):
                        st.session_state["wb_route_run"] = run_id  # show what was saved before it stopped
                    if "/login" in str(exc):  # installed but signed out: show the other ways to continue
                        st.session_state["cc_status"] = {"available": False, "reason": str(exc)}
                else:
                    st.session_state["wb_route_run"] = run_id
                    st.session_state.pop("wb_ai_error", None)
                    st.session_state["wb_route"] = workspace.VIEWS[0]
                    _say("추출이 끝났습니다. 비교표에서 값을 눌러 원문과 대조하세요.")
                    st.rerun()
        pending = st.session_state.get("wb_pending_run")
        if (error := st.session_state.get("wb_ai_error")) and pending in project.runs():
            st.error(ui.md(error), icon=":material/error:")  # it quotes Claude's own words
            if flow.manifest(project, pending)["state"] == "awaiting_extraction":
                with st.expander("남은 문헌을 웹 AI(Claude·ChatGPT 등)로 이어 하기"):
                    _web_ai_pack(project, pending)
    else:
        st.warning("**이 컴퓨터에는 AI 실행 도구(Claude Code)가 없거나 로그인돼 있지 않습니다.** 아래 셋 중 하나로 진행합니다.", icon=":material/info:")
        if example:
            st.markdown("**① 예제 응답으로 비교표 보기** — 공통 사례(논문 3편)에 미리 만들어 둔 응답. 새 AI 실행이 아니며 전부 미검토 상태.")
        st.markdown("**② 쓰던 웹 AI(Claude·ChatGPT 등)에 붙여 넣기** — 문헌마다 '요청문+원문 묶음'을 복사해 붙이고, 돌아온 JSON을 아래에 붙여 넣으면 됩니다.")
        if st.button("요청문 묶음 만들기", key="wb_make_request", width="stretch"):
            try:
                st.session_state["wb_pending_run"] = flow.prepare(project)
            except ValueError as exc:
                st.error(str(exc))
        pending = st.session_state.get("wb_pending_run")
        if pending and pending in project.runs():
            _web_ai_pack(project, pending)
            with st.expander("Claude Code를 쓰는 사람에게 넘길 한 줄 요청문"):
                st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {pending}\nrequests/의 원문을 읽고 모든 문헌을 추출해 import-extraction으로 가져와 줘. 사람의 검토 상태는 바꾸지 마.",
                        language=None, wrap_lines=True)
                if st.button("새로 읽기", key="wb_reload", icon=":material/refresh:"):
                    st.rerun()
        with st.expander("③ 내 컴퓨터에 Claude Code 설치하기 · 자세히"):
            st.markdown("Claude Code는 앤트로픽의 터미널 AI 도구입니다. 설치 뒤 터미널에서 `claude`를 실행해 로그인하면, 이 버튼이 바로 실행으로 바뀝니다. "
                        "[설치 안내](https://docs.anthropic.com/claude-code) · 쓰던 Claude 계정의 사용량이 적용됩니다.  \n"
                        "Claude 데스크톱 앱에만 로그인했다면 여기서는 로그인 안 된 것으로 나옵니다. 데스크톱 앱의 로그인은 "
                        "이 앱이 실행하는 `claude` 명령으로 넘어오지 않으니, 일반 터미널에서 `claude`를 한 번 열어 /login 하세요. "
                        "그게 어렵다면 위 **②** 웹 AI 경로를 쓰면 됩니다.")
            if st.button("다시 확인", key="wb_cc_recheck"):
                st.session_state.pop("cc_status", None)
                st.rerun()
    if example:
        st.divider()
        if st.button("예제 응답으로 비교표 보기", key="wb_example", type="primary" if not status["available"] else "secondary", width="stretch"):
            from deep_research.examples import load_reference
            try:
                run_id = load_reference(project)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state["wb_route_run"] = run_id
                st.session_state["wb_route"] = workspace.VIEWS[0]
                _say("예시 응답을 넣었습니다. 비교표의 값을 눌러 원문과 대조해 보세요.")
                st.rerun()
    with st.expander("응답 JSON 올리기 · 다른 사람이 만든 응답"):
        target = st.selectbox("실행", project.runs(), key="wb_resp_run") if project.runs() else None
        files = st.file_uploader("responses/*.json", type="json", accept_multiple_files=True, key="wb_resp")
        if st.button("가져오기", disabled=not (files and target), key="wb_resp_btn"):
            for file in files:
                try:
                    flow.import_extraction(project, target, json.loads(file.getvalue()))
                except ValueError as exc:
                    st.error(f"{file.name}: {exc}")
            st.rerun()


def _web_ai_pack(project, pending):
    """One document at a time: download the request+source pack, paste the chat AI's JSON back."""
    run = flow.manifest(project, pending)
    titles = {r["source_id"]: ui.short(project.source(r["source_id"])["title"], 50) for r in run["requests"]}
    done_ids = {s for s in titles if (project.run_dir(pending) / "responses" / (s + ".json")).exists()}
    target = st.selectbox("문헌", list(titles), format_func=lambda s: ("✓ " if s in done_ids else "○ ") + titles[s], key="wb_pack_src")
    pack = flow.prompt_pack(project, pending, target)
    st.download_button(f"요청문 묶음 내려받기 · {len(pack) // 1000}천 자", pack, f"{project.root.name}_{target}_prompt.txt", key="wb_pack_dl", width="stretch", icon=":material/content_copy:")
    st.caption("받은 .txt를 웹 AI 대화창에 통째로 붙여 넣으세요(긴 글 허용 모델 권장). AI가 돌려준 JSON을 아래에 붙여 넣고 「가져오기」. 응답은 원문과 대조해 저장됩니다.")
    reply = st.text_area("AI 응답(JSON) 붙여넣기", key="wb_pack_reply", height=120, placeholder='{"request_id": "...", "rows": [...]}')
    if st.button("가져오기", key="wb_pack_import", disabled=not reply.strip()):
        try:
            text = reply.strip()
            if text.startswith("```"):
                text = text.strip("`").split("\n", 1)[-1].rsplit("```", 1)[0]
            flow.import_extraction(project, pending, json.loads(text))
        except (ValueError, json.JSONDecodeError) as exc:
            st.error(f"가져오지 못했습니다: {exc}")
        else:
            st.session_state["wb_route_run"] = pending
            st.session_state["wb_route"] = workspace.VIEWS[0]
            st.session_state["wb_clear_reply"] = True
            _say(f"{ui.md(titles[target])} 응답을 가져왔습니다. 남은 문헌도 같은 방법으로.")
            st.rerun()


def _export_popover(project, runs):
    if not runs:
        st.caption("추출 결과가 생기면 여기서 내려받습니다.")
        return
    run_id = st.session_state.get("wb_run") if st.session_state.get("wb_run") in runs else runs[0]
    stem = f"{project.root.name}_{run_id}"
    include_pdfs = st.checkbox("원본 PDF도 ZIP에 포함", key="wb_zip_pdf")
    st.download_button("결과 ZIP · 보고서 + 표 CSV + JSON", export_zip(project, run_id, include_pdfs), f"{stem}.zip", type="primary", width="stretch", key="wb_zip", icon=":material/folder_zip:")
    st.download_button("보고서만 · Markdown", report(project, run_id), f"{stem}.md", width="stretch", key="wb_md", icon=":material/description:")
    st.download_button("참고문헌 목록 · 텍스트", bibliography(project, run_id), f"{stem}_references.txt", width="stretch", key="wb_bib", icon=":material/format_list_numbered:")
    st.caption("한글·Word에는 ZIP 안 comparison.csv(문헌×항목)·evidence.csv(근거별 기록)를 엑셀로 열어 붙이는 것이 가장 쉽습니다.")


def _synthesis_controls(project, run_id):
    from deep_research.providers import claude_code_status, run_claude_code
    approved = flow.accepted(project, run_id)
    st.markdown(f"**종합문(선택)** · 채택 근거 {len(approved)}건으로 AI 초안")
    st.caption("실행하면 채택한 값·발췌·조사 설정을 Claude Code에 전달합니다. 이용 조건과 사용량이 적용됩니다.")
    if st.button("종합 요청 만들기", disabled=not approved, key="wb_synth"):
        flow.prepare_synthesis(project, run_id)
        status = claude_code_status()
        if status["available"]:
            with st.spinner("Claude Code가 채택 근거를 종합하는 중"):
                try:
                    run_claude_code(project, run_id, "synthesis")
                except ValueError as exc:
                    st.error(ui.md(str(exc)))  # no rerun: it would clear the message
                else:
                    st.rerun()
        else:
            st.warning(status["reason"] + " 요청문은 「단계별 보기 → 5 · 종합」에 있습니다.")
    if flow.current_synthesis(project, run_id):
        st.success("종합문이 준비됐습니다. 「종합·출처」 탭에서 각 주장의 근거를 확인하세요.")


def reset_design(project):
    project.save_config(dict(DEFAULT_PLAN), [dict(f) for f in DEFAULT_FIELDS], DEFAULT_RULES)


def project_title(project):
    return read_json(project.root / "project.json")["title"]
