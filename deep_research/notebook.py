"""Local reading tools. These functions never call a search service or an AI provider."""
from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
import uuid
import zipfile

from .documents import locate_quote, normalize
from .exports import citation, text
from .project import now, read_json, write_json

READING_STATES = {"next": "먼저 읽기", "later": "나중에", "done": "읽음"}
NOTE_KINDS = ["주요 결과", "연구 방법", "적용 한계", "후속 질문", "기타"]


def candidate_key(record):
    doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", (record.get("doi") or "").strip(), flags=re.I).casefold()
    if doi:
        return "doi:" + doi
    if record.get("external_id"):
        return f"id:{record.get('provider', '')}:{record['external_id']}"
    title = unicodedata.normalize("NFKC", record.get("title") or "").casefold()
    return "title:" + re.sub(r"\s+", " ", title).strip()


TEXT_STATES = {"full": "본문 확보", "no_text": "글자 없는 PDF", "abstract": "초록만", "none": "미확보"}


def text_status(item, catalog_by_id):
    """What can actually be read for a candidate. An abstract is not the paper: a candidate with
    only an abstract must not look like one whose full text was read."""
    source = catalog_by_id.get(item.get("source_id") or "")
    if source:
        return "no_text" if bool(source.get("page_count")) and not source.get("text_pages") else "full"
    return "abstract" if (item.get("abstract") or "").strip() else "none"


def candidate_integrity(item, catalog_by_id=None):
    """The stored check, the registered source's check, or OpenAlex's retraction flag from search."""
    from .integrity import from_search, merge_records
    source = (catalog_by_id or {}).get(item.get("source_id") or "") or {}
    return merge_records(item.get("doi") or source.get("doi", ""),
                         source.get("integrity"), item.get("integrity"), from_search(item))


def update_reading(project, key, state, reason):
    if state not in READING_STATES:
        raise ValueError("읽기 상태를 선택하세요.")
    with project.lock:
        items = project.collection()
        item = next((i for i in items if candidate_key(i) == key), None)
        if item is None:
            raise ValueError("후보 문헌을 찾을 수 없습니다.")
        item["reading"] = {"state": state, "reason": reason.strip(), "updated_at": now()}
        write_json(project.root / "collection.json", items)


def search_passages(project, query, source_ids=None, limit=80):
    """AND keyword search inside each indexed passage, with stable source/page references."""
    terms = [normalize(t) for t in query.split() if normalize(t)]
    if not terms or len("".join(terms)) < 2:
        raise ValueError("두 글자 이상의 검색어를 입력하세요.")
    if not 1 <= limit <= 200:
        raise ValueError("검색 한도는 1~200이어야 합니다.")
    hits, total = [], 0
    for source in project.catalog():
        if source_ids is not None and source["id"] not in source_ids:
            continue
        index = project.index(source["id"])
        for passage in index["passages"]:
            if all(t in normalize(passage["text"]) for t in terms):
                total += 1
                if len(hits) < limit:
                    hits.append({"source_id": source["id"], "title": source["title"],
                                 "passage_id": passage["id"], "page": passage["page"],
                                 "text": passage["text"]})
    return {"query": query, "total": total, "hits": hits, "limit": limit}


def notes(project):
    path = project.root / "reading-notes.json"
    return read_json(path) if path.exists() else []


def save_note(project, source_id, passage_id, quote, memo, kind="기타"):
    """A quotation and a researcher's memo, never an automatically accepted research claim."""
    if kind not in NOTE_KINDS or not quote.strip() or not memo.strip():
        raise ValueError("분류·원문 발췌·내 메모를 모두 입력하세요.")
    with project.lock:
        source = project.source(source_id)
        index = project.index(source_id)
        locator = locate_quote(index, passage_id, quote.strip())
        if locator["status"] not in {"exact_normalized", "ambiguous", "unsupported_page_geometry"}:
            raise ValueError("발췌를 선택한 원문 구간에서 찾지 못했습니다. 원문의 문구를 그대로 복사하세요.")
        if locator["status"] == "unsupported_page_geometry" and not locator.get("text_found"):
            raise ValueError("발췌를 선택한 원문 구간에서 찾지 못했습니다.")
        record = {"id": "n_" + uuid.uuid4().hex[:16], "source_id": source_id,
                  "source_sha256": source["sha256"], "kind": kind, "quote": quote.strip(),
                  "memo": memo.strip(), "locator": locator, "created_at": now(),
                  "revision": 1, "history": [], "review_status": "unreviewed_note"}
        existing = notes(project)
        duplicate = next((n for n in existing if all(n.get(k) == record[k]
                         for k in ("source_id", "kind", "quote", "memo"))), None)
        if duplicate:
            return duplicate
        write_json(project.root / "reading-notes.json", existing + [record])
        return record


