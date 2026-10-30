# Deep Research Kit

**문헌을 찾고, 원문을 읽고, 근거를 판단하고, 바뀐 기준의 결과를 비교하는 로컬 문헌조사 도구.**

기술영향평가를 공통 사례로 제공하지만 조사 질문·선별 기준·추출 항목을 바꾸면 논문 준비, 정책 비교, 사업 검토에도 사용할 수 있습니다.

- **UI**: 조사 설계 → 문헌 선별 → 추출 → 실제 PDF 하이라이트와 사람의 검토 → 종합 → 비교·내보내기
- **스킬**: `.claude/skills/deep-research/SKILL.md`. 같은 프로젝트 파일과 Python 코어를 사용합니다.
- **다음 작업**: Markdown + JSON + CSV로 문헌 ID·근거 ID·원문 위치·검토 상태를 보존합니다. 위키 작성은 다음 단계입니다.

## 시작하기

Python 3.11 이상과 [uv](https://docs.astral.sh/uv/getting-started/installation/)가 필요합니다. `uv`는 필요한 Python이 없으면 관리형 Python을 설치할 수 있습니다. 처음 설치할 때 인터넷이 필요합니다.

GitHub에서 이 저장소를 fork/clone하거나 ZIP을 풀고, **저장소 폴더의 터미널**에서 실행하세요.

```sh
uv sync --frozen
uv run streamlit run app.py --server.address 127.0.0.1
```

브라우저에서 `http://localhost:8501`을 엽니다. macOS는 `sh start.command`, Windows는 `start.bat`도 사용할 수 있습니다. 파일을 더블클릭하는 방식이 OS 설정에 막히면 위 터미널 명령을 사용하세요.

1. 왼쪽에서 프로젝트를 만듭니다. **공통 사례 준비**는 실제 논문 3편을 공식 자료원에서 내려받습니다. 최초 다운로드가 막히면 아래의 수업 전 준비를 사용하세요.
2. 조사 목적·범위·포함/제외 기준·추출 항목을 저장합니다.
3. PDF를 등록하고, 원문을 보면서 포함/제외/보류와 이유를 남깁니다. 같은 연구의 여러 보고서는 같은 연구 ID를 지정합니다.
4. **새 추출 실행 만들기**를 누릅니다. 이때의 기준과 문헌이 실행 기록에 고정됩니다.
5. Claude Code에서 이 저장소를 열고 UI의 `/deep-research` 요청을 붙여 넣습니다. 스킬이 원문을 읽고 JSON 응답을 작성해 공통 CLI로 가져옵니다.
6. UI에서 저장된 응답을 새로 읽습니다. **추출값 옆의 실제 PDF**를 확인하고 채택·수정 후 채택·보류·제외를 기록합니다.
7. 종합 요청을 만들어 스킬로 실행합니다. 채택한 근거만 AI 종합에 사용됩니다.
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

공통 사례를 처음 살펴볼 때는 **원문 추출 → 공통 사례·사전 작성 예시 → 기준 추출 예시 불러오기**를 사용할 수 있습니다. 12개 추출값을 원문과 대조해 가져오며 전부 미검토 상태입니다. 이는 새 AI 실행이 아닙니다. 같은 PDF 해시와 기본 설계에서만 사용할 수 있고, 학생이 지침을 고친 다음에는 스킬이나 API로 새로 추출해야 합니다.

## 내 연구에 쓰기

예: “지방정부의 생성형 AI 도입 지침은 개인정보·책임·직원 교육을 어떻게 다루는가?”

- 조사 설계에서 지역, 문서 유형, 발행 기간과 선정 기준을 정합니다.
- 직접 확보한 정책 PDF를 등록합니다.
- 추출 항목을 `data_protection`, `accountability`, `training`처럼 고유 ID와 지침으로 바꿉니다.
- 원문에 명시한 내용과 자신의 해석을 분리해서 검토합니다. 한 문서를 여러 정책의 독립 근거로 중복 집계하지 않습니다.
- 채택한 근거를 종합하고 원문 위치와 함께 내보냅니다.

## 뜯어보기

```text
app.py                          # 로컬 UI
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
  catalog.json                  # 선별 상태·이유·연구 ID
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
- 이 버전은 텍스트 레이어가 있는 PDF를 대상으로 합니다. OCR, 웹페이지 원문 저장, 표 구조 인식, 스캔 이미지 추출은 지원하지 않습니다.
- 회전·cropbox가 다른 페이지는 원본을 보여주되 자동 강조를 검증된 위치로 처리하지 않습니다. 인쇄된 쪽 번호는 자동 추정하지 않으며 PDF의 1부터 시작하는 쪽수를 씁니다.
- 다단 편집·특수 글꼴·수식으로 읽기 순서가 깨질 수 있습니다. 위치 일치가 실패하면 보류하고 원문을 확인하세요.
- 줄끝 하이픈으로 나뉜 단어(`produc-`/`tivity`)는 이어 쓴 인용도 찾지만, 인쇄된 그대로의 대조를 먼저 시도합니다. 쪽을 넘는 인용은 찾지 못하므로 쪽마다 나누어 인용하세요.
- Crossref는 선택적인 서지 검색입니다. 웹 전체 딥리서치, 유료 원문 접근권, Scite의 전 세계 인용 맥락 데이터베이스를 제공하지 않습니다.
- 기본 서버는 localhost에서 실행합니다. 계정·접근 제어를 제공하지 않으므로 공용 인터넷 서비스로 그대로 배포하지 마세요.

## 개발 검증과 재사용

```sh
uv sync --frozen --extra dev
uv run pytest -q
uv run ruff check .
```

[재사용 분석](docs/REUSE.md), [검증 기록](docs/VALIDATION.md), [라이선스](LICENSE), [외부 구성요소 고지](THIRD_PARTY_NOTICES.md)를 확인하세요.

프로젝트 스킬 형식은 [Claude Code 공식 문서](https://code.claude.com/docs/en/skills), 선택 API 요청 구조는 [공식 Chat Completions API 문서](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)를 기준으로 작성했습니다.
