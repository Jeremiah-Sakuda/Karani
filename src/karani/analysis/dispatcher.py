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
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from datetime import UTC, datetime

from karani.analysis.cache import MissingCacheEntry, ResponseCache
from karani.analysis.client import ModelClient
from karani.analysis.prompts import Criterion
from karani.analysis.worker import WorkerOutcome, analyze_submission
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
    threads_outstanding: int = 0

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

    _write(
        store,
        Event.build(
            run_id=run_id,
            step=Step.RUN_STARTED,
            item_id=run_id,
            ts=ts,
            payload={"submissions": len(refs), "criteria": [c.criterion_id for c in criteria]},
        ),
        summary,
    )

    # Terminal state per student, read from what actually got written rather than from what
    # the workers claim.
    terminal: set[str] = set()
    total_attempts = 0

    # NOT a `with` block, deliberately.
    #
    # `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True)`, which blocks until every
    # worker thread finishes -- including the one that is hung. So even after `as_completed`
    # correctly raised at T_max and the dispatcher correctly wrote TaskAbandoned, leaving the
    # `with` block put the wait straight back: the run still took as long as the hung worker.
    # Measured: 30s against a 2s deadline, with the timeout handling working perfectly.
    #
    # Owning the executor lets the deadline mean what it says.
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
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

        # The deadline is passed to `as_completed`, not merely checked inside the loop.
        #
        # This was the defect that falsified the "no run hangs" invariant outright. With
        # `timeout=None`, the loop body only runs when a future *completes*, so a worker
        # blocked forever meant the deadline check was never reached: T_max bounded the time
        # between completions and not the run. Verified before the fix — one worker sleeping
        # 25s against `t_max_seconds=1` returned after 25 seconds, not 1.
        #
        # A hung worker is exactly the case the join exists for, and it was the one case the
        # join could not survive.
        remaining = max(1.0, t_max_seconds - (time.monotonic() - started))
        try:
            completed_iter = as_completed(futures, timeout=remaining)
            for future in completed_iter:
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
                    _write(
                        store,
                        Event.build(
                            run_id=run_id,
                            step=Step.RUN_ABORTED,
                            item_id=run_id,
                            ts=datetime.now(UTC),
                            payload={"reason": summary.abort_reason},
                        ),
                        summary,
                    )
                    for pending in futures.values():
                        if pending.student_id not in terminal:
                            _abandon(store, run_id, pending.student_id, "run_aborted", summary)
                    break

                try:
                    outcome, error = future.result()
                except MissingCacheEntry:
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
                    _write(
                        store,
                        Event.build(
                            run_id=run_id,
                            step=Step.TASK_FAILED,
                            item_id=ref.student_id,
                            ts=datetime.now(UTC),
                            payload={
                                "student_id": ref.student_id,
                                "stage": "worker",
                                "reason": f"{type(exc).__name__}: {exc}",
                            },
                        ),
                        summary,
                    )
                    summary.failed.append(ref.student_id)
                    terminal.add(ref.student_id)
                    continue

                if error is not None:
                    # An unparseable submission is a visible failure with a queue item, never an
                    # empty rendition that would report the student submitted nothing relevant.
                    _write(
                        store,
                        Event.build(
                            run_id=run_id,
                            step=Step.TASK_FAILED,
                            item_id=ref.student_id,
                            ts=datetime.now(UTC),
                            payload={
                                "student_id": ref.student_id,
                                "stage": "ingest",
                                "reason": error,
                            },
                        ),
                        summary,
                    )
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
                            terminal.add(pending_ref.student_id)
                    break

        except FuturesTimeout:
            # T_max reached with work still outstanding. The dispatcher writes TaskAbandoned
            # for every unit that never reached a terminal state, and the run renders around
            # them. A worker that has hung cannot report that it has hung, which is why this
            # is the dispatcher's job and not the worker's.
            for pending_ref in futures.values():
                if pending_ref.student_id not in terminal:
                    _abandon(store, run_id, pending_ref.student_id, "join_timeout", summary)
                    terminal.add(pending_ref.student_id)
            # Do not wait on the hung workers. Python threads are not killable; the run is
            # done regardless, and for a Cloud Run Job the process exits moments later.
            pool.shutdown(wait=False, cancel_futures=True)

        # --- the join ---------------------------------------------------------------------
        # Anything still without a terminal event is abandoned here, regardless of why. A unit
        # that vanished without writing anything is exactly the case a worker cannot self-report.
        for ref in refs:
            if ref.student_id not in terminal:
                _abandon(store, run_id, ref.student_id, "join_timeout", summary)

    finally:
        # Never wait on threads that may never return.
        #
        # Precise about what this does and does not achieve, because an earlier comment here
        # overclaimed: `cancel_futures=True` cancels *pending* futures, and a future that is
        # already RUNNING cannot be cancelled -- Python cannot interrupt a thread from
        # outside it. ThreadPoolExecutor also registers an atexit hook that joins its workers,
        # so a permanently blocked worker holds the interpreter open past every deadline set
        # here.
        #
        # So this bounds the LOGICAL run: TaskAbandoned is written, render() fires, the
        # artifact exists. Bounding the PROCESS is `karani.runtime.hard_exit`, called by the
        # entrypoint once the artifact is durable. It lives there and not here because a
        # library must not kill its host process.
        pool.shutdown(wait=False, cancel_futures=True)

    from karani.runtime import worker_threads_outstanding

    summary.threads_outstanding = len(worker_threads_outstanding())
    summary.wall_clock_seconds = time.monotonic() - started

    _write(
        store,
        Event.build(
            run_id=run_id,
            step=Step.RENDER_COMPLETED,
            item_id=run_id,
            ts=datetime.now(UTC),
            payload={
                "completed": len(summary.completed),
                "abandoned": len(summary.abandoned),
                "failed": len(summary.failed),
            },
        ),
        summary,
    )

    return summary


def _run_one(
    *,
    ref: SubmissionRef,
    run_id: str,
    criteria: list[Criterion],
    client: ModelClient,
    cache: ResponseCache,
    scanner: Scanner,
    project: str = "",
) -> tuple[WorkerOutcome | None, str | None]:
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


def _abandon(
    store: EventStore, run_id: str, student_id: str, reason: str, summary: RunSummary
) -> None:
    """Write TaskAbandoned once per student, ever.

    Calling this twice for one student with different reasons mints the same deterministic
    event ID with different content -- a real EventIdCollision. The store was right to raise;
    the caller was wrong to ask. That crashed the run-level circuit breaker, which is the one
    mechanism whose whole job is to end a run cleanly.
    """
    if student_id in summary.abandoned:
        return
    _write(
        store,
        Event.build(
            run_id=run_id,
            step=Step.TASK_ABANDONED,
            item_id=student_id,
            ts=datetime.now(UTC),
            payload={"student_id": student_id, "reason": reason},
        ),
        summary,
    )
    summary.abandoned.append(student_id)


def _write(store: EventStore, event: Event, summary: RunSummary) -> None:
    if store.create(event):
        summary.events_written += 1
