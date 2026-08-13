"""Format extractors: `.md`/`.txt`, `.docx`, `.pdf`.

Each returns raw text plus the `source_projection` that honestly describes how the text was
obtained. That label is not bookkeeping — it decides whether a citation into this document
can be positionally anchored at all:

    text       markdown or plain text; offsets are exact
    docx       paragraph text from the document body; offsets are exact
    pdf_text   an embedded text layer; offsets are exact *within the extracted text*
    pdf_image  no usable text layer; anchoring degrades to doc_only
    unparseable the file could not be read; the unit fails and enters the anomaly queue

The important design decision is what happens when extraction goes badly. It would be easy
to return whatever partial text came out and let analysis proceed. Karani does not, because
a citation into partially-extracted text points at an offset that does not correspond to
anything a human reader can find, and the docket would render a highlight in the wrong place
with full confidence. A wrong highlight is worse than an absent one: the absent one is
visibly absent, and the wrong one is believed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SourceProjection = Literal["text", "docx", "pdf_text", "pdf_image", "unparseable"]

# Below this many characters of extracted text, a PDF is treated as having no usable text
# layer. Scanned documents commonly yield a handful of stray glyphs from page furniture
# rather than nothing at all, and a handful of stray glyphs is worse than none: it looks
# like success.
_PDF_TEXT_FLOOR = 200


class UnparseableSource(Exception):
    """The file could not be read as any supported format.

    Raised rather than returning empty text. An empty rendition would produce an empty span
    registry, every criterion would come back `no_evidence`, and the run would report with
    total confidence that a student submitted nothing of relevance — when in fact the
    pipeline could not open their file. That failure has to be visible as a failure.
    """


@dataclass(frozen=True)
class Extracted:
    text: str
    projection: SourceProjection
    kind: str
    page_count: int = 0


def extract(path: Path) -> Extracted:
    suffix = path.suffix.lower()
    if suffix in (".md", ".txt", ".markdown"):
        return _extract_text(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    raise UnparseableSource(f"unsupported format {suffix!r} for {path.name}")


def _extract_text(path: Path) -> Extracted:
    try:
        raw = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise UnparseableSource(f"{path.name} is not valid UTF-8: {exc}") from exc
    if not raw.strip():
        raise UnparseableSource(f"{path.name} is empty")
    return Extracted(text=raw, projection="text", kind="md")


def _extract_docx(path: Path) -> Extracted:
    try:
        import docx  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise UnparseableSource("python-docx is not installed") from exc

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise UnparseableSource(f"{path.name} could not be opened as .docx: {exc}") from exc

    # Paragraph text only, joined by blank lines so the normalizer's paragraph map lines up
    # with the document's own paragraph structure. Tables and headers are deliberately not
    # extracted: their reading order is ambiguous, and an ambiguous reading order produces
    # offsets that do not correspond to how a human reads the page.
    paragraphs = [p.text.strip() for p in document.paragraphs]
    raw = "\n\n".join(p for p in paragraphs if p)
    if not raw.strip():
        raise UnparseableSource(f"{path.name} contains no extractable paragraph text")
    return Extracted(text=raw, projection="docx", kind="docx")


def _extract_pdf(path: Path) -> Extracted:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise UnparseableSource("pypdf is not installed") from exc

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise UnparseableSource(f"{path.name} could not be read as PDF: {exc}") from exc

    raw = "\n\n".join(_rejoin_pdf_paragraphs(p) for p in pages if p.strip())

    if len(raw.strip()) < _PDF_TEXT_FLOOR:
        # No usable text layer. The document still enters the run — a student is not
        # penalised for submitting a scan — but anchoring degrades to doc_only and the
        # viewer shows an honesty chip instead of a highlight it cannot place.
        return Extracted(
            text=raw,
            projection="pdf_image",
            kind="pdf",
            page_count=len(reader.pages),
        )

    return Extracted(text=raw, projection="pdf_text", kind="pdf", page_count=len(reader.pages))


def _rejoin_pdf_paragraphs(page_text: str) -> str:
    """Reconstruct paragraph boundaries from a PDF's hard-wrapped lines.

    A PDF has no paragraphs. It has glyphs at coordinates, and `extract_text()` hands back
    one line per typeset line, wrapped at whatever width the page used. Treating that output
    as prose collapses an entire page into a single block: an 1,100-word essay became **two**
    citable spans, which makes every citation resolve to "somewhere on this page" and quietly
    destroys the point of having a span registry at all.

    The heuristic: a wrapped line runs nearly the full measure, so the *last* line of a
    paragraph is the one that both ends a sentence and falls visibly short of the column
    width. Median line length is used as the measure rather than a fixed character count,
    because it adapts to the document's own typesetting instead of assuming one.

    This is genuinely a heuristic and the boundary is worth stating: a paragraph whose final
    line happens to fill the measure merges with the next one, and a short line ending in an
    abbreviation can split one paragraph in two. Both produce span boundaries that are wrong
    by a paragraph — visible in the viewer, and never silent, because the citation still
    resolves to text that contains the quote. The alternative, one span per page, is wrong by
    a page every time.
    """
    lines = [ln.rstrip() for ln in page_text.splitlines()]
    lines = [ln for ln in lines if ln.strip()]
    if not lines:
        return ""

    widths = sorted(len(ln) for ln in lines)
    median = widths[len(widths) // 2] or 1
    # A line must fall meaningfully short of the measure to count as a paragraph ending.
    short_enough = median * 0.85

    paragraphs: list[str] = []
    buffer: list[str] = []

    for line in lines:
        buffer.append(line.strip())
        ends_sentence = line.rstrip().endswith((".", "!", "?", '"', "”", ":"))
        if ends_sentence and len(line) < short_enough:
            paragraphs.append(" ".join(buffer))
            buffer = []

    if buffer:
        paragraphs.append(" ".join(buffer))

    return "\n\n".join(p for p in paragraphs if p)
