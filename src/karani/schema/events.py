"""The append-only event log — the one thing every artifact is folded from.

Two properties are doing all the work here.

**Event IDs are deterministic**, derived from `(run_id, step, item_id, attempt)` rather than
generated. A worker that is retried at the same attempt number computes the same ID, so the
write is idempotent by construction instead of by a dedupe pass that has to be trusted. This
is also why the response cache must be durable and shared rather than in-process: the
retried worker has to regenerate byte-identical content for the collision check to conclude
"same event" rather than "two different events fighting over one ID".

**Writes are `create()`-only.** Not by convention — by a custom IAM role that grants `create`
and `get` and withholds `update` and `delete`, plus Firestore rules for the browser path. The
log cannot be rewritten by the pipeline that produces it, which is what makes it evidence
rather than a report.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from karani.canon import content_hash, sha256_text


class Step(StrEnum):
    """Every event type, and the only ones that exist.

    Declared as a closed enum rather than free strings so that an event type invented at a
    call site is a validation error rather than a silent new category that `render()` then
    ignores — a fold that silently skips an unknown event produces an artifact that is
    quietly missing something, which is the worst available failure mode for a log whose
    purpose is completeness.
    """

    RUN_STARTED = "RunStarted"
    SUBMISSION_INGESTED = "SubmissionIngested"
    RENDITION_FROZEN = "RenditionFrozen"
    TRIAGE_DECIDED = "TriageDecided"
    ARMOR_SCANNED = "ArmorScanned"
    INJECTION_DETECTED = "InjectionDetected"
    OBSERVATION_DRAFTED = "ObservationDrafted"
    OBSERVATION_REJECTED = "ObservationRejected"
    OBSERVATION_ACCEPTED = "ObservationAccepted"
    NO_EVIDENCE_RECORDED = "NoEvidenceRecorded"
    NEEDS_HUMAN_REVIEW = "NeedsHumanReview"
    TASK_FAILED = "TaskFailed"
    TASK_ABANDONED = "TaskAbandoned"
    OBSERVATION_EDITED_BY_HUMAN = "ObservationEditedByHuman"
    RENDER_COMPLETED = "RenderCompleted"
    ARTIFACT_DELIVERED = "ArtifactDelivered"
    RUN_ABORTED = "RunAborted"


# The fold's total order. `render()` must produce byte-identical output from a shuffled log
# (KAR-103), so it cannot depend on arrival order, and it cannot depend on timestamps either:
# two events written in the same millisecond by parallel workers would tie, and a tie broken
# by chance is a byte-unstable render. Ordering is therefore derived purely from content —
# this rank, then item, then attempt, then the deterministic ID as the final tiebreak.
STEP_RANK: dict[Step, int] = {
    Step.RUN_STARTED: 0,
    Step.SUBMISSION_INGESTED: 10,
    Step.RENDITION_FROZEN: 20,
    Step.TRIAGE_DECIDED: 30,
    Step.ARMOR_SCANNED: 40,
    Step.INJECTION_DETECTED: 50,
    Step.OBSERVATION_DRAFTED: 60,
    Step.OBSERVATION_REJECTED: 70,
    Step.OBSERVATION_ACCEPTED: 80,
    Step.NO_EVIDENCE_RECORDED: 90,
    Step.NEEDS_HUMAN_REVIEW: 100,
    Step.TASK_FAILED: 110,
    Step.TASK_ABANDONED: 120,
    Step.OBSERVATION_EDITED_BY_HUMAN: 130,
    Step.RENDER_COMPLETED: 140,
    Step.ARTIFACT_DELIVERED: 150,
    Step.RUN_ABORTED: 160,
}

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]")
_MAX_ID_LEN = 400


def make_event_id(run_id: str, step: Step, item_id: str, attempt: int) -> str:
    """Derive the event's identity from what it is, not from when it was written.

    Kept human-readable where possible, because these IDs show up in the docket, in the
    anomaly queue, and on camera; an opaque hash would make the demo harder to follow for no
    gain. Long item IDs fall back to a hash suffix so the result stays a legal Firestore
    document ID.
    """
    safe_item = _UNSAFE.sub("_", item_id)
    candidate = f"{step.value}~{safe_item}~a{attempt}"
    if len(candidate.encode("utf-8")) > _MAX_ID_LEN:
        digest = sha256_text(f"{run_id}|{step.value}|{item_id}|{attempt}")[:32]
        candidate = f"{step.value}~{digest}~a{attempt}"
    return candidate


class Event(BaseModel):
    """One immutable fact about one run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    run_id: str
    step: Step
    item_id: str
    attempt: int = Field(default=0, ge=0)
    ts: datetime
    payload: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        run_id: str,
        step: Step,
        item_id: str,
        ts: datetime,
        attempt: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> Event:
        return cls(
            event_id=make_event_id(run_id, step, item_id, attempt),
            run_id=run_id,
            step=step,
            item_id=item_id,
            attempt=attempt,
            ts=ts,
            payload=payload or {},
        )

    @property
    def content_hash(self) -> str:
        """Identity of the event's *content*, excluding its timestamp.

        The timestamp is deliberately excluded. A worker retried at the same attempt number
        is the same logical event even though the clock moved between the two writes; if `ts`
        participated, every legitimate idempotent retry would raise `EventIdCollision` and
        the collision check would become noise that operators learn to ignore.
        """
        return content_hash(
            {
                "run_id": self.run_id,
                "step": self.step.value,
                "item_id": self.item_id,
                "attempt": self.attempt,
                "payload": self.payload,
            }
        )

    @property
    def sort_key(self) -> tuple[int, str, int, str]:
        return (STEP_RANK[self.step], self.item_id, self.attempt, self.event_id)


class EventIdCollision(RuntimeError):
    """Two different payloads claimed one deterministic event ID.

    This is never recovered from and never silently deduped. The IDs are derived from
    `(run_id, step, item_id, attempt)`, so a collision with differing content means two
    genuinely different facts believe they are the same fact — which makes every artifact
    folded from this log unsound. Failing loudly here is the only honest option; the
    alternative is an evidence sheet that is wrong in a way nobody can see.
    """

    def __init__(self, event_id: str, existing_hash: str, incoming_hash: str) -> None:
        super().__init__(
            f"EventIdCollision on {event_id!r}: an event already exists under this "
            f"deterministic ID with content hash {existing_hash[:12]}…, and the incoming "
            f"write has content hash {incoming_hash[:12]}…. These are different facts "
            f"claiming one identity. Not deduping."
        )
        self.event_id = event_id
        self.existing_hash = existing_hash
        self.incoming_hash = incoming_hash
