"""Firestore-backed append-only event store — the deployed path.

Same narrow interface as the local store, and the same two semantics that matter:
deterministic IDs and create-only writes with a content-hash collision check. What differs is
that here the guarantee is not the interface's to give. `create()` on a Firestore document
reference fails with `ALREADY_EXISTS` if the document is there, and the pipeline service
accounts hold a custom IAM role granting `create` and `get` and withholding `update` and
`delete` — so a mutation is refused by the platform, not by this class.

That distinction is the whole point of KAR-102 asserting the boundary on the *deployed* path
and not only in the emulator: an emulator does not evaluate IAM at all, so a green emulator
test says nothing about the surface the pipeline actually uses.
"""

from __future__ import annotations

from typing import Any

from karani.schema.events import Event, EventIdCollision


class FirestoreEventStore:
    """Append-only event store on Firestore. No update. No delete."""

    def __init__(
        self, project: str, use_emulator: bool = False, database: str | None = None
    ) -> None:
        from google.cloud import firestore

        from karani.config import EVENTS_DATABASE

        # The EVENTS database, explicitly. Never the grades database, and never `(default)`.
        # A pipeline identity's IAM binding is conditioned on this database name, so pointing
        # this client elsewhere produces PERMISSION_DENIED rather than a quiet write to the
        # wrong place.
        self.database = database or EVENTS_DATABASE

        if use_emulator:
            # The emulator ignores credentials but still wants a project ID.
            self._client = firestore.Client(project=project or "karani-local")
        else:
            if not project:
                raise ValueError(
                    "the firestore backend needs GOOGLE_CLOUD_PROJECT. To run without "
                    "credentials use KARANI_STORE_BACKEND=local (which `make demo` does)."
                )
            self._client = firestore.Client(project=project, database=self.database)
        self.project = project

    def _doc(self, run_id: str, event_id: str) -> Any:
        return (
            self._client.collection("runs").document(run_id).collection("events").document(event_id)
        )

    def create(self, event: Event) -> bool:
        """Write an event that does not exist. Never overwrites one that does.

        `create()` rather than `set()` is load-bearing: `set()` would silently overwrite, and
        the collision check below would never run because there would be no collision to
        detect. The one that matters is the mismatch branch — two different facts under one
        deterministic ID means every artifact folded from this log is unsound, and there is no
        recovery from that, only a loud failure.
        """
        from google.api_core.exceptions import AlreadyExists

        payload = {
            "event_id": event.event_id,
            "run_id": event.run_id,
            "step": event.step.value,
            "item_id": event.item_id,
            "attempt": event.attempt,
            "ts": event.ts,
            "payload": event.payload,
            # Stored so a collision can be adjudicated by reading, without re-deriving the
            # hash from a payload that may have been round-tripped through Firestore's own
            # type coercion.
            "content_hash": event.content_hash,
        }

        try:
            self._doc(event.run_id, event.event_id).create(payload)
            return True
        except AlreadyExists:
            existing = self._doc(event.run_id, event.event_id).get()
            existing_hash = (existing.to_dict() or {}).get("content_hash", "")
            if existing_hash == event.content_hash:
                # An idempotent retry rewriting the same fact. Expected, not an error.
                return False
            raise EventIdCollision(event.event_id, existing_hash, event.content_hash) from None

    def get(self, run_id: str, event_id: str) -> Event | None:
        snapshot = self._doc(run_id, event_id).get()
        if not snapshot.exists:
            return None
        return _to_event(snapshot.to_dict() or {})

    def read_run(self, run_id: str) -> list[Event]:
        """Every event of one run.

        No ordering is imposed here, deliberately. `render()` derives its own total order from
        event content, so a Firestore query that returned documents in a different sequence
        than the local store cannot change the rendered artifact — which is what makes the
        replay test's guarantee hold across backends rather than only against one.
        """
        collection = self._client.collection("runs").document(run_id).collection("events").stream()
        return [_to_event(doc.to_dict() or {}) for doc in collection]

    def list_runs(self) -> list[str]:
        """Every run that has at least one event — derived from the events, not the parents.

        This used to stream the `runs` collection, which returned `[]` forever on the
        deployed path. The store writes `runs/{run_id}/events/{event_id}` and never creates
        the parent document, and Firestore does not list ancestor-only documents — they are
        "missing" documents that exist purely as paths. So the very first deployed job run
        wrote 228 real events, and the docket, asking this method what runs existed, was
        told none: every nightly run would have accumulated invisibly while the docket fell
        back to the baked-in recorded log, indefinitely, with nothing looking wrong.

        Found the way it had to be found — by deploying, executing the job, and reading what
        the docket actually served.

        Creating the parent doc on first write was the alternative and loses twice: the
        pipeline role is create-only, so the racing writers' parent upsert would need an
        update permission the append-only invariant exists to withhold; and it would not
        make runs written before the fix visible. A collection-group query sees the events
        themselves. `select([])` fetches document *references* only — no field payloads —
        so the cost is one lightweight row per event, fine at the scale of nightly class
        runs and honest to name here so nobody is surprised at a much larger one.
        """
        run_ids = {
            doc.reference.parent.parent.id
            for doc in self._client.collection_group("events").select([]).stream()
        }
        # The deployed IAM tests write minimal probe documents to prove the boundary --
        # `probe-<uuid>` paths whose payloads are not full events. They are permission
        # probes, not runs, and the convention is the prefix: anything under `probe-` is
        # invisible here. Without this the newest gate run's probe could sort last, be
        # picked up as "the latest run", and crash the docket at container start on a
        # document that was never an event.
        return sorted(run_id for run_id in run_ids if not run_id.startswith("probe-"))


def _to_event(data: dict[str, Any]) -> Event:
    return Event(
        event_id=str(data["event_id"]),
        run_id=str(data["run_id"]),
        step=data["step"],
        item_id=str(data["item_id"]),
        attempt=int(data.get("attempt", 0)),
        ts=data["ts"],
        payload=dict(data.get("payload") or {}),
    )
