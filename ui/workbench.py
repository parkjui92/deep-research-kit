"""The default working screen: a literature × item comparison table first, the PDF next to it.

Rayyan/Covidence/Elicit all put the thing the researcher is making (the table) in the middle and
tuck the process (search, runs, settings) into actions around it. The six stage pages remain as the
step-by-step learning mode; everything here calls the same core."""
from __future__ import annotations

import json
import re

import streamlit as st

from deep_research import workflow as flow
from deep_research.exports import bibliography, citation, display_value, export_zip, report
from deep_research.project import (
    DEFAULT_FIELDS,
    DEFAULT_PLAN,
    DEFAULT_RULES,
    has_no_text,
    no_text_note,
    read_json,
)

from . import chrome as ui

CELL_TONE = {"accept": "go", "edit": "edit", "hold": "wait", "reject": "stop", "pending": "todo"}

GLYPH = {"pending": "○", "accept": "✓", "edit": "✎", "hold": "⏸", "reject": "✗"}
REVIEW_CHOICES = {"accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외"}
LEGEND = "○ 미검토 · ✓ 채택 · ✎ 수정 후 채택 · ⏸ 보류 · ✗ 제외 · — 읽은 범위에서 못 찾음 · ? 원문 위치 미확인"


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
    return f"{mark} {ui.short(display_value(row) or '', 60)}"


def _slug(name):
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or "item-" + str(abs(hash(name)) % 10000)


def _say(message):
    """Success feedback where the person is looking: toast (bottom-right) plus the top banner."""
    st.session_state["flash"] = message
    st.toast(message, icon=":material/check_circle:")


