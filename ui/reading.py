"""A useful research workflow even when no AI provider is connected."""
from __future__ import annotations

import hashlib

import streamlit as st

from deep_research import integrity, notebook
from deep_research.exports import citation
from deep_research.project import read_json

from . import chrome as ui
from . import translation
from .research import candidate_label, highlight, query_terms


def _candidate_table_pick(table_key, keys):
    rows = st.session_state.get(table_key, {}).get("selection", {}).get("rows", [])
    if rows and 0 <= rows[0] < len(keys):
        st.session_state["wb_candidate"] = keys[rows[0]]


def _candidate_picker_changed():
    # Native table selection is read-only; a fresh table clears its old highlight.
    st.session_state["wb_candidate_table_epoch"] = st.session_state.get("wb_candidate_table_epoch", 0) + 1


def _clear_candidate_filters():
    st.session_state.update(wb_candidate_query="", wb_candidate_reading=None, wb_candidate_text=None)


def candidate_queue(project):
    from deep_research.providers import collect

    items = project.collection()
    st.header("읽기 후보함", anchor=False)
    st.caption("검색을 바꿔도 남습니다. 읽기 우선순위는 문헌의 포함·제외 판단과 별도입니다.")
    if not items:
        st.info("문헌 검색에서 후보를 담으세요. PDF를 받기 전에 먼저 읽을 이유를 정리할 수 있습니다.")
        return
    order = {"next": 0, "later": 1, "done": 2}
    items.sort(key=lambda x: order.get((x.get("reading") or {}).get("state", "next"), 0))
    catalog = {s["id"]: s for s in project.catalog()}
    a, b, c = st.columns([2, 1, 1])
    query = a.text_input("후보 안에서 검색", placeholder="제목·초록·읽을 이유·저자·DOI", key="wb_candidate_query")
    reading = b.selectbox("읽기 상태", [None, *notebook.READING_STATES], key="wb_candidate_reading",
                          format_func=lambda value: notebook.READING_STATES.get(value, "모든 상태"))
    text_state = c.selectbox("원문 확보", [None, *notebook.TEXT_STATES], key="wb_candidate_text",
                             format_func=lambda value: notebook.TEXT_STATES.get(value, "모든 원문"))
    terms = query.casefold().split()
    visible = [i for i in items
               if (reading is None or (i.get("reading") or {}).get("state", "next") == reading)
               and (text_state is None or notebook.text_status(i, catalog) == text_state)
               and all(term in " ".join([i["title"], i.get("abstract") or "", i.get("doi") or "",
                                          " ".join(i.get("authors") or []),
                                          (i.get("reading") or {}).get("reason", "")]).casefold() for term in terms)]
    st.caption(f"후보 {len(visible)}편 / 전체 {len(items)}편 · 표에서 한 행을 선택하면 아래에서 읽을 이유와 원문을 확인합니다.")
    if not visible:
        st.info("조건에 맞는 후보가 없습니다. 후보는 그대로 보관되어 있습니다.")
        st.button("후보 필터 초기화", key="wb_candidate_reset", on_click=_clear_candidate_filters)
        return
    keys = [notebook.candidate_key(i) for i in visible]
    if st.session_state.get("wb_candidate") not in keys:
        st.session_state["wb_candidate"] = keys[0]
    signature = hashlib.sha256("\n".join(keys).encode()).hexdigest()[:12]
    table_key = f"wb_candidate_table_{signature}_{st.session_state.get('wb_candidate_table_epoch', 0)}"
    st.dataframe([{"선택": "선택됨" if notebook.candidate_key(i) == st.session_state["wb_candidate"] else "",
                   "문헌": i["title"],
                   "원문": notebook.TEXT_STATES[notebook.text_status(i, catalog)],
                   "철회·정정": integrity.label(notebook.candidate_integrity(i, catalog)),
                   "읽기": notebook.READING_STATES.get((i.get("reading") or {}).get("state", "next")),
                   "연도": i.get("year"),
                   "읽을 이유·메모": (i.get("reading") or {}).get("reason", "")} for i in visible],
                 hide_index=True, width="stretch", height=min(70 + len(visible) * 36, 300),
                 key=table_key, selection_mode="single-row", on_select=lambda: _candidate_table_pick(table_key, keys),
                 column_config={"문헌": st.column_config.TextColumn(width="large"),
                                "선택": st.column_config.TextColumn(width="small")})
    st.caption("원문: 본문 확보 · 글자 없는 PDF(스캔본, 검색·추출 불가) · 초록만 · 미확보. 초록만 읽은 후보를 본문 근거로 쓰지 마세요.")
    a, b = st.columns(2)
    with a.popover("후보 선택", help="키보드 또는 좁은 화면에서 제목으로 후보를 선택합니다."):
        key = st.selectbox("살펴볼 후보", keys, key="wb_candidate", on_change=_candidate_picker_changed,
                           format_func=lambda k: candidate_label(next(i for i in visible if notebook.candidate_key(i) == k)))
    with b.popover("보이는 후보 일괄 작업"):
        st.caption(f"현재 필터에 맞는 후보 {len(visible)}편에만 적용합니다.")
        with_doi = [i for i in visible if i.get("doi")]
        if with_doi and st.button(f"DOI가 있는 후보 {len(with_doi)}편 철회·정정 확인", key="wb_integrity_candidates",
                              icon=":material/fact_check:", help="Crossref에 DOI만 보내 철회·정정·우려 표명 고지를 조회합니다. Crossref에 없는 DOI(arXiv 등)는 OpenAlex의 철회 표시만 봅니다."):
            _check_candidates(project, with_doi, catalog)
            st.rerun()
        waiting = [i for i in visible if i.get("source_id") not in catalog and (i.get("reading") or {}).get("state", "next") != "done"]
        if waiting and st.button(f"PDF 없는 후보 {len(waiting)}편 공개 PDF 한꺼번에 찾기", key="wb_collect_all",
                             icon=":material/download:", help="후보마다 공개 사본(OA 주소·arXiv·Unpaywall 등)을 찾아 등록합니다. "
                             "'읽음'으로 둔 후보는 빼고, 받지 못한 것은 「PDF를 아직 받지 못한 문헌」에 남습니다."):
            _collect_all(project, waiting)
            st.rerun()
    item = next(i for i in visible if notebook.candidate_key(i) == key)
    state = item.get("reading") or {}
    st.markdown("**선택한 후보 · " + ui.md(item["title"]) + "**")
    st.caption(notebook.READING_STATES.get(state.get("state", "next"), "먼저 읽기")
               + " · " + notebook.TEXT_STATES[notebook.text_status(item, catalog)])
    if item.get("status") == "pdf_missing" and item.get("source_id") not in catalog:
        from deep_research.acquire import attempts_summary

        st.warning("공개 PDF를 확보하지 못했습니다. 후보와 읽을 이유는 저장되어 있습니다.")
        st.caption("시도 결과 · " + attempts_summary(item.get("attempts", [])))
        st.caption("아래 ‘출처 열기’에서 직접 받은 PDF를 등록하거나, 문헌 검색으로 돌아가 다른 공개 판본을 찾아보세요.")
        if st.button("PDF 직접 가져오기로 이동", key="wb_candidate_import"):
            st.session_state["wb_library_route"] = "내 PDF"
            st.session_state["flash"] = "‘PDF·참고문헌 가져오기’에서 받은 PDF를 선택하고 ‘등록’을 누르세요."
            st.rerun()
    ui.integrity_note(notebook.candidate_integrity(item, catalog), "철회·정정 · ")
    terms = query_terms(item.get("discovered_in"))
    ko = translation.cache(project)
    translation.show(ko, item["title"])
    if item.get("abstract"):
        st.markdown(f'<div class="drk-abstract">{highlight(item["abstract"], terms)}</div>', unsafe_allow_html=True)
        translation.show(ko, item["abstract"])
        if terms:
            st.caption("노란 표시는 이 후보를 찾은 검색어가 나온 자리입니다. 관련성 판단이 아니니 읽을 이유는 직접 적으세요.")
    else:
        st.markdown("초록 정보가 없습니다. 출처에서 내용을 확인하세요.")
    if item.get("discovered_in"):
        st.caption("발견한 검색어 · " + ui.md(" / ".join(item["discovered_in"])))
    a, b = st.columns(2)
    with a:
        translation.control(project, [item["title"], item.get("abstract", "")], "cand_" + key, "이 후보의 영문 한글 번역", paste=False)
    with b:
        translation.control(project, [t for i in visible for t in (i["title"], i.get("abstract", ""))], "cand_all",
                            "보이는 후보의 영문 한글 번역")
    with st.form("wb_reading_" + key):
        status = st.radio("읽기 우선순위", list(notebook.READING_STATES),
                          index=list(notebook.READING_STATES).index(state.get("state", "next")),
                          format_func=notebook.READING_STATES.get, horizontal=True)
        reason = st.text_area("읽을 이유·메모", state.get("reason", ""), height=80,
                              placeholder="예: 조사 대상이 같음 / 기존 연구와 다른 측정 방법 / 한계 확인")
        if st.form_submit_button("후보 메모 저장", type="primary"):
            notebook.update_reading(project, key, status, reason)
            st.session_state["flash"] = "후보 메모를 저장했습니다."
            st.rerun()
    a, b = st.columns(2)
    url = ui.safe_url(item.get("url") or ("https://doi.org/" + item["doi"] if item.get("doi") else ""))
    if url:
        a.link_button("출처 열기", url, width="stretch")
    if item.get("source_id") in catalog:
        if b.button("내 PDF에서 읽기", type="primary", width="stretch"):
            st.session_state["wb_read_source"] = item["source_id"]
            st.session_state["wb_library_route"] = "원문 검색·노트"
            st.session_state.pop("wb_local_results", None)
            st.rerun()
    elif b.button("공개 PDF 찾아 등록", type="primary", width="stretch"):
        try:
            with st.spinner("공개 원문을 찾는 중 · 이 문헌에 한해 외부 자료원에 연결합니다"):
                result = collect(project, item)
        except (ValueError, OSError) as exc:
            st.error("PDF를 등록하지 못했습니다: " + ui.md(str(exc)))
            st.caption("후보와 읽기 메모는 남아 있습니다. 다시 시도하거나 「내 PDF」에서 다른 파일을 가져오세요.")
        else:
            if result.get("source_id"):
                st.session_state["flash"] = "PDF를 등록했습니다."
            st.rerun()


