"""Visual vocabulary shared by every page: status words and colors, header strip, empty states, PDF pane.

Tokens and the reasons behind them are in docs/DESIGN.md. Status labels live only here so that
a review state looks the same in the sidebar, the tables and the evidence card.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st
import streamlit.components.v1 as components
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
MATCH = {"matched": ("위치 찾음", "gray", ":material/location_on:"),
         "needs_check": ("위치 미확인", "orange", ":material/location_off:"),
         "not_found": ("미발견", "gray", ":material/search_off:")}
DECISION = {"include": ("포함", "green", ":material/check:"),
            "exclude": ("제외", "gray", ":material/block:"),
            "pending": ("보류", "blue", ":material/radio_button_unchecked:")}
RUN_STATE = {"awaiting_extraction": ("응답 대기", "blue", ":material/hourglass_empty:"),
             "review": ("응답 도착 · 검토 가능", "orange", ":material/rate_review:"),
             "complete": ("종합 완료", "green", ":material/check_circle:")}
# Internal codes that used to leak into Korean screens and reports.
CODE_WORD = {"exact_normalized": "글자 그대로 일치", "multiple": "여러 곳에서 일치", "unmatched": "원문에서 못 찾음",
             "ambiguous": "같은 문장이 여러 곳", "too_short": "구절이 너무 짧음", "invalid_passage": "구간 없음",
             "unsupported_page_geometry": "회전·잘린 쪽", "matched": "위치 찾음", "needs_check": "위치 미확인",
             "not_found": "미발견", "accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외",
             "pending": "미검토", "include": "포함", "exclude": "제외"}
STAGE_HINT = {"1 · 조사 설계": "질문·기준·추출 항목", "2 · 문헌 선별": "논문 단위 · 어떤 논문을 쓸지(AI가 읽기 전)", "3 · 원문 추출": "기준을 고정하고 AI에게 원문 읽히기",
              "4 · 근거 검토": "값 단위 · AI가 뽑은 값이 원문과 맞는지(AI가 읽은 뒤)", "5 · 종합": "채택 근거만으로 답", "6 · 비교·내보내기": "전후 비교 · ZIP"}
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


def code_word(code: str) -> str:
    return CODE_WORD.get(code, code)


def local_time(iso: str) -> str:
    """UTC timestamps from the core → Korean local time for the screen."""
    try:
        moment = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return iso[:16].replace("T", " ")


def scroll_top():
    """Streamlit keeps the scroll position across pages; a new stage should start at its title."""
    components.html("<script>const m=parent.document.querySelector('[data-testid=\"stMain\"]');if(m){m.scrollTo(0,0);}</script>", height=0)


def go_to(stage: str):
    st.session_state["stage_value"] = stage
    st.session_state["scroll_top"] = True
    st.rerun()


def next_button(stage: str, key: str):
    """One visible next action after a save, so nobody has to hunt the sidebar."""
    if st.button(f"다음 · {stage} →", key=key):
        go_to(stage)


def short(text: str, limit: int = 48) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def todo(project, stage: str):
    """'지금 할 일' card at the top of every stage: what to do here, where things stand, and the next step.

    New users opened the common case with every field already filled in and could not tell what
    was expected of them — this card says it in one sentence per stage."""
    sources = project.catalog()
    included = sum(s["decision"] == "include" for s in sources)
    runs = project.runs()
    answered = [r for r in runs if any((project.run_dir(r) / "responses").glob("*.json"))]
    kept = sum(len(flow.accepted(project, r)) for r in answered)
    example = (project.root / "example-manifest.json").exists()
    i = STAGES.index(stage)
    if i == 0:
        task = ("예시 질문·포함/제외 기준·추출 항목이 **미리 채워져** 있습니다. 수업에서는 읽어 보기만 하고 다음으로 가도 됩니다. "
                "내 연구에 쓰려면 값을 바꾸고 「설계 저장」." if example else
                "조사 질문·포함/제외 기준·추출 항목을 적고 「설계 저장」을 누릅니다.")
        state = "예시 값 채워짐" if example else "설계 저장됨"
    elif i == 1:
        task = "**논문 한 편씩** 조사에 쓸지 정합니다(AI가 읽기 전). 오른쪽 PDF를 보며 **포함·제외·보류**와 이유(필수)를 「선별 저장」. 고른 이유가 된 문장을 근거 구절에 붙이면 PDF에 표시됩니다. 값 하나하나를 보는 것은 4단계입니다."
        judged = sum(1 for s in sources if s["decision"] != "pending" or s.get("reason"))
        state = f"등록 {len(sources)}편 · 판단 {judged}편(포함 {included}) · 미판단 {len(sources) - judged}편"
    elif i == 2:
        task = "포함한 문헌을 AI에게 읽힙니다. **Claude Code가 있으면 ①**, 없으면 **② 수업용 예시 응답**. 결과는 4단계에서 봅니다."
        state = f"실행 {len(runs)}개 · 응답 있는 실행 {len(answered)}개" if runs else ("아직 실행 없음" if included else "포함한 문헌이 없어 실행을 만들 수 없음 → 2단계")
    elif i == 3:
        task = "2단계에서 고른 논문에서 **AI가 뽑은 값 하나씩** 원문과 맞는지 봅니다(AI가 읽은 뒤). 주황 자리를 읽고 **채택·수정 후 채택·보류·제외**와 이유를 「판단 저장」. 채택은 원문 확인 표시가 필수입니다."
        state = f"채택 {kept}건" if answered else "검토할 응답 없음 → 3단계"
    elif i == 4:
        task = "(선택) 채택한 근거로 AI 종합문을 요청합니다. Claude Code가 없으면 건너뛰고 6단계로 가도 됩니다."
        state = f"채택 {kept}건"
    else:
        task = "결과 ZIP을 내려받아 제출·보관합니다. 기준을 바꿔 다시 돌린 실행이 있으면 전후를 비교합니다."
        state = f"실행 {len(runs)}개"
    # key= gives the wrapper a `st-key-drk-todo` class; assets/styles.css paints it indigo so it
    # never reads as one more white card.
    with st.container(border=True, key="drk-todo"):
        a, b = st.columns([4, 1.2])
        a.markdown(f'<span class="drk-todo-tag">지금 할 일 · {stage}</span>', unsafe_allow_html=True)
        a.markdown(task)
        a.caption(f"상태: {state}")
        if i + 1 < len(STAGES):
            with b:
                if st.button(f"다음 · {STAGES[i + 1]} →", key=f"todo-next-{i}", width="stretch"):
                    go_to(STAGES[i + 1])


def app_header(project, title: str, stage: str):
    """Product name + one line on what the tool does, the project as a chip, and a horizontal stepper
    (Covidence/Elicit onboarding pattern; GOV.UK task-list states: done ✓ · current ● · todo ○)."""
    status = stage_status(project, stage)
    steps = []
    for s in STAGES:
        state = status[s]
        number, name = s.split(" · ", 1)
        mark = "✓" if state == "done" else number
        steps.append(f'<div class="drk-step {state}"><span class="n">{mark}</span><span class="t">{name}</span></div>')
    st.markdown(
        '<div class="drk-app">'
        '<div class="drk-app-top"><div><div class="drk-wordmark">Deep Research Kit</div>'
        '<div class="drk-tagline">AI가 PDF에서 뽑은 값을, 사람이 원문으로 확인해 근거로 남기는 문헌조사 도구</div></div>'
        f'<div class="drk-project"><span class="k">프로젝트</span><span class="v">{title}</span><code>{project.root.name}</code></div></div>'
        f'<div class="drk-stepper">{"".join(steps)}</div></div>', unsafe_allow_html=True)


def header(title: str, lead: str, metrics: list[tuple] = ()):
    """Stage title, one sentence on what happens here, and small status chips (not big metric boxes)."""
    st.subheader(title)
    st.markdown(f'<div class="drk-lead">{lead}</div>', unsafe_allow_html=True)
    if metrics:
        chips = []
        for item in metrics:
            label, value, *rest = item
            tip = f' title="{rest[0]}"' if rest else ""
            chips.append(f'<span class="drk-chip"{tip}><span class="k">{label}</span><span class="v">{value}</span></span>')
        st.markdown('<div class="drk-chips">' + "".join(chips) + '</div>', unsafe_allow_html=True)


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
    done = {STAGES[0]: True, STAGES[1]: any(s["decision"] != "pending" or s.get("reason") for s in sources),
            STAGES[2]: bool(extracted), STAGES[3]: reviewed, STAGES[4]: synthesized, STAGES[5]: False}
    return {s: "current" if s == current else ("done" if done[s] else "todo") for s in STAGES}


def show_pdf(project, source_id, locators=None, page=1, identity="source", caption=None):
    project.index(source_id)
    data = (project.source_dir(source_id) / "original.pdf").read_bytes()
    boxes = []
    for locator in locators or []:
        for box in locator["boxes"]:
            boxes.append({**box, "id": f"box-{len(boxes) + 1}"})
    boxes.sort(key=lambda b: (b["page"], b["y"], b["x"]))
    key = flow.fingerprint([source_id, identity, page, boxes])[:20]
    options = {"scroll_to_annotation": 1} if boxes else {"scroll_to_page": page}
    zoom = st.slider("원문 확대", 0.8, 2.5, 1.0, 0.1, key="zoom-" + source_id)
    boxes = [{**box, "color": "#F59E0B"} for box in boxes]
    pdf_viewer(data, height=680, annotations=boxes, render_text=True, pages_to_render=[page],
               zoom_level=zoom, annotation_outline_size=2, key="pdf-" + key, **options)
    st.caption(caption or "실제 원본 PDF · 쪽수는 파일의 첫 페이지부터 셉니다. 주황 테두리는 발췌 문자열의 위치이며, 뜻을 뒷받침하는지는 사람이 읽고 판단합니다.")
