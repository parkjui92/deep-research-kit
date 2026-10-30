"""Local review desk. All persistent operations use the same core as the skill/CLI."""
import json
from pathlib import Path

import streamlit as st
import yaml
from streamlit_pdf_viewer import pdf_viewer

from deep_research import workflow as flow
from deep_research.exports import compare, export_zip, matrix, report
from deep_research.project import Project, read_json, safe_id

st.set_page_config(page_title="Deep Research Kit · 근거 검토실", page_icon="📖", layout="wide")
st.markdown("""<style>
.stApp {background:#f8f7f3} [data-testid="stSidebar"] {background:#eeeee7}
h1,h2,h3 {letter-spacing:-.035em} .stButton>button[kind="primary"] {background:#255b4c;border-color:#255b4c}
[data-testid="stMetric"] {background:#fff;border:1px solid #dedfd5;padding:16px;border-radius:12px}
code {word-break:break-word} [data-testid="stCaptionContainer"] {color:#566358}
</style>""", unsafe_allow_html=True)

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(exist_ok=True)
STAGES = ["1 · 조사 설계", "2 · 문헌 선별", "3 · 원문 추출", "4 · 근거 검토", "5 · 종합", "6 · 비교·내보내기"]
DECISIONS = {"include": "포함", "exclude": "제외", "pending": "보류"}
REVIEWS = {"accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외"}


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
    st.caption("실제 원본 PDF · 쪽수는 파일의 첫 페이지부터 계산합니다. 강조는 문자열 위치이며 의미 검토는 별도입니다.")


def choose_run(project, key):
    runs = project.runs()
    if not runs:
        st.info("문헌을 선별한 다음 ‘원문 추출’에서 실행을 만드세요.")
        return None
    return st.selectbox("실행 기록", runs, key=key)


def plan_page(project):
    st.subheader("무엇을, 어떤 기준으로 조사할까요?")
    config = project.config()
    plan = config["plan"]
    with st.form("plan-" + str(project.root)):
        question = st.text_input("조사 질문", plan["question"])
        purpose = st.text_area("조사 목적", plan.get("purpose", ""), height=85)
        scope = st.text_area("대상과 범위", plan.get("scope", ""), height=85)
        a, b = st.columns(2)
        inclusion = a.text_area("포함 기준", plan.get("inclusion", ""))
        exclusion = b.text_area("제외 기준", plan.get("exclusion", ""))
        limit = st.number_input("한 실행에서 다룰 문헌 수 상한", 1, 100, plan["max_documents"])
        page_limit = st.number_input("문헌당 처음부터 읽을 PDF 쪽수 · 0은 전체", 0, 1000, plan.get("max_pages_per_document", 20))
        st.caption("기본은 첫 20쪽입니다. 긴 부록까지 읽으려면 0을 지정하세요. 읽은 범위는 근거·보고서에 표시됩니다.")
        output = st.text_input("결과 형태", plan.get("output", ""))
        st.markdown("**추출 항목 — 한 항목의 지침을 바꾸고 새 실행과 비교해 보세요.**")
        fields = st.data_editor(config["fields"], num_rows="dynamic", width="stretch", key="fields-" + str(project.root))
        rules = st.text_area("종합 지침", config["synthesis_rules"], height=150)
        if st.form_submit_button("설계 저장", type="primary"):
            project.save_config({"question": question, "purpose": purpose, "scope": scope,
                                 "inclusion": inclusion, "exclusion": exclusion,
                                 "max_documents": int(limit), "max_pages_per_document": int(page_limit), "output": output}, fields, rules)
            st.success("설계를 저장했습니다. 질문·범위·선별 기준이 바뀌었다면 문헌 선별을 다시 확인하세요.")
    with st.expander("뜯어보기 · 실제 설정 파일"):
        st.code(str(project.root / "research-plan.yaml"))
        st.code(yaml.safe_dump(project.config(), allow_unicode=True, sort_keys=False), language="yaml")
        st.caption("config/extraction-fields.yaml, config/synthesis-rules.md도 직접 수정할 수 있습니다. UI와 스킬이 같은 파일을 읽습니다.")


