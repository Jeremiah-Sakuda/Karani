"""Rendition freeze (KAR-304) — read the source file exactly once, then never again.

The property: **the cited artifact cannot drift.** After freeze, editing, replacing, or
deleting the source file changes nothing downstream. Every span offset, every citation,
every highlight in the docket's viewer, and every hash resolves against the frozen rendition.

This is not defensive over-engineering. It closes a failure that is invisible when it
happens: a `.docx` re-saved by a different word processor version shifts whitespace by a few
characters, every stored offset slides, and the evidence sheet still renders — pointing at
text that is a sentence off from what was cited. Nothing errors. The citation just quietly
becomes wrong, and the more confident the interface looks, the less likely anyone is to check.

Freezing also makes the identity honest in the other direction: `rendition_id` hashes the
normalizer version and the extractor version alongside the text, so upgrading a parser
produces a visibly different artifact instead of the same ID over subtly different content.
"""

from __future__ import annotations

from dataclasses import dataclass

from karani.ingest.extract import Extracted, UnparseableSource, extract
from karani.ingest.normalize import normalize_with_offsets
from karani.ingest.source import SubmissionRef
from karani.schema.rendition import Rendition
from karani.schema.spans import SpanRegistry


@dataclass(frozen=True)
class FrozenSubmission:
    ref: SubmissionRef
    rendition: Rendition
    registry: SpanRegistry

    @property
    def anchor_confidence(self) -> str:
        return self.rendition.anchor_capability


def freeze(ref: SubmissionRef) -> FrozenSubmission:
    """Read, extract, normalize, hash, and mint the span registry. Raises on unparseable.

    `UnparseableSource` propagates rather than being swallowed into an empty rendition. An
    empty rendition would yield an empty span registry, every criterion would return
    `no_evidence`, and the run would report with complete confidence that a student's work
    contained nothing relevant — when what actually happened is that Karani could not open
    their file. The caller turns this into a `TaskFailed` event and an anomaly-queue item,
    which is a visible failure rather than a confident wrong answer.
    """
    extracted: Extracted = extract(ref.path)

    text, offsets = normalize_with_offsets(extracted.text)
    if not offsets:
        raise UnparseableSource(
            f"{ref.filename} normalized to text with no paragraphs; nothing is citable"
        )

    rendition = Rendition.freeze(
        doc_id=ref.doc_id,
        student_id=ref.student_id,
        text=text,
        paragraphs=offsets,
        source_projection=extracted.projection,
        source_filename=ref.filename,
        source_kind=extracted.kind,
    )
    registry = SpanRegistry.build(rendition.rendition_id, rendition.doc_id, text, offsets)

    # Assert the registry agrees with the rendition before anything downstream trusts it.
    # If these disagree, offsets are meaningless and every citation resolving through them
    # would point at text nobody wrote. Cheap to check once; impossible to notice later.
    for span in registry.spans.values():
        if not span.verify_against(text):
            raise RuntimeError(
                f"span {span.span_id} does not hash to its slice of rendition "
                f"{rendition.rendition_id[:12]}…; the registry and the rendition diverged "
                f"at construction time"
            )

    return FrozenSubmission(ref=ref, rendition=rendition, registry=registry)
