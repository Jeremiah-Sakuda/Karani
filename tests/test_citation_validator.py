"""KAR-104 — the citation validator.

Every test here states the property it proves before it proves it. The question to ask of
any of them is the one PRD §4 asks: *could this go green with the property false?*
"""

from __future__ import annotations

import pytest

from karani.canon import sha256_text
from karani.schema.observation import Citation
from karani.validate.citation import Layer, build_citation, validate_citation

from .factories import SHARED_PHRASE, demo_rendition, misattributed_citation


@pytest.fixture
def rendition_and_registry():
    return demo_rendition()


def test_honest_citation_is_accepted(rendition_and_registry):
    """Property: a citation that names a real span and quotes it at the location it claims
    passes all three deterministic layers.

    Without this the suite could pass by rejecting everything, which would satisfy every
    other test in this file while making the system useless.
    """
    rendition, registry = rendition_and_registry
    citation = build_citation(
        span_id="sp-0012",
        quote=SHARED_PHRASE,
        registry=registry,
        rendition_text=rendition.text,
    )

    result = validate_citation(citation, registry=registry, rendition_text=rendition.text)

    assert result.ok
    assert result.verification.referential is True
    assert result.verification.quote_check is True
    assert result.verification.positional is True


def test_fabricated_span_id_is_rejected(rendition_and_registry):
    """Property: a citation can only name a span minted at ingest.

    The span vocabulary is closed. A model that invents `sp-9999` is not making a debatable
    claim about the text — it is naming something that does not exist, and set membership
    settles it without judgement.
    """
    rendition, registry = rendition_and_registry
    quote = SHARED_PHRASE
    citation = Citation(
        span_id="sp-9999",
        quote=quote,
        quote_hash=sha256_text(quote),
        prefix="",
        suffix="",
    )

    result = validate_citation(citation, registry=registry, rendition_text=rendition.text)

    assert not result.ok
    assert result.failed_layer is Layer.REFERENTIAL
    assert result.verification.referential is False


def test_real_span_with_wrong_quote_is_rejected(rendition_and_registry):
    """Property: the quoted text must actually occur in the span being cited.

    This is the case where the span is real and the quotation is invented — the most common
    shape of a fabricated citation, and the one a reader is least likely to check.
    """
    rendition, registry = rendition_and_registry
    quote = "a sentence that appears nowhere in this document"
    citation = Citation(
        span_id="sp-0012",
        quote=quote,
        quote_hash=sha256_text(quote),
        prefix="",
        suffix="",
    )

    result = validate_citation(citation, registry=registry, rendition_text=rendition.text)

    assert not result.ok
    assert result.failed_layer is Layer.QUOTE
    assert result.verification.referential is True
    assert result.verification.quote_check is False


def test_misattribution_across_spans_sharing_a_phrase_is_rejected(rendition_and_registry):
    """Property: a citation must point at the location the quote was actually taken from —
    not merely at *a* location where the phrase happens to occur.

    This is the PRD's named fixture, constructed exactly: a real quote lifted from span 12,
    attributed to span 47, where the identical phrase genuinely occurs in both.

    Why this cannot go green with the property false: the first two layers are *satisfied*
    by this input. Span 47 is in the registry, so referential membership passes. The phrase
    is genuinely present in span 47's text, so containment passes. A validator built from
    membership and containment alone — which is what "check the citation exists" usually
    means — accepts this citation and points an instructor at the wrong paragraph, in a
    document where paragraph 12 concedes a point and paragraph 47 reverses it.

    Only positional identity separates them, and only because the citation carries the
    context it saw at the source.
    """
    rendition, registry = rendition_and_registry

    # Both preconditions of the fixture, asserted rather than assumed. If a future edit to
    # the demo rendition broke either one, this test would still pass while no longer
    # testing anything.
    span_12 = registry.get("sp-0012")
    span_47 = registry.get("sp-0047")
    assert span_12 is not None and span_47 is not None
    assert SHARED_PHRASE in span_12.text_from(rendition.text)
    assert SHARED_PHRASE in span_47.text_from(rendition.text)

    citation = misattributed_citation(registry, rendition.text)
    assert citation.span_id == "sp-0047"

    result = validate_citation(citation, registry=registry, rendition_text=rendition.text)

    assert not result.ok, "misattributed citation was accepted"
    assert result.failed_layer is Layer.POSITIONAL
    assert result.verification.referential is True, "referential layer should have passed"
    assert result.verification.quote_check is True, "quote layer should have passed"
    assert result.verification.positional is False


def test_correct_attribution_of_the_same_phrase_is_accepted(rendition_and_registry):
    """Property: the positional check rejects misattribution without rejecting the phrase.

    The complement of the test above, and the one that keeps it honest. The same repeated
    phrase, cited correctly against each of the two spans it occurs in, must be accepted
    both times. A validator that rejected any repeated phrase would pass the misattribution
    test for entirely the wrong reason.
    """
    rendition, registry = rendition_and_registry

    for span_id in ("sp-0012", "sp-0047"):
        citation = build_citation(
            span_id=span_id,
            quote=SHARED_PHRASE,
            registry=registry,
            rendition_text=rendition.text,
        )
        result = validate_citation(citation, registry=registry, rendition_text=rendition.text)
        assert result.ok, f"honest citation of {span_id} was rejected"


def test_tampered_quote_hash_is_rejected(rendition_and_registry):
    """Property: the quote and its hash travel together and are checked against each other.

    Cheap, and it closes the gap where a payload is edited in transit or in storage and the
    quote no longer matches what was validated.
    """
    rendition, registry = rendition_and_registry
    honest = build_citation(
        span_id="sp-0012", quote=SHARED_PHRASE, registry=registry, rendition_text=rendition.text
    )

    # Constructed via model_construct: the schema's own validator would reject this at
    # construction time, which is the point — this asserts the *validator* also catches it,
    # so the guarantee does not depend on the object having been built through the schema.
    tampered = Citation.model_construct(
        span_id=honest.span_id,
        quote="a different quote entirely",
        quote_hash=honest.quote_hash,
        prefix=honest.prefix,
        suffix=honest.suffix,
    )

    result = validate_citation(tampered, registry=registry, rendition_text=rendition.text)
    assert not result.ok
    assert result.failed_layer is Layer.QUOTE


def test_doc_only_anchor_records_positional_as_not_run(rendition_and_registry):
    """Property: an anchor that cannot be verified positionally is recorded as unverified,
    never as verified.

    A page-image projection has no character offsets. The honest outcome is `None` — not
    run — which is what makes the docket render an honesty chip instead of a highlight it
    cannot place. `False` would read as "checked and failed"; `True` would be a lie.
    """
    rendition, registry = rendition_and_registry
    citation = build_citation(
        span_id="sp-0012", quote=SHARED_PHRASE, registry=registry, rendition_text=rendition.text
    )

    result = validate_citation(
        citation,
        registry=registry,
        rendition_text=rendition.text,
        anchor_confidence="doc_only",
    )

    assert result.ok
    assert result.verification.positional is None
