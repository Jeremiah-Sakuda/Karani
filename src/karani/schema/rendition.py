"""The rendition — the frozen artifact that everything cites and everything displays.

The problem this solves: a citation into a source file is a citation into something that can
change. A student re-uploads, a converter is updated, a `.docx` is opened and re-saved with
different whitespace, and every stored offset now points somewhere else. The evidence sheet
still renders. It is just quietly wrong.

So the source file is read exactly once and normalized into an immutable rendition. Spans are
minted from the rendition, the model is shown the rendition, the docket's click-to-locus
viewer displays the rendition, and the source file is never consulted again. Editing it after
ingest changes nothing downstream, which is KAR-304's acceptance criterion and the reason the
identity hash includes the normalizer and extractor versions: a different pipeline produces a
different artifact, and saying so is cheaper than discovering it later.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from karani.canon import sha256_text
from karani.config import EXTRACTOR_VERSIONS, NORMALIZER_VERSION

SourceProjection = Literal["text", "docx", "pdf_text", "pdf_image", "unparseable"]


def compute_rendition_id(normalized_text: str, extractor_version: str) -> str:
    """`sha256(normalizer_version ‖ extractor_versions ‖ normalized_text)`.

    Including the tool versions rather than only the text means an extractor upgrade that
    changes one character of whitespace yields a visibly different rendition, instead of the
    same ID over subtly different content. Identical content through an identical pipeline
    yields an identical ID — the other half of KAR-304.
    """
    return sha256_text(f"{NORMALIZER_VERSION}␟{extractor_version}␟{normalized_text}")


class Rendition(BaseModel):
    """Normalized text plus the paragraph→offset map the span registry is built from."""

    model_config = ConfigDict(extra="forbid")

    rendition_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    doc_id: str
    student_id: str
    text: str
    paragraphs: list[tuple[int, int]]
    source_projection: SourceProjection
    source_filename: str
    normalizer_version: str = NORMALIZER_VERSION
    extractor_version: str

    # Present only when the projection is pdf_image: page images cannot carry character
    # offsets, so citations against them degrade to doc_only and the viewer shows an honesty
    # chip rather than a highlight it cannot actually place. Documented, not hidden.
    page_image_paths: list[str] = Field(default_factory=list)

    @classmethod
    def freeze(
        cls,
        *,
        doc_id: str,
        student_id: str,
        text: str,
        paragraphs: list[tuple[int, int]],
        source_projection: SourceProjection,
        source_filename: str,
        source_kind: str,
        page_image_paths: list[str] | None = None,
    ) -> Rendition:
        extractor_version = EXTRACTOR_VERSIONS.get(source_kind, "unknown")
        return cls(
            rendition_id=compute_rendition_id(text, extractor_version),
            doc_id=doc_id,
            student_id=student_id,
            text=text,
            paragraphs=paragraphs,
            source_projection=source_projection,
            source_filename=source_filename,
            extractor_version=extractor_version,
            page_image_paths=page_image_paths or [],
        )

    @property
    def anchor_capability(self) -> Literal["exact", "doc_only"]:
        """What this rendition can honestly support as an anchor.

        A page-image projection has no character offsets to anchor to. Returning `doc_only`
        here is what makes the viewer show a chip saying so instead of a highlight placed by
        guesswork — a wrong highlight is worse than an absent one, because it is believed.
        """
        return "doc_only" if self.source_projection in ("pdf_image", "unparseable") else "exact"
