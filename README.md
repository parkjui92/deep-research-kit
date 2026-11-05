# Deep Research Kit

**문헌을 찾고, 내 PDF에서 근거를 확인하고, 보고서에 쓸 기록으로 정리하는 로컬 문헌조사 도구.** PDF 검색·독서 노트·서지·자료 내보내기는 AI 없이 사용할 수 있습니다. AI 추출은 Claude Code, 웹 AI 또는 설정한 API를 선택해 사용하며 제공자의 비용·한도는 별도입니다.

## 왜 만들었나

문헌을 모아도 “왜 이 문헌을 읽으려 했는지”, “이 메모는 어느 쪽에서 나온 것인지”, “AI의 해석을 누가 확인했는지”가 쉽게 흩어집니다. 이 도구는 후보를 고르는 이유, 원문 발췌, 사람의 메모와 검토 판단을 프로젝트 폴더에 함께 남깁니다. 수업에서 “AI에게 조사를 맡기되 근거는 사람이 확인한다”를 연습하는 교재로 시작했습니다.

기존 도구에도 무료 기능이 있습니다. Elicit은 보고서 내보내기가 모든 플랜에서 가능하지만 일부 추출표 내보내기는 유료 조건이 있고, ResearchRabbit은 인용 탐색과 서지 내보내기를 무료로 제공합니다. 이 도구는 **AI 구독 없이 자료를 읽고 정리하는 흐름, 로컬 기록, 선택한 AI 연결, 근거별 사람의 검토**를 함께 제공하는 데 집중합니다. [비교 근거와 구현 범위](docs/RESEARCH-WORKSPACE-2026-11-05.md)를 참고하세요.

## 어떻게 쓰나

1. **두 경로로 시작** — 「＋ 새 조사」에서 「조사 질문에서 시작」 또는 「PDF에서 시작」을 고릅니다. 내 질문과 선택적인 제목을 입력하면 프로젝트가 만들어집니다.
2. **문헌 모으기** — 「문헌 검색」에서 OpenAlex·arXiv·Crossref를 검색하고 후보함에 담습니다. 「읽기 후보」에서 먼저 읽기·나중에·읽음과 읽을 이유를 저장합니다. 공개 PDF는 선택한 후보에서 따로 가져옵니다. 확보하지 못한 PDF는 「내 PDF」에서 직접 가져오거나 다운로드 폴더 연결을 사용합니다. RIS/BibTeX 가져오기도 지원합니다.
3. **AI 없이 읽기** — 「원문 검색·노트」에서 등록한 PDF 전체를 키워드로 검색합니다. 발췌와 내 메모를 저장하면 PDF 쪽·원문 위치가 남습니다. 저장된 노트는 AI 근거의 채택 판단과 별도입니다.
4. **근거 비교** — 「조사 설정」에서 질문·선별 기준·비교 항목을 정하고, 포함한 문헌을 선택한 AI로 추출합니다. 비교표의 셀을 고르면 옆에서 값·발췌를 확인합니다. 「PDF와 나란히 크게 검토」로 원문 강조를 보며 채택·수정·보류·제외와 이유를 기록합니다. 수정 입력란은 ‘수정 후 채택’을 고를 때 표시됩니다.
5. **보고서에 쓰기** — 「독서 노트·자료」에서 노트 Markdown, 참고문헌 RIS, 자료 ZIP(검색 이력 CSV·후보·노트·선택한 원본 PDF)을 받습니다. 「AI 근거 결과」에서는 채택한 근거, 종합문과 출처, 결과 ZIP을 확인합니다. 종합 실행과 파일 다운로드는 별도 탭에 있습니다.

첫 화면의 「예제로 살펴보기」에서 **논문 3편 예제 체험**을 열 수 있습니다. 사전 작성한 응답이며 새 AI 추론이나 사람의 검토 완료를 뜻하지 않습니다. 「조사 설정 → 단계별 보기」는 기존 학습 모드입니다.

