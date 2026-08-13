"""The citation validator (KAR-104).

Four layers, cheapest and most decisive first. Three of them are here; the fourth
(entailment) is a model call and lives in `karani.validate.entailment`, because a
deterministic check that can reject a citation should never wait on a model to do it.

    1. Referential  — is this span_id in the registry at all?   set membership
    2. Quote        — does this text actually appear in that span?  string containment
    3. Positional   — does it appear *at the place the citation claims*?  context identity
    4. Entailment   — does the span actually support the claim?   (separate module)

Layer 3 is the one that earns its keep, and it is worth being explicit about why, because it
looks redundant next to layer 2.

Consider the misattribution case the acceptance criterion demands: a quote genuinely lifted
from span 12, attributed to span 47, where the phrase occurs in *both* spans. Layer 1 passes:
span 47 is real. Layer 2 passes: the phrase is genuinely present in span 47. A validator built
from membership and containment alone accepts a citation that points at the wrong passage,
and it does so on a document where the two passages may make opposite arguments.

What separates them is not the quote. It is what surrounds the quote. So a citation carries
`prefix` and `suffix` — the characters immediately before and after the quote *at the source
location* — and layer 3 recomputes both from the frozen rendition at the offset the citation
claims, and requires them to match. A quote taken from span 12 arrives carrying span 12's
neighbourhood, and span 47's neighbourhood is different, so the citation is rejected.

**The honest boundary.** If a phrase occurs twice with *identical* 32-character context on
both sides, layer 3 cannot separate the two occurrences, and neither could a careful human
reader working from the same evidence. In that case the two locations are genuinely
interchangeable for the purpose of the claim. This is stated rather than hidden, and it is
why entailment exists as a layer above.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from karani.canon import sha256_text
from karani.config import CONTEXT_CHARS
from karani.schema.observation import Citation, Observation, Verification
from karani.schema.spans import SpanRegistry


class Layer(StrEnum):
    REFERENTIAL = "referential"
    QUOTE = "quote_check"
    POSITIONAL = "positional"


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    verification: Verification
    failed_layer: Layer | None = None
    # Fed back to the analyst worker on a reject. Says what was wrong specifically enough to
    # be actionable, and never suggests a correction: a validator that proposes the fix is
    # writing the observation, which would make the whole check circular.
    feedback: str = ""

    @property
    def rejection_reason(self) -> str:
        return "" if self.ok else f"{self.failed_layer}: {self.feedback}"


def context_around(text: str, start: int, end: int, width: int = CONTEXT_CHARS) -> tuple[str, str]:
    """The `width` characters on each side of `text[start:end]`.

    Truncated rather than padded at document boundaries: a quote opening a document has a
    shorter prefix, and inventing padding would make two different positions compare equal.
    """
    return text[max(0, start - width) : start], text[end : end + width]


def validate_citation(
    citation: Citation,
    *,
    registry: SpanRegistry,
    rendition_text: str,
    anchor_confidence: str = "exact",
) -> ValidationResult:
    # --- Layer 1: referential ----------------------------------------------------------
    # Set membership against a vocabulary minted at ingest. A model cannot invent a span
    # here; it can only name one that already exists or fail this check.
    span = registry.get(citation.span_id)
    if span is None:
        return ValidationResult(
            ok=False,
            verification=Verification(referential=False),
            failed_layer=Layer.REFERENTIAL,
            feedback=(
                f"span_id {citation.span_id!r} is not in the span registry for this "
                f"rendition. Cite only span IDs that appear in the text you were given."
            ),
        )

    span_text = span.text_from(rendition_text)

    # The registry and the rendition must agree before anything downstream is meaningful.
    # If they do not, offsets are untrustworthy and every citation resolving through them is
    # suspect, so this fails the citation rather than proceeding on bad data.
    if sha256_text(span_text) != span.sha256:
        return ValidationResult(
            ok=False,
            verification=Verification(referential=False),
            failed_layer=Layer.REFERENTIAL,
            feedback=(
                f"span {span.span_id} does not hash to its registered value; the registry "
                f"and the rendition have diverged and no citation through it can be trusted"
            ),
        )

    # --- Layer 2: quote ----------------------------------------------------------------
    if sha256_text(citation.quote) != citation.quote_hash:
        return ValidationResult(
            ok=False,
            verification=Verification(referential=True, quote_check=False),
            failed_layer=Layer.QUOTE,
            feedback="quote_hash does not hash the accompanying quote",
        )

    if citation.quote not in span_text:
        return ValidationResult(
            ok=False,
            verification=Verification(referential=True, quote_check=False),
            failed_layer=Layer.QUOTE,
            feedback=(
                f"the quoted text does not occur in span {span.span_id}. Quote verbatim "
                f"from the span you are citing."
            ),
        )

    # --- Layer 3: positional identity --------------------------------------------------
    if anchor_confidence == "doc_only":
        # A page-image projection has no character offsets to anchor to. Rather than
        # fabricate a position, the citation is accepted at document granularity and the
        # viewer renders an honesty chip instead of a highlight. Recorded as `None` — not
        # run — never as `True`.
        return ValidationResult(
            ok=True,
            verification=Verification(referential=True, quote_check=True, positional=None),
        )

    matched = False
    offset = span_text.find(citation.quote)
    while offset != -1:
        abs_start = span.char_start + offset
        abs_end = abs_start + len(citation.quote)
        prefix, suffix = context_around(rendition_text, abs_start, abs_end)
        if prefix == citation.prefix and suffix == citation.suffix:
            matched = True
            break
        # The phrase may legitimately occur more than once inside one span. Every occurrence
        # gets checked; one match is enough.
        offset = span_text.find(citation.quote, offset + 1)

    if not matched:
        return ValidationResult(
            ok=False,
            verification=Verification(referential=True, quote_check=True, positional=False),
            failed_layer=Layer.POSITIONAL,
            feedback=(
                f"the quote occurs in span {span.span_id}, but not with the surrounding "
                f"context this citation reports. The quote appears to have been taken from "
                f"a different location than the one cited."
            ),
        )

    return ValidationResult(
        ok=True,
        verification=Verification(referential=True, quote_check=True, positional=True),
    )


def validate_observation(
    observation: Observation,
    *,
    registry: SpanRegistry,
    rendition_text: str,
) -> ValidationResult:
    """Validate one observation, including the cited-XOR-no_evidence rule.

    `no_evidence` observations are valid without any citation check and — critically — are
    never retried (KAR-308). Absence is a finding, not a failure to find, and routing it into
    the retry loop would pressure the next attempt to produce a citation for something that
    genuinely is not there. That pressure is exactly how fabrication happens, and excluding
    absence from retry is what makes the attempt cap survivable.
    """
    if observation.kind == "no_evidence":
        return ValidationResult(ok=True, verification=Verification(referential=None, quote_check=None))

    assert observation.citation is not None  # guaranteed by the schema's model_validator
    return validate_citation(
        observation.citation,
        registry=registry,
        rendition_text=rendition_text,
        anchor_confidence=observation.anchor_confidence,
    )


def build_citation(
    *,
    span_id: str,
    quote: str,
    registry: SpanRegistry,
    rendition_text: str,
) -> Citation:
    """Construct a citation whose prefix/suffix are read from the rendition.

    Used by fixtures, tests, and the appeal-packet exporter — never on the analysis path.
    On the analysis path the model supplies the context it actually saw, and the validator
    checks it; if Karani computed the context itself from the span the model named, layer 3
    would be comparing the rendition against itself and would pass unconditionally.
    """
    span = registry.get(span_id)
    if span is None:
        raise KeyError(f"span {span_id!r} is not in the registry")
    span_text = span.text_from(rendition_text)
    offset = span_text.find(quote)
    if offset == -1:
        raise ValueError(f"quote does not occur in span {span_id!r}")
    abs_start = span.char_start + offset
    prefix, suffix = context_around(rendition_text, abs_start, abs_start + len(quote))
    return Citation(
        span_id=span_id,
        quote=quote,
        quote_hash=sha256_text(quote),
        prefix=prefix,
        suffix=suffix,
    )
