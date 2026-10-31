"""Portable research records: Markdown, JSON, CSV and optional original PDFs."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .project import read_json
from .workflow import accepted, current_synthesis, evidence, manifest, reviewed_value

WORD = {"exact_normalized": "글자 그대로 일치", "multiple": "여러 곳에서 일치", "unmatched": "원문에서 못 찾음",
        "ambiguous": "같은 문장이 여러 곳", "too_short": "구절이 너무 짧음", "invalid_passage": "구간 없음",
        "unsupported_page_geometry": "회전·잘린 쪽", "partial_word": "단어 일부만 일치", "matched": "위치 찾음", "needs_check": "위치 미확인", "not_found": "미발견",
        "accept": "채택", "edit": "수정 후 채택", "hold": "보류", "reject": "제외", "pending": "미검토",
        "include": "포함", "exclude": "제외"}


def word(code):
    return WORD.get(code, code)


def local(iso):
    try:
        moment = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        return moment.astimezone(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(iso)[:16]


def _authors_text(bib):
    names = [a for a in (bib or {}).get("authors", []) if a]
    if not names:
        return ""
    first = names[0]
    return first if len(names) == 1 else (f"{first} 외" if len(names) > 2 else f"{names[0]}·{names[1]}")


def citation(source, row=None):
    """One line a researcher can paste under a sentence: author(year). title. venue. DOI · PDF page · quote."""
    bib = source.get("bib") or {}
    head = ", ".join(x for x in (_authors_text(bib), str(bib.get("year") or "")) if x)
    parts = [f"{head}. " if head else "", source["title"].rstrip(".") + ".", f" {bib['venue']}." if bib.get("venue") else "",
             f" https://doi.org/{source['doi']}" if source.get("doi") else (f" {source['url']}" if source.get("url") else "")]
    line = "".join(parts).strip()
    if row:
        pages = sorted({loc["page"] for loc in row["locators"] if loc.get("page")})
        if pages:
            line += f" (PDF {', '.join(map(str, pages))}쪽)"
        quote = next((loc["quote"] for loc in row["locators"]), "")
        if quote:
            line += "\n원문: \"" + quote + "\""
        line += "\n추출값: " + str(display_value(row) or "읽은 범위에서 찾지 못함")
    return line


def bibliography(project, run_id):
    run = manifest(project, run_id)
    sources = [project.with_bib(s) for s in run["sources"]]
    lines = [citation(s) for s in sorted(sources, key=lambda s: (_authors_text(s.get("bib")), s["title"]))]
    return "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines)) + "\n"


def display_value(row):
    return reviewed_value(row)


def text(value):
    """Text from people, models and PDFs inside the Markdown report. As markup it could hide words
    in the report and on the review screen that still reach the CSV and the synthesis (#34), and
    `$…$` reads as a formula (#21). The CSV and the reference list keep the text as it is."""
    flat = " ".join(str(value).splitlines())  # a blank line would let a `[x]: …` line vanish
    return flat.replace("<", "&lt;").replace(">", "&gt;").replace("$", "\\$").replace("[", "\\[")


def cell(value):
    return text(value or "—").replace("|", "\\|").replace("\n", " ")


def matrix(project, run_id):
    run = manifest(project, run_id)
    approved = {(e["source_id"], e["field_id"]): e for e in accepted(project, run_id)}
    output = []
    for source in run["sources"]:
        record = {"문헌": source["title"], "문헌 ID": source["id"], "연구 ID": source["study_id"]}
        for field in run["config"]["fields"]:
            row = approved.get((source["id"], field["id"]))
            record[f"{field['name']} [{field['id']}]"] = display_value(row) if row else "채택 근거 없음"
        output.append(record)
    return output


def bundle_data(project, run_id):
    run = manifest(project, run_id)
    # Fail closed if a local original was replaced after extraction.
    for source in run["sources"]:
        project.index(source["id"])
    return {"schema": "drk-export/1", "run": run, "evidence": evidence(project, run_id),
            "reviews": read_json(project.run_dir(run_id) / "reviews.json"),
            "synthesis": current_synthesis(project, run_id)}


def report(project, run_id, local_pdf_links=False):
    data = bundle_data(project, run_id)
    run, rows, synthesis = data["run"], data["evidence"], data["synthesis"]
    sources = {s["id"]: project.with_bib(s) for s in run["sources"]}
    fields = {f["id"]: f["name"] for f in run["config"]["fields"]}
    approved = accepted(project, run_id)
    title = read_json(project.root / "project.json").get("title", "")
    reviewers = sorted({r["review"].get("reviewer") for r in rows if r["review"].get("reviewer")})
    notes = {r["note"] for r in rows if r.get("note")}
    lines = ["# " + text(run["config"]["plan"]["question"]), "",
             f"프로젝트: {text(title)} (`{project.root.name}`) · 실행 `{run_id}` · 실행 생성 {local(run['created_at'])} · 보고서 작성 {local(datetime.now(UTC).isoformat())}", "",
             (f"문헌 {len(sources)}건 · 연구 {len({s['study_id'] for s in sources.values()})}건 · "
             f"채택 근거 {len(approved)}/{len(rows)}건 · 검토자 {text(', '.join(reviewers)) or '없음'}"), "",
             "원문 문자열 일치, 사람의 근거 검토, AI 종합은 서로 다른 단계입니다. 쪽수는 PDF 파일의 첫 장부터 센 것이라 인쇄 쪽 번호와 다를 수 있습니다.", ""]
    if len(notes) == 1:
        lines += ["추출 메모(모든 근거 공통): " + text(next(iter(notes))), ""]
    lines += ["## 종합", ""]
    if synthesis:
        lines.append("아래는 검토된 근거에 기반한 AI 종합 초안입니다. 주장과 근거의 의미적 연결은 최종 확인이 필요합니다.\n")
        for claim in synthesis["claims"]:
            refs = ", ".join(f"[{e}](#{e})" for e in claim["evidence_ids"])
            lines.append(f"- **{claim['kind']}**: {text(claim['text'])} ({refs})")
        lines += ["", "### 남은 질문", ""] + ["- " + text(g) for g in synthesis.get("gaps", [])]
    else:
        lines.append("유효한 종합이 아직 없습니다. 현재 확인된 근거와 미확인 항목을 함께 제공합니다.")
    lines += ["", "## 채택한 근거", "", "| 문헌 | 항목 | 검토 후 값 | 근거 ID |", "|---|---|---|---|"]
    for row in approved:
        lines.append(f"| {cell(sources[row['source_id']]['title'])} | {cell(fields[row['field_id']])} | "
                     f"{cell(display_value(row))} | [{row['id']}](#{row['id']}) |")
    lines += ["", "## 검토 기록과 원문 위치", ""]
    for row in rows:
        source = sources[row["source_id"]]
        study = str(source["study_id"]).replace("`", "'")  # shown in a code span, so as it is
        lines += [f"<a id=\"{row['id']}\"></a>", f"### {row['id']} · {text(fields[row['field_id']])}", "",
                  f"문헌: {text(source['title'])} (`{source['id']}`), 연구 ID: `{study}`", "",
                  f"추출값: {text(row['value'] or '자료에서 찾지 못함')}", "",
                  f"읽기 범위: PDF {row['page_scope']['from']}~{row['page_scope']['to']}쪽 / 전체 {row['page_scope']['total']}쪽", "",
                  f"위치 대조: {word(row['match_status'])} · 검토: {word(row['review']['status'])}", "",
                  f"검토자: {text(row['review']['reviewer'] or '미검토')} · 이유: {text(row['review']['note'] or '—')}", ""]
        if row["review"]["status"] == "edit":
            lines += [f"수정값: {text(display_value(row))}", ""]
        for locator in row["locators"]:
            lines += [f"> {text(locator['quote']).replace(chr(10), ' ')}", ""]
            if locator.get("translation"):
                lines += [f"참고 번역(AI · 원문 대조 안 함): {text(locator['translation'])}", ""]
            lines += [f"PDF {locator['page']}쪽 · {word(locator['status'])} · 구간 `{locator['passage_id']}`", ""]
            if local_pdf_links:
                lines += [f"[원본 PDF 해당 쪽 열기](sources/{source['id']}.pdf#page={locator['page']})", ""]
        if row["note"] and len(notes) > 1:
            lines += ["추출 메모: " + text(row["note"]), ""]
    lines += ["## 확인 필요·제외", ""]
    for row in rows:
        if row not in approved:
            lines.append(f"- {row['id']}: {word(row['match_status'])} / {word(row['review']['status'])} — {text(row['review']['note'] or ('미검토' if len(notes) == 1 else row['note']))}")
    imported = {r["source_id"] for r in rows}
    for source in sources.values():
        if source["id"] not in imported:
            lines.append(f"- {text(source['title'])}: 추출 응답 없음")
    lines += ["", "## 선별 판단과 근거 구절", "",
              "실행에 포함한 문헌마다 포함 판단의 이유와, 그 근거로 적은 원문 구절·위치입니다. 구절 위치는 문자열 대조 결과이고 기준 적합성은 사람의 판단입니다.", ""]
    for source in sources.values():
        lines += [f"- **{text(source['title'])}** — 판단: {word(source['decision'])} · 이유: {text(source['reason'] or '—')}"]
        for quote in source.get("screen_quotes", []):
            where = (f"PDF {quote['page']}쪽" + (f" 외 {len(quote['occurrences']) - 1}곳" if quote.get("occurrences") else "")
                     if quote["status"] in {"exact_normalized", "multiple"} else "원문에서 찾지 못함")
            tag = {"inclusion": "포함 기준", "exclusion": "제외 기준"}.get(quote.get("criterion", ""), "기준 미표시")
            lines += [f"  - [{tag} · {where} · {word(quote['status'])}] {text(quote['quote']).replace(chr(10), ' ')}"]
    lines += ["", "## 참고문헌", ""]
    for i, source in enumerate(sorted(sources.values(), key=lambda s: (_authors_text(s.get("bib")), s["title"])), 1):
        lines.append(f"{i}. {text(citation(source))}  ")
        lines.append(f"   문헌 ID `{source['id']}` · SHA-256 `{source['sha256'][:16]}…`")
    lines += ["", "## 위키로 이어가기", "",
              "이 문서와 research.json을 함께 가져오세요. 근거 ID·문헌 ID·원문 위치·검토 상태를 보존하세요.",
              "미검토 항목을 확정된 사실로 옮기지 마세요. 같은 연구의 보고서를 중복 집계하지 마세요.", ""]
    return "\n".join(lines)


def export_zip(project, run_id, include_pdfs=False):
    data = bundle_data(project, run_id)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("research.md", report(project, run_id, local_pdf_links=include_pdfs))
        archive.writestr("research.json", json.dumps(data, ensure_ascii=False, indent=2))
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        writer.writerow(["근거 ID", "문헌 ID", "문헌", "항목", "검토 후 값", "위치 대조", "검토 상태", "검토자", "검토 이유", "PDF 쪽"])
        sources = {s["id"]: s for s in data["run"]["sources"]}
        fields = {f["id"]: f["name"] for f in data["run"]["config"]["fields"]}
        for row in data["evidence"]:
            pages = ", ".join(str(loc["page"]) for loc in row["locators"] if loc.get("page")) or ""
            values = [row["id"], row["source_id"], sources.get(row["source_id"], {}).get("title", ""), fields.get(row["field_id"], row["field_id"]),
                      display_value(row) or "", word(row["match_status"]), word(row["review"]["status"]),
                      row["review"].get("reviewer", "") or "", row["review"].get("note", "") or "", pages]
            # Spreadsheet formula injection protection for user/model text.
            writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for v in values])
        archive.writestr("evidence.csv", "\ufeff" + csv_buffer.getvalue())
        comparison = matrix(project, run_id)
        comparison_buffer = io.StringIO()
        comparison_writer = csv.writer(comparison_buffer)
        comparison_writer.writerow(comparison[0].keys())
        for record in comparison:
            comparison_writer.writerow(["'" + str(v) if str(v).startswith(("=", "+", "-", "@")) else v for v in record.values()])
        archive.writestr("comparison.csv", "\ufeff" + comparison_buffer.getvalue())
        for source in data["run"]["sources"]:
            if include_pdfs:
                archive.write(project.source_dir(source["id"]) / "original.pdf", "sources/" + source["id"] + ".pdf")
        archive.writestr("README.txt", "Markdown + research.json + CSV는 같은 실행의 기록입니다.\n"
                          "PDF 파일을 포함했다면 원 저작물의 이용 조건이 계속 적용됩니다.\n"
                          "PDF 쪽수는 1부터 세며 인쇄된 쪽 번호와 다를 수 있습니다. 좌표는 좌상단 기준 PDF point입니다.\n")
    return buffer.getvalue()


def compare(project, baseline, changed):
    a, b = manifest(project, baseline), manifest(project, changed)
    left = {(r["source_id"], r["field_id"]): r for r in evidence(project, baseline)}
    right = {(r["source_id"], r["field_id"]): r for r in evidence(project, changed)}
    differences = []
    for key in sorted(left.keys() | right.keys()):
        x, y = left.get(key), right.get(key)
        before = {"value": display_value(x), "match": x["match_status"], "review": x["review"]["status"]} if x else None
        after = {"value": display_value(y), "match": y["match_status"], "review": y["review"]["status"]} if y else None
        if before != after:
            differences.append({"source_id": key[0], "field_id": key[1], "before": before, "after": after})
    return {"baseline": baseline, "changed": changed, "config_before": a["config"],
            "config_after": b["config"], "source_ids_before": [s["id"] for s in a["sources"]],
            "source_ids_after": [s["id"] for s in b["sources"]], "differences": differences,
            "synthesis_before": current_synthesis(project, baseline), "synthesis_after": current_synthesis(project, changed)}