def workbench(project):
    runs = _answered_runs(project)
    all_runs = project.runs()
    for key in ("wb_run", "wb_pending_run", "wb_resp_run"):
        if st.session_state.get(key) and st.session_state[key] not in all_runs:
            st.session_state.pop(key, None)
    if st.session_state.pop("wb_scroll_top", False) or not st.session_state.get("wb_seen"):
        st.session_state["wb_seen"] = True
        ui.scroll_top()
    sources = project.catalog()
    included = [s for s in sources if s["decision"] == "include"]
    config = project.config()
    _action_bar(project, runs, included, config)
    if note := no_text_note([s for s in sources if s["decision"] != "exclude"]):
        st.warning(note, icon=":material/scanner:")
    search_results_panel(project)
    if not runs:
        _onboarding(project, sources, included)
        return
    if st.session_state.get("wb_run") not in runs:
        st.session_state["wb_run"] = runs[0]
    run_id = st.session_state["wb_run"]
    run = flow.manifest(project, run_id)
    rows = flow.evidence(project, run_id)
    run_fields = run["config"]["fields"]
    run_field_ids = {f["id"] for f in run_fields}
    # Columns = items in the current design; items added after this run show as "AI 추출 대기".
    fields = run_fields + [f for f in config["fields"] if f["id"] not in run_field_ids]
    run_source_ids = {s["id"] for s in run["sources"]}
    new_sources = [s for s in included if s["id"] not in run_source_ids]
    waiting = [c for c in project.collection() if c.get("status") == "pdf_missing"]
    by_key = {(r["source_id"], r["field_id"]): r for r in rows}
    kept = sum(r["review"]["status"] in {"accept", "edit"} for r in rows)
    pending = sum(r["review"]["status"] == "pending" for r in rows)
    missing = sum(r["value"] is None for r in rows)
    chips = [("문헌", f"{len(run['sources']) + len(new_sources)}편" + (f" · PDF 없음 {len(waiting)}" if waiting else "")),
             ("항목", f"{len(fields)}개" + (f" · 추출 대기 {len(fields) - len(run_fields)}" if len(fields) > len(run_fields) else "")),
             ("채택", f"{kept}/{len(rows)}"), ("미검토", pending), ("못 찾음", missing)]
    if new_sources or len(fields) > len(run_fields):
        st.info(f"새로 더한 문헌 {len(new_sources)}편 · 항목 {len(fields) - len(run_fields)}개는 아직 AI가 읽지 않았습니다. 「AI로 추출」을 다시 실행하면 채워집니다(이전 실행과 검토 기록은 보존).", icon=":material/info:")
    chips_html = "".join(f'<span class="drk-chip"><span class="k">{k}</span><span class="v">{v}</span></span>' for k, v in chips)
    top_l, top_r = st.columns([3, 1.4])
    top_l.markdown('<div class="drk-chips">' + chips_html + "</div>", unsafe_allow_html=True)
    if len(runs) > 1:
        top_r.selectbox("실행", runs, key="wb_run", format_func=lambda r: ui.local_time(flow.manifest(project, r)["created_at"]) + " · " + r[-6:],
                        label_visibility="collapsed")
    # ---- comparison table (row = document, column = item). Each cell is a button: one click
    # opens the value next to its source. (st.dataframe can select rows or columns, not a cell.)
    ids = [r["id"] for r in rows]
    if (jump := st.session_state.pop("wb_next", None)) in ids:
        st.session_state["wb_pick"] = jump
    if st.session_state.get("wb_pick") not in ids:
        st.session_state["wb_pick"] = next((r["id"] for r in rows if r["review"]["status"] == "pending"), ids[0] if ids else None)
    if not ids:
        ui.empty("이 실행에는 추출값이 없습니다.", "「AI로 추출」을 다시 실행하세요.")
        return
    st.caption("비교표 · " + LEGEND + " · 칸을 누르면 아래에 원문과 수정란이 열립니다")
    widths = [1.3] + [1.0] * len(fields)
    with st.container(key="drk-grid"):
        head = st.columns(widths, gap="small")
        head[0].markdown('<div class="drk-th">문헌</div>', unsafe_allow_html=True)
        for col, field in zip(head[1:], fields):
            col.markdown(f'<div class="drk-th" title="{field["instruction"]}">{field["name"]}</div>', unsafe_allow_html=True)
        for source in run["sources"]:
            cols = st.columns(widths, gap="small")
            bib = project.with_bib(source).get("bib") or {}
            meta = " · ".join(x for x in (ui.short(", ".join(bib.get("authors", [])[:2]), 30), str(bib.get("year") or "")) if x)
            cols[0].markdown(f'<div class="drk-td-title" title="{source["title"]}">{ui.short(source["title"], 56)}<span>{meta}</span></div>', unsafe_allow_html=True)
            for col, field in zip(cols[1:], fields):
                cell = by_key.get((source["id"], field["id"]))
                if cell is None:
                    col.markdown('<div class="drk-td-empty">AI 추출 대기</div>', unsafe_allow_html=True)
                    continue
                selected = cell["id"] == st.session_state["wb_pick"]
                tone = "none" if cell["value"] is None else CELL_TONE.get(cell["review"]["status"], "todo")
                with col.container(key=f"tone-{tone}-{cell['id']}"):
                    if st.button(_cell(cell) or "—", key="cell-" + cell["id"], width="stretch", type="primary" if selected else "secondary",
                                 help=(cell["value"] or "읽은 범위에서 찾지 못함") + f"\n\n검토: {ui.word(ui.REVIEW, cell['review']['status'])}"):
                        st.session_state["wb_pick"] = cell["id"]
                        st.session_state["wb_scroll_top"] = True
                        st.rerun()
        for source in new_sources:
            cols = st.columns(widths, gap="small")
            cols[0].markdown(f'<div class="drk-td-title" title="{source["title"]}">{ui.short(source["title"], 56)}<span>새 문헌 · 포함</span></div>', unsafe_allow_html=True)
            for col in cols[1:]:
                col.markdown('<div class="drk-td-empty">AI 추출 대기</div>', unsafe_allow_html=True)
        for cand in waiting:
            cols = st.columns(widths, gap="small")
            link = cand.get("url") or ("https://doi.org/" + cand["doi"] if cand.get("doi") else "")
            cols[0].markdown(f'<div class="drk-td-title">{ui.short(cand["title"], 56)}<span>PDF 없음 · <a href="{link}" target="_blank">원문 링크</a> → 「PDF 가져오기」로 올리면 묶입니다</span></div>', unsafe_allow_html=True)
            for col in cols[1:]:
                col.markdown('<div class="drk-td-empty">—</div>', unsafe_allow_html=True)
    row = next(r for r in rows if r["id"] == st.session_state["wb_pick"])
    source = project.with_bib(next(s for s in run["sources"] if s["id"] == row["source_id"]))
    field_name = next(f["name"] for f in fields if f["id"] == row["field_id"])
    left, right = st.columns([1, 1.5], gap="large")
    with left:
        _detail(project, run_id, row, source, field_name, rows)
    with right:
        if row["locators"]:
            pick = st.selectbox("원문 자리", range(len(row["locators"])), format_func=lambda i: f"{i + 1} · PDF {row['locators'][i]['page']}쪽",
                                key="wb_loc_" + row["id"], label_visibility="collapsed") if len(row["locators"]) > 1 else 0
            locator = row["locators"][pick]
            ui.show_pdf(project, row["source_id"], [locator], page=locator["page"] or 1, identity="wb-" + row["id"],
                        caption="주황 테두리 = AI가 이 값을 뽑아낸 원문 문장. 자리가 맞다는 뜻이지 값이 옳다는 뜻은 아닙니다.")
        else:
            ui.show_pdf(project, row["source_id"], identity="wb-" + row["id"], caption="이 항목은 읽은 범위에서 찾지 못했습니다. 원문을 넘기며 직접 확인하세요.")