def _collect_all(project, items):
    from deep_research.providers import collect
    bar = st.progress(0.0, text=f"0/{len(items)}편 · 공개 PDF를 찾는 중")
    got = 0
    for n, item in enumerate(items, 1):
        try:
            got += bool(collect(project, item).get("source_id"))
        except (ValueError, OSError):
            pass  # a broken or duplicate file: the candidate stays as it was
        bar.progress(n / len(items), text=f"{n}/{len(items)}편 · PDF {got}편 등록")
    st.session_state["flash"] = (f"{len(items)}편 가운데 {got}편의 PDF를 등록했습니다."
                                 + (f" 나머지 {len(items) - got}편은 「PDF를 아직 받지 못한 문헌」에서 내 브라우저로 받으세요."
                                    if got < len(items) else ""))


def _check_candidates(project, items, catalog):
    with st.spinner("Crossref에서 철회·정정 고지를 조회하는 중"):
        records = []
        for item in items:
            previous = notebook.candidate_integrity(item, catalog) or {}
            record = integrity.check_doi(item["doi"], previous=previous)
            project.set_candidate_integrity(notebook.candidate_key(item), record)
            if item.get("source_id") in catalog:
                project.set_integrity(item["source_id"], record)
            records.append(record)
    found = integrity.flagged(records)
    failed = sum(r.get("check_status", r["status"]) == "unknown" for r in records)
    message = f"{len(records)}편 확인 · 철회·정정·우려 고지 {len(found)}편" + (f" · 조회 실패 {failed}편" if failed else "")
    st.session_state["flash"] = message + ". 고지가 없다는 것이 문헌의 타당성을 뜻하지는 않습니다."


