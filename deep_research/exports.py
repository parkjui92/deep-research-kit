"""Portable research records: Markdown, JSON, CSV and optional original PDFs."""
from __future__ import annotations

import csv
import io
import json
import zipfile

from .project import read_json
from .workflow import accepted, current_synthesis, evidence, manifest


def display_value(row):
    return row["review"].get("edited_value") if row["review"]["status"] == "edit" else row["value"]


def cell(text):
    return str(text or "—").replace("|", "\\|").replace("\n", " ")


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
    sources = {s["id"]: s for s in run["sources"]}
    fields = {f["id"]: f["name"] for f in run["config"]["fields"]}
    approved = accepted(project, run_id)
    lines = ["# " + run["config"]["plan"]["question"], "", f"실행: `{run_id}`", "",
             (f"문헌 {len(sources)}건 · 연구 {len({s['study_id'] for s in sources.values()})}건 · "
             f"채택 근거 {len(approved)}/{len(rows)}건"), "",
             "원문 문자열 일치, 사람의 근거 검토, AI 종합은 서로 다른 단계입니다.", "",
             "## 종합", ""]
    if synthesis:
        lines.append("아래는 검토된 근거에 기반한 AI 종합 초안입니다. 주장과 근거의 의미적 연결은 최종 확인이 필요합니다.\n")
        for claim in synthesis["claims"]:
            refs = ", ".join(f"[{e}](#{e})" for e in claim["evidence_ids"])
            lines.append(f"- **{claim['kind']}**: {claim['text']} ({refs})")
        lines += ["", "### 남은 질문", ""] + ["- " + str(g) for g in synthesis.get("gaps", [])]
    else:
        lines.append("유효한 종합이 아직 없습니다. 현재 확인된 근거와 미확인 항목을 함께 제공합니다.")
    lines += ["", "## 채택한 근거", "", "| 문헌 | 항목 | 검토 후 값 | 근거 ID |", "|---|---|---|---|"]
    for row in approved:
        lines.append(f"| {cell(sources[row['source_id']]['title'])} | {cell(fields[row['field_id']])} | "
                     f"{cell(display_value(row))} | [{row['id']}](#{row['id']}) |")
    lines += ["", "## 검토 기록과 원문 위치", ""]
    for row in rows:
        source = sources[row["source_id"]]
        lines += [f"<a id=\"{row['id']}\"></a>", f"### {row['id']} · {fields[row['field_id']]}", "",
                  f"문헌: {source['title']} (`{source['id']}`), 연구 ID: `{source['study_id']}`", "",
                  f"추출값: {row['value'] or '자료에서 찾지 못함'}", "",
                  f"읽기 범위: PDF {row['page_scope']['from']}~{row['page_scope']['to']}쪽 / 전체 {row['page_scope']['total']}쪽", "",
                  f"위치 대조: `{row['match_status']}` · 검토: `{row['review']['status']}`", "",
                  f"검토자: {row['review']['reviewer'] or '미검토'} · 이유: {row['review']['note'] or '—'}", ""]
        if row["review"]["status"] == "edit":
            lines += [f"수정값: {display_value(row)}", ""]
        for locator in row["locators"]:
            lines += [f"> {locator['quote'].replace(chr(10), ' ')}", "",
                      f"PDF {locator['page']}쪽 · `{locator['status']}` · `{locator['passage_id']}`", ""]
            if local_pdf_links:
                lines += [f"[원본 PDF 해당 쪽 열기](sources/{source['id']}.pdf#page={locator['page']})", ""]
        if row["note"]:
            lines += ["추출 메모: " + row["note"], ""]
    lines += ["## 확인 필요·제외", ""]
    for row in rows:
        if row not in approved:
            lines.append(f"- {row['id']}: {row['match_status']} / {row['review']['status']} — {row['review']['note'] or row['note']}")
    imported = {r["source_id"] for r in rows}
    for source in sources.values():
        if source["id"] not in imported:
            lines.append(f"- {source['title']}: 추출 응답 없음")
    lines += ["", "## 자료 목록", ""]
    for source in sources.values():
        link = source["url"] or ("https://doi.org/" + source["doi"] if source["doi"] else "원문은 프로젝트에 보관")
        lines += [f"- {source['title']} — {link}", f"  - ID: `{source['id']}` · SHA-256: `{source['sha256']}`"]
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
        writer.writerow(["evidence_id", "source_id", "field_id", "value", "match_status", "review_status"])
        for row in data["evidence"]:
            values = [row["id"], row["source_id"], row["field_id"], display_value(row) or "", row["match_status"], row["review"]["status"]]
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
