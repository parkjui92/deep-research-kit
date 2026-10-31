"""Getting the PDF of a search hit, and tying a PDF that arrives later to the hit it belongs to.

Without a browser the app takes only open copies, in this order: the hit's own open PDF link, the
other open copies OpenAlex lists, arXiv, Unpaywall (open copies by DOI), and the `citation_pdf_url`
that journal and repository pages carry. A publisher's own page or PDF link is opened only when
Unpaywall says the article is open: on a campus network an automatic request could otherwise pull
subscription PDFs in bulk. Every try is recorded with its result. Nothing here gets past a login, a
paywall or a bot check: what no open source hands over, the person downloads in their own browser,
and the app picks the file up from their downloads folder or an upload and ties it to the waiting
hit by the PDF's own DOI, arXiv number or full title.
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

CONTACT = os.environ.get("DRK_CONTACT_EMAIL") or "drk@example.org"  # sent to Unpaywall only
UA = {"User-Agent": "deep-research-kit/0.3"}
PAUSE = 0.5          # seconds between any two requests, also across hits
MAX_BYTES = 100 * 1024 * 1024
MAX_PAGES = 3        # landing pages read per hit
BUDGET = 40          # seconds spent on one hit before it waits for the person's browser
REQUEST_TIMEOUT = 15
_last_request = [0.0]


def _web(url) -> bool:
    return isinstance(url, str) and url.lower().startswith(("https://", "http://"))


def _canonical(url):
    """One spelling per DOI page, so http://dx.doi.org/X and https://doi.org/X count once."""
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "https://doi.org/", url or "", flags=re.I)


def _wait():
    """Space requests out: one person clicking 「담기」 on fifty hits must not look like a crawler."""
    if PAUSE:
        delay = _last_request[0] + PAUSE - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    _last_request[0] = time.monotonic()


def _fetch(url, client, deadline):
    """(bytes or None, final URL, result word). Stops at 100 MB and at the hit's deadline, also
    while a slow server keeps trickling bytes."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, url, "시간 한도"
    _wait()
    try:
        with client.stream("GET", url, timeout=min(REQUEST_TIMEOUT, max(remaining, 1))) as response:
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
                if time.monotonic() > deadline:
                    return None, final, "시간 한도"
            return bytes(data), final, "PDF" if data[:5] == b"%PDF-" else "PDF 아님"
    except httpx.HTTPError as exc:
        return None, url, f"연결 실패({type(exc).__name__})"


ARXIV_ID = r"((?:\d{4}\.\d{4,5}|[a-z][a-z\-]*(?:\.[a-z]{2})?/\d{7})(?:v\d+)?)"


def _arxiv_id(candidate) -> str:
    """New (2507.09089v2) and old (hep-th/9901001) arXiv numbers from a DOI, URL or id."""
    for text in (candidate.get("doi"), candidate.get("url"), candidate.get("pdf_url"), candidate.get("external_id")):
        match = re.search(r"arxiv(?:\.org/(?:abs|pdf)/|[.:/])" + ARXIV_ID, text or "", re.I)
        if match:
            return match.group(1)
    if candidate.get("provider") == "arXiv" and re.fullmatch(ARXIV_ID, candidate.get("external_id") or "", re.I):
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


def _unpaywall(doi, client, attempts, deadline):
    """(open PDF addresses, open landing pages, is_oa or None when unknown)."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return [], [], None
    _wait()
    try:
        response = client.get("https://api.unpaywall.org/v2/" + quote(doi, safe="/"), params={"email": CONTACT},
                              timeout=min(REQUEST_TIMEOUT, max(remaining, 1)))
        data = response.json() if response.status_code == 200 else None
    except httpx.HTTPError as exc:
        attempts.append({"route": "Unpaywall", "url": doi, "result": f"연결 실패({type(exc).__name__})"})
        return [], [], None
    except ValueError:  # a captive portal or a maintenance page answers 200 with HTML
        data = "not json"
    if response.status_code != 200 or not isinstance(data, dict):
        attempts.append({"route": "Unpaywall", "url": doi,
                         "result": f"HTTP {response.status_code}" if response.status_code != 200 else "응답 형식 오류"})
        return [], [], None
    places = [p for p in [data.get("best_oa_location")] + list(data.get("oa_locations") or []) if isinstance(p, dict)]
    pdfs = [p.get("url_for_pdf") for p in places if _web(p.get("url_for_pdf"))]
    pages = [p.get("url_for_landing_page") for p in places if _web(p.get("url_for_landing_page"))]
    if not pdfs and not pages:
        attempts.append({"route": "Unpaywall", "url": doi, "result": "오픈액세스 사본 없음"})
    return list(dict.fromkeys(pdfs)), list(dict.fromkeys(pages)), bool(data.get("is_oa"))


