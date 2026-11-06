"""Turn a reader's source-linked notes into their own report paragraphs, without AI."""
from __future__ import annotations

from copy import deepcopy

import streamlit as st

from deep_research import integrity, notebook
from deep_research import writing as draft
from deep_research.exports import citation

from . import chrome as ui


def _read_note(note):
    st.session_state["wb_report_return"] = True
    st.session_state["wb_route"] = "문헌 모으기"
    st.session_state["wb_library_route"] = "원문 검색·노트"
    st.session_state["wb_read_source"] = note["source_id"]
    st.session_state["wb_passage_" + note["source_id"]] = note["locator"]["passage_id"]
    st.session_state.pop("wb_local_results", None)


def _values(section):
    return {"title": (section or {}).get("title", ""), "claim": (section or {}).get("claim", ""),
            "body": (section or {}).get("body", ""), "note_ids": list((section or {}).get("note_ids", []))}


def _buffer(section, pending):
    """Non-widget session drafts survive Streamlit's widget cleanup on navigation."""
    key = section["id"] if section else "new"
    buffers = st.session_state.setdefault("wb_draft_buffers", {})
    if key not in buffers:
        buffers[key] = {"base": deepcopy(section), "values": _values(section), "epoch": 0, "pending": None}
    buffer = buffers[key]
    if buffer["base"] != section and buffer["values"] == _values(buffer["base"]):
        # No local edits: refresh from a newer saved paragraph without dropping user work.
        buffer.update(base=deepcopy(section), values=_values(section), epoch=buffer["epoch"] + 1)
    if pending and buffer.get("pending") != pending["id"]:
        buffer["values"]["note_ids"] = list(dict.fromkeys([*buffer["values"]["note_ids"], pending["id"]]))
        if not section and not buffer["values"]["title"]:
            buffer["values"]["title"] = pending["kind"]
        buffer.update(pending=pending["id"], epoch=buffer["epoch"] + 1)
    return key, buffer


def _remember_field(editor, field, widget):
    st.session_state["wb_draft_buffers"][editor]["values"][field] = deepcopy(st.session_state[widget])


def _choose_section(section_id):
    st.session_state["wb_draft_next"] = section_id or "new"


def _outline(sections, selected):
    with st.popover(f"목차 {len(sections)}개", icon=":material/format_list_bulleted:",
                    key="wb_draft_outline", width="stretch", disabled=not sections):
        with st.container(height=260 if len(sections) > 5 else "content", border=False):
            for index, section in enumerate(sections, 1):
                buffer = st.session_state.get("wb_draft_buffers", {}).get(section["id"])
                dirty = buffer and buffer["values"] != _values(buffer["base"])
                label = f"{index}. {ui.short(section['title'], 60)}" + (" · 미저장" if dirty else "")
                st.button(label, key="wb_draft_outline_" + section["id"], width="stretch",
                          type="primary" if section["id"] == selected else "secondary",
                          on_click=_choose_section, args=(section["id"],))


def _manage_section(project, section, document):
    sections = document["sections"]
    current_index = next(i for i, s in enumerate(sections) if s["id"] == section["id"])
    st.caption(f"목차 {current_index + 1}/{len(sections)} · 연결 노트 {len(section['note_ids'])}개")
    a, b = st.columns(2)
    if a.button("↑ 위로", key="wb_draft_up", disabled=current_index == 0):
        try:
            draft.move_section(project, section["id"], -1, document["revision"])
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    if b.button("↓ 아래로", key="wb_draft_down", disabled=current_index == len(sections) - 1):
        try:
            draft.move_section(project, section["id"], 1, document["revision"])
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()
    st.caption("보관하면 현재 목차와 내보내기에서 빠집니다. 아래 보관함에서 복원할 수 있습니다.")
    if st.button("이 논점 보관", key="wb_draft_archive", width="stretch"):
        try:
            draft.archive_section(project, section["id"], document["revision"])
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["wb_draft_next"] = "new"
            st.session_state["wb_draft_flash"] = "목차에서 뺐습니다. 보관한 논점에서 언제든 복원할 수 있습니다."
            st.rerun()


