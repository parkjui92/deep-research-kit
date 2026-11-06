"""Retraction and correction notices for a cited work, read from free metadata.

Crossref attaches the notices that update a work (``updated-by``: retraction, correction,
expression of concern …), including the Retraction Watch records it publishes. OpenAlex marks
retracted works with ``is_retracted``. Neither is complete: "no notice found" means only that
these indexes held none on the day of the check, never that the work is sound."""
from __future__ import annotations

import json
import re
from copy import deepcopy

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


def _observation(provider, status, checked_at, notices=None, **extra):
    return {"provider": provider, "status": status, "checked_at": checked_at, "notices": notices or [], **extra}


def _previous_checks(previous, doi):
    """Read old records once into source-specific observations without reinterpreting display labels
    on every subsequent check. Never carry a different DOI's warning onto a newly entered DOI."""
    if not previous or (previous.get("doi") and clean_doi(previous["doi"]) != doi):
        return [], {}
    if "checks" in previous and "providers" in previous:
        return deepcopy(previous["checks"]), deepcopy(previous["providers"])
    via, status = previous.get("via", ""), previous.get("status", "unknown")
    checks = []
    stamp = previous.get("checked_at", "")
    if "Crossref" in via and not via.startswith("OpenAlex"):
        notices = previous.get("notices") or []
        crossref_status = status_of(notices) if notices or "OpenAlex" in via else status
        checks.append(_observation("Crossref", crossref_status, stamp, notices, origin="legacy"))
    if "OpenAlex" in via:
        checks.append(_observation("OpenAlex", "retracted" if status == "retracted" else status, stamp, origin="legacy"))
    return checks, {c["provider"]: deepcopy(c) for c in checks}


def _record(doi, observations, previous=None):
    checks, providers = _previous_checks(previous, doi)
    for observation in observations:
        provider = observation["provider"]
        known = providers.get(provider, {})
        # An absent notice or a failed request does not revoke a notice previously observed.
        # Keep the warning and its original date, but expose the actual latest result separately.
        if known.get("status") in FLAGGED and SEVERITY.get(observation["status"], -1) < SEVERITY[known["status"]]:
            providers[provider] = {**known, "last_check": observation, "retained": True}
        else:
            providers[provider] = deepcopy(observation)
        checks.append(deepcopy(observation))
    current = [o for o in observations if o["status"] != "not_found"]
    # A fresh observation from another provider cannot resolve an outstanding failed check.
    # In particular a saved OpenAlex search flag must not hide a failed Crossref retry.
    latest = [p.get("last_check", p) for p in providers.values()]
    failures = [o for o in latest if o["status"] == "unknown"]
    warnings = [p for p in providers.values() if p["status"] in FLAGGED]
    status = max((p["status"] for p in warnings), key=SEVERITY.get) if warnings else (
        "unknown" if failures else current[-1]["status"] if current else "unknown")
    notices = {(n["type"], n.get("notice_doi", "")): n for p in providers.values() for n in p.get("notices", [])}
    crossref = providers.get("Crossref", {})
    crossref_latest = crossref.get("last_check", crossref)
    coverage = "retraction_and_correction" if crossref_latest.get("status") in {*FLAGGED, "clear"} else "retraction_only"
    via = " · ".join(providers)
    if coverage == "retraction_only" and "OpenAlex" in providers and not warnings:
        via += "(정정 고지는 확인 못 함)"
    record = {"schema": "drk-integrity/2", "doi": doi, "checked_at": observations[-1]["checked_at"],
              "via": via, "status": status, "notices": list(notices.values()), "coverage": coverage,
              "providers": providers, "checks": checks,
              "retained_warning": any(p.get("retained") for p in providers.values()),
              "check_status": "unknown" if failures else current[-1]["status"] if current else "unknown"}
    if failures:
        record["error"] = " · ".join(o["provider"] + " " + o.get("error", "확인 실패") for o in failures)
    return record


def merge_records(doi: str, *records: dict | None) -> dict | None:
    """Combine candidate/catalog observations without letting an older snapshot replace a newer
    check. Replaying the dated observations also retains warnings and deduplicates shared history."""
    doi = clean_doi(doi)
    unique = {}
    for record in records:
        checks, _ = _previous_checks(record, doi)
        for observation in checks:
            unique[json.dumps(observation, sort_keys=True, ensure_ascii=False)] = observation
    result = None
    for observation in sorted(unique.values(), key=lambda o: o.get("checked_at") or ""):
        result = _record(doi, [observation], result)
    return result


