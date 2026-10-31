# Deep Research Kit

**여러 논문을 내 질문에 맞는 비교표로 정리하고, AI가 뽑은 값을 원문으로 확인해 근거로 남기는 로컬 문헌조사 도구.** 소프트웨어는 무료이고, AI 실행은 사용자의 Claude Code 계정(또는 쓰던 웹 AI)을 씁니다.

## 왜 만들었나

문헌조사의 시간은 논문을 읽는 데보다 **정리하고 확인하는 데** 더 많이 듭니다. 논문을 모은 뒤 비교표를 따로 만들고, AI가 요약해 준 값이 맞는지 원문을 다시 뒤지고, 기준을 바꾸면 처음부터 다시 하고, 보고서에 옮길 때 저자·쪽수를 다시 찾습니다. Elicit 같은 도구가 이 일을 해 주지만 구독이 필요하고, 체계적 검토·출력 기능은 유료 요금제에 있습니다. 이 도구는 그 작업 흐름을 **내 컴퓨터에서, 내가 이미 쓰는 AI 계정으로** 끝내려고 만들었습니다. 수업(한양대 신흥기술영향평가, 2026-2학기 9주차)에서 "AI에게 조사를 맡기되 근거는 사람이 확인한다"를 연습하는 교재로 시작했고, 질문·선별 기준·추출 항목을 바꾸면 논문 준비·정책 비교·사업 검토에 그대로 씁니다.

## 어떻게 쓰나

1. **문헌 모으기** — 「문헌 찾기」에서 OpenAlex·arXiv·Crossref를 한 번에 검색해 후보를 담습니다. 오픈액세스 PDF는 자동으로 등록되고, 못 받은 것은 서지만 남아 원문 링크로 받아 올릴 수 있습니다. 내 PDF나 Zotero의 RIS/BibTeX도 「PDF 가져오기」로 넣습니다.
2. **항목 정하기** — 비교하고 싶은 것을 「항목 추가」에 "이름"이 아니라 **지침**으로 적습니다(예: 주요 결과 · 측정된 결과와 단위·조건을 보존한다). 기본 4개(대상·방법·결과·한계)가 들어 있습니다.
3. **AI로 추출** — 「AI로 추출」을 누르면 설치된 Claude Code를 앱이 직접 불러 문헌을 읽히고 비교표를 채웁니다. Claude Code가 없으면 문헌마다 '요청문+원문 묶음'을 내려받아 쓰던 웹 AI(Claude·ChatGPT 등)에 붙여 넣고, 돌아온 JSON을 붙여 넣으면 됩니다. 수업용 공통 사례(실제 논문 3편)에는 미리 만든 예제 응답이 있어 버튼 하나로 비교표를 봅니다.
4. **원문으로 확인** — 비교표의 칸을 누르면 그 값을 AI가 뽑아낸 **원문 문장이 PDF에 표시**됩니다. 앞뒤를 읽고 채택·수정 후 채택·보류·제외를 이유와 함께 저장합니다. 채택한 값만 결과에 들어갑니다.
5. **가져가기** — 「내보내기」에서 보고서(Markdown)·문헌×항목 표(CSV)·근거별 검토 기록(CSV)·JSON을 ZIP으로 받고, 칸마다 「인용 문장 복사」(저자·연도·제목·게재지·DOI·PDF 쪽·원문)와 참고문헌 목록을 씁니다. 항목이나 문헌을 더하면 새 실행이 만들어지고 이전 실행·검토는 보존되어 전후를 비교합니다.

처음이면 첫 화면의 **「논문 3편 예제 체험 · 바로 비교표 보기」**로 5분 안에 전체 흐름을 볼 수 있습니다. 조사 설계부터 한 단계씩 따라가는 **「단계별 보기」(학습 모드)**도 있습니다.

## 다른 도구와 다른 점

