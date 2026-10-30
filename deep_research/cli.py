import argparse
import json
import sys
from pathlib import Path

from . import workflow
from .exports import compare, export_zip, report
from .project import Project, atomic_text, read_json


def main(argv=None):
    # Windows pipes default to the locale code page; paper text needs UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser =argparse.ArgumentParser(description="근거를 추적하는 문헌조사 도구")
    parser.add_argument("--project", default="projects/my-research")
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--title", default="나의 문헌조사")
    add = commands.add_parser("add")
    add.add_argument("pdf")
    add.add_argument("--title", default="")
    add.add_argument("--doi", default="")
    add.add_argument("--url", default="")
    screen = commands.add_parser("screen")
    screen.add_argument("source_id")
    screen.add_argument("decision", choices=["include", "exclude", "pending"])
    screen.add_argument("--reason", required=True)
    screen.add_argument("--study-id")
    commands.add_parser("prepare")
    commands.add_parser("status")
    read = commands.add_parser("read-request")
    read.add_argument("run_id")
    read.add_argument("source_id")
    read.add_argument("--start", type=int, default=0)
    read.add_argument("--count", type=int, default=5)
    for name in ["import-extraction", "import-synthesis"]:
        command = commands.add_parser(name)
        command.add_argument("run_id")
        command.add_argument("response")
    for name in ["prepare-synthesis", "report", "api-extract", "api-synthesize"]:
        commands.add_parser(name).add_argument("run_id")
    review = commands.add_parser("review")
    review.add_argument("run_id")
    review.add_argument("evidence_id")
    review.add_argument("status", choices=["accept", "edit", "hold", "reject"])
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    review.add_argument("--value")
    export = commands.add_parser("export")
    export.add_argument("run_id")
    export.add_argument("output")
    export.add_argument("--include-pdfs", action="store_true")
    diff = commands.add_parser("compare")
    diff.add_argument("baseline")
    diff.add_argument("changed")
    search = commands.add_parser("search")
    search.add_argument("query")
    args = parser.parse_args(argv)
    project = Project(args.project)
    try:
        match args.command:
            case "init":
                project.initialize(args.title)
                result = str(project.root)
            case "add":
                path = Path(args.pdf)
                result = project.add_pdf(path.read_bytes(), path.name, args.title, args.doi, args.url)
            case "screen":
                project.screen(args.source_id, args.decision, args.reason, args.study_id)
                result = "saved"
            case "prepare":
                result = workflow.prepare(project)
            case "status":
                result = {"sources": project.catalog(), "runs": project.runs()}
            case "read-request":
                from .project import safe_id
                request = read_json(project.run_dir(args.run_id) / "requests" / (safe_id(args.source_id) + ".json"))
                start = max(0, args.start)
                count = max(1, min(20, args.count))
                result = {**request, "passages": request["passages"][start:start + count],
                          "total_passages": len(request["passages"]), "start": start,
                          "next_start": start + count if start + count < len(request["passages"]) else None}
            case "import-extraction":
                result = workflow.import_extraction(project, args.run_id, read_json(Path(args.response)))
            case "review":
                workflow.review(project, args.run_id, args.evidence_id, args.status, args.note, args.reviewer, args.value)
                result = "saved"
            case "prepare-synthesis":
                workflow.prepare_synthesis(project, args.run_id)
                result = str(project.run_dir(args.run_id) / "synthesis-request.json")
            case "import-synthesis":
                result = workflow.import_synthesis(project, args.run_id, read_json(Path(args.response)))
            case "report":
                output = project.run_dir(args.run_id) / "research.md"
                atomic_text(output, report(project, args.run_id))
                result = str(output)
            case "compare":
                result = compare(project, args.baseline, args.changed)
            case "export":
                path = Path(args.output)
                if path.exists():
                    raise ValueError("기존 내보내기 파일이 있습니다. 새 이름을 사용하세요.")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(export_zip(project, args.run_id, args.include_pdfs))
                result = str(path)
            case "search":
                from .providers import crossref_search
                result = crossref_search(project, args.query)
            case "api-extract":
                from .providers import extract_with_api
                extract_with_api(project, args.run_id)
                result = "saved"
            case "api-synthesize":
                from .providers import synthesize_with_api
                result = synthesize_with_api(project, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f"오류: {exc}\n")


if __name__ == "__main__":
    main()
