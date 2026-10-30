"""Three actual papers. Downloads are separate from the software license."""
import argparse
from pathlib import Path

import httpx

from .project import DEFAULT_FIELDS, DEFAULT_PLAN, DEFAULT_RULES, Project, read_json, write_json

PAPERS = [
    {"key": "metr-2025-v2", "title": "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity",
     "authors": "Joel Becker, Nate Rush, Elizabeth Barnes, David Rein", "year": 2025,
     "doi": "10.48550/arXiv.2507.09089", "url": "https://arxiv.org/abs/2507.09089v2",
     "pdf": "https://arxiv.org/pdf/2507.09089v2", "license": "CC BY 4.0",
     "license_url": "https://creativecommons.org/licenses/by/4.0/"},
    {"key": "ideation-2025-v1", "title": "The Ideation-Execution Gap: Execution Outcomes of LLM-Generated versus Human Research Ideas",
     "authors": "Chenglei Si, Tatsunori Hashimoto, Diyi Yang", "year": 2025,
     "doi": "10.48550/arXiv.2506.20803", "url": "https://arxiv.org/abs/2506.20803v1",
     "pdf": "https://arxiv.org/pdf/2506.20803v1", "license": "CC BY 4.0",
     "license_url": "https://creativecommons.org/licenses/by/4.0/"},
    {"key": "reproduction-2026-vor", "title": "AI-assisted teams outperform AI-led teams but not human-only teams in assessing research reproducibility in quantitative social science",
     "authors": "Abel Brodeur et al.", "year": 2026,
     "doi": "10.1073/pnas.2524747123", "url": "https://discovery.ucl.ac.uk/id/eprint/10230346/",
     "pdf": "https://eprints.whiterose.ac.uk/id/eprint/241548/1/brodeur-et-al-2026-ai-assisted-teams-outperform-ai-led-teams-but-not-human-only-teams-in-assessing-research-1.pdf",
     "mirror": "https://discovery.ucl.ac.uk/id/eprint/10230346/1/BRODEU~1.PDF",
     "license": "CC BY-NC-ND 4.0", "license_url": "https://creativecommons.org/licenses/by-nc-nd/4.0/"},
]


def create_example(target, cache=None):
    target = Path(target)
    project = Project(target)
    if not (target / "project.json").exists():
        project.initialize("AI와 지식업무 · 공통 문헌조사 사례")
    cache = Path(cache) if cache else Path(__file__).resolve().parent.parent / "example-cache"
    cache.mkdir(parents=True, exist_ok=True)
    manifest = []
    for paper in PAPERS:
        path = cache / (paper["key"] + ".pdf")
        if not path.exists():
            downloaded = None
            for url in dict.fromkeys([paper["pdf"], paper.get("mirror", paper["pdf"]) ]):
                try:
                    response = httpx.get(url, follow_redirects=True, timeout=60)
                    response.raise_for_status()
                    if response.content.startswith(b"%PDF-"):
                        downloaded = response.content
                        break
                except httpx.HTTPError:
                    continue
            if downloaded is None:
                raise ValueError(f"{paper['key']} 다운로드 실패. 앞서 등록한 자료는 보존됩니다. 공식 PDF를 example-cache/{paper['key']}.pdf에 저장하고 다시 실행하세요.") from None
            path.write_bytes(downloaded)
        source_id = project.add_pdf(path.read_bytes(), path.name, paper["title"], paper["doi"], paper["url"])
        manifest.append({**paper, "source_id": source_id, "sha256": project.source(source_id)["sha256"]})
    write_json(target / "example-manifest.json", manifest)
    return project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default="projects/class-example")
    parser.add_argument("--cache", default="example-cache")
    args = parser.parse_args()
    project = create_example(args.project, args.cache)
    print(project.root)


def load_reference(project):
    """Explicit fixture import, never masquerading as a fresh AI extraction."""
    from .documents import locate_quote
    from .workflow import import_extraction, prepare
    config = project.config()
    effective_plan = {**DEFAULT_PLAN, **config["plan"]}
    if effective_plan != DEFAULT_PLAN or config["fields"] != DEFAULT_FIELDS or config["synthesis_rules"] != DEFAULT_RULES:
        raise ValueError("사전 작성 예시는 기본 설계에서만 사용합니다. 바꾼 기준은 새 AI 추출로 실행하세요.")
    fixture = read_json(Path(__file__).resolve().parent.parent / "examples/reference-extraction.json")
    selected = []
    for doc in fixture["documents"]:
        source = next((s for s in project.catalog() if s["sha256"] == doc["sha256"]), None)
        if source is None:
            raise ValueError("기준 예시와 같은 원본 PDF가 필요합니다. 문헌 버전·다운로드 원본을 확인하세요.")
        selected.append((doc, source))
    selected_ids = {s["id"] for _, s in selected}
    if any(s["decision"] == "include" and s["id"] not in selected_ids for s in project.catalog()):
        raise ValueError("사전 예시는 공통 문헌 3편만 포함한 프로젝트에서 사용하세요.")
    for doc, source in selected:
        project.screen(source["id"], "include", "공통 사례의 사전 선별 예시: 실증적 과업 결과. 학습자가 기준 적합성을 재검토할 것.")
    run_id = prepare(project)
    for doc, source in selected:
        req = read_json(project.run_dir(run_id) / "requests" / (source["id"] + ".json"))
        index = project.index(source["id"])
        rows = []
        for row in doc["rows"]:
            quotes = []
            for quote in row["quotes"]:
                passage = next((p for p in req["passages"] if locate_quote(index, p["id"], quote)["status"] == "exact_normalized"), None)
                if passage is None:
                    raise ValueError(f"기준 예시 원문 위치를 찾지 못했습니다: {doc['key']} / {row['field_id']}")
                quotes.append({"passage_id": passage["id"], "quote": quote})
            rows.append({"source_id": source["id"], "field_id": row["field_id"],
                         "value": row["value"], "quotes": quotes, "note": fixture["notice"]})
        import_extraction(project, run_id, {"request_id": req["request_id"], "rows": rows,
                                          "mode": "prepared_reference_not_live_ai"})
    return run_id


if __name__ == "__main__":
    main()