def sources_page(project):
    st.subheader("문헌을 모으고 선별 이유를 남깁니다")
    with st.expander("PDF 등록", expanded=not project.catalog()):
        files = st.file_uploader("직접 확보한 원문 PDF", type="pdf", accept_multiple_files=True)
        if st.button("선택한 PDF 등록", disabled=not files):
            for file in files:
                with st.spinner(file.name + " 색인 중"):
                    project.add_pdf(file.getvalue(), file.name)
            st.success("등록했습니다. 동일한 파일은 중복 등록되지 않습니다.")
    with st.expander("학술 자료 찾기 · Crossref"):
        st.caption("서지정보 탐색입니다. 원문 전문 검색이나 체계적 문헌고찰의 포괄성을 보장하지 않습니다.")
        query = st.text_input("검색어")
        if st.button("검색하고 기록 남기기"):
            from deep_research.providers import crossref_search
            st.session_state["search_results"] = crossref_search(project, query)
        if st.session_state.get("search_results"):
            st.dataframe(st.session_state["search_results"], width="stretch")
    sources = project.catalog()
    if not sources:
        st.info("PDF를 등록하거나 왼쪽에서 공통 사례를 준비하세요.")
        return
    st.dataframe([{k: s[k] for k in ("id", "title", "decision", "study_id", "page_count", "text_pages")} for s in sources], hide_index=True, width="stretch")
    source_id = st.selectbox("검토할 문헌", [s["id"] for s in sources],
                            format_func=lambda sid: project.source(sid)["title"])
    source = project.source(source_id)
    left, right = st.columns([1, 1.8], gap="large")
    with left:
        with st.form("screen-" + source_id):
            title = st.text_input("문헌 제목", source["title"])
            doi = st.text_input("DOI · 선택", source["doi"])
            url = st.text_input("출처 주소 · 선택", source["url"])
            study_id = st.text_input("연구 ID", source["study_id"], help="같은 연구의 사전공개본·출판본은 같은 연구 ID를 지정하세요.")
            decision = st.radio("선별 판단", list(DECISIONS), index=list(DECISIONS).index(source["decision"]), format_func=DECISIONS.get, horizontal=True)
            reason = st.text_area("판단 이유", source["reason"])
            if st.form_submit_button("선별 저장", type="primary"):
                project.screen(source_id, decision, reason, study_id, title, doi, url)
                st.rerun()
        if source.get("criteria_hash") != project.criteria_hash():
            st.warning("현재 조사 기준으로 선별을 확인하고 저장하세요.")
        if source["text_pages"] < source["page_count"]:
            st.warning("텍스트가 없는 페이지가 있습니다. 스캔 문서는 이 버전에서 자동 추출할 수 없습니다.")
        page = st.number_input("미리 볼 PDF 쪽", 1, max(1, source["page_count"]), 1)
    with right:
        show_pdf(project, source_id, page=int(page))


