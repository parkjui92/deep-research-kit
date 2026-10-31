from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import yaml
from filelock import FileLock

from .documents import digest, index_pdf, locate_anywhere

SCREEN_QUOTE_PREFIX = {"포함": "inclusion", "포함:": "inclusion", "제외": "exclusion", "제외:": "exclusion",
                       "inclusion": "inclusion", "exclusion": "exclusion"}


def parse_screen_quotes(text: str) -> list[dict]:
    """One quote per line. `포함: …` / `제외: …` names the criterion the quote speaks to."""
    quotes = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        criterion = ""
        head, sep, rest = line.partition(":")
        if sep and head.strip() in SCREEN_QUOTE_PREFIX and head.strip() not in {"inclusion", "exclusion"}:
            criterion, line = SCREEN_QUOTE_PREFIX[head.strip()], rest.strip()
        elif sep and head.strip() in {"inclusion", "exclusion"}:
            criterion, line = head.strip(), rest.strip()
        if line:
            quotes.append({"text": line, "criterion": criterion})
    return quotes


def format_screen_quotes(quotes: list[dict]) -> str:
    label = {"inclusion": "포함: ", "exclusion": "제외: ", "": ""}
    return "\n".join(label.get(q.get("criterion", ""), "") + q["quote"] for q in quotes or [])

DEFAULT_PLAN = {
    "question": "AI 활용은 연구·지식업무의 생산성과 품질에 어떤 영향을 미치는가?",
    "purpose": "기술영향평가에 활용할 근거와 적용 한계를 정리한다.",
    "scope": "실제 수행 결과를 평가한 연구. 아이디어 평가와 실행 결과를 구분한다.",
    "inclusion": "대상, 방법, 결과를 확인할 수 있는 실증연구",
    "exclusion": "성과 측정 없이 기대나 전망만 제시한 자료",
    "max_documents": 8,
    "max_pages_per_document": 20,
    "output": "질문별 근거 표와 검토된 주장, 상충 결과, 남은 질문",
}
DEFAULT_FIELDS = [
    {"id": "population", "name": "대상과 맥락", "instruction": "누가 어떤 과업을 수행했는지 추출한다."},
    {"id": "method", "name": "연구 방법", "instruction": "설계, 비교집단, 자료를 구분한다."},
    {"id": "finding", "name": "주요 결과", "instruction": "측정된 결과와 단위·조건을 보존한다."},
    {"id": "limitations", "name": "적용 한계", "instruction": "저자가 밝힌 한계. 추론은 별도로 표시한다."},
]
DEFAULT_RULES = """질문에 대한 답을 근거 ID와 함께 작성한다.
같은 연구의 여러 보고서를 독립 연구로 세지 않는다.
서로 다른 대상·방법·측정을 먼저 비교하고, 결과 차이를 자동으로 모순으로 판단하지 않는다.
일치·상충·불확실성을 구분한다. 못 찾은 결과를 효과가 없다는 증거로 쓰지 않는다.
검토 보류·제외·원문 미확인 근거를 결론에서 제외한다.
"""


def now() -> str:
    return datetime.now(UTC).isoformat()


def atomic_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".writing-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


# How much text a field should hold (#29). Kept as a tag at the end of the field's instruction, so
# the config format, earlier runs and the prepared example all stay as they were.
DEFAULT_LENGTH = "핵심 1문장"
LENGTH_CHOICES = [DEFAULT_LENGTH, "요약 2~3문장", "상세 4~6문장", "수치만"]
_LENGTH_TAG = re.compile(r"\s*\[분량: ([^\]]*?)\.? 값의 문장마다 그 문장을 뒷받침하는 발췌를 1개 이상 붙인다\]\s*$")


def length_of(instruction: str) -> str:
    match = _LENGTH_TAG.search(instruction or "")
    return match.group(1) if match else DEFAULT_LENGTH


