"""Read-only views of research evidence; never infer human approval from a match."""
from __future__ import annotations

from deep_research.exports import display_value

FILTERS = ["전체", "미검토", "보류", "채택", "제외", "위치 미확인", "미발견"]


def filter_evidence(rows, sources, query="", status="전체", field_ids=None):
    sources = {s["id"]: s for s in sources}
    terms = query.casefold().split()
    found = []
    for row in rows:
        state = row["review"]["status"]
        if field_ids is not None and row["field_id"] not in field_ids:
            continue
        if status == "미검토" and state != "pending":
            continue
        if status == "보류" and state != "hold":
            continue
        if status == "채택" and state not in {"accept", "edit"}:
            continue
        if status == "제외" and state != "reject":
            continue
        if status == "위치 미확인" and row["match_status"] != "needs_check":
            continue
        if status == "미발견" and row["value"] is not None:
            continue
        source = sources.get(row["source_id"], {})
        bib = source.get("bib") or {}
        haystack = " ".join([
            source.get("title", ""), " ".join(bib.get("authors", [])),
            str(bib.get("year") or ""), source.get("doi", ""),
            display_value(row) or "", row.get("value") or "",
            " ".join(loc.get("quote", "") for loc in row.get("locators", [])),
        ]).casefold()
        if all(term in haystack for term in terms):
            found.append(row)
    return found


def review_counts(rows):
    """Hold is a recorded decision but remains unresolved work."""
    return {
        "total": len(rows),
        "kept": sum(r["review"]["status"] in {"accept", "edit"} for r in rows),
        "pending": sum(r["review"]["status"] == "pending" for r in rows),
        "held": sum(r["review"]["status"] == "hold" for r in rows),
        "resolved": sum(r["review"]["status"] in {"accept", "edit", "reject"} for r in rows),
        "unlocated": sum(r["match_status"] == "needs_check" for r in rows),
        "missing": sum(r["value"] is None for r in rows),
    }


def coverage(rows, sources, fields):
    """Display the evidence gaps without calling absence of extraction a research gap."""
    cells = {(r["source_id"], r["field_id"]): r for r in rows}
    result = []
    for field in fields:
        group = [cells[(s["id"], field["id"])] for s in sources
                 if (s["id"], field["id"]) in cells]
        counts = review_counts(group)
        result.append({"항목": field["name"], "채택": counts["kept"],
                       "미검토": counts["pending"], "보류": counts["held"],
                       "제외": sum(r["review"]["status"] == "reject" for r in group),
                       "미발견": counts["missing"], "추출 대기": len(sources) - len(group)})
    return result


def search_view(results, query="", oa_only=False, order="관련도순"):
    terms = query.casefold().split()
    filtered = [r for r in results if (not oa_only or r.get("oa") or r.get("pdf_url"))
                and all(t in " ".join([r["title"], " ".join(r.get("authors", [])),
                                       r.get("abstract", ""), r.get("doi", "")]).casefold()
                        for t in terms)]
    if order == "최신순":
        filtered.sort(key=lambda r: r.get("year") or 0, reverse=True)
    elif order == "피인용순":
        filtered.sort(key=lambda r: r.get("cited_by") or 0, reverse=True)
    return filtered
