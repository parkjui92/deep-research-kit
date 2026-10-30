# 재사용과 역공학 검토

작성: 2026-10-30. 공개 소스는 저장소 소스 분석을, 배포된 JavaScript는 설치된 REA를 사용했다. 정적 관찰과 실행 검증을 구분한다.

## 가져온 것

**streamlit-pdf-viewer 0.0.30을 의존성으로 사용한다.** 학생이 원문을 눈으로 읽을 수 있는 PDF 렌더링·하이라이트 구현을 재사용한다. 별도 앱 전체를 fork하지 않고, 조사 설계·검토 이력·실행 비교·내보내기는 우리 공통 Python 코어에서 구현했다.

소스 확인 커밋: `c0dea0a5127f746c993c678ea6241d4685679b31` (Apache-2.0)

- [Python 인터페이스](https://github.com/ScienciaLAB/streamlit-pdf-viewer/blob/c0dea0a5127f746c993c678ea6241d4685679b31/streamlit_pdf_viewer/__init__.py)
- [PDF 렌더러](https://github.com/ScienciaLAB/streamlit-pdf-viewer/blob/c0dea0a5127f746c993c678ea6241d4685679b31/streamlit_pdf_viewer/frontend/src/PdfViewer.vue)

관찰: 좌표는 좌상단 기준 PDF point, page는 1부터 센다. `scroll_to_annotation`은 ID가 아닌 위치 인덱스다. `scroll_to_page`와 동시에 지정할 수 없다. annotation 변경만 감시하는 watcher가 없으므로 문헌·근거·좌표를 포함한 component key로 다시 마운트한다. URL 문자열을 바로 넘기지 않고 보존한 PDF bytes를 전달한다.

## REA 배포 파일 분석

입력: 설치한 wheel의 `frontend/dist/js/app.459f111b.js`.

- 배포 디렉터리 SHA-256: `de720267af98f07550d3de072137404bcf591a62166475751d0a441ceb5e7e84`
- 선택한 JS SHA-256: `8fc344e0ab06f9f63ee350ad2e6962e0c17825266dfec58977481dadb56b3197`
- REA `analyze-javascript-application`, summary 출력 + 전체 evidence bundle 저장.
- 선택한 JS 1개 파싱 성공, parse failure 0. 분석한 텍스트 11,942 bytes, AST 4,251 nodes, findings 22.
- 전체 아티팩트 중 4개 파일은 분석 범위 밖이다. 정적 그래프의 전체 커버리지는 partial이며 런타임 동작을 증명하지 않는다.
- 첫 실행은 macOS 컴파일 캐시의 쓰기 권한으로 실패했다. 승인된 동일 범위 실행에서 분석을 완료했다. 실패를 분석 성공으로 기록하지 않았다.
- 전체 원시 증거는 로컬 개발 검증용이며 사용자 머신 절대경로를 포함하므로 공개 패키지에 넣지 않는다. 위 해시·범위·결과 요약으로 재현 대상을 특정한다.

## EviStreams에서 배운 것과 버린 것

프런트엔드 `937bdc6e1d8750164e18a7ce2e8ad09cb4a3d276`, 백엔드 `aae3b7699526fe3d636340c850a63e6da052b288`, 모두 Apache-2.0.

- [SourceLocation 모델과 정규화 매핑](https://github.com/karthik-strikes/evistream_backend/blob/aae3b7699526fe3d636340c850a63e6da052b288/utils/source_linker.py): 추출값과 문헌의 원문 위치를 분리하는 설계를 참고했다.
- [textMatch](https://github.com/karthik-strikes/evistream_frontend/blob/937bdc6e1d8750164e18a7ce2e8ad09cb4a3d276/lib/textMatch.ts): 긴 단어 하나를 찾는 fallback과 영숫자만 남기는 정규화는 채택하지 않았다. 한국어를 보존하고 실제 매칭 위치의 원래 단어 좌표를 사용한다.
- 반복 문구는 ambiguous, 원문에 없는 인용은 unmatched로 남긴다. 느슨한 유사도 점수를 검증 완료로 올리지 않는다.
- 모델에게 bbox를 생성시키지 않는다. PDF 파서가 반환한 좌표로 실제 문서에 강조한다.

## 우리 도구에서 추가한 학습·업무 기능

1. 질문·선별 기준·추출 지침을 학생이 수정할 수 있다.
2. 새 기준은 원문을 다시 읽는 새 실행을 만든다. 이전 실행을 비교 기준으로 보존한다.
3. 파일 해시와 요청 ID로 원본 교체·이전 응답 재사용을 감지한다.
4. 문자열 매칭과 사람의 채택 판단을 분리하고 검토 이력을 남긴다.
5. 검토 변경 시 종합을 만료시켜 과거 판단이 최신 결과처럼 남지 않게 한다.
6. 결과를 Markdown·JSON·CSV로 넘겨 위키에서도 근거와 검토 상태를 유지한다.
