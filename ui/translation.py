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
    """Translate missing English; outstanding web-AI batches survive navigation and reloads.
    Both widget keys and selected-request state belong to this project, never to another one."""
    project_key = translate.key(str(project.root))
    scope = project_key + "_" + key
    chosen_key, flash_key = f"tr_req_{scope}", f"tr_flash_{project_key}"
    if message := st.session_state.pop(flash_key, None):
        st.success(message)
    todo = translate.missing(cache(project), texts)
    pending = translate.pending_requests(project, key)
    if not todo and not pending:
        return
    help_text = ("Claude Code가 영문을 한국어로 옮깁니다. 번역은 이 프로젝트에 저장돼 다시 번역하지 않으며, "
                 "참고용이라 근거 대조·인용·내보내기는 원문 그대로입니다.")
    ready = _claude_ready()
    if ready and todo and st.button(f"{label} · {len(todo)}건", key=f"tr_go_{scope}", icon=":material/translate:", help=help_text,
                                    width="content" if compact else "stretch"):
        from deep_research.providers import run_claude_translate
        try:
            request = translate.prepare(project, todo, context=key)
            st.session_state[chosen_key] = request["request_id"]
            with st.spinner(f"Claude Code가 {len(request['items'])}건을 번역하는 중 · 몇 분 걸릴 수 있습니다"):
                stored = run_claude_translate(project, request_id=request["request_id"])
        except ValueError as exc:
            st.error(str(exc))
            pending = translate.pending_requests(project, key)
        else:
            left = len(translate.missing(cache(project), texts))
            st.session_state[flash_key] = f"번역 {stored}건을 저장했습니다." + (f" 남은 {left}건은 이어서 번역할 수 있습니다." if left else "")
            st.rerun()
    if not paste and ready:
        return
    with st.expander("Claude Code 없이 번역 (웹 AI에 붙여 넣기)" if ready else f"{label} · {len(todo)}건 (웹 AI에 붙여 넣기)",
                     icon=":material/content_paste:", expanded=bool(pending)):
        st.caption("요청문을 ChatGPT·Claude 같은 웹 AI에 붙여 넣고, 받은 JSON을 아래 칸에 붙여 넣으세요. "
                   "요청문에는 번역할 영문이 들어 있습니다. 다른 화면에서 번역을 요청해도 이전 요청을 이어서 저장할 수 있습니다.")
        if len(todo) > translate.MAX_ITEMS:
            st.caption(f"한 번에 최대 {translate.MAX_ITEMS}건을 요청합니다. 저장 후 남은 항목을 이어서 요청하세요.")
        if todo and st.button("요청문 만들기", key=f"tr_make_{scope}"):
            try:
                request = translate.prepare(project, todo, context=key)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state[chosen_key] = request["request_id"]
                pending = translate.pending_requests(project, key)
        if not pending:
            return
        requests = {r["request_id"]: r for r in pending}
        selected = st.session_state.get(chosen_key)
        if selected not in requests:
            selected = next(iter(requests))
        if len(requests) > 1:
            def request_label(rid):
                request = requests[rid]
                return f"{request['created_at'][:16]} · {len(request['items'])}건 · {request['items'][0]['text'][:48]}"
            selected = st.selectbox("응답을 저장할 번역 요청", list(requests), index=list(requests).index(selected),
                                    format_func=request_label, key=f"tr_batch_{scope}")
        st.session_state[chosen_key] = selected
        request = requests[selected]
        left = len(translate.remaining(project, request))
        st.caption(f"이 요청 {len(request['items'])}건 · 저장 대기 {left}건")
        st.code(translate.prompt_text(request), language=None)
        with st.form(f"tr_form_{scope}_{selected}"):
            answer = st.text_area("웹 AI의 응답(JSON)", height=120)
            if st.form_submit_button("번역 저장"):
                try:
                    stored = translate.import_answer(project, translate.parse_answer(answer), "웹 AI", request_id=selected)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    left = len(translate.remaining(project, request))
                    st.session_state[flash_key] = (f"번역 {stored}건을 저장했습니다." if stored else "이미 저장한 번역입니다.")
                    if left:
                        st.session_state[flash_key] += f" 이 요청의 {left}건이 남았습니다. 나머지 응답을 이어서 저장하세요."
                    else:
                        st.session_state.pop(chosen_key, None)
                    st.rerun()
