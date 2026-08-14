"""Process-level termination — the part `T_max` could not give us.

`run_pipeline` bounds the **logical** run: at `T_max` the dispatcher writes `TaskAbandoned`
for anything outstanding, `render()` fires, and the artifact exists. That is genuinely
guaranteed and it is tested.

It does **not** guarantee the OS process exits, and an earlier comment in the dispatcher
claimed it did. That comment was wrong, and the reason is worth stating precisely because it
is a documented Python behaviour rather than a bug:

- `Executor.shutdown(wait=False, cancel_futures=True)` cancels *pending* futures. A future
  that is already **running** cannot be cancelled — Python has no mechanism to interrupt a
  thread from outside it.
- `ThreadPoolExecutor` registers a `threading._register_atexit` hook, so the interpreter
  joins its worker threads before exiting. A permanently blocked worker therefore holds the
  process open past every deadline the application sets.

So the honest position was: the run completes around a hung worker, and the *process* does
not. For a Cloud Run Job that means the task sits burning its timeout with its work already
finished — which is not a correctness failure, but it is a liveness claim this project was
making and could not keep.

**What this module does about it.** After the artifact is written and the exit code is known,
the entrypoint calls `hard_exit`. If worker threads are still alive it flushes the streams and
calls `os._exit`, which terminates the process without waiting for any thread and without
running the atexit hooks that would.

`os._exit` is a blunt instrument and that is why it lives here rather than in the library.
Nothing that could be imported into someone else's process calls it. The rule it follows: only
after the run's own durable output is complete, because everything Karani produces is already
on disk or in Firestore by that point — the log is append-only and written as it goes, so
there is nothing buffered that a graceful shutdown would have saved.
"""

from __future__ import annotations

import os
import sys
import threading


def worker_threads_outstanding(prefix: str = "ThreadPoolExecutor") -> list[str]:
    """Names of executor worker threads still alive.

    Identified by name rather than by holding references to the futures, because the futures
    that matter are the ones the executor could not cancel — the running ones — and by
    definition nothing holds a handle that can stop them.
    """
    return [
        t.name
        for t in threading.enumerate()
        if t is not threading.current_thread() and t.name.startswith(prefix) and t.is_alive()
    ]


def hard_exit(
    code: int, *, reason: str = "", quiet: bool = False, prefix: str = "ThreadPoolExecutor"
) -> None:
    """Exit the process now, refusing to wait for threads that will not return.

    When no worker threads are outstanding this returns normally and the caller exits the
    ordinary way, so the blunt path is taken only when the ordinary one would hang.
    """
    outstanding = worker_threads_outstanding(prefix)
    if not outstanding:
        return

    if not quiet:
        print(
            f"\n{len(outstanding)} worker thread(s) did not return"
            f"{f' ({reason})' if reason else ''}."
            f"\nThe run is complete and its artifact is written; Python cannot interrupt a"
            f"\nrunning thread, so the process is exiting rather than waiting for them.",
            file=sys.stderr,
        )

    # Everything durable is already flushed: the event log is append-only and fsync'd per
    # write, and the rendered artifact was written before this call. Only the streams need
    # flushing, because os._exit skips that too.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