## 작업 공간 개선 (2026-11-05)

**문헌 모으기 → 근거 비교 → 보고서에 쓰기**를 실제 앱에 반영했습니다.

- 후보함: 검색을 바꿔도 남는 문헌·읽기 우선순위·선정 메모·발견 검색어.
- 로컬 읽기: PDF 키워드 검색, 쪽수·발췌·내 메모, 저장한 노트에서 원문으로 복귀.
- 비교표: 셀 옆의 근거 확인, 표시 항목·검토 상태 필터, PDF 집중 검토.
- 내보내기: AI 실행 전에도 자료·노트·서지를 받으며, 검토한 AI 결과는 별도로 받습니다.
- 데이터 안내: 로컬 보관, 외부 검색, AI 원문 전송을 실행 지점에서 구분합니다.

같은 날 연구용 AI 도구 벤치마킹([비교 기록](docs/BENCHMARK-2026-11-05.md))에서 고른 기능을 더했습니다.

- 조사 진행 띠: 검색 → 후보 → PDF → 포함 → 추출 → 검토 → 채택 건수를 화면 맨 위에 보이고, 누르면 그 단계로 갑니다.
- 철회·정정 확인: 후보·내 문헌·채택 근거의 DOI를 Crossref(없으면 OpenAlex)에 보내 철회·정정·우려 표명 고지를 조회합니다. 결과는 배지·보고서·근거 CSV에 남고, 고지가 없다는 것을 '문제없음'으로 표시하지 않습니다.
- 원문 상태: 후보마다 본문 확보 / 글자 없는 PDF / 초록만 / 미확보를 나눠 보입니다.
- 다른 문헌과 비교: 채택할 때 검토자가 '같은 지표·단위 / 조건이 다름 / 비교 불가'를 고르면 항목별로 집계합니다. AI가 정하거나 찬반으로 합치지 않습니다.
- 종합문 인용 미리보기: 인용을 누르면 발췌·쪽·검토 상태가 먼저 보이고, 거기서 비교표로 갑니다. 종합문의 '일치·차이' 같은 분류에는 'AI 분류'를 붙입니다.
- 시작 화면의 선택 칸(대상·분야·영문 검색어·발행연도), 후보 초록의 검색어 표시, '피인용 많은 순' 정렬 이름과 도움말.

자료 ZIP은 다른 도구에서 읽을 수 있는 자료 묶음이며, 자동 복원용 프로젝트 백업은 아닙니다. OCR·여러 기기 동기화·공동 편집은 이번 구현에 포함하지 않았습니다. [구현 및 검증 기록](docs/RESEARCH-WORKSPACE-2026-11-05.md)

## 다른 도구와 다른 점

공식 기능 안내를 기준으로 비교했습니다(2026-10-31). 제품별 실제 정확도·속도를 같은 과제로 측정한 평가는 아닙니다.

| 흐름 | Deep Research Kit | Elicit | Liner Scholar |
|---|---|---|---|
| 중심 작업 | 로컬 PDF의 추출값을 사람이 대조하고 근거 기록으로 남기기 | 질문·선별·구조화된 데이터 추출·보고서 | 논문 탐색·문헌 비교·인용·문헌고찰 초안 |
| 근거 확인 | 추출값→발췌→PDF 위치, 채택·수정·보류·제외 기록 | 추출표 셀의 원문 발췌, 선별 이유·사용자 판단 수정 | 원출처와 인용을 연결하는 탐색 흐름 |
| 이번에 보강한 부분 | 탐색·검토·결과 분리, 검색·필터, 집중 검토, 종합문 출처 이동 | 질문과 기준을 먼저 설정하는 흐름을 참고 | 탐색·비교·출처를 같은 공간에서 연결하는 흐름을 참고 |
| 현재 제약 | 새 추출은 사용자 AI 연결 필요, 텍스트 PDF 중심, 변경 부분만 재추출은 미구현 | 기능 범위·사용량은 요금제에 따라 다름 | 기능 범위·사용량은 요금제에 따라 다름 |

