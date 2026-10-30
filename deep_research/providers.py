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


# ---------------------------------------------------------------------------
# Literature collection: search → candidates → open-access PDF → registered source.
# Metadata-only candidates stay in collection.json so the search trail is auditable.
# ---------------------------------------------------------------------------
OPENALEX = "https://api.openalex.org/works"
UA = {"User-Agent": "deep-research-kit/0.2 (mailto:drk@example.org)"}


def _authors_openalex(work):
    names = [a.get("author", {}).get("display_name", "") for a in work.get("authorships", [])]
    return [n for n in names if n]


def _candidate(**kw):
    base = {"provider": "", "title": "", "authors": [], "year": None, "venue": "", "doi": "", "url": "",
            "pdf_url": "", "oa": False, "cited_by": None, "abstract": "", "external_id": ""}
    base.update(kw)
    base["doi"] = (base["doi"] or "").replace("https://doi.org/", "").lower()
    return base


def openalex_search(query, limit=20, year_from=None):
    params = {"search": query, "per-page": max(1, min(int(limit), 50)), "mailto": "drk@example.org"}
    if year_from:
        params["filter"] = f"publication_year:>{int(year_from) - 1}"
    response = httpx.get(OPENALEX, params=params, headers=UA, timeout=30)
    response.raise_for_status()
    payload = response.json()
    out = []
    for w in payload.get("results", []):
        loc = w.get("primary_location") or {}
        best = w.get("best_oa_location") or {}
        abstract = ""
        if w.get("abstract_inverted_index"):
            positions = sorted((p, t) for t, ps in w["abstract_inverted_index"].items() for p in ps)
            abstract = " ".join(t for _, t in positions)[:600]
        out.append(_candidate(provider="OpenAlex", title=w.get("display_name") or w.get("title") or "",
                              authors=_authors_openalex(w), year=w.get("publication_year"),
                              venue=(loc.get("source") or {}).get("display_name", "") if loc else "",
                              doi=w.get("doi") or "", url=(w.get("doi") or w.get("id") or ""),
                              pdf_url=best.get("pdf_url") or "", oa=bool((w.get("open_access") or {}).get("is_oa")),
                              cited_by=w.get("cited_by_count"), abstract=abstract, external_id=w.get("id", "")))
    return payload.get("meta", {}).get("count", len(out)), out


def arxiv_search(query, limit=20):
    response = httpx.get("https://export.arxiv.org/api/query", params={"search_query": f"all:{query}", "max_results": max(1, min(int(limit), 50))},
                         headers=UA, timeout=30)
    response.raise_for_status()
    import xml.etree.ElementTree as ET
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in ET.fromstring(response.text).findall("a:entry", ns):
        ident = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        short = ident.rsplit("/abs/", 1)[-1]
        doi = entry.findtext("{http://arxiv.org/schemas/atom}doi", default="") or f"10.48550/arXiv.{short.split('v')[0]}"
        out.append(_candidate(provider="arXiv", title=" ".join((entry.findtext("a:title", default="", namespaces=ns) or "").split()),
                              authors=[a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)],
                              year=int((entry.findtext("a:published", default="0000", namespaces=ns) or "0000")[:4]) or None,
                              venue="arXiv", doi=doi, url=ident, pdf_url=f"https://arxiv.org/pdf/{short}", oa=True,
                              abstract=" ".join((entry.findtext("a:summary", default="", namespaces=ns) or "").split())[:600], external_id=short))
    return len(out), out


def crossref_candidates(query, limit=20):
    response = httpx.get("https://api.crossref.org/works", params={"query": query, "rows": max(1, min(int(limit), 50))}, headers=UA, timeout=30)
    response.raise_for_status()
    message = response.json()["message"]
    out = []
    for i in message.get("items", []):
        year = None
        for key in ("published-print", "published-online", "issued", "created"):
            parts = (i.get(key) or {}).get("date-parts") or [[None]]
            if parts and parts[0] and parts[0][0]:
                year = parts[0][0]
                break
        pdf = next((link.get("URL") for link in i.get("link", []) if "pdf" in (link.get("content-type") or "")), "")
        out.append(_candidate(provider="Crossref", title=(i.get("title") or [""])[0], doi=i.get("DOI", ""), url=i.get("URL", ""),
                              authors=[" ".join(x for x in (a.get("given"), a.get("family")) if x) for a in i.get("author", [])],
                              year=year, venue=(i.get("container-title") or [""])[0], pdf_url=pdf or "",
                              cited_by=i.get("is-referenced-by-count")))
    return message.get("total-results", len(out)), out