def find_pdf(candidate, client=None):
    """(PDF bytes or None, the list of tries). Stops at the first real PDF."""
    attempts, tried = [], set()
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=REQUEST_TIMEOUT, headers=UA)
    deadline = time.monotonic() + BUDGET

    def attempt(route, url):
        url = _canonical(url)
        if not _web(url) or url in tried:
            return None
        tried.add(url)
        data, _, result = _fetch(url, client, deadline)
        attempts.append({"route": route, "url": url, "result": "받음" if result == "PDF" else result})
        return data if result == "PDF" else None

    def read_page(url):
        url = _canonical(url)
        if not _web(url) or url in tried:
            return None
        tried.add(url)
        body, final, result = _fetch(url, client, deadline)
        if result == "PDF":  # the "landing page" was the PDF itself
            attempts.append({"route": "논문 페이지", "url": url, "result": "받음"})
            return body
        links = citation_pdf_urls(body.decode("utf-8", errors="replace"), final) if body else []
        attempts.append({"route": "논문 페이지", "url": url,
                         "result": result if result != "PDF 아님" else ("PDF 주소 표시 있음" if links else "PDF 주소 표시 없음")})
        for link_url in links:
            if data := attempt("논문 페이지의 citation_pdf_url", link_url):
                return data
        return None

    try:
        # Known open copies: OpenAlex's open locations, arXiv, a PDF the person's own library listed.
        own_link = candidate.get("pdf_url") if candidate.get("provider") != "Crossref" else ""
        for route, url in [("검색 결과의 PDF 주소", own_link),
                           *[("OpenAlex의 다른 원문 위치", u) for u in candidate.get("pdf_urls") or []]]:
            if data := attempt(route, url):
                return data, attempts
        if arxiv := _arxiv_id(candidate):
            if data := attempt("arXiv", f"https://arxiv.org/pdf/{arxiv}"):
                return data, attempts
        doi = (candidate.get("doi") or "").strip()
        pdfs, landing, is_oa = _unpaywall(doi, client, attempts, deadline) if doi else ([], [], None)
        for url in pdfs:
            if data := attempt("Unpaywall", url):
                return data, attempts
        pages = list(landing)
        # The publisher's own page and PDF link only for an article Unpaywall calls open. Without
        # a DOI nothing can be checked, so the address the hit came with is read as it is.
        if is_oa or not doi:
            publisher_pdf = candidate.get("pdf_url") if candidate.get("provider") == "Crossref" else ""
            if is_oa and (data := attempt("출판사 PDF 주소(오픈액세스)", publisher_pdf)):
                return data, attempts
            pages += [candidate.get("url"), f"https://doi.org/{doi}" if doi else ""]
        elif doi and is_oa is False:
            attempts.append({"route": "출판사 페이지", "url": f"https://doi.org/{doi}", "result": "오픈액세스가 아니라 열지 않음"})
        elif doi:
            attempts.append({"route": "출판사 페이지", "url": f"https://doi.org/{doi}", "result": "오픈액세스 여부를 몰라 열지 않음"})
        pages = [u for u in dict.fromkeys(_canonical(u) for u in pages) if _web(u) and u not in tried][:MAX_PAGES]
        for page_url in pages:
            if time.monotonic() > deadline:
                break
            if data := read_page(page_url):
                return data, attempts
        if time.monotonic() > deadline:
            attempts.append({"route": "시간 한도", "url": "", "result": f"{BUDGET}초 안에 찾지 못함"})
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
SUPPLEMENT = re.compile(r"supplementa|supporting information|appendix|erratum|corrigendum|보충\s*자료|부록", re.I)
TITLE_ZONE = 1500  # characters at the top of page 1 where a title is printed


def _key(text) -> str:
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", text or "").casefold())


