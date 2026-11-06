"""A human-written report outline linked to reading notes; never AI evidence approval."""
from __future__ import annotations

import copy
import uuid

from . import integrity, notebook
from .exports import citation, text
from .project import now, read_json, write_json

FILE = "report-draft.json"


def load(project):
    path = project.root / FILE
    return read_json(path) if path.exists() else {"schema": "drk-draft/1", "revision": 0, "sections": [], "history": []}


def _check_revision(draft, expected_revision):
    if expected_revision is not None and expected_revision != draft["revision"]:
        raise ValueError("다른 화면에서 초안이 수정되었습니다. 화면을 새로고침한 뒤 다시 확인하세요.")


def _linked_notes(project, note_ids):
    records = {n["id"]: n for n in notebook.notes(project)}
    if any(n not in records for n in note_ids):
        raise ValueError("연결할 노트를 찾을 수 없습니다. 이 프로젝트의 노트를 다시 선택하세요.")
    selected = [records[n] for n in dict.fromkeys(note_ids)]
    for note in selected:
        source = project.source(note["source_id"])
        project.index(source["id"])
        if note["source_sha256"] != source["sha256"]:
            raise ValueError("노트가 참조한 원본 PDF가 달라졌습니다.")
    return selected


def save_section(project, title, claim="", body="", note_ids=(), section_id=None, expected_revision=None):
    """Save one outline point/paragraph, preserving prior versions and the linked note versions."""
    if not isinstance(title, str) or not title.strip():
        raise ValueError("논점 제목을 입력하세요.")
    if not isinstance(claim, str) or not isinstance(body, str):
        raise ValueError("핵심 주장과 문단은 글로 입력하세요.")
    with project.lock:
        draft = load(project)
        _check_revision(draft, expected_revision)
        selected = _linked_notes(project, note_ids)
        previous = next((s for s in draft["sections"] if s["id"] == section_id), None)
        if section_id and previous is None:
            raise ValueError("수정할 논점을 찾을 수 없습니다.")
        at = now()
        section = {"id": section_id or "d_" + uuid.uuid4().hex[:16], "title": title.strip(),
                   "claim": claim.strip(), "body": body.strip(), "note_ids": [n["id"] for n in selected],
                   "note_versions": {n["id"]: n.get("revision", 1) for n in selected},
                   "created_at": previous["created_at"] if previous else at, "updated_at": at,
                   "authorship": "human_draft"}
        draft["history"].append({"at": at, "action": "edit" if previous else "add", "section_id": section["id"],
                                 "previous": copy.deepcopy(previous), "revision": draft["revision"]})
        if previous:
            draft["sections"][draft["sections"].index(previous)] = section
        else:
            draft["sections"].append(section)
        draft["revision"] += 1
        write_json(project.root / FILE, draft)
        return section


def move_section(project, section_id, direction, expected_revision=None):
    if direction not in {-1, 1}:
        raise ValueError("이동 방향이 올바르지 않습니다.")
    with project.lock:
        draft = load(project)
        _check_revision(draft, expected_revision)
        ids = [s["id"] for s in draft["sections"]]
        if section_id not in ids:
            raise ValueError("이동할 논점을 찾을 수 없습니다.")
        index = ids.index(section_id)
        other = index + direction
        if other < 0 or other >= len(ids):
            return
        draft["history"].append({"at": now(), "action": "reorder", "previous_order": ids,
                                 "revision": draft["revision"]})
        draft["sections"][index], draft["sections"][other] = draft["sections"][other], draft["sections"][index]
        draft["revision"] += 1
        write_json(project.root / FILE, draft)


def archive_section(project, section_id, expected_revision=None):
    """Remove an obsolete point from the active outline, with reversible storage and history."""
    with project.lock:
        draft = load(project)
        _check_revision(draft, expected_revision)
        section = next((s for s in draft["sections"] if s["id"] == section_id), None)
        if section is None:
            raise ValueError("보관할 논점을 찾을 수 없습니다.")
        at = now()
        position = draft["sections"].index(section)
        draft.setdefault("archived", []).append({"section": section, "position": position, "at": at})
        draft["history"].append({"at": at, "action": "archive", "section_id": section_id,
                                 "previous": copy.deepcopy(section), "revision": draft["revision"]})
        draft["sections"].remove(section)
        draft["revision"] += 1
        write_json(project.root / FILE, draft)