PROVIDERS = {"OpenAlex": openalex_search, "arXiv": arxiv_search, "Crossref": crossref_candidates}


def search_literature(project, query, providers=("OpenAlex",), limit=20):
    """Search one or more free indexes, merge by DOI, log the search for the PRISMA trail."""
    if not query.strip():
        raise ValueError("검색어를 입력하세요.")
    merged, errors, totals = {}, {}, {}
    for name in providers:
        try:
            total, items = PROVIDERS[name](query, limit)
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            errors[name] = type(exc).__name__
            continue
        totals[name] = total
        for item in items:
            key = item["doi"] or item["title"].strip().lower()
            if key in merged:
                old = merged[key]
                old["pdf_url"] = old["pdf_url"] or item["pdf_url"]
                old["oa"] = old["oa"] or item["oa"]
                old["venue"] = old["venue"] or item["venue"]
                old["abstract"] = old["abstract"] or item["abstract"]
                old["providers"] = sorted(set(old.get("providers", [old["provider"]]) + [name]))
            else:
                merged[key] = {**item, "providers": [name]}
    results = list(merged.values())
    project.log_search({"provider": "+".join(providers), "query": query, "status": "success" if results or not errors else "failed",
                        "limit": limit, "totals": totals, "errors": errors, "returned": len(results),
                        "items": [{"title": r["title"], "doi": r["doi"], "url": r["url"]} for r in results]})
    if not results and errors:
        raise ValueError("검색 서버에 연결하지 못했습니다(" + ", ".join(errors) + "). PDF 직접 등록으로 계속할 수 있습니다.")
    return results


def fetch_pdf(url, timeout=60):
    """Download an open-access PDF. Returns bytes or None (HTML landing pages are not PDFs)."""
    if not url:
        return None
    try:
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=UA) as client:
            response = client.get(url)
            response.raise_for_status()
            if response.content.startswith(b"%PDF-"):
                return response.content
    except httpx.HTTPError:
        return None
    return None


def collect(project, candidate):
    """Add a search candidate to the project: register the PDF when one can be fetched,
    otherwise keep it as a metadata-only item waiting for a manual upload."""
    data = fetch_pdf(candidate.get("pdf_url")) or (fetch_pdf(candidate["url"]) if "arxiv.org" in (candidate.get("url") or "") else None)
    record = {k: candidate.get(k) for k in ("title", "authors", "year", "venue", "doi", "url", "pdf_url", "oa", "provider")}
    if data:
        source_id = project.add_pdf(data, (candidate["doi"].replace("/", "_") or candidate["title"][:40]) + ".pdf",
                                    candidate["title"], candidate["doi"], candidate["url"])
        project.set_bibliography(source_id, candidate.get("authors") or [], candidate.get("year"), candidate.get("venue") or "")
        record.update(status="added", source_id=source_id)
    else:
        record.update(status="pdf_missing", source_id=None)
    project.remember_candidate(record)
    return record


def parse_ris(text):
    """Zotero/EndNote RIS export → candidates (TY..ER blocks)."""
    out, cur = [], {}
    for raw in text.splitlines():
        if len(raw) < 6 or raw[2:6] != "  - ":
            continue
        tag, value = raw[:2], raw[6:].strip()
        if tag == "TY":
            cur = {"authors": []}
        elif tag == "ER":
            if cur.get("title"):
                out.append(_candidate(provider="RIS", **cur))
            cur = {}
        elif tag in ("TI", "T1"):
            cur["title"] = value
        elif tag in ("AU", "A1"):
            cur.setdefault("authors", []).append(value)
        elif tag in ("PY", "Y1"):
            cur["year"] = int(value[:4]) if value[:4].isdigit() else None
        elif tag in ("JO", "JF", "T2", "J2"):
            cur.setdefault("venue", value)
        elif tag == "DO":
            cur["doi"] = value
        elif tag == "UR":
            cur.setdefault("url", value)
        elif tag == "L1" and value.lower().endswith(".pdf"):
            cur["pdf_url"] = value
    return out