def _note_links(project, notes, sources, values, editor, token):
    """Narrow the add list without silently dropping the already selected notes."""
    add, summary = st.columns([1.3, 2.7], vertical_alignment="center")
    with add.popover("노트 연결 편집", icon=":material/add_link:", key="wb_draft_link_popover", width="stretch"):
        query = st.text_input("연결할 노트 검색", placeholder="메모·원문 발췌·문헌 제목", key="wb_draft_link_query")
        ids = [None, *dict.fromkeys(n["source_id"] for n in notes.values())]
        if st.session_state.get("wb_draft_link_source") not in ids:
            st.session_state["wb_draft_link_source"] = None
        source_id = st.selectbox("노트의 문헌", ids, key="wb_draft_link_source",
                                format_func=lambda sid: sources[sid]["title"] if sid else "모든 문헌")
        matches = {n["id"] for n in notebook.filter_notes(project, query, source_id=source_id)}
        visible = [nid for nid in notes if nid in matches or nid in values["note_ids"]]
        st.caption(f"검색 결과 {len(matches)}개 · 이미 연결한 노트는 검색 조건과 관계없이 유지됩니다.")
        linked = st.multiselect("이 논점에 연결할 노트", visible, default=values["note_ids"],
                                key="wb_draft_links_" + token,
                                on_change=_remember_field, args=(editor, "note_ids", "wb_draft_links_" + token),
                                format_func=lambda n: f"{ui.short(notes[n]['memo'], 54)} · "
                                f"{ui.short(sources[notes[n]['source_id']]['title'], 35)} · PDF {notes[n]['locator']['page']}쪽")
        if not matches:
            st.info("검색 조건에 맞는 노트가 없습니다. 검색어 또는 문헌 조건을 바꿔 보세요.")
    summary.caption(f"연결 노트 {len(linked)}개 · 문헌 {len({notes[n]['source_id'] for n in linked})}편"
                    + " · 연결은 근거 채택과 별도입니다.")
    return linked


def _source_panel(notes, sources, linked, editor):
    st.markdown("**연결한 출처 노트**")
    if not linked:
        st.info("‘노트 연결 편집’에서 문단에 사용할 노트를 선택하세요.")
        return
    key = "wb_draft_note_pick_" + editor
    if st.session_state.get(key) not in linked:
        previous = st.session_state["wb_draft_buffers"][editor].get("picked_note")
        st.session_state[key] = previous if previous in linked else linked[0]
    nid = st.selectbox("원문을 확인할 노트", linked, key=key,
                       format_func=lambda n: f"{linked.index(n) + 1}. {ui.short(notes[n]['memo'], 58)} · PDF {notes[n]['locator']['page']}쪽")
    note = notes[nid]
    st.session_state["wb_draft_buffers"][editor]["picked_note"] = nid
    source = sources[note["source_id"]]
    other_flagged = {notes[n]["source_id"] for n in linked
                     if notes[n]["source_id"] != note["source_id"]
                     and (sources[notes[n]["source_id"]].get("integrity") or {}).get("status") in integrity.FLAGGED}
    if other_flagged:
        st.warning("다른 연결 문헌에도 고지가 있습니다: " + " · ".join(
            integrity.label(sources[sid]["integrity"]) + " — " + ui.md(ui.short(sources[sid]["title"], 50))
            for sid in sorted(other_flagged)))
    with st.container(border=True, key="drk-writing-source"):
        st.button("원문에서 확인", key="wb_draft_read_" + nid, on_click=_read_note, args=(note,), width="stretch")
        st.markdown("**" + ui.md(source["title"]) + "**")
        bib = source.get("bib") or {}
        meta = " · ".join(str(v) for v in (", ".join((bib.get("authors") or [])[:2]), bib.get("year")) if v)
        st.caption((ui.md(meta) + " · " if meta else "") + f"PDF {note['locator']['page']}쪽 · 노트 버전 {note.get('revision', 1)}")
        record = source.get("integrity")
        if (record or {}).get("status") in integrity.FLAGGED:
            ui.integrity_note(record, "인용 전 확인 · ")
        with st.container(height=350, border=False):
            st.caption("원문 발췌")
            st.markdown(ui.quote_html(note["locator"]), unsafe_allow_html=True)
            st.caption("내 메모 · 미검토")
            st.markdown(ui.md(note["memo"]))
        with st.expander("인용 정보"):
            st.code(citation(source), language=None, wrap_lines=True)


