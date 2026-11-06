"""Short, reusable guidance alongside the real research workflow."""
from pathlib import Path

import streamlit as st

VIDEO_DIR = Path(__file__).resolve().parents[1] / "docs" / "videos" / "2026-11-07"
VIDEOS = {
    "90초 핵심 보기": "deep-research-kit-quickstart-ko.mp4",
    "전체 사용법 · 4분 57초": "deep-research-kit-intro-ko.mp4",
}


def quick_guide():
    st.markdown(
        "1. **문헌 찾기** — ‘문헌 모으기 → 문헌 검색’에서 검색하고 읽을 문헌을 **후보함**에 담으세요.\n"
        "2. **PDF 확보하기** — ‘읽기 후보’에서 **공개 PDF 찾아 등록**을 누르세요. "
        "이미 가진 파일은 ‘내 PDF’에서 가져오면 됩니다.\n"
        "3. **읽고 메모하기** — ‘원문 검색·노트’에서 키워드를 찾고, "
        "**원문 발췌와 내 메모**를 구분해 저장하세요. 쪽수도 함께 남습니다.\n"
        "4. **보고서 쓰기** — **저장한 노트로 보고서 쓰기**를 눌러 논점·주장·문단을 작성하고 "
        "**논점·문단 저장**을 누르세요. ‘전체 초안·내보내기’에서 출처 주석이 붙은 초안을 내려받습니다."
    )
    st.caption("이 과정은 AI 없이도 가능합니다. 여러 문헌을 같은 항목으로 비교하려면 "
               "‘근거 비교 → AI 추출’을 추가로 사용하고, 원문을 확인한 뒤 판단을 남기세요.")


def intro_videos():
    selected = st.radio("영상 선택", list(VIDEOS), horizontal=True, key="intro_video_choice")
    path = VIDEO_DIR / VIDEOS[selected]
    if path.is_file():
        st.video(str(path), autoplay=False)
        st.caption("한국어 자막 · 소리 없음 · 실제 조작 전후 화면에 클릭 표시를 넣은 편집 영상입니다.")
    else:
        st.info("이 설치본에는 영상 파일이 없습니다. 아래 사용 안내로 시작하거나 저장소에서 영상을 받을 수 있습니다.")
        st.link_button("GitHub에서 소개 영상 열기",
                       "https://github.com/parkjui92/deep-research-kit/tree/main/docs/videos/2026-11-07")


def _toggle_video():
    st.session_state["start_show_video"] = not st.session_state.get("start_show_video", False)


def start_help():
    with st.container(border=True):
        st.header("처음이라면, 문헌 한 편으로 따라 해 보세요", anchor=False)
        st.caption("위의 ‘조사 질문에서 시작’에 질문과 검색어를 입력하세요. PDF가 있다면 ‘PDF에서 시작’을 고르면 됩니다.")
        quick_guide()
        show = st.session_state.get("start_show_video", False)
        label = "소개 영상 닫기" if show else "소개 영상 보기 · 90초 핵심 / 전체 4분 57초"
        st.button(label, key="start_watch_video", icon=":material/play_circle:", on_click=_toggle_video)
        if show:
            intro_videos()
        with st.expander("파일 형식이 낯설다면 · RIS, Markdown, ZIP"):
            st.markdown(
                "- **RIS·BibTeX**: 제목·저자·연도·DOI 같은 **참고문헌 정보**를 주고받는 파일입니다. "
                "Zotero·EndNote에서 내보낸 목록을 가져올 때 쓰며, PDF 원문 자체는 들어 있지 않습니다.\n"
                "- **Markdown (.md)**: 제목·문단·출처 주석을 담는 텍스트 문서입니다. "
                "일반 텍스트 편집기로 열고 다른 집필 도구로 옮길 수 있습니다.\n"
                "- **ZIP**: 노트·초안·이력 등 여러 파일을 한 번에 받는 압축 파일입니다."
            )