| | Deep Research Kit | 일반 AI 요약·딥리서치 | Elicit 류 | Zotero |
|---|---|---|---|---|
| 비용 | 무료(AI는 내 계정) | 구독 | 무료 제한 + 유료 | 무료 |
| AI가 뽑은 값의 근거 | **원문 PDF의 그 문장에 테두리** — 문자열이 실제로 있는 자리만 인정, 없으면 '못 찾음'으로 표시 | 링크·각주 수준 | 발췌 표시 | 해당 없음 |
| 사람의 확인 | **채택·수정·보류·제외 기록이 필수**, 채택한 값만 결과에. AI 원래 값과 사람의 수정값을 따로 보존 | 없음 | 수정 가능 | 주석 |
| 기준을 바꿨을 때 | 실행 단위로 설계·문헌·값·판단을 고정하고 **전후 비교**, 판단이 바뀌면 이전 종합은 만료 | 다시 질문 | 열 추가 | 해당 없음 |
| 결과 | 비교표 CSV·근거 기록 CSV·보고서·참고문헌·인용 문장, 모두 파일로 내 폴더에 | 채팅 텍스트 | 표 내보내기(유료) | 참고문헌 |
| 한계 | 새 AI 추출에 Claude Code 또는 웹 AI 붙여넣기가 필요 · 텍스트 층 있는 PDF만 · "바뀐 부분만 재처리"는 다음 판 | | | |

원칙은 하나입니다. **문자열이 원문에 있다는 것, 사람이 읽고 채택했다는 것, AI가 종합했다는 것을 섞지 않는다.** 각 단계의 상태를 기록으로 남기고, 어느 하나를 다른 것으로 바꿔 말하지 않습니다.

## 구성

- **작업 화면(기본)**: 문헌 × 항목 비교표와 원문 PDF. 상단 「문헌 찾기 · PDF 가져오기 · 항목 추가 · AI로 추출 · 내보내기 · 단계별 보기」. 화면 규칙은 [docs/DESIGN.md](docs/DESIGN.md)
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

브라우저가 열리지 않으면 `http://localhost:8501`을 직접 엽니다. 첫 화면의 **「내 문헌으로 시작」** 또는 **「논문 3편 예제 체험 · 바로 비교표 보기」**를 누르면 됩니다. 아래 1~9는 「단계별 보기」(학습 모드)의 순서입니다. macOS는 `sh start.command`, Windows는 `start.bat`도 사용할 수 있습니다. 파일을 더블클릭하는 방식이 OS 설정에 막히면 위 터미널 명령을 사용하세요.

설치가 막힐 때:

- **Windows에서 「uv를 찾지 못했습니다」**: PowerShell에서 `winget install astral-sh.uv`를 실행하고 `start.bat`을 다시 실행합니다. 방금 설치해 PATH가 아직 반영되지 않았어도 `start.bat`이 winget·공식 설치 스크립트의 설치 위치를 직접 찾고, pip로 설치했다면 `py -m uv`로 한 번 더 찾습니다. 그래도 안 되면 로그아웃 후 다시 로그인(또는 재시작)하거나 Python의 `Scripts` 폴더를 PATH에 추가합니다.
- **Windows에서 「애플리케이션 제어 정책에서 이 파일을 차단했습니다」**(`DLL load failed` 등): 설치가 실패한 것이 아니라 Windows 보안 정책(스마트 앱 컨트롤이나 기관의 응용 프로그램 제어)이 내려받은 라이브러리 파일을 막은 것일 수 있습니다. 이벤트 뷰어 → 응용 프로그램 및 서비스 로그 → Microsoft → Windows → CodeIntegrity → Operational에 이벤트 3077 같은 차단 기록이 있는지 보면 구분됩니다. 보안 정책을 직접 끄지 말고 기관 관리자에게 문의하세요. 한 PC에서는 막힌 라이브러리의 다른 판을 쓴 별도 환경(예: `uv run --frozen --with "pandas==3.0.1" streamlit run app.py --server.address 127.0.0.1`)에서 동작한 사례가 있으나, 모든 환경의 해법으로 확인된 것은 아닙니다.
- **Claude 데스크톱 앱만 쓰는 경우**: 데스크톱 앱의 로그인은 이 앱이 실행하는 `claude` 명령으로 넘어오지 않습니다. 「AI로 추출」을 쓰려면 일반 터미널에서 `claude`를 열어 `/login` 하거나, 웹 AI에 요청문을 붙여 넣는 경로를 씁니다.