def report_draft(project):
    records = notebook.notes(project)
    notes = {n["id"]: n for n in records}
    sources = {s["id"]: project.with_bib(s) for s in project.catalog()}
    document = draft.load(project)
    sections = document["sections"]
    st.header("노트로 내 보고서 쓰기", anchor=False)
    st.caption("노트를 연결해 문단을 직접 쓰고 내보내세요.")
    if message := st.session_state.pop("wb_draft_flash", None):
        st.success(message)
    pending_id = st.session_state.get("wb_report_note_to_link")
    pending = notes.get(pending_id)
    if pending:
        st.info("연결할 노트를 가져왔습니다. 새 논점을 만들거나 기존 논점을 고른 뒤 ‘논점·문단 저장’을 누르세요.")
    if not records:
        st.info("먼저 목차와 문단을 적어도 됩니다. 문헌 모으기 → 원문 검색·노트에서 발췌·메모를 남긴 뒤 여기에 연결하세요.")
    edit, preview = st.tabs(["논점·문단 쓰기", "전체 초안·내보내기"])
    with edit:
        ids = [None] + [s["id"] for s in sections]
        if target := st.session_state.pop("wb_draft_next", None):
            if target == "new" or target in ids:
                st.session_state["wb_draft_section"] = None if target == "new" else target
        if "wb_draft_section" not in st.session_state:
            st.session_state["wb_draft_section"] = st.session_state.get("wb_draft_active")
        if st.session_state.get("wb_draft_section") not in ids:
            st.session_state["wb_draft_section"] = None
        with st.container(key="drk-draft-navigation"):
            choose, outline, manage = st.columns([3.8, 1.1, 1.3], vertical_alignment="bottom")
            selected = choose.selectbox("편집할 논점", ids, key="wb_draft_section", placeholder="＋ 새 논점",
                                    format_func=lambda i: "＋ 새 논점" if i is None else
                                    next(f"{j + 1}. {s['title']}" for j, s in enumerate(sections) if s["id"] == i))
            with outline:
                _outline(sections, selected)
        st.session_state["wb_draft_active"] = selected
        section = next((s for s in sections if s["id"] == selected), None)
        with manage.popover("논점 관리", icon=":material/more_horiz:", key="wb_draft_manage",
                            width="stretch", disabled=section is None):
            if section:
                _manage_section(project, section, document)
        if section:
            if draft.changed_notes(section, records):
                st.warning("이 문단을 저장한 뒤 연결 노트가 수정되었습니다. 아래 최신 메모와 문단을 대조한 뒤 다시 저장하세요.")
        editor, buffer = _buffer(section, pending)
        token = f"{editor}_{buffer['epoch']}"
        values = buffer["values"]
        stale = buffer["base"] != section
        if stale:
            st.warning("다른 화면에서 이 논점의 저장본이 바뀌었습니다. 작성 중 내용은 유지했습니다. 필요한 내용을 복사한 뒤 저장본을 다시 불러오세요.")
            if st.button("작성 중 내용 버리고 저장본 불러오기", key="wb_draft_reload"):
                buffer.update(base=deepcopy(section), values=_values(section), epoch=buffer["epoch"] + 1)
                st.rerun()
        if values != _values(buffer["base"]):
            st.caption("미저장 변경 · 이 탭에서 유지됩니다. 파일에 남기려면 ‘논점·문단 저장’을 누르세요.")
        linked = _note_links(project, notes, sources, values, editor, token)
        left, right = st.columns([1.5, 1], gap="large")
        with left:
            with st.container():
                title = st.text_input("논점 제목", values["title"],
                                      placeholder="예: 생산성 효과는 과업과 숙련도에 따라 달랐다", key="wb_draft_title_" + token,
                                      on_change=_remember_field, args=(editor, "title", "wb_draft_title_" + token))
                claim = st.text_area("핵심 주장", values["claim"], height=80,
                                     placeholder="이 문단에서 말하려는 요점을 한두 문장으로 적으세요.", key="wb_draft_claim_" + token,
                                     on_change=_remember_field, args=(editor, "claim", "wb_draft_claim_" + token))
                body = st.text_area("내가 쓸 문단", values["body"], height=210,
                                    placeholder="원문 근거, 해석, 적용 조건을 구분하며 작성하세요.", key="wb_draft_body_" + token,
                                    on_change=_remember_field, args=(editor, "body", "wb_draft_body_" + token))
                st.caption("연결한 노트의 원문·쪽수는 초안 끝의 출처 주석으로 함께 내보냅니다.")
                if st.button("논점·문단 저장", type="primary", key="wb_draft_save", disabled=stale):
                    try:
                        saved = draft.save_section(project, title, claim, body, linked, selected, document["revision"])
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["wb_draft_buffers"].pop(editor, None)
                        st.session_state["wb_draft_buffers"][saved["id"]] = {
                            "base": deepcopy(saved), "values": _values(saved), "epoch": buffer["epoch"] + 1, "pending": None}
                        st.session_state["wb_draft_next"] = saved["id"]
                        st.session_state.pop("wb_report_note_to_link", None)
                        st.session_state["wb_draft_flash"] = "논점·문단과 출처 노트를 저장했습니다. 전체 초안에서 순서와 인용을 확인하세요."
                        st.rerun()
        with right:
            _source_panel(notes, sources, linked, editor)
        if section:
            versions = [h for h in document["history"] if h.get("section_id") == selected and h.get("previous")]
            if versions:
                with st.expander(f"이전 문단 기록 · {len(versions)}회"):
                    for version in reversed(versions):
                        previous = version["previous"]
                        st.caption(ui.local_time(version["at"]))
                        st.text(previous["title"] + "\n" + previous["claim"] + "\n\n" + previous["body"])
        if archived := document.get("archived"):
            with st.expander(f"보관한 논점 · {len(archived)}개"):
                for item in archived:
                    old = item["section"]
                    st.markdown("**" + ui.md(old["title"]) + "**")
                    st.caption(f"연결 노트 {len(old['note_ids'])}개 · {ui.local_time(item['at'])} 보관")
                    if st.button("목차로 복원", key="wb_draft_restore_" + old["id"]):
                        try:
                            draft.restore_section(project, old["id"], document["revision"])
                        except ValueError as exc:
                            st.error(str(exc))
                        else:
                            st.session_state["wb_draft_next"] = old["id"]
                            st.session_state["wb_draft_flash"] = "논점을 목차로 복원했습니다."
                            st.rerun()
    with preview:
        if not sections:
            st.info("논점을 저장하면 목차 순서대로 문단과 출처 노트를 볼 수 있습니다.")
        text = draft.markdown(project)
        st.download_button("보고서 초안 · Markdown", text, "report-draft.md", "text/markdown",
                           key="wb_draft_download", disabled=not sections, on_click="ignore")
        st.caption("수정 이력과 연결 노트 버전까지 보관하려면 ‘독서 노트·자료’에서 자료 ZIP을 내려받으세요.")
        st.caption("미리보기와 내보내기에는 마지막으로 저장한 내용이 들어갑니다.")
        st.markdown(text)
