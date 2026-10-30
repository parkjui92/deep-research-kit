"""Package a clean source checkout and optionally the separately licensed class corpus."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [".gitignore", "CLAUDE.md", "LICENSE", "README.md", "THIRD_PARTY_NOTICES.md",
         "app.py", "pyproject.toml", "uv.lock", "start.command", "start.bat"]
FOLDERS = [".claude", ".github", ".streamlit", "deep_research", "docs", "examples", "tests", "tools"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--classroom", action="store_true")
    args = parser.parse_args()
    kind = "classroom" if args.classroom else "source"
    output = ROOT / "dist" / f"deep-research-kit-0.1.0-{kind}.zip"
    output.parent.mkdir(exist_ok=True)
    paths = [ROOT / f for f in FILES]
    for folder in FOLDERS:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and
                     "__pycache__" not in p.parts and not p.name.endswith(".pyc") and p.name != "secrets.toml")
    if args.classroom:
        from deep_research.examples import PAPERS
        for paper in PAPERS:
            path = ROOT / "example-cache" / (paper["key"] + ".pdf")
            if not path.exists():
                raise SystemExit("먼저 공통 사례의 원본 PDF를 모두 준비하세요.")
            paths.append(path)
    hashes = {}
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(paths)):
            relative = path.relative_to(ROOT).as_posix()
            archive.write(path, "deep-research-kit/" + relative)
            hashes[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        archive.writestr("deep-research-kit/RELEASE-MANIFEST.json", json.dumps(
            {"version": "0.1.0", "kind": kind, "sha256": hashes}, ensure_ascii=False, indent=2))
    print(f"{output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
