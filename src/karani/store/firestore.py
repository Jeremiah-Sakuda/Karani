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

    def __init__(self, project: str, use_emulator: bool = False) -> None:
        from google.cloud import firestore

        if use_emulator:
            # The emulator ignores credentials but still wants a project ID.
            self._client = firestore.Client(project=project or "karani-local")
        else:
            if not project:
                raise ValueError(
                    "the firestore backend needs GOOGLE_CLOUD_PROJECT. To run without "
                    "credentials use KARANI_STORE_BACKEND=local (which `make demo` does)."
                )
            self._client = firestore.Client(project=project)
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
        return sorted(doc.id for doc in self._client.collection("runs").stream())


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