1. 왼쪽에서 프로젝트를 만듭니다. **공통 사례 만들기**는 실제 논문 3편을 공식 자료원에서 내려받습니다(약 20초, 적은 제목이 그대로 쓰입니다). 최초 다운로드가 막히면 아래의 수업 전 준비를 사용하세요. 단계마다 화면 맨 위 「지금 할 일」 카드가 그 단계에서 할 일과 다음 단계를 알려 줍니다.
2. 조사 목적·범위·포함/제외 기준·추출 항목을 저장합니다.
3. PDF를 등록하고, 원문을 보면서 포함/제외/보류와 이유(필수)를 남깁니다. 판단의 근거가 된 원문 문장을 「근거 구절」에 붙이면 PDF에서 그 자리를 찾아 강조합니다. 같은 연구의 여러 보고서는 같은 연구 ID를 지정합니다.
4. 3단계에서 **AI를 돌릴 방법을 고릅니다.** ① Claude Code(앤트로픽의 터미널 AI 도구)가 있으면 「새 추출 실행 만들기」 → 화면의 `/deep-research` 요청문을 Claude Code에 붙여 넣기 → 「저장된 응답 새로 읽기」. ② 없으면 공통 사례에 한해 「수업용 예시 응답 불러오기」(새 AI 실행이 아니며, 이미 저장한 선별 판단은 바꾸지 않음). ③ 다른 사람이 만든 응답 JSON을 올릴 수도 있습니다.
5. 실행은 그 시점의 기준과 문헌을 고정한 작업 묶음입니다. 응답이 없는 빈 실행은 화면에서 지울 수 있습니다.
6. UI에서 저장된 응답을 새로 읽습니다. **추출값 옆의 실제 PDF**를 확인하고 채택·수정 후 채택·보류·제외를 기록합니다.
7. (선택) 종합 요청을 만들어 스킬로 실행합니다. 채택한 근거만 AI 종합에 사용됩니다. Claude Code가 없으면 이 단계는 건너뛰어도 되며, 채택 근거 표와 검토 기록이 결과물입니다.
8. 추출 항목 하나를 고쳐 **새 실행**을 만듭니다. 원문을 다시 읽은 결과를 기존 실행과 비교하고 개선 이슈를 작성합니다.
9. 결과 ZIP을 내려받아 다음 주 위키 작업에 사용합니다.

스킬 실행에는 사용 중인 Claude Code 계정의 이용 조건과 사용량이 적용됩니다. UI 자체는 AI를 내장하지 않습니다. Claude Code가 없으면 다른 에이전트에 요청 JSON을 전달하거나 선택 API 경로를 사용할 수 있습니다. AI를 사용할 수 없는 경우 PDF 검토와 기존 결과 확인은 가능하지만 새로운 AI 추출을 실행한 것으로 표시하지 않습니다.

수업의 기본 읽기 범위는 **각 문헌의 첫 20쪽**입니다. 긴 부록의 처리 시간과 AI 사용량을 줄이기 위한 명시적 범위이며, 문헌 전체를 읽었다는 뜻이 아닙니다. 설계에서 쪽수 제한을 0으로 바꾸면 전체를 읽습니다. 각 근거와 보고서에 실제 읽기 범위를 보존합니다.

## 수업 전 공통 사례 준비

```sh
uv run python -m deep_research.examples --project projects/class-example
```

실제 원문과 해시·출처·버전·이용 조건은 `projects/class-example/example-manifest.json`에 기록됩니다. `example-cache/`의 PDF를 미리 준비하면 같은 자료를 네트워크 없이 다시 등록할 수 있습니다. 준비에 실패한 자료는 오류로 표시되며, 내려받은 자료는 보존됩니다.