def reading_room(project):
    sources = project.catalog()
    if st.session_state.get("wb_report_return"):
        if st.button("보고서 초안으로 돌아가기", key="wb_return_to_draft"):
            st.session_state["wb_route"] = "보고서에 쓰기"
            st.session_state["wb_output_route"] = "내 보고서 초안"
            st.session_state.pop("wb_report_return", None)
            st.rerun()
    elif st.session_state.get("wb_notes_return"):
        if st.button("독서 노트로 돌아가기", key="wb_return_to_notes"):
            st.session_state.update(st.session_state.pop("wb_notes_return"))
            st.session_state["wb_route"] = "보고서에 쓰기"
            st.session_state["wb_output_route"] = "독서 노트·자료"
            st.rerun()
    st.header("내 PDF에서 찾고 기록하기", anchor=False)
    st.caption("AI 없이 이 프로젝트의 원문만 검색합니다. 검색어는 외부로 보내지 않습니다. 스캔본은 텍스트 층이 있어야 검색됩니다.")
    if not sources:
        st.info("내 PDF에 논문·보고서를 가져오면 원문 검색과 독서 노트를 사용할 수 있습니다.")
        return
    with st.form("wb_local_search"):
        query = st.text_input("원문 검색어", placeholder="영문 PDF: productivity, sample · 한글 PDF: 생산성, 표본", key="wb_local_query")
        submitted = st.form_submit_button("내 PDF 전체에서 검색", type="primary")
    if submitted:
        try:
            result = notebook.search_passages(project, query)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["wb_local_results"] = result
            st.session_state.pop("wb_local_pick", None)
    found = st.session_state.get("wb_local_results")
    chosen = None
    if found:
        st.caption(f"「{ui.md(found['query'])}」 · 일치 구간 {found['total']}개 / 최대 {found['limit']}개 표시. 단어가 같은 구간에 있는지 검색하며 의미적 관련도 순위가 아닙니다.")
        hits = found["hits"]
        if hits:
            pick = st.selectbox("검색된 원문 구간", range(len(hits)), key="wb_local_pick",
                                format_func=lambda i: f"{hits[i]['title']} · PDF {hits[i]['page']}쪽 · {ui.short(hits[i]['text'], 75)}")
            chosen = hits[pick]
            translation.control(project, [h["text"] for h in hits], "hits", "검색된 영문 구간 모두 한글 번역")
        else:
            st.info("읽을 수 있는 원문에서 찾지 못했습니다. 영문 PDF라면 productivity처럼 원문 언어로 검색하세요. "
                    "아래에서 직접 읽을 문헌을 골라도 됩니다.")
        if st.button("검색 닫고 직접 읽기", key="wb_local_clear"):
            if chosen:
                st.session_state["wb_read_source"] = chosen["source_id"]
                st.session_state["wb_passage_" + chosen["source_id"]] = chosen["passage_id"]
            st.session_state.pop("wb_local_results", None)
            st.rerun()
    if chosen is None:
        ids = [s["id"] for s in sources]
        if st.session_state.get("wb_read_source") not in ids:
            st.session_state["wb_read_source"] = ids[0]
        sid = st.selectbox("읽을 PDF", ids, key="wb_read_source",
                           format_func=lambda i: next(s["title"] for s in sources if s["id"] == i))
        passages = project.index(sid)["passages"]
        if not passages:
            st.warning("텍스트 층이 없습니다. OCR 처리한 PDF를 별도 문헌으로 등록하세요.")
            ui.show_pdf(project, sid)
            return
        passage_id = st.selectbox("원문 구간", [p["id"] for p in passages], key="wb_passage_" + sid,
                                  format_func=lambda i: next(f"PDF {p['page']}쪽 · {ui.short(p['text'], 90)}" for p in passages if p["id"] == i))
        passage = next(p for p in passages if p["id"] == passage_id)
        chosen = {"source_id": sid, "passage_id": passage_id, **passage}
    sid, passage_id = chosen["source_id"], chosen["passage_id"]
    with st.container(key="drk-reading-inspector"):
        left, right = st.columns([1, 1.25], gap="large")
        with left:
            st.markdown("**선택한 원문**")
            st.text(chosen["text"])
            if not translation.show(translation.cache(project), chosen["text"]):
                translation.control(project, [chosen["text"]], "passage_" + sid + passage_id, "이 구간 한글 번역", compact=True,
                                    paste="wb_local_results" not in st.session_state)
            with st.form("wb_note_" + sid + passage_id):
                kind = st.selectbox("노트 분류", notebook.NOTE_KINDS)
                quote = st.text_area("원문에서 남길 발췌", chosen["text"], height=100)
                memo = st.text_area("내 메모", height=90, placeholder="이 내용이 내 질문에 왜 필요한지, 어떤 조건에서 사용할지 적으세요.")
                if st.form_submit_button("발췌·메모 저장", type="primary"):
                    try:
                        saved = notebook.save_note(project, sid, passage_id, quote, memo, kind)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["wb_saved_note"] = saved
                        st.success("원문 쪽수와 함께 저장했습니다. 보고서에 쓰기 → 독서 노트에서 볼 수 있습니다.")
            saved = st.session_state.get("wb_saved_note")
            if saved and saved["source_id"] == sid and saved["locator"]["passage_id"] == passage_id:
                a, b = st.columns(2)
                if a.button("저장한 노트로 보고서 쓰기", key="wb_saved_note_report"):
                    st.session_state["wb_route"] = "보고서에 쓰기"
                    st.session_state["wb_output_route"] = "내 보고서 초안"
                    st.session_state["wb_report_note_to_link"] = saved["id"]
                    st.rerun()
                if b.button("독서 노트 보기", key="wb_saved_note_list"):
                    st.session_state["wb_route"] = "보고서에 쓰기"
                    st.session_state["wb_output_route"] = "독서 노트·자료"
                    st.session_state["wb_notes_query"] = ""
                    st.session_state["wb_notes_kind"] = None
                    st.session_state["wb_notes_source"] = None
                    st.session_state["wb_notes_page"] = 1
                    st.rerun()
            st.caption("노트 저장은 근거 채택이 아닙니다. AI 결과와 사람의 메모를 구분해 보관합니다.")
        with right:
            ui.show_pdf(project, sid, page=chosen["page"], identity="reading-" + passage_id,
                        caption="선택한 구간이 있는 원본 PDF입니다. 쪽수는 파일의 첫 페이지부터 셉니다.")