def _detail(project, run_id, row, source, field_name, rows):
    with st.container(border=True):
        a, b = st.columns(2)
        with a:
            ui.badge(ui.MATCH, row["match_status"])
        with b:
            ui.badge(ui.REVIEW, row["review"]["status"])
        st.markdown(f"**{field_name}** · {ui.short(source['title'], 60)}")
        st.markdown(f'<div class="drk-value">{row["value"] or "읽은 범위에서 찾지 못함"}</div>', unsafe_allow_html=True)
        for locator in row["locators"]:
            st.markdown(f'<div class="drk-quote">{locator["quote"]}</div><div class="drk-meta">PDF {locator["page"]}쪽 · {ui.code_word(locator["status"])}</div>',
                        unsafe_allow_html=True)
        if row["value"] is None:
            st.caption(f"읽은 범위 PDF {row['page_scope']['from']}~{row['page_scope']['to']}쪽 / 전체 {row['page_scope']['total']}쪽. "
                       "범위 밖에 있을 수 있습니다 — 설계에서 읽을 쪽수를 0(전체)으로 두고 다시 추출하면 확인됩니다.")
        with st.form("wb-review-" + row["id"]):
            previous = row["review"]["status"] if row["review"]["status"] in REVIEW_CHOICES else None
            status = st.radio("이 값을", list(REVIEW_CHOICES), index=list(REVIEW_CHOICES).index(previous) if previous else None,
                              format_func=REVIEW_CHOICES.get, horizontal=True,
                              help="채택 = 원문과 맞아 그대로 씀 · 수정 후 채택 = 고쳐 씀(원래 값 보존) · 보류 = 더 확인 · 제외 = 원문과 다르거나 쓸 수 없음")
            checked = st.checkbox("원문의 앞뒤 문맥을 읽고 판단했습니다 (채택·수정 후 채택에 필수)")
            value = st.text_area("수정한 값 (수정 후 채택일 때)", row["review"].get("edited_value") or row["value"] or "", height=70)
            note = st.text_input("이유 한 줄 (필수)", row["review"].get("note", ""), placeholder="예: 표 3의 값과 일치 / 단위가 빠져 보완")
            reviewer = st.text_input("검토자 (필수 · 한 번 적으면 이 프로젝트에 기억)", st.session_state.get("reviewer") or project.reviewer())
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
                        flow.review(project, run_id, row["id"], status, note, reviewer, value)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["reviewer"] = reviewer
                        project.remember_reviewer(reviewer)
                        after = [r["id"] for r in rows if r["review"]["status"] == "pending" and r["id"] != row["id"]]
                        st.session_state["wb_next"] = after[0] if after else row["id"]
                        st.session_state["wb_scroll_top"] = True
                        _say(f"저장했습니다 · {field_name} → {REVIEW_CHOICES[status]}" + ("" if after else " · 미검토가 없습니다. 내보내기로 가세요."))
                        st.rerun()
        with st.expander("인용 문장 복사", icon=":material/format_quote:"):
            st.code(citation(source, row), language=None)
            st.caption("저자·연도·게재지는 DOI로 받아 온 서지 정보입니다. 쪽수는 PDF 파일 기준이라 인쇄 쪽과 다를 수 있습니다.")


