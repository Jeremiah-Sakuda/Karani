"""Grades — the one thing Karani stores that Karani cannot write.

**Grades live in a separate Firestore database**, not a separate collection. That distinction
is the entire security boundary and it is worth stating why, because "separate collection"
sounds equivalent and is not:

`datastore.entities.create` cannot be scoped to a collection. A role granting it over a
database authorises creating a document *anywhere* in that database. And the Firestore server
SDK does not evaluate Security Rules at all — server clients are authorised by IAM alone. So
events and grades in one database means every identity that can append an event can create a
grade, whatever the rules file says.

This repository claimed the opposite for a while. The append-only role was bound at project
scope with `--condition=None`, which authorised exactly the write the README said was
impossible. Every local test passed, because local tests do not evaluate IAM either.

What makes the claim true now:

    grades          `karani-grades` database. No pipeline identity is bound to it, at all.
    events          `karani-events` database. Pipeline identities are bound here, and the
                    binding carries an IAM condition naming this database.
    instructor      authenticates as a person. Never a service account.

And the test that proves it attempts a **fresh-document create** against the grades database —
the precise operation the granted permission would authorise. A `.set()` on a fixed document
ID is a different operation and can be denied while a create succeeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from karani.config import GRADES_DATABASE


@dataclass(frozen=True)
class Grade:
    """A grade. Written by a person, never derived from an observation.

    There is deliberately no constructor path from an `Observation` to a `Grade`. Not a
    disabled one — none. If a future change wants to add "suggest a grade from the evidence",
    it has to write that function, and writing it is the moment someone should stop.
    """

    student_id: str
    value: str
    actor: str
    ts: datetime
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "student_id": self.student_id,
            "grade": self.value,
            "actor": self.actor,
            "ts": self.ts.isoformat(),
            "note": self.note,
        }


class GradesStore:
    """Read and write `grades/` on the grades database, as the instructor.

    Used by the docket under an instructor's authenticated session, and by nothing on the
    pipeline path. The pipeline cannot construct a working one: its identity has no binding on
    this database, so every call raises `PermissionDenied`.
    """

    def __init__(self, project: str, database: str = GRADES_DATABASE) -> None:
        from google.cloud import firestore

        self.project = project
        self.database = database
        self._client = firestore.Client(project=project, database=database)

    def read_all(self) -> dict[str, str]:
        """Every grade the instructor has written, as `{student_id: grade}`.

        This is what the CSV export reads. If it returns an empty dict the export writes empty
        cells, which is the correct behaviour before grading has happened — Karani exports the
        blank rather than filling it.
        """
        return {
            doc.id: str((doc.to_dict() or {}).get("grade", ""))
            for doc in self._client.collection("grades").stream()
        }

    def write(self, grade: Grade) -> None:
        """Record a grade, and append to its immutable history.

        The grade document may be revised; the history entry may not. An instructor changing
        a grade is ordinary and expected. An instructor's revision history disappearing is not,
        and it is the thing an appeal would turn on.
        """
        doc = self._client.collection("grades").document(grade.student_id)
        doc.set(grade.to_dict())
        doc.collection("history").document(f"{grade.ts.isoformat()}-{grade.actor}").create(
            grade.to_dict()
        )


def open_grades_store(project: str) -> GradesStore | None:
    """Open the grades store, or return None when it is unreachable.

    Returns `None` rather than raising so the docket degrades to exporting blank grade cells
    instead of failing. An export of blank grades is correct-and-incomplete; a crash during
    ratification loses the instructor's work.
    """
    if not project:
        return None
    try:
        return GradesStore(project)
    except Exception:  # noqa: BLE001 - unreachable grades storage is a degraded, not fatal, state
        return None


def instructor_grade(student_id: str, value: str, actor: str, note: str = "") -> Grade:
    return Grade(student_id=student_id, value=value, actor=actor, ts=datetime.now(UTC), note=note)
