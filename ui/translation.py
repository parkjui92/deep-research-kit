"""Korean reference translations beside English text, and the control that asks for them."""
from __future__ import annotations

import streamlit as st

from deep_research import translate

from . import chrome as ui


def cache(project) -> dict:
    return translate.load(project)


def html(text: str) -> str:
    """The translation as shown under its original: marked, muted, never mistaken for it."""
    return f'<div class="drk-translation">{ui.h(translate.LABEL)} · {ui.h(text)}</div>' if text else ""


def show(cached: dict, text) -> bool:
    """Draw the stored translation of `text` if there is one. Returns whether it drew."""
    ko = translate.lookup(cached, text)
    if ko:
        st.markdown(html(ko), unsafe_allow_html=True)
    return bool(ko)


def _claude_ready() -> bool:
    if "drk_claude_ready" not in st.session_state:
        from deep_research.providers import claude_code_status
        st.session_state["drk_claude_ready"] = claude_code_status()["available"]
    return st.session_state["drk_claude_ready"]


def control(project, texts, key: str, label: str = "영문 한글 번역", compact: bool = False, paste: bool = True):
    """A button that translates the English among `texts` that has no stored translation.
    Draws nothing when there is nothing to translate. `paste=False` leaves out the web-AI path
    where a broader control on the same screen already offers it."""
    if message := st.session_state.pop("flash_translate", None):
        st.success(message)
    todo = translate.missing(cache(project), texts)
    if not todo:
        return
    help_text = ("Claude Code가 영문을 한국어로 옮깁니다. 번역은 이 프로젝트에 저장돼 다시 번역하지 않으며, "
                 "참고용이라 근거 대조·인용·내보내기는 원문 그대로입니다.")
    ready = _claude_ready()
    if ready and st.button(f"{label} · {len(todo)}건", key=f"tr_go_{key}", icon=":material/translate:", help=help_text,
                           width="content" if compact else "stretch"):
        translate.prepare(project, todo)
        from deep_research.providers import run_claude_translate
        try:
            with st.spinner(f"Claude Code가 {len(todo)}건을 번역하는 중 · 몇 분 걸릴 수 있습니다"):
                stored = run_claude_translate(project)
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state["flash_translate"] = f"번역 {stored}건을 저장했습니다."
            st.rerun()
    if not paste and ready:
        return
    with st.expander("Claude Code 없이 번역 (웹 AI에 붙여 넣기)" if ready else f"{label} · {len(todo)}건 (웹 AI에 붙여 넣기)",
                     icon=":material/content_paste:", expanded=f"tr_req_{key}" in st.session_state):
        st.caption("Claude Code가 없으면 아래 요청문을 ChatGPT·Claude 같은 웹 AI에 붙여 넣고, 받은 JSON을 아래 칸에 붙여 넣으세요. "
                   "요청문에는 번역할 영문만 들어 있습니다.")
        if st.button("요청문 만들기", key=f"tr_make_{key}"):
            st.session_state[f"tr_req_{key}"] = translate.prompt_text(translate.prepare(project, todo))
        if request := st.session_state.get(f"tr_req_{key}"):
            st.code(request, language=None)
            with st.form(f"tr_form_{key}"):
                answer = st.text_area("웹 AI의 응답(JSON)", height=120)
                if st.form_submit_button("번역 저장"):
                    try:
                        stored = translate.import_answer(project, translate.parse_answer(answer), "웹 AI")
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop(f"tr_req_{key}", None)
                        st.session_state["flash_translate"] = f"번역 {stored}건을 저장했습니다."
                        st.rerun()
