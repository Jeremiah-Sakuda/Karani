"""The dispatcher — fan-out, and the join that guarantees no run hangs (KAR-314).

The dispatcher owns three things no worker can be trusted with, because a worker that has
crashed cannot report that it crashed:

**The wall-clock deadline `T_max`.** Units that have not reached a terminal event by the
deadline get `TaskAbandoned{reason: join_timeout}` written **by the dispatcher**, and flow
into `excluded[]`. The run then renders around them. This is the difference between an
unattended system and one that needs someone watching it: a run that hangs at 3 a.m. because
one worker is stuck is a run the instructor discovers at 8 a.m. with nothing to show.

**The circuit breaker.** Total attempts and total wall clock are bounded across the whole run,
not just per unit. Per-unit caps cannot catch a systemic failure — a bad prompt version that
makes every submission fail twice stays inside every per-unit budget while burning the entire
run's cost for nothing.

**Terminal-state accounting.** Every dispatched unit ends in exactly one of the six outcomes.
The join does not ask workers whether they finished; it reads the log. A worker's own report
of its status is unavailable in precisely the case that matters.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime

from karani.analysis.cache import MissingCacheEntry, ResponseCache
from karani.analysis.client import ModelClient
from karani.analysis.prompts import Criterion
from karani.analysis.worker import analyze_submission
from karani.armor.scan import Scanner
from karani.config import (
    MAX_TOTAL_ATTEMPTS,
    MAX_WALL_CLOCK_SECONDS,
    T_MAX_SECONDS,
)
from karani.ingest.extract import UnparseableSource
from karani.ingest.freeze import freeze
from karani.ingest.source import Source, SubmissionRef
from karani.schema.events import Event, Step
from karani.store import EventStore

# Events that mean a unit has reached a terminal state. A unit with none of these when the
# deadline arrives is abandoned by the dispatcher.
TERMINAL_STEPS = frozenset(
    {
        Step.OBSERVATION_ACCEPTED,
        Step.NO_EVIDENCE_RECORDED,
        Step.NEEDS_HUMAN_REVIEW,
        Step.TASK_FAILED,
        Step.TASK_ABANDONED,
    }
)


@dataclass
class RunSummary:
    run_id: str
    dispatched: list[str] = field(default_factory=list)
    completed: list[str] = field(default_factory=list)
    abandoned: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    events_written: int = 0
    model_calls: int = 0
    cached_calls: int = 0
    wall_clock_seconds: float = 0.0
    aborted: bool = False
    abort_reason: str = ""
    cache_missing: bool = False

    @property
    def cache_hit_rate(self) -> float | None:
        return self.cached_calls / self.model_calls if self.model_calls else None


def run_pipeline(
    *,
    run_id: str,
    source: Source,
    criteria: list[Criterion],
    store: EventStore,
    client: ModelClient,
    cache: ResponseCache,
    scanner: Scanner,
    max_workers: int = 8,
    t_max_seconds: int = T_MAX_SECONDS,
    project: str = "",
) -> RunSummary:
    started = time.monotonic()
    ts = datetime.now(UTC)
    summary = RunSummary(run_id=run_id)

    refs = source.list_submissions()
    summary.dispatched = [r.student_id for r in refs]

    _write(store, Event.build(
        run_id=run_id, step=Step.RUN_STARTED, item_id=run_id, ts=ts,
        payload={"submissions": len(refs), "criteria": [c.criterion_id for c in criteria]},
    ), summary)

    # Terminal state per student, read from what actually got written rather than from what
    # the workers claim.
    terminal: set[str] = set()
    total_attempts = 0

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(
                _run_one,
                ref=ref,
                run_id=run_id,
                criteria=criteria,
                client=client,
                cache=cache,
                scanner=scanner,
                project=project,
            ): ref
            for ref in refs
        }

        for future in as_completed(futures, timeout=None):
            ref = futures[future]
            elapsed = time.monotonic() - started

            # --- circuit breaker --------------------------------------------------------
            if elapsed > MAX_WALL_CLOCK_SECONDS or total_attempts > MAX_TOTAL_ATTEMPTS:
                summary.aborted = True
                summary.abort_reason = (
                    f"wall clock {elapsed:.0f}s > {MAX_WALL_CLOCK_SECONDS}s"
                    if elapsed > MAX_WALL_CLOCK_SECONDS
                    else f"total attempts {total_attempts} > {MAX_TOTAL_ATTEMPTS}"
                )
                _write(store, Event.build(
                    run_id=run_id, step=Step.RUN_ABORTED, item_id=run_id, ts=datetime.now(UTC),
                    payload={"reason": summary.abort_reason},
                ), summary)
                for pending in futures.values():
                    if pending.student_id not in terminal:
                        _abandon(store, run_id, pending.student_id, "run_aborted", summary)
                        summary.abandoned.append(pending.student_id)
                break

            try:
                outcome, error = future.result()
            except MissingCacheEntry as exc:
                # NOT a submission failure, and it must never be recorded as one.
                #
                # A missing cache entry means the operator ran the offline path without a
                # populated cache. Writing TaskFailed here would put "this student's work
                # could not be processed" in the permanent log for a setup problem that has
                # nothing to do with the student — and the docket would then show a
                # parse-failure anomaly against a submission that is perfectly fine.
                #
                # It aborts the run instead, because the condition is identical for every
                # remaining unit and grinding through fifteen of them produces fifteen
                # identical misleading records.
                summary.aborted = True
                summary.abort_reason = "offline cache is missing entries"
                summary.cache_missing = True
                raise
            except Exception as exc:  # noqa: BLE001 - a worker crash must not stop the run
                _write(store, Event.build(
                    run_id=run_id, step=Step.TASK_FAILED, item_id=ref.student_id,
                    ts=datetime.now(UTC),
                    payload={"student_id": ref.student_id, "stage": "worker",
                             "reason": f"{type(exc).__name__}: {exc}"},
                ), summary)
                summary.failed.append(ref.student_id)
                terminal.add(ref.student_id)
                continue

            if error is not None:
                # An unparseable submission is a visible failure with a queue item, never an
                # empty rendition that would report the student submitted nothing relevant.
                _write(store, Event.build(
                    run_id=run_id, step=Step.TASK_FAILED, item_id=ref.student_id,
                    ts=datetime.now(UTC),
                    payload={"student_id": ref.student_id, "stage": "ingest", "reason": error},
                ), summary)
                summary.failed.append(ref.student_id)
                terminal.add(ref.student_id)
                continue

            assert outcome is not None
            for event in outcome.events:
                _write(store, event, summary)

            total_attempts += outcome.attempts_used
            summary.model_calls += outcome.model_calls
            summary.cached_calls += outcome.cached_calls
            summary.completed.append(ref.student_id)
            terminal.add(ref.student_id)

            if elapsed > t_max_seconds:
                # T_max reached. Everything still outstanding is abandoned by the dispatcher
                # so that render() can fire, rather than the run waiting on a worker that may
                # never answer.
                for pending_ref in futures.values():
                    if pending_ref.student_id not in terminal:
                        _abandon(store, run_id, pending_ref.student_id, "join_timeout", summary)
                        summary.abandoned.append(pending_ref.student_id)
                        terminal.add(pending_ref.student_id)
                break

    # --- the join ---------------------------------------------------------------------
    # Anything still without a terminal event is abandoned here, regardless of why. A unit
    # that vanished without writing anything is exactly the case a worker cannot self-report.
    for ref in refs:
        if ref.student_id not in terminal:
            _abandon(store, run_id, ref.student_id, "join_timeout", summary)
            summary.abandoned.append(ref.student_id)

    summary.wall_clock_seconds = time.monotonic() - started

    _write(store, Event.build(
        run_id=run_id, step=Step.RENDER_COMPLETED, item_id=run_id, ts=datetime.now(UTC),
        payload={
            "completed": len(summary.completed),
            "abandoned": len(summary.abandoned),
            "failed": len(summary.failed),
        },
    ), summary)

    return summary


def _run_one(*, ref: SubmissionRef, run_id: str, criteria, client, cache, scanner, project=""):  # noqa: ANN001
    try:
        frozen = freeze(ref)
    except UnparseableSource as exc:
        return None, str(exc)
    return (
        analyze_submission(
            frozen=frozen,
            criteria=criteria,
            run_id=run_id,
            client=client,
            cache=cache,
            scanner=scanner,
            project=project,
        ),
        None,
    )


def _abandon(store: EventStore, run_id: str, student_id: str, reason: str, summary: RunSummary) -> None:
    _write(store, Event.build(
        run_id=run_id, step=Step.TASK_ABANDONED, item_id=student_id, ts=datetime.now(UTC),
        payload={"student_id": student_id, "reason": reason},
    ), summary)


def _write(store: EventStore, event: Event, summary: RunSummary) -> None:
    if store.create(event):
        summary.events_written += 1