def extraction_page(project):
    st.subheader("지금의 기준으로 원문을 다시 읽습니다")
    st.write("새 실행은 설계와 문헌 목록을 고정합니다. 이전 실행과 검토 기록은 보존됩니다.")
    if st.button("새 추출 실행 만들기", type="primary"):
        run_id = flow.prepare(project)
        st.session_state["extract_run"] = run_id
        st.success("원문에서 새 요청을 만들었습니다.")
    with st.expander("공통 사례 · 사전 작성 예시로 구조 살펴보기"):
        st.caption("새 AI 실행이 아닙니다. 같은 원본·기본 설계에서만 불러오며, 모든 근거는 미검토 상태입니다.")
        if st.button("기준 추출 예시 불러오기"):
            from deep_research.examples import load_reference
            st.session_state["extract_run"] = load_reference(project)
            st.rerun()
    run_id = choose_run(project, "extract_run")
    if not run_id:
        return
    folder = project.run_dir(run_id)
    run = flow.manifest(project, run_id)
    st.caption(f"상태: {run['state']} · 시작: {run['created_at']}")
    st.markdown("**기본 실행 · Claude Code에서 이 저장소를 열고 다음 요청을 붙여 넣으세요.**")
    st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {run_id}\nrequests/의 원문을 읽고 모든 문헌을 추출해 import-extraction으로 가져와 줘. 사람의 검토 상태는 바꾸지 마.")
    st.write("스킬은 AI 모델을 이용합니다. 별도 API 키 없이 기존 Claude Code 세션에서 실행할 수 있으며 해당 서비스의 사용량이 적용됩니다.")
    for req in run["requests"]:
        imported = (folder / "responses" / (req["source_id"] + ".json")).exists()
        with st.expander(("✓ " if imported else "○ ") + project.source(req["source_id"])["title"]):
            request = read_json(folder / "requests" / (req["source_id"] + ".json"))
            st.caption(f"원문 구간 {len(request['passages'])}개 · 요청 ID {req['request_id']}")
            for warning in request["warnings"]:
                st.warning(warning)
            st.download_button("요청 JSON", json.dumps(request, ensure_ascii=False, indent=2), req["source_id"] + "-request.json", key="req-" + req["request_id"])
    with st.expander("응답 파일 직접 가져오기"):
        responses = st.file_uploader("모델이 작성한 응답 JSON", type="json", accept_multiple_files=True)
        if st.button("원문과 대조하여 가져오기", disabled=not responses):
            for file in responses:
                flow.import_extraction(project, run_id, json.loads(file.getvalue()))
            st.rerun()
    with st.expander("선택 · 직접 API로 실행"):
        st.caption("DRK_API_BASE, DRK_MODEL, 필요시 DRK_API_KEY 환경변수를 설정합니다. 포함 문헌의 텍스트가 해당 서버로 전송됩니다.")
        consent = st.checkbox("선택한 API 서버에 이 문헌 텍스트를 전송합니다.")
        if st.button("API 추출 실행 / 이어서 실행", disabled=not consent):
            from deep_research.providers import extract_with_api
            with st.spinner("문헌별 추출 중 · 완료한 문헌은 저장됩니다"):
                extract_with_api(project, run_id)
            st.rerun()
    if st.button("저장된 응답 새로 읽기"):
        st.rerun()