def parse_bibtex(text):
    import re
    out = []
    for entry in re.split(r"@\w+\s*\{", text)[1:]:
        fields = dict((k.lower(), v.strip().strip("{}\"")) for k, v in re.findall(r"(\w+)\s*=\s*[{\"]((?:[^{}\"]|\{[^{}]*\})*)[}\"]", entry))
        if not fields.get("title"):
            continue
        out.append(_candidate(provider="BibTeX", title=re.sub(r"[{}]", "", fields["title"]),
                              authors=[a.strip() for a in fields.get("author", "").split(" and ") if a.strip()],
                              year=int(fields["year"][:4]) if fields.get("year", "")[:4].isdigit() else None,
                              venue=fields.get("journal") or fields.get("booktitle") or "", doi=fields.get("doi", ""),
                              url=fields.get("url", "") or (("https://doi.org/" + fields["doi"]) if fields.get("doi") else "")))
    return out


# ---------------------------------------------------------------------------
# Claude Code as the default AI runner (one button in the UI). Falls back to the copy-paste
# instructions when the CLI is missing or not logged in.
# ---------------------------------------------------------------------------
def claude_code_status():
    import shutil
    import subprocess
    exe = shutil.which("claude")
    if not exe:
        return {"available": False, "reason": "Claude Code(claude 명령)가 설치돼 있지 않습니다."}
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    try:
        probe = subprocess.run([exe, "-p", "OK라고만 답해", "--output-format", "text"], capture_output=True, text=True, timeout=60, env=env)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"available": False, "reason": f"Claude Code 응답 없음({type(exc).__name__})."}
    text = (probe.stdout + probe.stderr).strip()
    if probe.returncode != 0 or "Not logged in" in text or "login" in text.lower() and "/login" in text:
        return {"available": False, "reason": "Claude Code에 로그인돼 있지 않습니다. 터미널에서 `claude`를 열어 /login 뒤 다시 누르세요."}
    return {"available": True, "reason": ""}


def run_claude_code(project, run_id, kind="extraction", timeout=1800):
    """Run the project's /deep-research skill headlessly for one run. The skill itself imports
    responses through the CLI, so the project state is updated by the same core code."""
    import shutil
    import subprocess
    exe = shutil.which("claude")
    if not exe:
        raise ValueError("Claude Code(claude 명령)를 찾지 못했습니다.")
    root = project.root.resolve().parent.parent
    if kind == "extraction":
        prompt = (f"/deep-research\n프로젝트: {project.root.resolve()}\n실행: {run_id}\n"
                  "requests/의 원문을 읽고 모든 문헌을 추출해 import-extraction으로 가져와 줘. 사람의 검토 상태는 바꾸지 마. 끝나면 가져온 문헌 수만 한 줄로 보고해.")
    else:
        prompt = (f"/deep-research\n프로젝트: {project.root.resolve()}\n실행: {run_id}\n"
                  "synthesis-request.json의 채택 근거를 종합하고 import-synthesis로 가져와 줘. 끝나면 주장 수만 한 줄로 보고해.")
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    allowed = ["Read", "Glob", "Grep", "Write", "Edit", "Bash(uv run drk:*)", "Bash(uv run python:*)", "Bash(python3:*)", "Bash(mkdir:*)", "Bash(ls:*)", "Bash(cat:*)"]
    try:
        result = subprocess.run([exe, "-p", prompt, "--output-format", "text", "--allowedTools", *allowed, "--add-dir", str(project.root.resolve())],
                                cwd=root, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise ValueError("Claude Code 실행이 제한 시간을 넘겼습니다. 이미 가져온 문헌은 저장돼 있으니 「저장된 응답 새로 읽기」 뒤 다시 실행하세요.") from None
    if result.returncode != 0:
        raise ValueError("Claude Code 실행 실패: " + (result.stderr or result.stdout).strip()[:300])
    return (result.stdout or "").strip()[:500]
