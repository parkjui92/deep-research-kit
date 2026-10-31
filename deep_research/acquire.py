"""Getting the PDF of a search hit, and tying a PDF that arrives later to the hit it belongs to.

Without a browser the app tries, in order: the hit's own PDF link, the other open copies OpenAlex
lists, arXiv, Unpaywall, and the `citation_pdf_url` that most journal and repository pages carry.
Every try is recorded with its result. Nothing here gets past a login, a paywall or a bot check:
what no open source hands over, the person downloads in their own browser, and the app picks the
file up from their downloads folder or from an upload and ties it to the waiting hit by DOI or title.
"""
from __future__ import annotations

import html
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urljoin

import httpx
import pdfplumber

from .project import now

CONTACT = os.environ.get("DRK_CONTACT_EMAIL") or "drk@example.org"
UA = {"User-Agent": f"deep-research-kit/0.3 (mailto:{CONTACT})"}
PAUSE = 0.3          # seconds between requests in one search for a PDF
MAX_BYTES = 100 * 1024 * 1024
MAX_PAGES = 3        # landing pages read per hit
BUDGET = 40          # seconds spent on one hit before it waits for the person's browser


def _web(url) -> bool:
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def _fetch(url, client):
    """(bytes or None, final URL, result word). Stops at 100 MB."""
    try:
        with client.stream("GET", url) as response:
            final = str(response.url)
            if response.status_code >= 400:
                denied = response.status_code in (401, 402, 403, 429)
                return None, final, f"접근 거부({response.status_code})" if denied else f"HTTP {response.status_code}"
            if int(response.headers.get("content-length") or 0) > MAX_BYTES:
                return None, final, "100 MB 초과"
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    return None, final, "100 MB 초과"
            return bytes(data), final, "PDF" if data[:5] == b"%PDF-" else "PDF 아님"
    except httpx.HTTPError as exc:
        return None, url, f"연결 실패({type(exc).__name__})"


def _arxiv_id(candidate) -> str:
    for text in (candidate.get("doi"), candidate.get("url"), candidate.get("pdf_url"), candidate.get("external_id")):
        match = re.search(r"arxiv(?:\.org/(?:abs|pdf)/|[.:])(\d{4}\.\d{4,5}(?:v\d+)?)", text or "", re.I)
        if match:
            return match.group(1)
    if candidate.get("provider") == "arXiv" and re.fullmatch(r"\d{4}\.\d{4,5}(v\d+)?", candidate.get("external_id") or ""):
        return candidate["external_id"]
    return ""


def citation_pdf_urls(page: str, base: str) -> list:
    """PDF addresses a landing page declares for indexers: <meta name="citation_pdf_url"> (Google
    Scholar's convention, used by most journals and repositories) and <link rel="alternate"
    type="application/pdf">. Read as text; nothing on the page is run."""
    found = []
    for tag in re.findall(r"<meta\b[^>]*>", page, re.I):
        if re.search(r"""name\s*=\s*["']citation_pdf_url["']""", tag, re.I):
            if match := re.search(r"""content\s*=\s*["']([^"']+)["']""", tag, re.I):
                found.append(match.group(1))
    for tag in re.findall(r"<link\b[^>]*>", page, re.I):
        if re.search(r"""type\s*=\s*["']application/pdf["']""", tag, re.I) and re.search(r"""rel\s*=\s*["'][^"']*alternate""", tag, re.I):
            if match := re.search(r"""href\s*=\s*["']([^"']+)["']""", tag, re.I):
                found.append(match.group(1))
    urls = (urljoin(base, html.unescape(u.strip())) for u in found)
    return [u for u in dict.fromkeys(urls) if _web(u)]


