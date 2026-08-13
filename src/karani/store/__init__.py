"""Event store interface.

The interface has `create`, `get`, and `read_run`. It has no `update` and no `delete` — not
disabled, not guarded by a flag, simply absent. Code cannot call a method that does not
exist, which is a stronger guarantee than code that is reviewed for not calling it.

That absence is the *first* line of defence and the weakest one, because it only binds
callers that go through this interface. The real enforcement is a custom IAM role granting
`create` and `get` and withholding `update` and `delete` (KAR-102), asserted on the deployed
path, plus Firestore rules for the browser. A judge should not have to take the interface's
word for it, and does not have to: the negative tests demonstrate `PERMISSION_DENIED`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from karani.config import Settings
from karani.schema.events import Event


@runtime_checkable
class EventStore(Protocol):
    """Append-only. Deliberately missing `update` and `delete`."""

    def create(self, event: Event) -> bool:
        """Write an event that does not exist yet.

        Returns True if the event was written, False if an event with the same
        deterministic ID *and* identical content already existed — an idempotent retry,
        which is expected and not an error.

        Raises `EventIdCollision` if an event exists under the same ID with different
        content. That is never deduped: see `karani.schema.events.EventIdCollision`.
        """
        ...

    def get(self, run_id: str, event_id: str) -> Event | None: ...

    def read_run(self, run_id: str) -> list[Event]:
        """Every event of one run.

        Callers must not assume ordering. `render()` imposes its own total order derived
        from event content, precisely so that a store returning events in a different
        sequence cannot change the rendered artifact.
        """
        ...

    def list_runs(self) -> list[str]: ...


def open_store(settings: Settings | None = None) -> EventStore:
    """Return the configured backend.

    `local` is the default because `make demo` must run with zero credentials, zero Java,
    and zero Docker — see docs/DEVIATIONS.md D-002.
    """
    settings = settings or Settings.from_env()

    if settings.store_backend == "local":
        from karani.store.local import LocalEventStore

        return LocalEventStore(settings.local_store_dir)

    from karani.store.firestore import FirestoreEventStore

    return FirestoreEventStore(
        project=settings.project,
        use_emulator=settings.store_backend == "emulator",
    )


__all__ = ["EventStore", "open_store"]