def review_page(project):
    st.subheader("추출값 옆에서 실제 원문을 확인합니다")
    run_id = choose_run(project, "review_run")
    if not run_id:
        return
    rows = flow.evidence(project, run_id)
    if not rows:
        st.info("원문 추출 응답을 먼저 가져오세요.")
        return
    fields = {f["id"]: f["name"] for f in flow.manifest(project, run_id)["config"]["fields"]}
    selected = st.selectbox("검토할 근거", [r["id"] for r in rows], format_func=lambda eid:
        next(f"{project.source(r['source_id'])['title']} · {fields[r['field_id']]} · {r['review']['status']}" for r in rows if r["id"] == eid))
    row = next(r for r in rows if r["id"] == selected)
    left, right = st.columns([1, 1.8], gap="large")
    with left:
        st.markdown("**AI 추출값**")
        st.write(row["value"] or "자료에서 찾지 못함")
        st.caption(row["id"])
        if row["match_status"] == "matched":
            st.success("발췌 문자열의 원문 위치를 찾았습니다. 아래에서 의미와 문맥을 검토하세요.")
        else:
            st.warning("원문 위치 미확인 또는 미발견입니다. 채택할 수 없으며 보류·제외로 기록할 수 있습니다.")
        for locator in row["locators"]:
            st.markdown("**원문 발췌**")
            st.write(locator["quote"])
            joined = " · 줄끝 하이픈을 이어 대조" if locator.get("dehyphenated") else ""
            st.caption(f"PDF {locator['page']}쪽 · {locator['status']}{joined}")
        st.caption(row["note"])
        with st.form("review-" + run_id + selected):
            previous_status = row["review"]["status"] if row["review"]["status"] in REVIEWS else "hold"
            status = st.radio("내 판단", list(REVIEWS), index=list(REVIEWS).index(previous_status), format_func=REVIEWS.get, horizontal=True)
            value = st.text_area("수정 후 채택할 값", row["review"].get("edited_value") or row["value"] or "")
            note = st.text_area("판단 이유·조건·한계", row["review"].get("note", ""))
            reviewer = st.text_input("검토자", st.session_state.get("reviewer", ""))
            checked = st.checkbox("원문 문맥을 읽고 추출값을 뒷받침하는지 판단했습니다.")
            if st.form_submit_button("판단 저장", type="primary"):
                if status in {"accept", "edit"} and not checked:
                    raise ValueError("채택하려면 원문 문맥 확인 항목을 선택하세요.")
                flow.review(project, run_id, selected, status, note, reviewer, value)
                st.session_state["reviewer"] = reviewer
                st.session_state["flash"] = "판단을 저장했습니다. 다음 근거를 검토하거나 종합 단계로 이동하세요."
                st.rerun()
        st.caption("판단을 바꾸면 이전 종합은 만료됩니다. 원래 추출값과 검토 이력은 보존됩니다.")
    with right:
        if row["locators"]:
            pick = st.selectbox("보여줄 발췌", range(len(row["locators"])), format_func=lambda i: f"{i+1} · PDF {row['locators'][i]['page']}쪽")
            locator = row["locators"][pick]
            show_pdf(project, row["source_id"], [locator], page=locator["page"] or 1, identity=selected)
        else:
            show_pdf(project, row["source_id"], identity=selected)


def synthesis_page(project):
    st.subheader("채택한 근거만 연결해 답을 만듭니다")
    run_id = choose_run(project, "synthesis_run")
    if not run_id:
        return
    rows = flow.evidence(project, run_id)
    approved = flow.accepted(project, run_id)
    a, b = st.columns(2)
    a.metric("채택한 근거", len(approved))
    b.metric("미검토·보류·제외", len(rows) - len(approved))
    st.dataframe(matrix(project, run_id), width="stretch", hide_index=True)
    if st.button("검토 결과로 종합 요청 만들기", type="primary", disabled=not approved):
        flow.prepare_synthesis(project, run_id)
        st.success("종합 요청을 저장했습니다.")
    request_path = project.run_dir(run_id) / "synthesis-request.json"
    if request_path.exists():
        st.code(f"/deep-research\n프로젝트: {project.root}\n실행: {run_id}\nsynthesis-request.json의 채택 근거를 종합하고 import-synthesis로 가져와 줘.")
        with st.expander("종합 JSON 직접 가져오기"):
            response = st.file_uploader("종합 응답", type="json", key="synthesis_upload")
            if st.button("종합 가져오기", disabled=response is None):
                flow.import_synthesis(project, run_id, json.loads(response.getvalue()))
                st.rerun()
    with st.expander("선택 · 직접 API 종합"):
        consent = st.checkbox("채택 근거를 설정한 API 서버로 전송합니다.")
        if st.button("API 종합 실행", disabled=not consent or not approved):
            from deep_research.providers import synthesize_with_api
            with st.spinner("채택 근거를 종합하고 있습니다"):
                synthesize_with_api(project, run_id)
            st.rerun()
    if st.button("종합 결과 새로 읽기"):
        st.rerun()
    st.markdown(report(project, run_id))