def _unpaywall(doi, client, attempts):
    """Open copies Unpaywall knows for a DOI: PDF addresses, and landing pages to read next."""
    try:
        response = client.get("https://api.unpaywall.org/v2/" + quote(doi, safe="/"), params={"email": CONTACT})
    except httpx.HTTPError as exc:
        attempts.append({"route": "Unpaywall", "url": doi, "result": f"연결 실패({type(exc).__name__})"})
        return [], []
    if response.status_code != 200:
        attempts.append({"route": "Unpaywall", "url": doi, "result": f"HTTP {response.status_code}"})
        return [], []
    data = response.json()
    places = [data.get("best_oa_location") or {}] + list(data.get("oa_locations") or [])
    pdfs = [p.get("url_for_pdf") for p in places if _web(p.get("url_for_pdf"))]
    pages = [p.get("url_for_landing_page") for p in places if _web(p.get("url_for_landing_page"))]
    if not pdfs and not pages:
        attempts.append({"route": "Unpaywall", "url": doi, "result": "오픈액세스 사본 없음"})
    return list(dict.fromkeys(pdfs)), list(dict.fromkeys(pages))


def find_pdf(candidate, client=None):
    """(PDF bytes or None, the list of tries). Stops at the first real PDF."""
    attempts, tried = [], set()
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=15, headers=UA)
    deadline = time.monotonic() + BUDGET

    def attempt(route, url):
        if not _web(url) or url in tried or time.monotonic() > deadline:
            return None
        if tried and PAUSE:
            time.sleep(PAUSE)
        tried.add(url)
        data, _, result = _fetch(url, client)
        attempts.append({"route": route, "url": url, "result": "받음" if result == "PDF" else result})
        return data if result == "PDF" else None

    try:
        for route, url in [("검색 결과의 PDF 주소", candidate.get("pdf_url")),
                           *[("OpenAlex의 다른 원문 위치", u) for u in candidate.get("pdf_urls") or []]]:
            if data := attempt(route, url):
                return data, attempts
        if arxiv := _arxiv_id(candidate):
            if data := attempt("arXiv", f"https://arxiv.org/pdf/{arxiv}"):
                return data, attempts
        doi = (candidate.get("doi") or "").strip()
        landing = []
        if doi:
            pdfs, landing = _unpaywall(doi, client, attempts)
            for url in pdfs:
                if data := attempt("Unpaywall", url):
                    return data, attempts
        pages = [u for u in dict.fromkeys([candidate.get("url"), f"https://doi.org/{doi}" if doi else "", *landing])
                 if _web(u) and u not in tried][:MAX_PAGES]
        for page_url in pages:
            if time.monotonic() > deadline:
                attempts.append({"route": "시간 한도", "url": "", "result": f"{BUDGET}초 안에 찾지 못함"})
                break
            if tried and PAUSE:
                time.sleep(PAUSE)
            tried.add(page_url)
            body, final, result = _fetch(page_url, client)
            if result == "PDF":  # the "landing page" was the PDF itself
                attempts.append({"route": "논문 페이지", "url": page_url, "result": "받음"})
                return body, attempts
            links = citation_pdf_urls(body.decode("utf-8", errors="replace"), final) if body else []
            attempts.append({"route": "논문 페이지", "url": page_url,
                             "result": result if result != "PDF 아님" else ("PDF 주소 표시 있음" if links else "PDF 주소 표시 없음")})
            for url in links:
                if data := attempt("논문 페이지의 citation_pdf_url", url):
                    return data, attempts
        return None, attempts
    finally:
        if own:
            client.close()


def attempts_summary(attempts) -> str:
    return " · ".join(f"{a['route']} → {a['result']}" for a in attempts) or "시도 기록 없음"


# ---------------------------------------------------------------------------
# Tying a PDF that arrived later (upload, downloads folder) to the hit waiting for it.
# ---------------------------------------------------------------------------
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.I)


def _key(text) -> str:
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", text or "").casefold())


def pdf_text(path, pages=2) -> str:
    """The text of the first pages, where the title and DOI are printed."""
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages[:pages])
    except Exception:  # a broken or encrypted file simply matches nothing
        return ""


