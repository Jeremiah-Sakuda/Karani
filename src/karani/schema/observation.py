"""The observation — Karani's only claim record, and the place the central invariant lives.

Read the field list for what is *absent*. There is no score, no rank, no percentile, no
`meets`/`exceeds`/`below` enum, no letter, no numeric quality field of any kind, and no
`extraction_confidence` float. This is not an omission to be filled in later; it is the
product. When the public challenge box (KAR-412) says *"there is no field for what you
asked for,"* this class is the thing it is pointing at.

`extra="forbid"` is load-bearing for that claim. Without it, a downstream caller could
attach `score=0.8` to an observation at runtime and the schema would shrug. With it, the
absence is enforced at every construction site rather than merely documented here.

The one number on this record is `attempts`, and it describes the system's own bookkeeping —
how many times *Karani* tried — never the submission's quality. That distinction is the
whole line between a process field and a verdict in costume.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from karani.canon import sha256_text

Kind = Literal["evidence", "no_evidence"]
AnchorConfidence = Literal["exact", "fuzzy", "doc_only"]
SourceProjection = Literal["text", "docx", "pdf_text", "pdf_image", "unparseable"]

# Field names that would turn an observation into a verdict. Asserted by a test against the
# model's actual field set, so adding one is a test failure rather than a review comment.
BANNED_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "score",
        "grade",
        "rank",
        "rating",
        "percentile",
        "points",
        "mark",
        "marks",
        "level",
        "tier",
        "band",
        "quality",
        "assessment",
        "verdict",
        "judgement",
        "judgment",
        "meets",
        "exceeds",
        "below",
        "proficiency",
        "mastery",
        "extraction_confidence",
        "confidence",
        "letter_grade",
        "gpa",
        "weight",
    }
)


class Citation(BaseModel):
    """A pointer into the closed span vocabulary, carrying its own positional identity.

    `prefix` and `suffix` are the mechanism, not metadata. A quote can genuinely occur in
    two different spans of the same document; "is this phrase present in span 47" therefore
    cannot distinguish a correct citation from a misattributed one. What surrounds the quote
    can. The validator recomputes both from the rendition and requires them to match at the
    exact offset the citation claims — see `karani.validate.citation`.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    span_id: str = Field(pattern=r"^sp-\d{4}$")
    quote: str = Field(min_length=1)
    quote_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    prefix: str
    suffix: str

    @model_validator(mode="after")
    def _hash_matches(self) -> Citation:
        if sha256_text(self.quote) != self.quote_hash:
            raise ValueError("quote_hash does not hash the quote it accompanies")
        return self


class Provenance(BaseModel):
    """What produced this observation. Mandatory, and mandatory *now*.

    Retrofitting provenance after the analysis phase means re-running every fixture, which
    is why KAR-101 insists it lands with the first schema rather than when it first feels
    necessary.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    temperature: float
    ts: datetime


class Verification(BaseModel):
    """What each validation layer concluded.

    `None` means "not run", which is different from `False` meaning "run and failed". An
    entailment check that never executed must never be readable as one that passed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    referential: bool | None = None
    positional: bool | None = None
    quote_check: bool | None = None
    entailment: bool | None = None
    # Layer 5 (KAR-417): the cross-family second reader. None = not run -- the deployed
    # nightly job has no local Gemma and records exactly that. Never readable as a pass.
    second_reader: bool | None = None


class Review(BaseModel):
    """An instructor's edit. Edits supersede; they never mutate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reviewer_id: str
    edit_reason: str
    ts: datetime


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation_id: str
    run_id: str
    student_id: str
    criterion_id: str

    kind: Kind
    text: str

    # Null if and only if kind == "no_evidence". Enforced below, in both directions.
    citation: Citation | None = None

    # Populated only for no_evidence: a note about *the search*, never about the work.
    # "No passage addressing this criterion was located" is a claim about what Karani
    # found. "The student did not address this criterion" would be a verdict, and is
    # exactly the sentence this field exists to keep out of the system.
    search_notes: str | None = None

    anchor_confidence: AnchorConfidence = "exact"
    supersedes: str | None = None
    review: Review | None = None

    provenance: Provenance
    verification: Verification = Field(default_factory=Verification)

    attempts: int = Field(default=1, ge=1)
    created_at: datetime
    source_projection: SourceProjection = "text"

    # Set by the anomaly router, not by any model. A flagged observation still renders.
    needs_human: bool = False
    needs_human_reason: str | None = None

    @model_validator(mode="after")
    def _cited_xor_no_evidence(self) -> Observation:
        """The rule that makes absence first-class: cited XOR no_evidence.

        Both halves matter. An `evidence` observation without a citation is an uncited
        claim, which is the failure mode this entire system exists to prevent. A
        `no_evidence` observation *with* a citation is subtler and worse: it would let a
        finding of absence smuggle in a pointer, and absence is the one outcome that is
        deliberately excluded from the retry loop (KAR-308). If it could carry a citation,
        it could be retried into one.
        """
        if self.kind == "evidence" and self.citation is None:
            raise ValueError(
                "an 'evidence' observation must carry a citation; "
                "an uncited claim is the thing this schema exists to reject"
            )
        if self.kind == "no_evidence" and self.citation is not None:
            raise ValueError("a 'no_evidence' observation must not carry a citation")
        if self.kind == "no_evidence" and not self.search_notes:
            raise ValueError(
                "a 'no_evidence' observation must record search_notes — a claim about the "
                "search that was performed, never about the work"
            )
        return self

    @classmethod
    def banned_fields_present(cls) -> set[str]:
        """Any verdict-shaped field that has crept onto the schema. Asserted by a test."""
        return set(cls.model_fields) & BANNED_FIELD_NAMES