def export_page(project):
    st.subheader("바뀐 판단을 비교하고 다음 작업으로 가져갑니다")
    run_id = choose_run(project, "export_run")
    if not run_id:
        return
    st.caption("9주차 결과 → 10주차 위키 재료. 근거 ID, 원문 위치, 검토 상태를 함께 보존합니다.")
    include_pdfs = st.checkbox("원본 PDF도 ZIP에 포함", help="내보낸 원문의 이용 조건은 원저작물의 조건을 따릅니다.")
    st.download_button("Markdown + JSON + CSV 내려받기", export_zip(project, run_id, include_pdfs), f"{run_id}.zip", type="primary")
    st.download_button("조사 보고서 Markdown", report(project, run_id), f"{run_id}.md")
    runs = project.runs()
    if len(runs) > 1:
        baseline = st.selectbox("비교 기준 실행", [r for r in runs if r != run_id])
        result = compare(project, baseline, run_id)
        st.markdown("**설계 변경**")
        a, b = st.columns(2)
        a.json(result["config_before"], expanded=False)
        b.json(result["config_after"], expanded=False)
        st.markdown("**추출값·검토 상태 변경**")
        if result["differences"]:
            st.dataframe(result["differences"], width="stretch")
        else:
            st.info("추출값과 검토 상태의 차이가 없습니다. 변경이 반드시 개선을 의미하지는 않습니다.")
        st.download_button("비교 JSON", json.dumps(result, ensure_ascii=False, indent=2), "comparison.json")
    with st.expander("개선 이슈 작성"):
        template = f"## 재현 환경\nDeep Research Kit 0.1.0\n\n## 바꾼 기준\n\n## 기대한 결과\n\n## 실제 결과\n\n## 재현 방법\n실행: {run_id}\n\n## 제안\n\n※ 원문·개인정보·API 키를 공개 이슈에 붙이지 마세요.\n"
        issue = st.text_area("원 저장소의 Issues에 남길 초안", template, height=280)
        st.download_button("이슈 초안 저장", issue, "issue.md")


def main():
    st.sidebar.markdown("### DEEP RESEARCH KIT\n근거 검토실")
    existing = sorted(p.name for p in PROJECTS.iterdir() if (p / "project.json").exists())
    with st.sidebar.expander("프로젝트 만들기"):
        name = st.text_input("폴더 이름 · 영문·숫자·하이픈", "my-research")
        title = st.text_input("프로젝트 제목", "나의 문헌조사")
        if st.button("빈 프로젝트 만들기"):
            Project(PROJECTS / safe_id(name)).initialize(title)
            st.session_state["project_name"] = name
            st.rerun()
        if st.button("공통 사례 준비 · 실제 논문 3편"):
            from deep_research.examples import create_example
            target = PROJECTS / safe_id(name)
            with st.spinner("공식 자료원에서 PDF를 준비하고 있습니다"):
                create_example(target)
            st.session_state["project_name"] = name
            st.rerun()
    if not existing:
        st.title("찾은 자료를, 확인한 근거로.")
        st.write("조사 기준을 정하고, 실제 PDF의 근거를 읽고, 판단을 남기는 문헌조사 작업 공간입니다.")
        st.info("왼쪽에서 빈 프로젝트 또는 공통 사례를 만드세요.")
        st.markdown("**설계 → 선별 → 추출 → 원문 검토 → 종합 → 비교·내보내기**")
        return
    name = st.sidebar.selectbox("프로젝트", existing, key="project_name")
    project = Project(PROJECTS / name)
    st.sidebar.caption(str(project.root))
    stage = st.sidebar.radio("작업 단계", STAGES)
    st.title(read_json(project.root / "project.json")["title"])
    st.caption("AI가 추출하고, 사람이 근거를 판단합니다.")
    if message := st.session_state.pop("flash", None):
        st.success(message)
    pages = [plan_page, sources_page, extraction_page, review_page, synthesis_page, export_page]
    pages[STAGES.index(stage)](project)


try:
    main()
except (ValueError, OSError, KeyError, TypeError) as exc:
    st.error(str(exc))
    st.caption("이미 저장한 문헌·실행·검토 기록은 프로젝트 폴더에 남아 있습니다.")