| 자료 | 사용하는 버전 | 원문 이용 조건 |
|---|---|---|
| Becker et al., *Measuring the Impact of Early-2025 AI…* | arXiv 2507.09089 v2, 2025 | CC BY 4.0 |
| Si, Hashimoto & Yang, *The Ideation-Execution Gap…* | arXiv 2506.20803 v1, 2025 | CC BY 4.0 |
| Brodeur et al., *AI-assisted teams outperform…* | PNAS 출판본, 2026 | CC BY-NC-ND 4.0 |

이는 수업용으로 고정한 자료 묶음이며 특정 주제의 포괄적인 최신 문헌 목록은 아닙니다. PDF 원본은 코드의 Apache 라이선스에 포함되지 않습니다. 재배포 시 각 문헌의 이용 조건과 저작자·출처·버전을 유지해야 합니다.

공통 사례를 처음 살펴볼 때는 **3 · 원문 추출 → ② 수업용 예시 응답 불러오기**를 사용할 수 있습니다. 12개 추출값을 원문과 대조해 가져오며 전부 미검토 상태입니다. 이는 새 AI 실행이 아닙니다. 같은 PDF와 기본 설계에서만 쓸 수 있고(설계를 바꿨으면 화면의 「기본 설계로 되돌리고 예시 불러오기」), 학생이 지침을 고친 다음에는 스킬이나 API로 새로 추출해야 합니다. 이미 저장한 선별 판단·이유·근거 구절은 바꾸지 않고, 아직 판단하지 않은 문헌만 포함으로 둡니다. 응답 없는 빈 실행이 같은 문헌으로 있으면 새 실행을 만들지 않고 그 실행을 채웁니다.

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

## 선택 API

Chat Completions와 JSON 응답 형식을 지원하는 서버를 연결할 수 있습니다. 환경변수 `DRK_API_BASE`(예: 서버의 `/v1` 주소), `DRK_MODEL`, 필요 시 `DRK_API_KEY`를 설정하세요. `.env` 자동 로딩은 하지 않습니다. API 키는 파일·보고서에 저장하지 않습니다.

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
- 기본 서버는 localhost에서 실행합니다. 계정·접근 제어를 제공하지 않으므로 공용 인터넷 서비스로 그대로 배포하지 마세요.

## 함께 만든 사람들

2026년 10월 31일, 수업 실습과 각자의 문헌조사에서 이 킷을 직접 설치해 쓴 분들이 이슈와 수정 PR을 보냈습니다. 재현 절차와 코드 위치까지 적어 준 덕분에 아래가 나아졌습니다.

### 협업으로 좋아진 점

