"""The span registry — the closed vocabulary of things a citation is allowed to point at.

This is the mechanism the whole citation-identity argument rests on. Spans are minted once,
at ingest, from the frozen rendition. Nothing later in the pipeline can create one. An
analyst worker that wants to cite something can only name a span that already exists, so
"did the model make this citation up?" reduces to a set-membership test rather than a
judgement call.

This is also why there is no vector database (PRD §1.4). Chunk retrieval would hand the
model a *subset* of the spans and then ask it to be exhaustive, which manufactures both
false `no_evidence` and pressure to fabricate. Whole-document context is not a convenience
here; it is the enabling condition for a closed vocabulary.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from karani.canon import sha256_text


class Span(BaseModel):
    """One citable region of a frozen rendition.

    Offsets are character offsets into the rendition's normalized text, never into the
    source file. The source file may be edited, moved, or deleted after ingest without
    changing anything a citation resolves to.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    span_id: str = Field(pattern=r"^sp-\d{4}$")
    rendition_id: str
    doc_id: str
    para_index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def _ordered(self) -> Span:
        if self.char_end <= self.char_start:
            raise ValueError(
                f"{self.span_id}: char_end ({self.char_end}) must exceed "
                f"char_start ({self.char_start}); an empty span is not citable"
            )
        return self

    def text_from(self, rendition_text: str) -> str:
        return rendition_text[self.char_start : self.char_end]

    def verify_against(self, rendition_text: str) -> bool:
        """KAR-305's property: a span's hash matches the rendition slice it names.

        If this returns False the registry and the rendition have diverged, which means a
        citation could resolve to text that is not the text the model saw. There is no
        recovery from that and no partial credit for it.
        """
        return sha256_text(self.text_from(rendition_text)) == self.sha256


class SpanRegistry(BaseModel):
    """Every span of one rendition. Immutable once built."""

    model_config = ConfigDict(extra="forbid")

    rendition_id: str
    spans: dict[str, Span]

    @classmethod
    def build(cls, rendition_id: str, doc_id: str, text: str, paragraphs: list[tuple[int, int]]) -> SpanRegistry:
        """Mint the closed vocabulary from a frozen rendition.

        `paragraphs` is the normalizer's paragraph→offset map: a list of (start, end)
        character offsets. Span IDs are assigned by paragraph order and zero-padded so that
        they sort lexicographically the way a reader expects, which matters because these
        strings appear interleaved in the prompt and in the docket's URLs.
        """
        spans: dict[str, Span] = {}
        for index, (start, end) in enumerate(paragraphs):
            if end <= start:
                continue
            span_id = f"sp-{index:04d}"
            spans[span_id] = Span(
                span_id=span_id,
                rendition_id=rendition_id,
                doc_id=doc_id,
                para_index=index,
                char_start=start,
                char_end=end,
                sha256=sha256_text(text[start:end]),
            )
        return cls(rendition_id=rendition_id, spans=spans)

    def __contains__(self, span_id: object) -> bool:
        return isinstance(span_id, str) and span_id in self.spans

    def get(self, span_id: str) -> Span | None:
        return self.spans.get(span_id)

    def interleaved_text(self, rendition_text: str) -> str:
        """The rendition as the analyst worker sees it, with span IDs inline.

        The model is shown `[[sp-0007]] <paragraph text>` and told it may cite only IDs that
        appear in this text. Interleaving rather than appending a separate index matters:
        the ID is adjacent to the text it names, so citing correctly requires no
        cross-referencing step for the model to get wrong.
        """
        parts: list[str] = []
        for span_id in sorted(self.spans):
            span = self.spans[span_id]
            parts.append(f"[[{span_id}]] {span.text_from(rendition_text)}")
        return "\n\n".join(parts)