def _onboarding(project, sources, included):
    with st.container(border=True):
        st.markdown("**비교표가 아직 없습니다.** 순서대로 하면 몇 분 안에 첫 표가 나옵니다.")
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"**① 문헌 모으기**  \n위 「문헌 찾기」에서 검색해 담거나 「PDF 가져오기」로 올립니다.  \n지금 {len(sources)}편")
        c2.markdown(f"**② 쓸 논문 고르기**  \n문헌마다 포함·제외를 정합니다(「단계별 보기 → 2 · 문헌 선별」).  \n지금 포함 {len(included)}편")
        c3.markdown("**③ AI로 추출**  \n위 「AI로 추출」. Claude Code가 있으면 바로, 없으면 요청문 복사 또는 예제 응답.")
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
    c1, c2, c3, c4, c5, c6 = st.columns([1, 1, 1, 1.1, 1, 1])
    with c1, st.popover("문헌 찾기", icon=":material/search:", width="stretch"):
        _search_popover(project)
    with c2, st.popover("PDF 가져오기", icon=":material/upload_file:", width="stretch"):
        _import_popover(project)
    with c3, st.popover("항목 추가", icon=":material/view_column:", width="stretch"):
        _fields_popover(project, config)
    with c4, st.popover("AI로 추출", icon=":material/auto_awesome:", width="stretch"):
        _extract_popover(project, runs, included, config)
    with c5, st.popover("내보내기", icon=":material/download:", width="stretch"):
        _export_popover(project, runs)
    with c6:
        if st.button("단계별 보기", icon=":material/school:", width="stretch", help="조사 설계·선별·검토를 한 단계씩 따라가는 학습 모드"):
            st.session_state["mode"] = st.session_state["mode_pick"] = "단계별(학습)"
            st.rerun()


def _search_popover(project):
    from deep_research.providers import search_literature
    st.markdown("**무료 색인에서 찾아 담기** — OpenAlex(전 분야)·arXiv·Crossref")
    query = st.text_input("검색어", key="wb_q", placeholder="예: generative AI knowledge work productivity experiment")
    providers = st.multiselect("어디서", ["OpenAlex", "arXiv", "Crossref"], default=["OpenAlex"], key="wb_prov")
    a, b = st.columns(2)
    year_from = a.number_input("발행연도 이후 (0=전체)", 0, 2100, 0, key="wb_year")
    limit = b.number_input("최대 건수", 5, 50, 20, key="wb_limit")
    if st.button("검색", disabled=not query.strip(), key="wb_search_btn"):
        try:
            results = search_literature(project, query, providers or ["OpenAlex"], limit)
        except ValueError as exc:
            st.error(str(exc))
        else:
            if year_from:
                results = [r for r in results if (r.get("year") or 0) >= year_from]
            seen, unique = set(), []
            for r in results:  # preprint + published copies collapse into one row (OA pdf wins)
                key = re.sub(r"[^a-z0-9]", "", r["title"].lower())[:80]
                if key in seen:
                    continue
                seen.add(key)
                unique.append(r)
            st.session_state["wb_results"] = unique
    results = st.session_state.get("wb_results") or []
    if results:
        st.caption(f"{len(results)}건을 찾았습니다. 팝업을 닫으면 본문에 넓은 표로 보이며 거기서 담습니다.")
    return