| 영역 | 나아진 점 | 관련 이슈·PR |
|---|---|---|
| 설치·첫 실행 | Python 3.12로 고정해 최신 Python에서 설치가 멈추지 않음. 실행만으로 `uv.lock`이 바뀌지 않음. 첫 실행의 `Email:` 대기와 Streamlit 스킬 설치 팝업을 없앰. PATH에 없거나 방금 설치한 uv도 찾음. Windows 보안 정책 차단을 설치 실패와 구분하는 안내 | [#1](https://github.com/parkjui92/deep-research-kit/issues/1) [#2](https://github.com/parkjui92/deep-research-kit/pull/2) [#9](https://github.com/parkjui92/deep-research-kit/issues/9) [#10](https://github.com/parkjui92/deep-research-kit/issues/10) [#11](https://github.com/parkjui92/deep-research-kit/issues/11) [#12](https://github.com/parkjui92/deep-research-kit/issues/12) [#23](https://github.com/parkjui92/deep-research-kit/issues/23) [#26](https://github.com/parkjui92/deep-research-kit/issues/26) |
| AI 실행의 안전과 신뢰 | 「AI로 추출」의 Claude Code 권한을 원문 읽기·해당 실행의 초안 쓰기·`drk` 명령으로 줄이고, 실행 중 사람의 검토 기록이 바뀌면 되돌림. 사용자 설정 변수 유지, 사용량을 쓰지 않는 상태 확인, 같은 프로젝트의 동시 실행 방지. Windows npm 설치본(`claude.cmd`)에서도 요청문과 옵션이 잘리지 않음. 저장된 결과로 성공을 판정하고 한글 Windows 출력도 UTF-8로 읽음 | [#3](https://github.com/parkjui92/deep-research-kit/issues/3) [#6](https://github.com/parkjui92/deep-research-kit/issues/6) [#7](https://github.com/parkjui92/deep-research-kit/pull/7) [#13](https://github.com/parkjui92/deep-research-kit/pull/13) [#24](https://github.com/parkjui92/deep-research-kit/issues/24) [#25](https://github.com/parkjui92/deep-research-kit/issues/25) [#32](https://github.com/parkjui92/deep-research-kit/issues/32) |
| 원문 대조의 정확도 | 쪽·구간 경계를 넘는 인용도 위치를 찾음. 단어 일부만 맞는 인용(`unlikely`→`likely`)은 일치로 보지 않음. 여백의 세로 arXiv 판·날짜 표기를 읽음. 글자 없는 스캔본은 AI 실행 전에 막음. 회전·CropBox 쪽은 채택할 수 없는 이유를 보여 줌 | [#4](https://github.com/parkjui92/deep-research-kit/issues/4) [#5](https://github.com/parkjui92/deep-research-kit/issues/5) [#8](https://github.com/parkjui92/deep-research-kit/pull/8) [#14](https://github.com/parkjui92/deep-research-kit/issues/14) [#15](https://github.com/parkjui92/deep-research-kit/pull/15) [#22](https://github.com/parkjui92/deep-research-kit/issues/22) [#30](https://github.com/parkjui92/deep-research-kit/issues/30) |
| 사람의 검토가 결과까지 | 고친 값이 「채택」 저장이나 종합 요청에서 AI 원래 값으로 돌아가지 않음. 화면에 보이는 글자와 CSV·보고서·종합으로 나가는 값이 같음(숨김 HTML·`$` 수식 해석 차단) | [#21](https://github.com/parkjui92/deep-research-kit/issues/21) [#31](https://github.com/parkjui92/deep-research-kit/issues/31) [#34](https://github.com/parkjui92/deep-research-kit/issues/34) |
| 검색 기록의 재현성 | arXiv는 검색어의 모든 낱말이 들어간 문헌만 찾고, 발행연도는 검색 서버에 필터로 보냄. 검색 기록이 화면에 보인 목록과 같음 | [#33](https://github.com/parkjui92/deep-research-kit/issues/33) |
| 처음 쓰는 사람의 안내 | 「단계별 보기」 전환 오류 해결. 칸 상세에 AI 메모와 읽기 범위 표시. 조사 질문이 예시 그대로면 추출 전에 알리고 문헌 수 상한을 보여 줌. 첫 화면에 흐름과 결과물, 판정 폼에 판정 기준과 입력 예시 | [#17](https://github.com/parkjui92/deep-research-kit/issues/17) [#18](https://github.com/parkjui92/deep-research-kit/issues/18) [#19](https://github.com/parkjui92/deep-research-kit/issues/19) [#20](https://github.com/parkjui92/deep-research-kit/issues/20) |

다음 판에서 설계를 검토할 제안: 원문 발췌 번역 보기([#16](https://github.com/parkjui92/deep-research-kit/issues/16)), 스캔본 OCR([#27](https://github.com/parkjui92/deep-research-kit/issues/27)), 한 칸의 근거 모두 보기([#28](https://github.com/parkjui92/deep-research-kit/issues/28)), 항목별 추출 분량([#29](https://github.com/parkjui92/deep-research-kit/issues/29)), 내 질문과 겹치는 문구 표시·정렬([#17](https://github.com/parkjui92/deep-research-kit/issues/17)).

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