def notes_panel(project):
    records = notebook.notes(project)
    st.header("출처가 붙은 독서 노트", anchor=False)
    st.caption("직접 적은 메모를 찾아 고치고, 보고서의 논점에 연결하세요. AI 검토·채택 결과와 별도로 보관합니다.")
    if not records:
        st.info("문헌 모으기 → 원문 검색·노트에서 발췌와 메모를 남기세요. AI 연결이 없어도 사용할 수 있습니다.")
        return
    sources = {s["id"]: s for s in project.catalog()}
    a, b, c = st.columns([2, 1, 1.5])
    query = a.text_input("노트 검색", placeholder="메모·발췌·문헌 제목", key="wb_notes_query")
    kind = b.selectbox("노트 분류", [None, *notebook.NOTE_KINDS], key="wb_notes_kind",
                       format_func=lambda k: k or "모든 분류")
    source_id = c.selectbox("노트의 문헌", [None, *dict.fromkeys(n["source_id"] for n in records)], key="wb_notes_source",
                            format_func=lambda sid: sources[sid]["title"] if sid else "모든 문헌")
    found = list(reversed(notebook.filter_notes(project, query, kind, source_id)))
    st.caption(f"노트 {len(found)}개 / 전체 {len(records)}개")
    if not found:
        st.info("조건에 맞는 노트가 없습니다. 검색어·분류·문헌 조건을 바꿔 보세요.")
        return
    pages = max(1, (len(found) + 7) // 8)
    if st.session_state.get("wb_notes_page", 1) > pages:
        st.session_state["wb_notes_page"] = 1
    page = st.selectbox("노트 페이지 · 8개씩", list(range(1, pages + 1)), key="wb_notes_page") if pages > 1 else 1
    for note in found[(page - 1) * 8:page * 8]:
        source = project.source(note["source_id"])
        identity = f"{ui.short(source['title'], 35)} · {note['locator']['page']}쪽 · {ui.short(note['memo'], 20)}"
        with st.container(border=True):
            st.caption(f"{ui.md(note['kind'])} · {ui.md(source['title'])} · PDF {note['locator']['page']}쪽")
            st.markdown(ui.quote_html(note["locator"]), unsafe_allow_html=True)
            st.markdown("**내 메모** · " + ui.md(note["memo"]))
            a, b = st.columns(2)
            if a.button("보고서에 연결 · " + identity, key="wb_note_link_" + note["id"], icon=":material/edit_note:"):
                st.session_state["wb_route"] = "보고서에 쓰기"
                st.session_state["wb_output_route"] = "내 보고서 초안"
                st.session_state["wb_report_note_to_link"] = note["id"]
                st.rerun()
            if b.button("이 원문 다시 읽기 · " + identity, key="wb_note_go_" + note["id"]):
                st.session_state["wb_notes_return"] = {"wb_notes_query": query, "wb_notes_kind": kind,
                                                        "wb_notes_source": source_id, "wb_notes_page": page}
                st.session_state.pop("wb_report_return", None)
                st.session_state["wb_route"] = "문헌 모으기"
                st.session_state["wb_library_route"] = "원문 검색·노트"
                st.session_state["wb_read_source"] = source["id"]
                st.session_state["wb_passage_" + source["id"]] = note["locator"]["passage_id"]
                st.session_state.pop("wb_local_results", None)
                st.rerun()
            with st.expander("메모 수정·이력 · " + identity):
                st.caption("원문 발췌와 쪽수는 보존합니다. 다른 구절을 기록하려면 원문에서 새 노트를 만드세요.")
                with st.form(f"wb_note_edit_{note['id']}_{note.get('revision', 1)}"):
                    edited_kind = st.selectbox("수정할 분류", notebook.NOTE_KINDS, index=notebook.NOTE_KINDS.index(note["kind"]))
                    memo = st.text_area("메모 수정", note["memo"], height=90)
                    if st.form_submit_button("메모 수정 저장"):
                        try:
                            notebook.update_note(project, note["id"], memo, edited_kind, note.get("revision", 1))
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["flash"] = "메모를 수정했습니다. 이전 내용은 이력에 남겼습니다."
                            st.rerun()
                if note.get("history"):
                    st.caption(f"현재 버전 {note.get('revision', 1)} · 이전 메모")
                    for version in reversed(note["history"]):
                        st.caption(f"버전 {version['revision']} · {ui.local_time(version['at'])} · {ui.md(version['kind'])}")
                        st.text(version["memo"])
            with st.expander("인용 정보"):
                st.code(citation(source), language=None, wrap_lines=True)


def materials_export(project):
    st.header("자료·노트 내보내기", anchor=False)
    st.caption("AI 실행 전에도 내려받을 수 있습니다. 서비스 구독 없이 검색 이력·후보·원문 메모를 보관하세요.")
    a, b = st.columns(2)
    a.download_button("독서 노트 · Markdown", notebook.notes_markdown(project),
                      "reading-notes.md", "text/markdown", width="stretch", key="wb_notes_download")
    b.download_button("참고문헌 · RIS", notebook.references_ris(project),
                      "references.ris", "application/x-research-info-systems", width="stretch", key="wb_ris_download",
                      help="제목·저자·연도·DOI를 담은 참고문헌 목록입니다. Zotero·EndNote에 가져올 수 있으며 PDF 원문은 포함하지 않습니다.")
    pdfs = st.checkbox("자료 묶음에 원본 PDF 포함", key="wb_material_pdfs")
    st.download_button("자료 ZIP · 후보·노트·보고서 초안·검색 이력", notebook.library_zip(project, pdfs),
                       f"{project.root.name}_materials.zip", "application/zip", width="stretch", key="wb_material_zip")
    st.caption("AI 실행·검토 기록은 ‘AI 근거 결과’의 결과 ZIP에서 별도로 받습니다. 자료 ZIP은 자동 복원용 백업 형식이 아닙니다.")
    history = read_json(project.root / "search-log.json")
    st.caption(f"현재 검색 이력 {len(history)}회 · 후보 {len(project.collection())}편 · PDF {len(project.catalog())}편 · 노트 {len(notebook.notes(project))}개")