def search_results_panel(project):
    """Search hits are shown in the main column (a popover is too narrow for title·venue·year·OA)."""
    from deep_research.providers import collect
    results = st.session_state.get("wb_results") or []
    if not results:
        return
    with st.container(border=True):
        head, close = st.columns([5, 1.4])
        head.markdown(f"**검색 결과 {len(results)}건** — 담을 문헌에 표시하고 「담기」. 오픈액세스(OA)는 PDF가 바로 등록됩니다.")
        if close.button("닫기", key="wb_results_close", icon=":material/close:", width="stretch"):
            st.session_state["wb_results"] = []
            st.rerun()
        edited = st.data_editor([{"담기": False, "제목": r["title"], "저자": ", ".join(r["authors"][:3]) + (" 외" if len(r["authors"]) > 3 else ""),
                                  "연도": r.get("year"), "학술지": r.get("venue", ""), "피인용": r.get("cited_by"), "PDF": "OA" if r.get("pdf_url") or r.get("oa") else "",
                                  "DOI": r.get("doi", "")} for r in results],
                                hide_index=True, width="stretch", key="wb_results_editor", disabled=["제목", "저자", "연도", "학술지", "피인용", "PDF", "DOI"],
                                height=min(80 + 36 * len(results), 520),
                                column_config={"담기": st.column_config.CheckboxColumn(width="small", help="칸을 한 번 눌러 표시(두 번 보이면 한 번 더)"),
                                               "제목": st.column_config.TextColumn(width="large"), "DOI": st.column_config.TextColumn(width="small")})
        chosen = [results[i] for i, r in enumerate(edited) if r.get("담기")]
        if st.button(f"선택한 {len(chosen)}건 담기 · 오픈액세스 PDF는 바로 등록", disabled=not chosen, key="wb_collect", type="primary"):
            added, missing = [], []
            with st.spinner("PDF를 받아 색인하는 중"):
                for cand in chosen:
                    record = collect(project, cand)
                    (added if record["status"] == "added" else missing).append(record)
            msg = f"PDF 등록 {len(added)}건"
            if missing:
                msg += f" · 서지만 담김 {len(missing)}건 — 비교표 아래 'PDF 없음' 줄의 원문 링크로 직접 받아 「PDF 가져오기」에 올리세요"
            _say(msg)
            st.session_state["wb_results"] = []
            st.rerun()
    pending = [c for c in project.collection() if c.get("status") == "pdf_missing"]
    if pending:
        st.markdown("**PDF가 아직 없는 문헌**")
        for c in pending[:10]:
            st.markdown(f"- [{ui.short(c['title'], 70)}]({c.get('url') or 'https://doi.org/' + (c.get('doi') or '')}) · {c.get('year') or ''}")


def _import_popover(project):
    from deep_research.providers import collect, parse_bibtex, parse_ris
    st.markdown("**내 PDF 올리기**")
    files = st.file_uploader("PDF (여러 개 가능)", type="pdf", accept_multiple_files=True, key="wb_pdfs")
    if st.button("등록", disabled=not files, key="wb_pdf_add"):
        for file in files:
            with st.spinner(file.name + " 색인 중"):
                project.add_pdf(file.getvalue(), file.name)
        _say(f"PDF {len(files)}건을 등록했습니다. 포함·제외는 「단계별 보기 → 2 · 문헌 선별」에서, 또는 아래 일괄 포함으로.")
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