def update_note(project, note_id, memo, kind, expected_revision=None):
    """Revise the reader's interpretation while keeping the original quotation and its history.

    A quotation is immutable: a different passage is a new note. Old notes without revision
    metadata start at version 1. An open form cannot silently replace a newer revision.
    """
    if kind not in NOTE_KINDS or not isinstance(memo, str) or not memo.strip():
        raise ValueError("노트 분류와 메모를 입력하세요.")
    with project.lock:
        records = notes(project)
        note = next((n for n in records if n["id"] == note_id), None)
        if note is None:
            raise ValueError("수정할 노트를 찾을 수 없습니다.")
        revision = note.get("revision", 1)
        if expected_revision is not None and expected_revision != revision:
            raise ValueError("다른 화면에서 이 노트가 수정되었습니다. 화면을 새로고침한 뒤 다시 확인하세요.")
        source = project.source(note["source_id"])
        project.index(source["id"])
        if source["sha256"] != note["source_sha256"]:
            raise ValueError("노트가 참조한 원본 PDF가 달라졌습니다.")
        if note["memo"] == memo.strip() and note["kind"] == kind:
            return note
        note.setdefault("history", []).append({"revision": revision, "memo": note["memo"],
            "kind": note["kind"], "at": note.get("updated_at", note["created_at"])})
        note.update(memo=memo.strip(), kind=kind, revision=revision + 1, updated_at=now())
        write_json(project.root / "reading-notes.json", records)
        return note


def filter_notes(project, query="", kind=None, source_id=None):
    """Find a reader's notes by source, kind and AND keywords in memo, quote or title."""
    sources = {s["id"]: s for s in project.catalog()}
    terms = query.casefold().split()
    return [n for n in notes(project)
            if (not kind or n["kind"] == kind) and (not source_id or n["source_id"] == source_id)
            and all(term in " ".join((n["memo"], n["quote"], sources[n["source_id"]]["title"])).casefold()
                    for term in terms)]


def csv_text(rows, columns):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["'" + str(v) if str(v).lstrip().startswith(("=", "+", "-", "@"))
                         else v for v in (row.get(c, "") for c in columns)])
    return "\ufeff" + buffer.getvalue()


def references_ris(project):
    """Export known bibliography, with no invented authors, year, or publication type."""
    entries = {}
    for item in project.collection():
        entries[candidate_key(item)] = dict(item)
    for source in project.catalog():
        bib = source.get("bib") or {}
        record = {**source, **bib}
        key = candidate_key(record)
        entries[key] = {**entries.get(key, {}), **record}
    def clean(value):
        return " ".join(str(value or "").split())

    lines = []
    for item in entries.values():
        lines += ["TY  - GEN", "TI  - " + clean(item["title"])]
        for author in item.get("authors") or []:
            lines.append("AU  - " + clean(author))
        for tag, value in (("PY", item.get("year")), ("JO", item.get("venue")),
                           ("DO", item.get("doi")), ("UR", item.get("url"))):
            if value:
                lines.append(f"{tag}  - {clean(value)}")
        lines += ["ER  -", ""]
    return "\n".join(lines)


def notes_markdown(project):
    lines = ["# 독서 노트", "", "연구자가 기록한 발췌와 메모입니다. AI 근거 채택·종합 결과와 별도이며, 메모의 의미적 타당성을 자동 검증하지 않습니다.", ""]
    for note in notes(project):
        source = project.source(note["source_id"])
        project.index(source["id"])
        lines += [f"## {text(note['kind'])} · {text(source['title'])}", "",
                  f"PDF {note['locator']['page']}쪽 · 노트 `{note['id']}`", "",
                  "> " + text(note["quote"]), "", "내 메모: " + text(note["memo"]), "",
                  text(citation(source)), ""]
    return "\n".join(lines)


def library_zip(project, include_pdfs=False):
    """Portable materials, notes and search log, usable before the first AI run."""
    from . import writing

    sources = project.catalog()
    for source in sources:
        project.index(source["id"])
    search_log = read_json(project.root / "search-log.json")
    rows = [{"검색 시각": r.get("at", ""), "검색어": r.get("query", ""),
             "자료원": r.get("provider", ""), "반환 건수": r.get("returned", ""),
             "연도 이후": (r.get("filters") or {}).get("year_from", ""),
             "자료원 오류": json.dumps(r.get("errors", {}), ensure_ascii=False)} for r in search_log]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("reading-notes.md", notes_markdown(project))
        archive.writestr("report-draft.md", writing.markdown(project))
        archive.writestr("report-draft.json", json.dumps(writing.load(project), ensure_ascii=False, indent=2))
        archive.writestr("references.ris", references_ris(project))
        archive.writestr("search-log.csv", csv_text(rows, ["검색 시각", "검색어", "자료원", "반환 건수", "연도 이후", "자료원 오류"]))
        archive.writestr("materials.json", json.dumps({"schema": "drk-materials/1",
            "project": read_json(project.root / "project.json"), "config": project.config(),
            "sources": sources, "candidates": project.collection(), "notes": notes(project),
            "report_draft": writing.load(project),
            "search_log": search_log}, ensure_ascii=False, indent=2))
        if include_pdfs:
            for source in sources:
                archive.write(project.source_dir(source["id"]) / "original.pdf", f"sources/{source['id']}.pdf")
        archive.writestr("README.txt", "자료·독서 노트·보고서 초안·검색 이력 묶음입니다. AI 실행/검토 전체 기록은 결과 ZIP을 별도로 받으세요.\n"
                          "노트와 수동 작성 초안은 검토 완료 근거가 아닙니다. 쪽수는 PDF 파일 기준입니다.\n"
                          "자동 복원 기능이 있는 프로젝트 백업 형식은 아닙니다. 원문의 이용 조건을 지켜 주세요.\n")
    return buffer.getvalue()