def restore_section(project, section_id, expected_revision=None):
    with project.lock:
        draft = load(project)
        _check_revision(draft, expected_revision)
        record = next((s for s in draft.get("archived", []) if s["section"]["id"] == section_id), None)
        if record is None:
            raise ValueError("복원할 논점을 찾을 수 없습니다.")
        draft["sections"].insert(min(record["position"], len(draft["sections"])), record["section"])
        draft["archived"].remove(record)
        draft["history"].append({"at": now(), "action": "restore", "section_id": section_id,
                                 "revision": draft["revision"]})
        draft["revision"] += 1
        write_json(project.root / FILE, draft)


def changed_notes(section, records):
    """Notes whose interpretation changed after the author last saved this paragraph."""
    by_id = {n["id"]: n for n in records}
    return [nid for nid in section["note_ids"]
            if nid not in by_id or by_id[nid].get("revision", 1) != section.get("note_versions", {}).get(nid, 1)]


def _paragraphs(value):
    return "\n\n".join(text(p) for p in value.split("\n\n") if p.strip())


def markdown(project):
    """Portable draft with stable note footnotes, explicit authorship and revision warnings."""
    draft = load(project)
    all_notes = notebook.notes(project)
    notes_by_id = {n["id"]: n for n in all_notes}
    linked = list(dict.fromkeys(nid for s in draft["sections"] for nid in s["note_ids"]))
    _linked_notes(project, linked)
    title = read_json(project.root / "project.json")["title"]
    lines = ["# " + text(title) + " · 보고서 초안", "", "연구자가 직접 작성한 초안입니다. 연결한 독서 노트의 원문 위치와 문단의 의미적 타당성은 별도로 확인해야 합니다. AI 근거의 채택 상태를 변경하지 않습니다.", "",
             "조사 질문: " + text(project.config()["plan"]["question"]), ""]
    cited_sources = {notes_by_id[nid]["source_id"]: project.with_bib(project.source(notes_by_id[nid]["source_id"])) for nid in linked}
    flagged = [s for s in cited_sources.values() if (s.get("integrity") or {}).get("status") in integrity.FLAGGED]
    if flagged:
        lines += ["## 문헌 고지 · 인용 전 확인", ""]
        for source in flagged:
            lines += ["- **" + text(source["title"]) + "**: " + text(integrity.explain(source["integrity"]))]
        lines.append("")
    for section in draft["sections"]:
        lines += ["## " + text(section["title"]), ""]
        if section["claim"]:
            lines += ["핵심 주장: " + text(section["claim"]), ""]
        lines += [_paragraphs(section["body"]) or "(문단 작성 전)", ""]
        if section["note_ids"]:
            lines += ["연결한 독서 노트: " + " ".join(f"[^{nid}]" for nid in section["note_ids"]), ""]
        else:
            lines += ["(아직 연결한 독서 노트가 없습니다.)", ""]
        if changed_notes(section, all_notes):
            lines += ["**재확인 필요: 연결 후 수정된 노트가 있습니다. 아래 출처 노트는 현재 버전입니다.**", ""]
    if linked:
        lines += ["## 출처 노트", ""]
    for nid in linked:
        note = notes_by_id[nid]
        source = project.with_bib(project.source(note["source_id"]))
        lines += [f"[^{nid}]: {text(citation(source))} · PDF {note['locator']['page']}쪽 · 노트 버전 {note.get('revision', 1)}",
                  "    원문: " + text(note["quote"]), "", "    내 메모: " + text(note["memo"]), "",
                  "    철회·정정: " + text(integrity.explain(source.get("integrity"))), ""]
    return "\n".join(lines)
