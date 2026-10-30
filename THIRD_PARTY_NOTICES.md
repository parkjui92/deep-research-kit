# Third-party notices

Deep Research Kit original code is licensed under Apache-2.0. Dependencies retain their respective licenses. No upstream application source file has been copied into this project.

| Component | Use | License / source |
|---|---|---|
| Streamlit | Local application UI | Apache-2.0 · https://github.com/streamlit/streamlit |
| streamlit-pdf-viewer 0.0.30 | Original PDF rendering and annotation display | Apache-2.0 · https://github.com/ScienciaLAB/streamlit-pdf-viewer |
| PDF.js (inside viewer) | Browser PDF rendering | Apache-2.0 · https://github.com/mozilla/pdf.js |
| pdfplumber / pdfminer.six | PDF word/text coordinates | MIT · https://github.com/jsvine/pdfplumber · https://github.com/pdfminer/pdfminer.six |
| pypdfium2 | Transitive rendering dependency and development visual checks | Apache-2.0 / BSD-3-Clause; bundled PDFium and third-party notices apply · https://github.com/pypdfium2-team/pypdfium2 |
| PyYAML | Configuration | MIT · https://github.com/yaml/pyyaml |
| filelock | Local project write locks | MIT (installed 3.32.7 metadata) · https://github.com/tox-dev/filelock |
| HTTPX | Optional API/search adapters | BSD-3-Clause · https://github.com/encode/httpx |

The pinned environment is described by `uv.lock`; installed package distributions include their own notices. Development dependencies include pytest (MIT), Ruff (MIT) and ReportLab (BSD).

## Architecture references

- EviStreams frontend/backend, Apache-2.0: source location / review drawer pattern. No fuzzy matching code copied. See `docs/REUSE.md` for exact commit references and rejected behaviors.
- Kotaemon, Apache-2.0: citation navigation reference only; no code copied.
- Thesys, AGPL-3.0: reference only; no code copied, dependency or derivative integration.
- REA: user-installed analysis tool, not bundled or required for student execution.

## Example documents

The original PDFs are separate works. Their authors, source URLs, versions and licenses appear in `deep_research/examples.py` and the generated `example-manifest.json`. The first two arXiv manuscripts are CC BY 4.0; the PNAS manuscript is CC BY-NC-ND 4.0. The source files are downloaded unchanged. The code license does not relicense these papers.
