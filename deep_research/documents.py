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


# Typographic variants a model commonly transcribes as ASCII. Folding them keeps
# the match on the printed words; it never invents text that is not on the page.
PUNCTUATION_FOLD = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-", "\u2013": "-", "\u2014": "-",
    "\u2015": "-", "\u2212": "-",
})


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold().translate(PUNCTUATION_FOLD)
    return "".join(c for c in folded if not c.isspace() and c != "\u00ad")


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
    haystack, mapping = _haystack(words)
    hits = _find(needle, haystack)
    dehyphenated = False
    if not hits:
        # The source text as printed always wins; joining a line-end hyphen is a fallback.
        joined, joined_mapping = _haystack(words, dehyphenate=True)
        if joined != haystack and (joined_hits := _find(needle, joined)):
            hits, mapping, dehyphenated = joined_hits, joined_mapping, True
    if not hits:
        continued = _locate_continued(index, passage, needle)
        if continued is not None:
            return {**result, **continued, "page_width": page["width"], "page_height": page["height"],
                    "context": passage["text"], "source_sha256": index["sha256"]}
    if len(hits) != 1:
        return {**result, "status": "ambiguous" if hits else "unmatched"}
    start = hits[0]
    selected = [{**w, "page": passage["page"]} for w in words[mapping[start]:mapping[start + len(needle) - 1] + 1]]
    return {**result, "status": "exact_normalized", "dehyphenated": dehyphenated, "boxes": _boxes(selected),
            "page_width": page["width"], "page_height": page["height"],
            "context": passage["text"], "source_sha256": index["sha256"]}


def _locate_continued(index: dict, passage: dict, needle: str):
    """A quote that starts in the cited passage and runs past its end: into the rest of the
    page (passages are overlapping word windows) and on into the next page. Still an exact
    match on the printed words in reading order; it must start inside the cited passage and
    occur only once in the stretch searched. Returns None when that does not hold."""
    number = passage["page"]
    words = [{**w, "page": number} for w in index["pages"][number - 1]["words"][passage["word_start"]:]]
    if number < len(index["pages"]):
        following = index["pages"][number]
        if following.get("anchors_supported", True):
            words += [{**w, "page": number + 1} for w in following["words"][:220]]
    own = passage["word_end"] - passage["word_start"]
    for dehyphenate in (False, True):
        haystack, mapping = _haystack(words, dehyphenate=dehyphenate)
        hits = _find(needle, haystack)
        if not hits:
            continue
        if len(hits) != 1 or mapping[hits[0]] >= own:
            return None
        start = hits[0]
        selected = words[mapping[start]:mapping[start + len(needle) - 1] + 1]
        return {"status": "exact_normalized", "dehyphenated": dehyphenate, "continued": True,
                "boxes": _boxes(selected), "pages": sorted({w["page"] for w in selected})}
    return None


def _boxes(selected: list) -> list:
    boxes = []
    for word in selected:
        if boxes and boxes[-1]["page"] == word["page"] and abs(boxes[-1]["y"] - word["top"]) < 3:
            b = boxes[-1]
            # Do not bridge columns with a giant rectangle.
            if 0 <= word["x0"] - (b["x"] + b["width"]) < 30:
                b["width"] = word["x1"] - b["x"]
                b["height"] = max(b["height"], word["bottom"] - b["y"])
                continue
        boxes.append({"page": word["page"], "x": word["x0"], "y": word["top"],
                      "width": word["x1"] - word["x0"],
                      "height": word["bottom"] - word["top"],
                      "color": "rgba(245, 191, 69, 0.35)"})
    return boxes


def locate_anywhere(index: dict, quote: str) -> dict:
    """Find a quote anywhere in the document. Only one printed occurrence counts.

    Passages overlap, so the same occurrence can surface twice; it is one hit when the
    first highlighted box lands on the same spot. Two different spots are ambiguous.
    """
    result = {"quote": quote, "status": "unmatched", "page": None, "boxes": [], "passage_id": None}
    if len(normalize(quote)) < 8:
        return {**result, "status": "too_short"}
    hits = {}
    for passage in index["passages"]:
        found = locate_quote(index, passage["id"], quote)
        if found["status"] == "ambiguous":
            # Two printed copies inside one window (e.g. a running head): record each copy.
            for copy in _each_hit(index, passage, quote):
                box = copy["boxes"][0]
                hits.setdefault((copy["page"], round(box["x"]), round(box["y"])), copy)
        elif found["status"] == "exact_normalized":
            box = found["boxes"][0]
            hits.setdefault((found["page"], round(box["x"]), round(box["y"])), found)
    if not hits:
        return result
    ordered = sorted(hits.values(), key=lambda h: (h["page"], h["boxes"][0]["y"], h["boxes"][0]["x"]))
    first = ordered[0]
    if len(ordered) == 1:
        return first
    # The sentence is printed in more than one place (abstract and body, say). Every place is
    # a true location of the printed words, so all of them are kept and the first is shown.
    return {**first, "status": "multiple", "occurrences": [{"page": h["page"], "boxes": h["boxes"],
                                                            "passage_id": h["passage_id"]} for h in ordered]}


def _each_hit(index: dict, passage: dict, quote: str) -> list:
    """Split a passage with repeated copies of the quote into one locator per copy."""
    needle = normalize(quote)
    page = index["pages"][passage["page"] - 1]
    words = page["words"][passage["word_start"]:passage["word_end"]]
    haystack, mapping = _haystack(words)
    out = []
    for start in _find(needle, haystack):
        lo, hi = mapping[start], mapping[start + len(needle) - 1]
        sub = {**passage, "id": passage["id"] + f"#{start}", "word_start": passage["word_start"] + lo,
               "word_end": passage["word_start"] + hi + 1}
        probe = {**index, "passages": [sub]}
        found = locate_quote(probe, sub["id"], quote)
        if found["status"] == "exact_normalized":
            out.append({**found, "passage_id": passage["id"]})
    return out


def _line_end_hyphen(words: list, i: int) -> bool:
    """`produc-` at the end of a line followed by `tivity` at the start of the next."""
    word, following = words[i], words[i + 1] if i + 1 < len(words) else None
    text = word["text"]
    if following is None or len(text) < 3 or not text.endswith("-") or not text[-2].isalpha():
        return False
    wrapped = following["top"] - word["top"] > 2 or following["x0"] < word["x0"]
    return wrapped and following["text"][:1].islower()


def _haystack(words: list, dehyphenate: bool = False):
    chars, mapping = [], []
    for i, word in enumerate(words):
        text = normalize(word["text"])
        if dehyphenate and _line_end_hyphen(words, i):
            text = text[:-1]
        for char in text:
            chars.append(char)
            mapping.append(i)
    return "".join(chars), mapping


def _find(needle: str, haystack: str) -> list:
    return [m.start() for m in re.finditer("(?=" + re.escape(needle) + ")", haystack)]
