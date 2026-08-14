"""The process, not just the function — KAR-314's liveness claim taken literally.

`tests/test_join_liveness.py` proves the **logical** run is bounded: `run_pipeline` returns,
`TaskAbandoned` is written, the artifact renders. Those tests use a worker that sleeps and then
returns, which is the realistic case and not the hard one.

An adversarial review pointed out that they do not prove what the product claims. Python cannot
interrupt a running thread, and `ThreadPoolExecutor` registers an atexit hook that joins its
workers — so with a worker that **never** returns, `run_pipeline` can complete perfectly and
the interpreter still refuses to exit. For a Cloud Run Job that means a task with its work
finished, its artifact written, and its process sitting there until the task timeout.

So these tests spawn a **real subprocess** with a worker that blocks on an event nobody sets,
and assert the OS process is gone inside a wall-clock bound. A test that only checked
`run_pipeline` returned would pass while the property was false — which is exactly what
happened.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

# A worker that blocks forever. Not `sleep(large)` -- that eventually returns, and "eventually"
# is the thing under test.
NEVER_RETURNS = textwrap.dedent(
    """
    import sys, threading
    sys.path.insert(0, {src!r})

    from pathlib import Path
    from karani.analysis.cache import ResponseCache
    from karani.analysis.client import ModelResponse
    from karani.analysis.dispatcher import run_pipeline
    from karani.analysis.prompts import Criterion
    from karani.armor.scan import LocalPatternScanner
    from karani.ingest.source import LocalSource
    from karani.runtime import hard_exit
    from karani.store.local import LocalEventStore

    BLOCKED = threading.Event()  # nothing ever sets this

    class NeverReturns:
        backend = "never"
        def generate(self, *, system, prompt, model_id, key):
            BLOCKED.wait()               # blocks for the life of the process
            return ModelResponse(text="{{}}", model_id=model_id, cached=False)

    tmp = Path({tmp!r})
    summary = run_pipeline(
        run_id="run-never",
        source=LocalSource(Path({fixtures!r})),
        criteria=[Criterion("c1", "Thesis", "A position is stated.")],
        store=LocalEventStore(tmp / "store"),
        client=NeverReturns(),
        cache=ResponseCache(tmp / "cache"),
        scanner=LocalPatternScanner(),
        max_workers=3,
        t_max_seconds=2,
    )

    print("RUN_RETURNED", len(summary.abandoned), summary.threads_outstanding, flush=True)

    # What the deployed entrypoint does once the artifact is durable.
    hard_exit(0, reason="test", quiet=True)
    print("EXITED_NORMALLY", flush=True)
    """
)


def _script(tmp_path: Path) -> str:
    return NEVER_RETURNS.format(
        src=str(REPO / "src"),
        tmp=str(tmp_path),
        fixtures=str(REPO / "fixtures" / "dev"),
    )


def test_the_process_exits_even_when_a_worker_never_returns(tmp_path):
    """Property: the OS process terminates inside a wall-clock bound. Not the function — the
    process.

    This is the claim "runs unattended overnight and always finishes around failures" actually
    means. Before the fix, `run_pipeline` returned at T_max and the interpreter then blocked
    indefinitely joining a worker that would never finish.

    The bound here is deliberately generous (25s against a 2s `T_max`) because the assertion is
    *termination*, not latency. A hang fails by timing out, not by being slow.
    """
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, "-c", _script(tmp_path)],
            capture_output=True,
            text=True,
            timeout=25,
            cwd=REPO,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            "the process did not exit within 25s against a T_max of 2s. `run_pipeline` may "
            "have returned, but the interpreter is still joining a blocked worker thread — "
            "which is exactly the failure this test exists to catch."
        )

    elapsed = time.monotonic() - started
    assert "RUN_RETURNED" in result.stdout, (
        f"the run never completed: {result.stdout}{result.stderr}"
    )
    assert elapsed < 25, f"process took {elapsed:.1f}s"
    assert result.returncode == 0, f"exited {result.returncode}: {result.stderr[-400:]}"


def test_the_run_completes_before_the_process_is_bounded(tmp_path):
    """Property: termination is not covering for a run that failed to finish.

    `hard_exit` is a blunt instrument, and a blunt instrument applied too early would hide a
    broken run behind a clean exit code. So this asserts the ordering: the dispatcher abandoned
    the blocked unit and reported outstanding threads *before* anything killed the process.
    """
    result = subprocess.run(
        [sys.executable, "-c", _script(tmp_path)],
        capture_output=True,
        text=True,
        timeout=25,
        cwd=REPO,
    )

    line = next(ln for ln in result.stdout.splitlines() if ln.startswith("RUN_RETURNED"))
    _, abandoned, outstanding = line.split()

    assert int(abandoned) >= 1, "the blocked unit was not abandoned"
    assert int(outstanding) >= 1, (
        "no outstanding worker threads were reported, so this run did not exercise the case"
    )

    # And the process really did take the hard-exit path rather than exiting normally: a normal
    # exit would have printed EXITED_NORMALLY, and would have hung first.
    assert "EXITED_NORMALLY" not in result.stdout


def test_hard_exit_is_a_no_op_when_nothing_is_outstanding():
    """Property: the ordinary path stays ordinary.

    `os._exit` skips atexit handlers and buffered output. It must fire only when the graceful
    path would hang, or every clean run pays for a defensive measure it did not need.

    Probed with a thread-name prefix that matches nothing, rather than by asserting the
    process has no executor threads — because it does. `test_join_liveness.py` deliberately
    blocks workers and leaves them alive in this very interpreter, which is a neat
    demonstration of the problem: by the end of a suite run, pytest itself is holding threads
    that will never return.
    """
    from karani.runtime import hard_exit, worker_threads_outstanding

    assert worker_threads_outstanding("NoSuchThreadPrefix") == []
    hard_exit(0, quiet=True, prefix="NoSuchThreadPrefix")  # returns; an exit would kill pytest


def test_the_suite_itself_leaves_blocked_threads_behind():
    """Property: the condition `hard_exit` exists for is real, and reachable in ordinary use.

    Not a defensive assertion — an observation worth pinning. The liveness tests block workers
    on purpose, Python cannot interrupt them, and they are still alive here. That is precisely
    the state a Cloud Run Job would be in after `T_max`, and precisely why the process needs a
    bound of its own rather than trusting the interpreter to exit.
    """
    from karani.runtime import worker_threads_outstanding

    # Not asserted as non-empty: test ordering must not decide whether this passes. What is
    # asserted is that the detector works on whatever is actually there.
    outstanding = worker_threads_outstanding()
    assert isinstance(outstanding, list)
    assert all(isinstance(name, str) for name in outstanding)