def partial_check(record: dict | None) -> bool:
    """A negative OpenAlex retraction flag does not check correction or concern notices."""
    return bool(record and record.get("status") == "clear" and
                (record.get("coverage") == "retraction_only" or record.get("via", "").startswith("OpenAlex")))


def check_doi(doi: str, client: httpx.Client | None = None, openalex_retracted: bool | None = None,
              *, previous: dict | None = None) -> dict:
    doi, stamp = clean_doi(doi), now()
    if not doi:
        return {"doi": doi, "checked_at": stamp, "status": "no_doi", "notices": [], "via": ""}
    # Kept for existing API callers. New callers pass the previous complete record.
    if openalex_retracted:
        previous = _record(doi, [_observation("OpenAlex", "retracted", stamp, origin="search")], previous)
    getter = client.get if client is not None else httpx.get
    try:
        response = getter(CROSSREF_WORK + doi, headers=UA, timeout=20)
        if response.status_code == 404:
            observations = [_observation("Crossref", "not_found", stamp), _openalex_only(doi, getter, stamp)]
            return _record(doi, observations, previous)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("message"), dict):
            raise ValueError("Crossref response has no work metadata")
        notices = notices_from_crossref(payload["message"])
        observation = _observation("Crossref", status_of(notices), stamp, notices)
    except (httpx.HTTPError, ValueError) as exc:
        observation = _observation("Crossref", "unknown", stamp, error=type(exc).__name__)
    return _record(doi, [observation], previous)


def _openalex_only(doi, getter, stamp):
    try:
        from .providers import openalex_key_params
        response = getter(OPENALEX_WORK + doi, params={"select": "id,is_retracted", **openalex_key_params()}, headers=UA, timeout=20)
        if response.status_code == 404:
            return _observation("OpenAlex", "unknown", stamp, error="Crossref·OpenAlex에 없는 DOI")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("is_retracted"), bool):
            raise ValueError("OpenAlex response has no retraction flag")
        retracted = payload["is_retracted"]
    except (httpx.HTTPError, ValueError) as exc:
        return _observation("OpenAlex", "unknown", stamp, error="Crossref에 없는 DOI · OpenAlex " + type(exc).__name__)
    return _observation("OpenAlex", "retracted" if retracted else "clear", stamp)


def from_search(candidate: dict) -> dict | None:
    """A search hit that OpenAlex already marks as retracted retains its source and date."""
    if not candidate.get("retracted"):
        return None
    return _record(clean_doi(candidate.get("doi", "")), [_observation("OpenAlex", "retracted", now(), origin="search")])


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
        if partial_check(record):
            return f"OpenAlex의 철회 표시가 없습니다({day} 확인). 정정·우려 고지는 확인하지 못했습니다. 고지가 없다는 것이 문헌의 타당성을 뜻하지는 않습니다."
        return f"{record.get('via')}에 철회·정정 고지가 없습니다({day} 확인). 고지가 없다는 것이 문헌의 타당성을 뜻하지는 않습니다."
    kinds = ", ".join(sorted({n["label"] for n in record.get("notices", [])}))
    retained = " 최근 조회에서 고지를 재확인하지 못해 이전 고지를 유지합니다." if record.get("retained_warning") else ""
    if record.get("check_status") == "unknown":
        retained += f" 최근 조회 실패: {record.get('error', '')}."
    return f"{LABEL[status]}{' · ' + kinds if kinds else ''} · {record.get('via')}({day} 조회).{retained} 인용하기 전에 고지 내용을 확인하세요."


def notice_links(record: dict | None) -> list[str]:
    return ["https://doi.org/" + n["notice_doi"] for n in (record or {}).get("notices", []) if n.get("notice_doi")]


def check_sources(project, source_ids=None, client: httpx.Client | None = None) -> list[dict]:
    """Check registered sources (all, or the given ids) and store the result on each catalog entry."""
    results = []
    for source in project.catalog():
        if source_ids is not None and source["id"] not in source_ids:
            continue
        previous = source.get("integrity") or {}
        record = check_doi(source.get("doi", ""), client, previous=previous)
        project.set_integrity(source["id"], record)
        results.append({"source_id": source["id"], "title": source["title"], **record})
    return results


def flagged(records) -> list:
    return [r for r in records if (r or {}).get("status") in FLAGGED]
