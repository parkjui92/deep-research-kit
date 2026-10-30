"""PDF provenance: immutable originals, Unicode-preserving exact quote anchors.

Coordinates are top-left PDF points, as required by streamlit-pdf-viewer.
No fuzzy hit is ever promoted to an exact match.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

import pdfplumber


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                   if not c.isspace() and c != "\u00ad")


def index_pdf(path: Path, source_id: str) -> dict:
    pages, passages = [], []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=2, y_tolerance=3, use_text_flow=True)
            # Keep the parser's reading order. Partition by lines, not character offsets.
            clean = [{"text": w["text"], "x0": w["x0"] - page.bbox[0],
                      "top": w["top"] - page.bbox[1],
                      "x1": w["x1"] - page.bbox[0],
                      "bottom": w["bottom"] - page.bbox[1]} for w in words]
            pages.append({"page": number, "width": page.width, "height": page.height,
                          "rotation": page.rotation,
                          "anchors_supported": page.rotation == 0 and
                              (page.cropbox is None or tuple(page.cropbox) == tuple(page.mediabox)),
                          "printed_label": None, "words": clean,
                          "status": "text_available" if clean else "no_text_layer"})
            for start in range(0, len(clean), 180):
                part = clean[start:start + 220]
                passages.append({"id": f"{source_id}:p{number}:w{start}", "page": number,
                                 "word_start": start, "word_end": start + len(part),
                                 "text": " ".join(w["text"] for w in part)})
    return {"source_id": source_id, "sha256": digest(path.read_bytes()),
            "parser": f"pdfplumber/{pdfplumber.__version__}",
            "reading_order": "pdf_content_stream",
            "pages": pages, "passages": passages}


def locate_quote(index: dict, passage_id: str, quote: str) -> dict:
    passage = next((p for p in index["passages"] if p["id"] == passage_id), None)
    result = {"passage_id": passage_id, "quote": quote, "status": "unmatched",
              "page": passage["page"] if passage else None, "boxes": []}
    if not passage:
        return {**result, "status": "invalid_passage"}
    needle = normalize(quote)
    if len(needle) < 8:
        return {**result, "status": "too_short"}
    page = index["pages"][passage["page"] - 1]
    if not page.get("anchors_supported", True):
        return {**result, "status": "unsupported_page_geometry"}
    words = page["words"][passage["word_start"]:passage["word_end"]]
    chars, mapping = [], []
    for i, word in enumerate(words):
        for char in normalize(word["text"]):
            chars.append(char)
            mapping.append(i)
    haystack = "".join(chars)
    hits = [m.start() for m in re.finditer("(?=" + re.escape(needle) + ")", haystack)]
    if len(hits) != 1:
        return {**result, "status": "ambiguous" if hits else "unmatched"}
    start = hits[0]
    selected = words[mapping[start]:mapping[start + len(needle) - 1] + 1]
    boxes = []
    for word in selected:
        if boxes and abs(boxes[-1]["y"] - word["top"]) < 3:
            b = boxes[-1]
            # Do not bridge columns with a giant rectangle.
            if 0 <= word["x0"] - (b["x"] + b["width"]) < 30:
                b["width"] = word["x1"] - b["x"]
                b["height"] = max(b["height"], word["bottom"] - b["y"])
                continue
        boxes.append({"page": passage["page"], "x": word["x0"], "y": word["top"],
                      "width": word["x1"] - word["x0"],
                      "height": word["bottom"] - word["top"],
                      "color": "rgba(245, 191, 69, 0.35)"})
    return {**result, "status": "exact_normalized", "boxes": boxes,
            "page_width": page["width"], "page_height": page["height"],
            "context": passage["text"], "source_sha256": index["sha256"]}
