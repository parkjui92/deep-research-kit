"""Retraction and correction notices for a cited work, read from free metadata.

Crossref attaches the notices that update a work (``updated-by``: retraction, correction,
expression of concern …), including the Retraction Watch records it publishes. OpenAlex marks
retracted works with ``is_retracted``. Neither is complete: "no notice found" means only that
these indexes held none on the day of the check, never that the work is sound."""
from __future__ import annotations

import re

import httpx

from .project import now

CROSSREF_WORK = "https://api.crossref.org/works/"
OPENALEX_WORK = "https://api.openalex.org/works/doi:"
UA = {"User-Agent": "deep-research-kit/0.3 (mailto:drk@example.org)"}

KIND = {"retraction": "retracted", "removal": "retracted", "withdrawal": "retracted",
        "expression_of_concern": "concern",
        "correction": "corrected", "erratum": "corrected", "corrigendum": "corrected", "addendum": "corrected"}
SEVERITY = {"retracted": 3, "concern": 2, "corrected": 1, "clear": 0}
LABEL = {"retracted": "철회됨", "concern": "우려 표명", "corrected": "정정 있음",
         "clear": "고지 없음", "unknown": "확인 실패", "no_doi": "DOI 없음", None: "확인 안 함"}
FLAGGED = {"retracted", "concern", "corrected"}


def clean_doi(doi: str) -> str:
    return re.sub(r"^https?://(?:dx\.)?doi\.org/", "", (doi or "").strip(), flags=re.I).lower()


def notices_from_crossref(message: dict) -> list[dict]:
    """One entry per notice; the same notice reported by the publisher and by Retraction Watch is kept once."""
    seen, out = set(), []
    for item in message.get("updated-by") or []:
        kind = (item.get("type") or "").lower()
        if kind not in KIND:
            continue
        parts = ((item.get("updated") or {}).get("date-parts") or [[None]])[0]
        date = "-".join(f"{p:02d}" if i else str(p) for i, p in enumerate(parts) if p) if parts and parts[0] else ""
        key = (kind, (item.get("DOI") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        out.append({"type": kind, "label": item.get("label") or kind, "notice_doi": (item.get("DOI") or "").lower(),
                    "date": date, "source": item.get("source") or ""})
    return out


def status_of(notices: list[dict], openalex_retracted: bool | None = None) -> str:
    states = [KIND[n["type"]] for n in notices] + (["retracted"] if openalex_retracted else [])
    return max(states, key=SEVERITY.get) if states else "clear"


def check_doi(doi: str, client: httpx.Client | None = None, openalex_retracted: bool | None = None) -> dict:
    doi = clean_doi(doi)
    base = {"doi": doi, "checked_at": now(), "via": "Crossref"}
    if not doi:
        return {**base, "status": "no_doi", "notices": [], "via": ""}
    getter = client.get if client is not None else httpx.get
    try:
        response = getter(CROSSREF_WORK + doi, headers=UA, timeout=20)
        if response.status_code == 404:
            # DOIs from other agencies (arXiv and other DataCite DOIs) are not in Crossref.
            return _openalex_only(doi, getter, base)
        response.raise_for_status()
        notices = notices_from_crossref(response.json().get("message") or {})
    except (httpx.HTTPError, ValueError) as exc:
        return {**base, "status": "unknown", "notices": [], "error": type(exc).__name__}
    via = "Crossref" + (" · OpenAlex" if openalex_retracted else "")
    return {**base, "status": status_of(notices, openalex_retracted), "notices": notices, "via": via}


def _openalex_only(doi, getter, base):
    try:
        from .providers import openalex_key_params
        response = getter(OPENALEX_WORK + doi, params={"select": "id,is_retracted", **openalex_key_params()}, headers=UA, timeout=20)
        if response.status_code == 404:
            return {**base, "status": "unknown", "notices": [], "error": "Crossref·OpenAlex에 없는 DOI"}
        response.raise_for_status()
        retracted = bool(response.json().get("is_retracted"))
    except (httpx.HTTPError, ValueError) as exc:
        return {**base, "status": "unknown", "notices": [], "error": "Crossref에 없는 DOI · OpenAlex " + type(exc).__name__}
    return {**base, "via": "OpenAlex(Crossref에 없는 DOI · 정정 고지는 확인 못 함)",
            "status": "retracted" if retracted else "clear", "notices": []}


def from_search(candidate: dict) -> dict | None:
    """A search hit that OpenAlex already marks as retracted carries that flag until a full check."""
    if not candidate.get("retracted"):
        return None
    return {"doi": clean_doi(candidate.get("doi", "")), "checked_at": now(), "via": "OpenAlex 검색 결과",
            "status": "retracted", "notices": []}


def label(record: dict | None) -> str:
    if not record:
        return LABEL[None]
    text = LABEL.get(record.get("status"), LABEL[None])
    if record.get("status") in FLAGGED and record.get("notices"):
        dates = sorted({n["date"] for n in record["notices"] if n.get("date")})
        if dates:
            text += f" ({dates[-1]})"
    return text


def explain(record: dict | None) -> str:
    """One line for a caption: what was checked, where and when, and what it does not mean."""
    if not record:
        return "철회·정정 여부를 아직 확인하지 않았습니다."
    status = record.get("status")
    day = (record.get("checked_at") or "")[:10]
    if status == "no_doi":
        return "DOI가 없어 철회·정정 고지를 조회할 수 없습니다. 출판사 페이지에서 직접 확인하세요."
    if status == "unknown":
        return f"철회·정정 조회에 실패했습니다({record.get('error', '')}). 다시 확인하거나 출판사 페이지를 보세요."
    if status == "clear":
        return f"{record.get('via')}에 철회·정정 고지가 없습니다({day} 확인). 고지가 없다는 것이 문헌의 타당성을 뜻하지는 않습니다."
    kinds = ", ".join(sorted({n["label"] for n in record.get("notices", [])}))
    return f"{LABEL[status]}{' · ' + kinds if kinds else ''} · {record.get('via')}({day} 확인). 인용하기 전에 고지 내용을 확인하세요."


def notice_links(record: dict | None) -> list[str]:
    return ["https://doi.org/" + n["notice_doi"] for n in (record or {}).get("notices", []) if n.get("notice_doi")]


def check_sources(project, source_ids=None, client: httpx.Client | None = None) -> list[dict]:
    """Check registered sources (all, or the given ids) and store the result on each catalog entry."""
    results = []
    for source in project.catalog():
        if source_ids is not None and source["id"] not in source_ids:
            continue
        previous = source.get("integrity") or {}
        record = check_doi(source.get("doi", ""), client, openalex_retracted=previous.get("via") == "OpenAlex 검색 결과" or None)
        project.set_integrity(source["id"], record)
        results.append({"source_id": source["id"], "title": source["title"], **record})
    return results


def flagged(records) -> list:
    return [r for r in records if (r or {}).get("status") in FLAGGED]