def waiting(project) -> list:
    return [c for c in project.collection() if c.get("status") == "pdf_missing"]


def match_waiting(project, text):
    """(hit, how) when exactly one waiting hit fits the text: its DOI is printed, or its whole
    title is. Two fits are not guessed between."""
    pending = waiting(project)
    dois = {d.rstrip(".,;)]}").lower() for d in DOI_PATTERN.findall(text or "")}
    by_doi = [c for c in pending if c.get("doi") and c["doi"].lower() in dois]
    if len(by_doi) == 1:
        return by_doi[0], "DOI"
    page = _key(text)
    by_title = [c for c in pending if len(_key(c.get("title"))) >= 15 and _key(c.get("title")) in page]
    if not by_doi and len(by_title) == 1:
        return by_title[0], "제목"
    return None, "후보가 여럿" if len(by_doi) > 1 or len(by_title) > 1 else ""


def link(project, source_id, candidate, how):
    """The registered PDF is this hit's: fill what the upload did not know, keep the trail."""
    project.fill_metadata(source_id, candidate.get("title") or "", candidate.get("doi") or "", candidate.get("url") or "")
    source = project.source(source_id)
    if not source.get("bib") and (candidate.get("authors") or candidate.get("year") or candidate.get("venue")):
        project.set_bibliography(source_id, candidate.get("authors") or [], candidate.get("year"), candidate.get("venue") or "")
    project.remember_candidate({**candidate, "status": "added", "source_id": source_id, "linked_by": how, "linked_at": now()})


def register(project, data, filename):
    """Register a PDF the person brought (upload or download) and tie it to a waiting hit if one
    fits. Returns (source_id, hit or None, how)."""
    source_id = project.add_pdf(data, filename)
    candidate, how = match_waiting(project, pdf_text(project.source_dir(source_id) / "original.pdf"))
    if candidate:
        link(project, source_id, candidate, how)
    return source_id, candidate, how


def match_file(project, path):
    """Which waiting hit a PDF on disk belongs to, without registering it."""
    return match_waiting(project, pdf_text(path))


def retry_waiting(project, client=None):
    """Try every waiting hit again (after a while, or with the wider search). Returns the hits
    that now have a PDF."""
    got = []
    for candidate in waiting(project):
        data, attempts = find_pdf(candidate, client)
        if data:
            source_id = project.add_pdf(data, (candidate.get("doi", "").replace("/", "_") or candidate["title"][:40]) + ".pdf",
                                        candidate["title"], candidate.get("doi", ""), candidate.get("url", ""))
            link(project, source_id, {**candidate, "attempts": attempts}, "자동 다시 찾기")
            got.append(candidate)
        else:
            project.remember_candidate({**candidate, "attempts": attempts})
    return got


# ---------------------------------------------------------------------------
# The person's downloads folder: new PDFs that finished downloading since watching began.
# ---------------------------------------------------------------------------
def downloads_folder() -> Path:
    return Path(os.environ.get("DRK_DOWNLOADS_DIR") or Path.home() / "Downloads")


def new_downloads(folder, since, seen, settle=2.0, clock=None) -> list:
    """PDF files in `folder` modified after `since`, not seen yet, and untouched for `settle`
    seconds (a browser still writing uses .crdownload, .part or .download, which are skipped)."""
    folder, clock = Path(folder), clock or time.time()
    found = []
    try:
        entries = list(folder.iterdir())
    except OSError:
        return []
    for path in entries:
        try:
            if not path.is_file() or path.suffix.lower() != ".pdf" or str(path) in seen:
                continue
            stat = path.stat()
        except OSError:
            continue
        if stat.st_mtime >= since and clock - stat.st_mtime >= settle and stat.st_size > 0:
            found.append(path)
    return sorted(found, key=lambda p: p.stat().st_mtime)


def read_download(path) -> bytes | None:
    data = Path(path).read_bytes()
    return data if data.startswith(b"%PDF-") and len(data) <= MAX_BYTES else None