def pdf_text(path) -> str:
    """The text of page 1, where a paper prints its own title, DOI and arXiv number. References
    (which cite other papers' DOIs) come later and are not read."""
    try:
        with pdfplumber.open(path) as pdf:
            return (pdf.pages[0].extract_text() or "") if pdf.pages else ""
    except Exception:  # a broken or encrypted file simply matches nothing
        return ""


def waiting(project) -> list:
    return [c for c in project.collection() if c.get("status") == "pdf_missing"]


def _dois(text):
    return [d.rstrip(".,;)]}").lower() for d in DOI_PATTERN.findall(text or "")]


def match_waiting(project, text):
    """(hit, how) when exactly one waiting hit is this PDF:
    - the first DOI printed on page 1 (the paper's own) is the hit's DOI, or
    - the hit's arXiv number is printed on page 1, or
    - the hit's full title (four words or more) is printed at the top of page 1 and the page
      prints no other DOI of its own; a DOI elsewhere on the page then confirms it.
    Supplements, appendices and errata are never tied automatically, and two fits are not guessed
    between: the person ties those by hand."""
    pending = waiting(project)
    dois = _dois(text)
    own_doi = dois[0] if dois else ""
    head = text[:TITLE_ZONE]
    head_key = _key(head)
    supplement = bool(SUPPLEMENT.search(head[:400]))
    fits = []
    for hit in pending:
        hit_doi = (hit.get("doi") or "").lower()
        title = hit.get("title") or ""
        title_fits = (len(title.split()) >= 4 or len(_key(title)) >= 20) and len(_key(title)) >= 15 and _key(title) in head_key
        arxiv = re.sub(r"v\d+$", "", _arxiv_id(hit))
        if hit_doi and hit_doi == own_doi and not supplement:
            fits.append((hit, "DOI"))
        elif arxiv and re.search(r"arxiv\s*:\s*" + re.escape(arxiv) + r"(v\d+)?\b", text, re.I) and not supplement:
            fits.append((hit, "arXiv 번호"))
        elif title_fits and not supplement and (not own_doi or not hit_doi or hit_doi in dois):
            fits.append((hit, "제목" if not hit_doi or hit_doi not in dois else "제목·DOI"))
    if len(fits) == 1:
        return fits[0]
    return None, "후보가 여럿" if len(fits) > 1 else ("보충자료로 보임" if supplement else "")


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
            name = (candidate.get("doi") or "").replace("/", "_") or (candidate.get("title") or "paper")[:40]
            source_id = project.add_pdf(data, name + ".pdf", candidate.get("title") or "", candidate.get("doi") or "",
                                        candidate.get("url") or "")
            link(project, source_id, {**candidate, "attempts": attempts}, "자동 다시 찾기")
            got.append(candidate)
        else:
            project.remember_candidate({**candidate, "attempts": attempts})
    return got


# ---------------------------------------------------------------------------
# The person's downloads folder: PDFs that appear after watching began.
# ---------------------------------------------------------------------------
def downloads_folder() -> Path:
    return Path(os.environ.get("DRK_DOWNLOADS_DIR") or Path.home() / "Downloads")


def pdfs_in(folder) -> set:
    """The PDFs in a folder now (raises OSError when the folder cannot be read)."""
    folder = Path(folder).expanduser()
    return {str(p) for p in folder.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()}


def new_downloads(folder, known, settle=2.0, clock=None) -> list:
    """PDFs in `folder` that are not in `known` (the files already there when watching began, plus
    the ones handled since). The file's own date is not used: browsers may stamp a download with
    the server's date, years back. A file written in place must be untouched for `settle` seconds;
    browsers usually write to .crdownload, .part or .download and rename when done, and those
    partial names are skipped. Raises OSError when the folder cannot be read."""
    clock = clock or time.time()
    found = []
    for name in pdfs_in(folder) - set(known):
        try:
            stat = Path(name).stat()
        except OSError:
            continue
        if stat.st_size > 0 and (clock - stat.st_mtime >= settle or stat.st_mtime > clock + 1):
            found.append((stat.st_mtime, Path(name)))
    return [path for _, path in sorted(found)]


def read_download(path) -> bytes | None:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return data if data.startswith(b"%PDF-") and len(data) <= MAX_BYTES else None
