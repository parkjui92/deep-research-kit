"""Optional HTTP adapters. Credentials are read only from environment, never exported."""
import json
import os

import httpx

from .project import read_json
from .workflow import import_extraction, import_synthesis, manifest, prepare_synthesis


def completion(request):
    base = os.environ.get("DRK_API_BASE", "").rstrip("/")
    model = os.environ.get("DRK_MODEL", "")
    if not base or not model:
        raise ValueError("API 선택 기능에는 DRK_API_BASE와 DRK_MODEL 설정이 필요합니다. 기본 경로는 스킬 실행입니다.")
    if not base.startswith(("https://", "http://localhost:", "http://127.0.0.1:")):
        raise ValueError("API 주소에는 HTTPS 또는 로컬 서버를 사용하세요.")
    if len(json.dumps(request, ensure_ascii=False)) > 180000:
        raise ValueError("API 요청이 너무 큽니다. 설계에서 읽을 쪽수를 줄여 새 실행을 만들거나 스킬로 나누어 읽으세요.")
    key = os.environ.get("DRK_API_KEY", "")
    headers = {"Authorization": "Bearer " + key} if key else {}
    try:
        response = httpx.post(base + "/chat/completions", headers=headers,
            json={"model": model, "messages": [
                {"role": "system", "content": request["instructions"]},
                {"role": "user", "content": json.dumps(request, ensure_ascii=False)}],
                "response_format": {"type": "json_object"}}, timeout=180)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except httpx.HTTPStatusError as exc:
        raise ValueError(f"API HTTP {exc.response.status_code}. 제공자 설정·한도·지원 형식을 확인하세요.") from None
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        raise ValueError("API 응답을 완료하지 못했습니다. 저장된 응답은 유지됩니다. 다시 시도하거나 스킬을 사용하세요.") from None


def extract_with_api(project, run_id):
    run = manifest(project, run_id)
    for item in run["requests"]:
        folder = project.run_dir(run_id)
        if (folder / "responses" / (item["source_id"] + ".json")).exists():
            continue
        request = read_json(folder / "requests" / (item["source_id"] + ".json"))
        import_extraction(project, run_id, completion(request))


def synthesize_with_api(project, run_id):
    request = prepare_synthesis(project, run_id)
    return import_synthesis(project, run_id, completion(request))


def crossref_search(project, query, limit=10):
    if not query.strip():
        raise ValueError("검색어를 입력하세요.")
    limit = max(1, min(int(limit), 30))
    try:
        response = httpx.get("https://api.crossref.org/works", params={"query": query, "rows": limit},
                             headers={"User-Agent": "deep-research-kit/0.1"}, timeout=25)
        response.raise_for_status()
        message = response.json()["message"]
    except (httpx.HTTPError, ValueError, KeyError):
        project.log_search({"provider": "Crossref", "query": query, "status": "failed", "limit": limit})
        raise ValueError("검색 서버에 연결하지 못했습니다. PDF 직접 등록으로 계속할 수 있습니다.") from None
    items = [{"title": (i.get("title") or [""])[0], "doi": i.get("DOI", ""),
              "url": i.get("URL", ""), "type": i.get("type", "")} for i in message["items"]]
    project.log_search({"provider": "Crossref", "query": query, "status": "success",
                        "limit": limit, "total_reported": message["total-results"], "returned": len(items), "items": items})
    return items
