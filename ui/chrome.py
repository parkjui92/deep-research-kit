"""Visual vocabulary shared by every page: status words and colors, header strip, empty states, PDF pane.

Tokens and the reasons behind them are in docs/DESIGN.md. Status labels live only here so that
a review state looks the same in the sidebar, the tables and the evidence card.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from streamlit_pdf_viewer import pdf_viewer

from deep_research import workflow as flow

ROOT = Path(__file__).resolve().parents[1]
STAGES = ["1 · 조사 설계", "2 · 문헌 선별", "3 · 원문 추출", "4 · 근거 검토", "5 · 종합", "6 · 비교·내보내기"]

# (label, badge color, icon). Blue marks unfinished work, green a human decision to keep,
# orange a hold, gray a stop. Red is reserved for errors (GOV.UK tag rule).
REVIEW = {"pending": ("미검토", "blue", ":material/radio_button_unchecked:"),
          "accept": ("채택", "green", ":material/check:"),
          "edit": ("수정 후 채택", "green", ":material/edit:"),
          "hold": ("보류", "orange", ":material/pause:"),
          "reject": ("제외", "gray", ":material/block:")}
MATCH = {"matched": ("위치 확인", "gray", ":material/location_on:"),
         "needs_check": ("위치 미확인", "orange", ":material/location_off:"),
         "not_found": ("미발견", "gray", ":material/search_off:")}
DECISION = {"include": ("포함", "green", ":material/check:"),
            "exclude": ("제외", "gray", ":material/block:"),
            "pending": ("보류", "blue", ":material/radio_button_unchecked:")}
RUN_STATE = {"awaiting_extraction": ("응답 대기", "blue", ":material/hourglass_empty:"),
             "review": ("검토 중", "orange", ":material/rate_review:"),
             "complete": ("종합 완료", "green", ":material/check_circle:")}
STAGE_MARK = {"done": "✓", "current": "●", "todo": "○"}


def inject_css():
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def badge(table: dict, key: str):
    label, color, icon = table.get(key, (key, "gray", None))
    st.badge(label, icon=icon, color=color)


def word(table: dict, key: str) -> str:
    """Plain-text status for tables and select boxes (color is never the only signal)."""
    return table.get(key, (key,))[0]


def short(text: str, limit: int = 48) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def header(title: str, lead: str, metrics: list[tuple] = ()):
    """Stage title, one sentence on what happens here, and the numbers that describe where things stand."""
    st.subheader(title)
    st.markdown(f'<div class="drk-lead">{lead}</div>', unsafe_allow_html=True)
    if metrics:
        for column, item in zip(st.columns(len(metrics)), metrics):
            label, value, *rest = item
            column.metric(label, value, help=rest[0] if rest else None, border=True)


def empty(message: str, hint: str = ""):
    """Carbon empty-state rule: say why it is empty and name one next action."""
    with st.container(border=True):
        st.markdown(f"**{message}**")
        if hint:
            st.caption(hint)


def stage_status(project, current: str) -> dict:
    """Which stages already have something saved. Used for the ✓ · ● · ○ marks in the sidebar."""
    sources = project.catalog()
    runs = project.runs()
    extracted = [r for r in runs if flow.manifest(project, r)["state"] != "awaiting_extraction"]
    reviewed = any(flow.accepted(project, r) for r in extracted)
    synthesized = any(flow.current_synthesis(project, r) for r in extracted)
    done = {STAGES[0]: True, STAGES[1]: any(s["decision"] != "pending" for s in sources),
            STAGES[2]: bool(extracted), STAGES[3]: reviewed, STAGES[4]: synthesized, STAGES[5]: False}
    return {s: "current" if s == current else ("done" if done[s] else "todo") for s in STAGES}


def show_pdf(project, source_id, locators=None, page=1, identity="source"):
    project.index(source_id)
    data = (project.source_dir(source_id) / "original.pdf").read_bytes()
    boxes = []
    for locator in locators or []:
        for box in locator["boxes"]:
            boxes.append({**box, "id": f"box-{len(boxes) + 1}"})
    boxes.sort(key=lambda b: (b["page"], b["y"], b["x"]))
    key = flow.fingerprint([source_id, identity, page, boxes])[:20]
    options = {"scroll_to_annotation": 1} if boxes else {"scroll_to_page": page}
    zoom = st.slider("원문 확대", 1.0, 2.5, 1.2, 0.1, key="zoom-" + source_id)
    boxes = [{**box, "color": "#d98b10"} for box in boxes]
    pdf_viewer(data, height=680, annotations=boxes, render_text=True, pages_to_render=[page],
               zoom_level=zoom, annotation_outline_size=2, key="pdf-" + key, **options)
    st.caption("실제 원본 PDF · 쪽수는 파일의 첫 페이지부터 셉니다. 주황 테두리는 발췌 문자열의 위치이며, 뜻을 뒷받침하는지는 사람이 읽고 판단합니다.")