def with_length(instruction: str, length: str) -> str:
    """The instruction with its length tag replaced. The default length adds no tag."""
    base = _LENGTH_TAG.sub("", instruction or "").rstrip()
    length = " ".join((length or "").replace("[", "").replace("]", "").split()).rstrip(".")
    if not length or length == DEFAULT_LENGTH:
        return base
    return f"{base} [분량: {length}. 값의 문장마다 그 문장을 뒷받침하는 발췌를 1개 이상 붙인다]"


def has_no_text(source: dict) -> bool:
    """Scanned PDF: pages but no text layer at all. Nothing in it can be extracted or located."""
    return bool(source.get("page_count")) and not source.get("text_pages")


def no_text_note(sources: list[dict]) -> str:
    titles = [s["title"] for s in sources if has_no_text(s)]
    if not titles:
        return ""
    return (f"글자 없는 PDF(스캔본) {len(titles)}건은 AI가 읽을 수 없어 추출할 수 없습니다: {', '.join(titles)}. "
            "제외로 바꾸거나, OCR(예: ocrmypdf)로 글자 층을 만든 PDF를 다시 올리세요.")


def safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise ValueError("잘못된 ID입니다.")
    return value


class Project:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self._lock = FileLock(str(self.root / ".project.lock"), timeout=10)

    @property
    def lock(self):
        return self._lock

    def initialize(self, title: str = "나의 문헌조사"):
        self.root.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if (self.root / "project.json").exists():
                raise ValueError("이미 있는 프로젝트입니다. 다른 폴더 이름을 사용하세요.")
            write_json(self.root / "project.json", {"schema": "drk-project/1",
                       "id": str(uuid.uuid4()), "title": title, "created_at": now()})
            write_json(self.root / "catalog.json", [])
            write_json(self.root / "search-log.json", [])
            self.save_config(DEFAULT_PLAN, DEFAULT_FIELDS, DEFAULT_RULES)
        return self

    def config(self):
        plan = yaml.safe_load((self.root / "research-plan.yaml").read_text(encoding="utf-8"))
        fields = yaml.safe_load((self.root / "config/extraction-fields.yaml").read_text(encoding="utf-8"))
        rules = (self.root / "config/synthesis-rules.md").read_text(encoding="utf-8")
        self.validate_config(plan, fields)
        return {"plan": plan, "fields": fields, "synthesis_rules": rules}

    @staticmethod
    def validate_config(plan, fields):
        if not isinstance(plan, dict) or not str(plan.get("question", "")).strip():
            raise ValueError("조사 질문이 필요합니다.")
        if not isinstance(plan.get("max_documents"), int) or not 1 <= plan["max_documents"] <= 100:
            raise ValueError("문헌 수 제한은 1~100의 정수여야 합니다.")
        if not isinstance(fields, list) or not 1 <= len(fields) <= 30:
            raise ValueError("추출 항목은 1~30개가 필요합니다.")
        page_limit = plan.get("max_pages_per_document", 20)
        if not isinstance(page_limit, int) or not 0 <= page_limit <= 1000:
            raise ValueError("문헌당 읽을 쪽수는 0(전체)~1000의 정수여야 합니다.")
        ids = set()
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("id"), str) or not field["id"].strip():
                raise ValueError("추출 항목마다 id(영문·숫자·하이픈)를 채우세요. 빈 줄은 지우세요.")
            safe_id(field["id"])
            if field["id"] in ids or not field.get("name") or not field.get("instruction"):
                raise ValueError("항목 ID는 고유해야 하며 이름·추출 지침이 필요합니다.")
            ids.add(field["id"])

    def save_config(self, plan, fields, rules):
        self.validate_config(plan, fields)
        with self.lock:
            atomic_text(self.root / "research-plan.yaml", yaml.safe_dump(plan, allow_unicode=True, sort_keys=False))
            atomic_text(self.root / "config/extraction-fields.yaml", yaml.safe_dump(fields, allow_unicode=True, sort_keys=False))
            atomic_text(self.root / "config/synthesis-rules.md", rules)

    def catalog(self):
        return read_json(self.root / "catalog.json")

    def source(self, source_id):
        source = next((s for s in self.catalog() if s["id"] == source_id), None)
        if source is None:
            raise ValueError("자료 ID를 찾을 수 없습니다.")
        return source

    def source_dir(self, source_id):
        return self.root / "sources" / safe_id(source_id)

    def index(self, source_id):
        source = self.source(source_id)
        path = self.source_dir(source_id) / "original.pdf"
        if digest(path.read_bytes()) != source["sha256"]:
            raise ValueError(f"원본 파일이 변경되었습니다: {source_id}. 새 자료로 등록하세요.")
        index_path = self.source_dir(source_id) / "index.json"
        if digest(index_path.read_bytes()) != source["index_sha256"]:
            raise ValueError("원문 색인이 변경되었습니다. 원본에서 다시 등록하세요.")
        index = read_json(index_path)
        if index["sha256"] != source["sha256"]:
            raise ValueError("원문 색인과 파일이 일치하지 않습니다.")
        return index

    def add_pdf(self, data: bytes, filename: str, title: str = "", doi: str = "", url: str = ""):
        if len(data) > 100 * 1024 * 1024 or not data.startswith(b"%PDF-"):
            raise ValueError("100 MB 이하의 PDF 파일이 필요합니다.")
        sha = digest(data)
        source_id = "s_" + sha[:16]
        with self.lock:
            catalog = self.catalog()
            if any(s["id"] == source_id for s in catalog):
                return source_id
            folder = self.source_dir(source_id)
            folder.mkdir(parents=True, exist_ok=True)
            original = folder / "original.pdf"
            original.write_bytes(data)
            try:
                index = index_pdf(original, source_id)
            except Exception as exc:
                raise ValueError(f"PDF를 읽지 못했습니다: {type(exc).__name__}. 암호·손상 여부를 확인하세요.") from exc
            write_json(folder / "index.json", index)
            clean_doi = re.sub(r"^https?://(?:dx\.)?doi.org/", "", doi.strip()).lower()
            catalog.append({"id": source_id, "sha256": sha, "filename": Path(filename).name,
                            "index_sha256": digest((folder / "index.json").read_bytes()),
                            "title": title or Path(filename).stem, "doi": clean_doi, "url": url,
                            "study_id": clean_doi or source_id, "decision": "pending", "reason": "",
                            "added_at": now(), "page_count": len(index["pages"]),
                            "text_pages": sum(p["status"] == "text_available" for p in index["pages"]),
                            "history": []})
            write_json(self.root / "catalog.json", catalog)
        return source_id

    def screen(self, source_id, decision, reason, study_id=None, title=None, doi=None, url=None, quotes=None):
        """Record a screening decision. `quotes` are printed passages that justify it; each is
        located in the PDF so the screen can highlight it. A quote that is not found stays in
        the record as `unmatched` — the decision is still the reviewer's, never the string match's."""
        if decision not in {"include", "exclude", "pending"} or not reason.strip():
            raise ValueError("선별 상태와 판단 이유가 필요합니다.")
        located = [self._locate_screen_quote(source_id, q) for q in (quotes or [])]
        with self.lock:
            catalog = self.catalog()
            source = next((s for s in catalog if s["id"] == source_id), None)
            if source is None:
                raise ValueError("자료 ID를 찾을 수 없습니다.")
            source["history"].append({"at": now(), "decision": decision, "reason": reason,
                                      "previous": source["decision"],
                                      "quotes": [{"quote": q["quote"], "criterion": q["criterion"], "status": q["status"]} for q in located]})
            source.update(decision=decision, reason=reason, screen_quotes=located)
            source["criteria_hash"] = self.criteria_hash()
            if study_id:
                source["study_id"] = study_id.strip()
            if title:
                source["title"] = title.strip()
            if doi is not None:
                source["doi"] = re.sub(r"^https?://(?:dx\.)?doi.org/", "", doi.strip()).lower()
            if url is not None:
                if url.strip() and not url.strip().startswith(("https://", "http://")):
                    raise ValueError("출처 주소는 http:// 또는 https://로 시작해야 합니다.")
                source["url"] = url.strip()
            write_json(self.root / "catalog.json", catalog)

    def _locate_screen_quote(self, source_id, quote):
        if isinstance(quote, str):
            quote = {"text": quote, "criterion": ""}
        text = " ".join(str(quote.get("text", "")).split())
        if not text:
            raise ValueError("빈 근거 구절은 저장할 수 없습니다.")
        criterion = quote.get("criterion", "")
        if criterion not in {"", "inclusion", "exclusion"}:
            raise ValueError("근거 구절의 기준은 '포함' 또는 '제외'만 가능합니다.")
        found = locate_anywhere(self.index(source_id), text)
        return {"quote": text, "criterion": criterion, "status": found["status"], "page": found["page"],
                "passage_id": found.get("passage_id"), "boxes": found["boxes"],
                "occurrences": found.get("occurrences", []),
                "dehyphenated": found.get("dehyphenated", False)}

    def criteria_hash(self):
        plan = self.config()["plan"]
        return digest(json.dumps({k: plan.get(k) for k in
                      ("question", "scope", "inclusion", "exclusion")},
                      sort_keys=True, ensure_ascii=False).encode())

    def run_dir(self, run_id):
        return self.root / "runs" / safe_id(run_id)

    def delete_empty_run(self, run_id):
        """Remove a run that never received a response. Anything with responses or reviews stays."""
        folder = self.run_dir(run_id)
        if not (folder / "run.json").exists():
            raise ValueError("실행을 찾을 수 없습니다.")
        if any((folder / "responses").glob("*.json")) or (folder / "reviews.json").exists() and read_json(folder / "reviews.json"):
            raise ValueError("응답이나 검토 기록이 있는 실행은 지우지 않습니다.")
        with self.lock:
            import shutil
            shutil.rmtree(folder)

    def runs(self):
        folder = self.root / "runs"
        return sorted([p.name for p in folder.iterdir() if p.is_dir() and (p / "run.json").exists()], reverse=True) if folder.exists() else []

    def reviewer(self) -> str:
        path = self.root / ".reviewer"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""  # noqa: E501

    def remember_reviewer(self, name: str):
        try:
            atomic_text(self.root / ".reviewer", name.strip())
        except OSError:
            pass

    def with_bib(self, source: dict) -> dict:
        """A run keeps a frozen copy of each source; bibliography may have been filled later."""
        try:
            live = self.source(source["id"])
        except ValueError:
            return source
        return {**source, "bib": live.get("bib") or source.get("bib") or {}}

    def collection(self):
        path = self.root / "collection.json"
        return read_json(path) if path.exists() else []

    def remember_candidate(self, record):
        """Search candidates the person chose to keep, with or without a PDF (the PRISMA trail)."""
        with self.lock:
            items = self.collection()
            key = record.get("doi") or record.get("title", "").strip().lower()
            items = [i for i in items if (i.get("doi") or i.get("title", "").strip().lower()) != key]
            items.append({**record, "at": now()})
            write_json(self.root / "collection.json", items)

    def set_bibliography(self, source_id, authors, year, venue):
        """Author·year·venue for citations. Stored on the catalog entry; never required."""
        with self.lock:
            catalog = self.catalog()
            source = next((s for s in catalog if s["id"] == source_id), None)
            if source is None:
                raise ValueError("자료 ID를 찾을 수 없습니다.")
            source["bib"] = {"authors": [str(a) for a in authors or []], "year": int(year) if str(year or "").isdigit() else year, "venue": venue or ""}
            write_json(self.root / "catalog.json", catalog)

    def log_search(self, record):
        with self.lock:
            records = read_json(self.root / "search-log.json")
            records.append({"id": "search_" + uuid.uuid4().hex[:10], "at": now(), **record})
            write_json(self.root / "search-log.json", records)