def _fields_popover(project, config):
    st.markdown("**비교 항목** — 이름이 아니라 지침이 AI가 가져올 것을 정합니다. 표에서 고치거나 줄을 지우고 「항목 저장」.")
    edited_fields = st.data_editor(config["fields"], num_rows="dynamic", width="stretch", key="wb_fields_editor",
                                   column_config={"id": st.column_config.TextColumn("id", width="small", help="영문·숫자·하이픈"),
                                                  "name": st.column_config.TextColumn("이름", width="medium"),
                                                  "instruction": st.column_config.TextColumn("추출 지침", width="large")})
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
    if st.button("항목 추가", disabled=not (name.strip() and instruction.strip()), key="wb_f_add"):
        fields = config["fields"] + [{"id": _slug(name), "name": name.strip(), "instruction": instruction.strip()}]
        project.save_config(config["plan"], fields, config["synthesis_rules"])
        _say(f"항목 「{name.strip()}」을 추가했습니다. 표에 'AI 추출 대기' 열로 보이며, 「AI로 추출」을 다시 실행하면 채워집니다.")
        st.rerun()
    st.caption("질문·범위·포함 기준·읽을 쪽수는 「단계별 보기 → 1 · 조사 설계」에서 바꿉니다.")


def _extract_popover(project, runs, included, config):
    from deep_research.providers import agent_busy, claude_code_status, run_claude_code
    st.markdown(f"**AI로 추출** — 포함 문헌 {len(included)}편 × 항목 {len(config['fields'])}개")
    example = (project.root / "example-manifest.json").exists()
    if not included:
        st.warning("포함으로 둔 문헌이 없습니다. 문헌을 담은 뒤 다시 누르세요.")
        return
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
                    st.error(str(exc))
                    st.session_state["wb_pending_run"] = run_id
                    if "/login" in str(exc):  # installed but signed out: show the other ways to continue
                        st.session_state["cc_status"] = {"available": False, "reason": str(exc)}
                    return
            st.session_state["wb_run"] = run_id
            _say("추출이 끝났습니다. 비교표에서 값을 눌러 원문과 대조하세요.")
            st.rerun()
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
                    st.session_state["wb_run"] = pending
                    st.session_state.pop("wb_pack_reply", None)
                    _say(f"{titles[target]} 응답을 가져왔습니다. 남은 문헌도 같은 방법으로.")
                    st.rerun()
            with st.expander("Claude Code를 쓰는 사람에게 넘길 한 줄 요청문"):
                st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {pending}\nrequests/의 원문을 읽고 모든 문헌을 추출해 import-extraction으로 가져와 줘. 사람의 검토 상태는 바꾸지 마.",
                        language=None, wrap_lines=True)
                if st.button("새로 읽기", key="wb_reload", icon=":material/refresh:"):
                    st.rerun()
        with st.expander("③ 내 컴퓨터에 Claude Code 설치하기 · 자세히"):
            st.markdown("Claude Code는 앤트로픽의 터미널 AI 도구입니다. 설치 뒤 터미널에서 `claude`를 실행해 로그인하면, 이 버튼이 바로 실행으로 바뀝니다. "
                        "[설치 안내](https://docs.anthropic.com/claude-code) · 쓰던 Claude 계정의 사용량이 적용됩니다.")
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
                st.session_state["wb_run"] = run_id
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
    st.divider()
    from deep_research.providers import claude_code_status, run_claude_code
    approved = flow.accepted(project, run_id)
    st.markdown(f"**종합문(선택)** · 채택 근거 {len(approved)}건으로 AI 초안")
    if st.button("종합 요청 만들기", disabled=not approved, key="wb_synth"):
        flow.prepare_synthesis(project, run_id)
        status = claude_code_status()
        if status["available"]:
            with st.spinner("Claude Code가 채택 근거를 종합하는 중"):
                try:
                    run_claude_code(project, run_id, "synthesis")
                except ValueError as exc:
                    st.error(str(exc))
            st.rerun()
        else:
            st.warning(status["reason"] + " 요청문은 「단계별 보기 → 5 · 종합」에 있습니다.")
    current = flow.current_synthesis(project, run_id)
    if current:
        for claim in current["claims"]:
            st.markdown(f"- **{claim['kind']}** {claim['text']}")


def reset_design(project):
    project.save_config(dict(DEFAULT_PLAN), [dict(f) for f in DEFAULT_FIELDS], DEFAULT_RULES)


def project_title(project):
    return read_json(project.root / "project.json")["title"]