근거: [Elicit 체계적 문헌고찰](https://support.elicit.com/en/articles/14759154-systematic-reviews-in-elicit), [Elicit Reports](https://elicit.com/solutions/reports), [Liner Scholar](https://liner.com/scholar).

## 구성

- **작업 화면(기본)**: 문헌 × 항목 비교표와 원문 PDF. 상단 「문헌 모으기 · 근거 비교 · 보고서에 쓰기」와 「조사 설정」. 화면 규칙은 [docs/DESIGN.md](docs/DESIGN.md)
- **단계별 보기(학습 모드)**: 조사 설계 → 문헌 선별(판단의 근거가 된 원문 구절을 적으면 PDF에서 그 자리를 찾아 강조) → 원문 추출 → 근거 검토 → 종합 → 비교·내보내기
- **스킬**: `.claude/skills/deep-research/SKILL.md` — Claude Code가 원문을 읽고 추출·종합 응답을 만들어 같은 코어로 가져옵니다
- **CLI**: `uv run drk …` — UI와 같은 `deep_research/` 코어. 숨은 상태 없이 프로젝트 폴더의 JSON·YAML이 전부입니다

## 시작하기

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. `uv`는 필요한 Python이 없으면 관리형 Python을 설치할 수 있습니다. 저장소의 `.python-version`에 검증된 버전(3.12)이 지정되어 있어, `uv`가 아직 의존성 휠이 없는 최신 Python을 고르지 않습니다. 처음 설치할 때 인터넷이 필요합니다.

GitHub에서 이 저장소를 fork/clone하거나 ZIP을 풀고, **저장소 폴더의 터미널**에서 실행하세요.

```sh
uv sync --frozen
uv run --frozen streamlit run app.py --server.address 127.0.0.1
```

`--frozen`은 저장소의 `uv.lock`을 그대로 쓰라는 뜻입니다. 빼면 실행만으로 `uv.lock`이 다시 쓰여 `git status`에 바뀐 파일로 보일 수 있습니다.

브라우저가 열리지 않으면 `http://localhost:8501`을 직접 엽니다. 첫 화면의 **「조사 질문에서 시작」·「PDF에서 시작」** 또는 「예제로 살펴보기」의 **「논문 3편 예제 체험 · 바로 비교표 보기」**를 누르면 됩니다. 아래 1~9는 「단계별 보기」(학습 모드)의 순서입니다. macOS는 `sh start.command`, Windows는 `start.bat`도 사용할 수 있습니다. 파일을 더블클릭하는 방식이 OS 설정에 막히면 위 터미널 명령을 사용하세요.

설치가 막힐 때:

- **Windows에서 「uv를 찾지 못했습니다」**: PowerShell에서 `winget install astral-sh.uv`를 실행하고 `start.bat`을 다시 실행합니다. 방금 설치해 PATH가 아직 반영되지 않았어도 `start.bat`이 winget·공식 설치 스크립트의 설치 위치를 직접 찾고, pip로 설치했다면 `py -m uv`로 한 번 더 찾습니다. 그래도 안 되면 로그아웃 후 다시 로그인(또는 재시작)하거나 Python의 `Scripts` 폴더를 PATH에 추가합니다.
- **Windows에서 「애플리케이션 제어 정책에서 이 파일을 차단했습니다」**(`DLL load failed` 등): 설치가 실패한 것이 아니라 Windows 보안 정책(스마트 앱 컨트롤이나 기관의 응용 프로그램 제어)이 내려받은 라이브러리 파일을 막은 것일 수 있습니다. 이벤트 뷰어 → 응용 프로그램 및 서비스 로그 → Microsoft → Windows → CodeIntegrity → Operational에 이벤트 3077 같은 차단 기록이 있는지 보면 구분됩니다. 보안 정책을 직접 끄지 말고 기관 관리자에게 문의하세요. 한 PC에서는 막힌 라이브러리의 다른 판을 쓴 별도 환경(예: `uv run --frozen --with "pandas==3.0.1" streamlit run app.py --server.address 127.0.0.1`)에서 동작한 사례가 있으나, 모든 환경의 해법으로 확인된 것은 아닙니다.
- **Claude 데스크톱 앱만 쓰는 경우**: 데스크톱 앱의 로그인은 이 앱이 실행하는 `claude` 명령으로 넘어오지 않습니다. 「AI로 추출」을 쓰려면 일반 터미널에서 `claude`를 열어 `/login` 하거나, 웹 AI에 요청문을 붙여 넣는 경로를 씁니다.

1. 「＋ 새 조사」에서 프로젝트를 만듭니다. **논문 3편 예제 체험**은 실제 논문 3편을 공식 자료원에서 내려받습니다(약 20초, 적은 제목이 그대로 쓰입니다). 다운로드가 막히면 화면 안내대로 공식 PDF를 `example-cache/`에 넣고 다시 만드세요. 단계마다 화면 맨 위 「지금 할 일」 카드가 그 단계에서 할 일과 다음 단계를 알려 줍니다.
2. 조사 목적·범위·포함/제외 기준·추출 항목을 저장합니다.
3. PDF를 등록하고, 원문을 보면서 포함/제외/보류와 이유(필수)를 남깁니다. 판단의 근거가 된 원문 문장을 「근거 구절」에 붙이면 PDF에서 그 자리를 찾아 강조합니다. 같은 연구의 여러 보고서는 같은 연구 ID를 지정합니다.
4. 3단계에서 **AI를 돌릴 방법을 고릅니다.** ① Claude Code(앤트로픽의 터미널 AI 도구)가 있으면 「새 추출 실행 만들기」 → 화면의 `/deep-research` 요청문을 Claude Code에 붙여 넣기 → 「저장된 응답 새로 읽기」. ② 없으면 공통 사례에 한해 「수업용 예시 응답 불러오기」(새 AI 실행이 아니며, 이미 저장한 선별 판단은 바꾸지 않음). ③ 다른 사람이 만든 응답 JSON을 올릴 수도 있습니다.
5. 실행은 그 시점의 기준과 문헌을 고정한 작업 묶음입니다. 응답이 없는 빈 실행은 화면에서 지울 수 있습니다.
6. UI에서 저장된 응답을 새로 읽습니다. **추출값 옆의 실제 PDF**를 확인하고 채택·수정 후 채택·보류·제외를 기록합니다.
7. (선택) 종합 요청을 만들어 스킬로 실행합니다. 채택한 근거만 AI 종합에 사용됩니다. Claude Code가 없으면 이 단계는 건너뛰어도 되며, 채택 근거 표와 검토 기록이 결과물입니다.
8. 추출 항목 하나를 고쳐 **새 실행**을 만듭니다. 원문을 다시 읽은 결과를 기존 실행과 비교하고 개선 이슈를 작성합니다.
9. 결과 ZIP을 내려받아 다음 주 위키 작업에 사용합니다.

스킬 실행에는 사용 중인 Claude Code 계정의 이용 조건과 사용량이 적용됩니다. UI 자체는 AI를 내장하지 않습니다. Claude Code가 없으면 다른 에이전트에 요청 JSON을 전달하거나 선택 API 경로를 사용할 수 있습니다. AI를 사용할 수 없는 경우 원문 검색·독서 노트·자료 내보내기와 기존 결과 확인은 가능하지만 새로운 AI 추출을 실행한 것으로 표시하지 않습니다.

수업의 기본 읽기 범위는 **각 문헌의 첫 20쪽**입니다. 긴 부록의 처리 시간과 AI 사용량을 줄이기 위한 명시적 범위이며, 문헌 전체를 읽었다는 뜻이 아닙니다. 설계에서 쪽수 제한을 0으로 바꾸면 전체를 읽습니다. 각 근거와 보고서에 실제 읽기 범위를 보존합니다.

## 내 연구에 쓰기

예: “지방정부의 생성형 AI 도입 지침은 개인정보·책임·직원 교육을 어떻게 다루는가?”

- 조사 설계에서 지역, 문서 유형, 발행 기간과 선정 기준을 정합니다.
- 직접 확보한 정책 PDF를 등록합니다.
- 추출 항목을 `data_protection`, `accountability`, `training`처럼 고유 ID와 지침으로 바꿉니다.
- 원문에 명시한 내용과 자신의 해석을 분리해서 검토합니다. 한 문서를 여러 정책의 독립 근거로 중복 집계하지 않습니다.
- 채택한 근거를 종합하고 원문 위치와 함께 내보냅니다.

## 뜯어보기

```text
app.py                          # 로컬 UI 진입점
ui/
  chrome.py                     # 상태 낱말·색, 머리 띠, 빈 상태, PDF 창 (docs/DESIGN.md)
  pages.py                      # 여섯 단계 화면
assets/styles.css · static/fonts/   # 보조 스타일 · Pretendard(OFL) 서브셋
deep_research/
  project.py                    # 설정·문헌·선별 기록
  documents.py                  # PDF 색인·원문 위치 대조
  workflow.py                   # 실행·추출·검토·종합
  exports.py                    # 비교·Markdown/JSON/CSV
  providers.py                  # 선택 API·Crossref 검색
.claude/skills/deep-research/    # 에이전트 실행 지시문
projects/<name>/
  research-plan.yaml
  config/extraction-fields.yaml
  config/synthesis-rules.md
  sources/<source_id>/           # 원본 PDF와 좌표 색인
  catalog.json                  # 선별 상태·이유·연구 ID·근거 구절(원문 위치 포함)
  search-log.json
  runs/<run_id>/                 # 고정한 기준·요청·응답·검토 이력
```

설정과 코드를 수정하고 커밋한 뒤, 기준 실행과 변경 실행의 차이를 이슈에 남기세요. 실제 연구 자료, 개인정보, API 키는 커밋하지 마세요. `projects/`, `example-cache/`, `.env`는 기본적으로 Git에서 제외됩니다.

## 저장 위치와 실행 범위

기본 저장 위치는 저장소의 `projects/`입니다. 환경변수 `DRK_PROJECTS_DIR`로 다른 로컬 저장 폴더를 지정할 수 있습니다. 서버가 다른 컴퓨터에서 실행된다면 자료도 그 컴퓨터에 저장됩니다. 웹 동기화·계정 인증·공동 편집 기능은 없습니다. 기본 실행 명령은 `127.0.0.1`에만 연결합니다.

OpenAlex는 키 없이 쓰면 같은 네트워크의 사용자가 하루 무료 한도를 나눠 쓰므로, 검색이 `HTTP 429`로 막힐 수 있습니다. 그때는 Crossref·arXiv를 고르거나, [OpenAlex](https://openalex.org/settings/api)에서 무료 키를 받아 환경변수 `OPENALEX_API_KEY`에 넣고 앱을 다시 시작하세요. 키는 검색 기록·내보내기에 저장하지 않습니다.

## 선택 API

Chat Completions와 JSON 응답 형식을 지원하는 서버를 연결할 수 있습니다. 환경변수 `DRK_API_BASE`(예: 서버의 `/v1` 주소), `DRK_MODEL`, 필요 시 `DRK_API_KEY`를 설정하세요. `.env` 자동 로딩은 하지 않습니다. API 키는 파일·보고서에 저장하지 않습니다. 설정 후 「근거 비교 → 비교표 새로 만들기 → 설정된 API로 추출」에서 주소의 종류와 모델을 확인하고 실행할 수 있습니다. `http://127.0.0.1:포트/v1` 또는 `http://localhost:포트/v1`의 호환 서버도 사용할 수 있으나, 모델을 설치하거나 호환성을 자동 검증하지는 않습니다. 로컬 주소의 서버가 외부로 중계할 수도 있으므로 서버 설정을 확인해야 합니다.

```sh
uv run drk --project projects/my-research api-extract RUN_ID
uv run drk --project projects/my-research api-synthesize RUN_ID
```

문헌별로 순서대로 실행하며 완료한 응답은 보존합니다. API에는 선택한 문헌의 추출 텍스트가 전송되고 제공자의 비용·한도가 적용됩니다. 응답 형식이나 컨텍스트 한도를 지원하지 않으면 오류를 표시합니다. 서버별 호환성을 보장하지 않습니다. 외부 유료 API 실계정 실행 여부는 [검증 기록](docs/VALIDATION.md)에 구분합니다.

## 결과를 해석할 때

- **문자열 위치 일치 ≠ 의미적 지지 ≠ 사실 검증 완료.** 채택 판단에는 원문 문맥과 방법·대상을 읽는 작업이 필요합니다.
- 미발견, 위치 미확인, 사람의 보류·제외는 결론에서 제외하고 별도로 남깁니다.
- 검토를 바꾸면 이전 종합이 만료됩니다. 새 검토에 맞춰 다시 종합해야 합니다.
- 이 버전은 텍스트 레이어가 있는 PDF를 대상으로 합니다. OCR, 웹페이지 원문 저장, 표 구조 인식, 스캔 이미지 추출은 지원하지 않습니다. 글자 없는 PDF(스캔본)는 화면에 경고가 뜨고 AI 추출 실행이 만들어지지 않습니다. 쓰려면 [OCRmyPDF](https://ocrmypdf.readthedocs.io/) 등으로 글자 층을 만든 뒤 다시 등록하세요(예: `ocrmypdf --language kor+eng in.pdf out.pdf`).
- 회전·CropBox(잘라 낸 영역)가 다른 쪽은 원본을 보여주되 자동 강조를 검증된 위치로 처리하지 않습니다. 화면에는 글자가 원문 구간에 있는지와 함께 '채택할 수 없음'의 이유가 나오며, 이런 쪽의 값은 보류·제외로만 기록할 수 있습니다. 인쇄된 쪽 번호는 자동 추정하지 않으며 PDF의 1부터 시작하는 쪽수를 씁니다.
- 원문 단어의 일부만 맞는 인용(`unlikely`를 `likely`로, `119%`·`0.19%`를 `19%`로, 「비효율적」을 「효율적」으로 자른 경우)은 '단어 일부만 일치'로 표시되고 채택할 수 없습니다. 붙은 문장부호, 낱말에 붙은 각주 번호(`productivity12`), 한국어 조사·어미, 띄어쓰기 없이 이어진 한국어·중국어·일본어의 중간부터 시작한 인용은 일치로 봅니다. 다만 앞에서 잘린 글자가 비·불·미·무 같은 부정 접두어이면 일치로 보지 않습니다.
- 다단 편집·특수 글꼴·수식으로 읽기 순서가 깨질 수 있습니다. 위치 일치가 실패하면 보류하고 원문을 확인하세요.
- 곡선 따옴표(’ “ ”)와 대시(– —)는 직선 부호로 접어 대조합니다. 그 밖의 글자가 다르면 위치를 찾지 못합니다.
- 줄끝 하이픈으로 나뉜 단어(`produc-`/`tivity`)는 이어 쓴 인용도 찾지만, 인쇄된 그대로의 대조를 먼저 시도합니다. 구간이나 다음 쪽으로 이어지는 인용도 인용이 시작되는 구간에서부터 이어서 찾습니다.
- 「문헌 찾기」의 발행연도 조건은 각 검색 서버에 필터로 보내고, 검색 기록(`search-log.json`)에는 적용한 조건·색인별로 보낸 검색어·화면에 보인 목록이 그대로 남습니다. arXiv는 검색어의 모든 낱말이 들어간 문헌만 찾습니다(따옴표로 묶으면 구문).
- Crossref는 선택적인 서지 검색입니다. 웹 전체 딥리서치, 유료 원문 접근권, Scite의 전 세계 인용 맥락 데이터베이스를 제공하지 않습니다.
- 자동 PDF 받기는 공개 사본만 받습니다. 출판사 자체 페이지와 PDF 링크는 Unpaywall이 오픈액세스라고 할 때만 엽니다. 학교망의 기관 인증으로 구독 PDF가 자동으로 몰려 받아지는 일을 막기 위해서입니다. 로그인·유료벽·봇 확인 창은 우회하지 않으며, 그런 문헌은 사람이 자기 브라우저에서 받습니다. 문헌 하나에 40초를 넘기지 않고, 모든 요청 사이에 간격을 둡니다. 연락처 이메일은 Unpaywall 조회에만 붙고(환경변수 `DRK_CONTACT_EMAIL`), 지켜볼 다운로드 폴더 기본값은 `DRK_DOWNLOADS_DIR`로 바꿀 수 있습니다.
- 「다운로드 폴더 지켜보기」는 켤 때 폴더에 없던 PDF만 봅니다(파일 날짜는 보지 않음). 1쪽에 맨 먼저 찍힌 DOI(그 논문 자신의 DOI)나 arXiv 번호, 또는 1쪽 머리의 전체 제목(네 낱말 이상)이 기다리는 문헌 하나와 맞을 때만 등록합니다. 참고문헌에 다른 논문의 DOI가 있어도 그것으로 묶지 않고, 보충자료·부록은 자동으로 묶지 않습니다. 맞지 않는 PDF는 「그래도 등록」을 눌러야 들어가고, 자동으로 고르기 어려우면 「올린 PDF와 직접 묶기」를 씁니다. macOS는 처음에 다운로드 폴더 접근을 허용할지 물을 수 있습니다.
- 기본 서버는 localhost에서 실행합니다. 계정·접근 제어를 제공하지 않으므로 공용 인터넷 서비스로 그대로 배포하지 마세요.

## 함께 만든 사람들

2026년 10월 31일, 수업 실습과 각자의 문헌조사에서 이 킷을 직접 설치해 쓴 분들이 이슈와 수정 PR을 보냈습니다. 재현 절차와 코드 위치까지 적어 준 덕분에 아래가 나아졌습니다.

### 개선된 점

| 영역 | 핵심 | 관련 이슈·PR |
|---|---|---|
| 설치·첫 실행 | Python 3.12 고정, 실행해도 `uv.lock` 그대로, 첫 실행 멈춤·팝업 제거, PATH 밖의 uv도 찾음 | [#1](https://github.com/parkjui92/deep-research-kit/issues/1) [#2](https://github.com/parkjui92/deep-research-kit/pull/2) [#9](https://github.com/parkjui92/deep-research-kit/issues/9) [#10](https://github.com/parkjui92/deep-research-kit/issues/10) [#11](https://github.com/parkjui92/deep-research-kit/issues/11) [#12](https://github.com/parkjui92/deep-research-kit/issues/12) [#23](https://github.com/parkjui92/deep-research-kit/issues/23) [#26](https://github.com/parkjui92/deep-research-kit/issues/26) |
| AI 실행의 안전 | Claude Code 권한 축소·검토 기록 보호, Windows `claude.cmd`·한글 출력 대응, 저장된 결과로 성공 판정 | [#3](https://github.com/parkjui92/deep-research-kit/issues/3) [#6](https://github.com/parkjui92/deep-research-kit/issues/6) [#7](https://github.com/parkjui92/deep-research-kit/pull/7) [#13](https://github.com/parkjui92/deep-research-kit/pull/13) [#24](https://github.com/parkjui92/deep-research-kit/issues/24) [#25](https://github.com/parkjui92/deep-research-kit/issues/25) [#32](https://github.com/parkjui92/deep-research-kit/issues/32) |
| 원문 대조의 정확도 | 경계를 넘는 인용 찾기, 단어 일부 일치 차단, 세로 arXiv 표기 읽기, 스캔본·회전 쪽 안내 | [#4](https://github.com/parkjui92/deep-research-kit/issues/4) [#5](https://github.com/parkjui92/deep-research-kit/issues/5) [#8](https://github.com/parkjui92/deep-research-kit/pull/8) [#14](https://github.com/parkjui92/deep-research-kit/issues/14) [#15](https://github.com/parkjui92/deep-research-kit/pull/15) [#22](https://github.com/parkjui92/deep-research-kit/issues/22) [#30](https://github.com/parkjui92/deep-research-kit/issues/30) |
| 검토 결과 보존 | 고친 값이 종합까지 유지, 화면에 보이는 값과 내보내는 값이 같음 | [#21](https://github.com/parkjui92/deep-research-kit/issues/21) [#31](https://github.com/parkjui92/deep-research-kit/issues/31) [#34](https://github.com/parkjui92/deep-research-kit/issues/34) |
| 검토 편의 | 한 칸의 발췌를 PDF에 모두 강조, 항목별 추출 분량, 영어 발췌의 참고 번역 | [#16](https://github.com/parkjui92/deep-research-kit/issues/16) [#28](https://github.com/parkjui92/deep-research-kit/issues/28) [#29](https://github.com/parkjui92/deep-research-kit/issues/29) |
| 문헌 수집 | 검색 기록이 화면 목록과 같음, 공개 PDF 자동 받기 확대, 내 브라우저로 받은 PDF 자동 등록·묶기 | [#33](https://github.com/parkjui92/deep-research-kit/issues/33) |
| 처음 쓰는 사람의 안내 | 단계별 보기 오류 해결, 추출 메모·읽기 범위 표시, 예시 질문 알림, 첫 화면에 흐름과 결과물 | [#17](https://github.com/parkjui92/deep-research-kit/issues/17) [#18](https://github.com/parkjui92/deep-research-kit/issues/18) [#19](https://github.com/parkjui92/deep-research-kit/issues/19) [#20](https://github.com/parkjui92/deep-research-kit/issues/20) |
| 남은 제안 | 스캔본 OCR(설치 부담으로 보류), 내 질문 기준으로 먼저 볼 칸 표시·정렬 | [#27](https://github.com/parkjui92/deep-research-kit/issues/27) [#17](https://github.com/parkjui92/deep-research-kit/issues/17) |

이슈와 PR로 기여한 분들은 저장소의 [Contributors](https://github.com/parkjui92/deep-research-kit/graphs/contributors)에 올라 있습니다.

이슈와 PR은 언제든 환영합니다. 재현 순서, 기대한 결과와 실제 결과, 관련 코드 위치를 적어 주면 가장 빨리 반영됩니다.

## 개발 검증과 재사용

```sh
uv lock --check
uv sync --frozen --extra dev
uv run --frozen pytest -q
uv run --frozen ruff check .
```

[화면 설계 원칙](docs/DESIGN.md), [재사용 분석](docs/REUSE.md), [검증 기록](docs/VALIDATION.md), [라이선스](LICENSE), [외부 구성요소 고지](THIRD_PARTY_NOTICES.md)를 확인하세요.

프로젝트 스킬 형식은 [Claude Code 공식 문서](https://code.claude.com/docs/en/skills), 선택 API 요청 구조는 [공식 Chat Completions API 문서](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)를 기준으로 작성했습니다.
