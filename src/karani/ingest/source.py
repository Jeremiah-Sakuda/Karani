"""Where submissions come from.

`LocalSource` is the default and the only path `make demo` uses, which is what makes
KAR-303's acceptance criterion — *a full run completes with zero Google OAuth* — true rather
than aspirational.

`drive_source.py` is deliberately absent. The scoping argument is worth stating because the
absence is a decision, not an omission: reading an instructor's Drive folder means either
`drive.readonly`, which grants access to their entire Drive, or a picker-scoped `drive.file`
flow, which is a consent UI, a token store, and a refresh path — a meaningful amount of
surface area for the *input* side of a system whose interesting behaviour is all downstream
of having the text. Drive *delivery* is in scope (KAR-406) and is a genuinely different
thing: one service account, one folder, write-only.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

# Ordered by preference. A student who submits both `s01.md` and `s01.pdf` is submitting one
# essay; picking deterministically rather than processing both is what keeps a run's shape a
# function of the roster rather than of directory listing order.
SUPPORTED_SUFFIXES = (".md", ".markdown", ".txt", ".docx", ".pdf")

# Files that live in a submissions folder without being submissions.
#
# This is not hypothetical tidiness. Running over this repository's own fixture directory
# ingested `MANIFEST.md` and produced a student called "MANIFEST" — with a rendition, a span
# registry, five observations, and a place in the class overview. A real instructor's folder
# contains the assignment sheet, the rubric, a syllabus excerpt, and whatever the LMS dropped
# in, and every one of them would have become a student.
#
# The failure is quiet, which is what makes it worth a hard exclusion rather than a warning:
# the fabricated student's sheet renders perfectly and reads exactly like every other sheet.
#
# Deterministic by name, because ingest must not depend on a model call. The general case --
# a file that is genuinely ambiguous, or a submission in the wrong language, or a scan of
# something that is not an essay -- is what the triage tier is for (KAR-315); this list only
# has to catch the names that are certain.
NON_SUBMISSION_STEMS = frozenset(
    {
        "readme",
        "manifest",
        "license",
        "licence",
        "notice",
        "contributing",
        "changelog",
        "rubric",
        "syllabus",
        "assignment",
        "instructions",
        "prompt",
        "index",
        "notes",
        "template",
        "example",
        "sample",
        "gradebook",
        "roster",
    }
)


@dataclass(frozen=True)
class SubmissionRef:
    """One student's submission, before anything has been read."""

    student_id: str
    path: Path
    filename: str

    @property
    def doc_id(self) -> str:
        return f"doc-{self.student_id}"


@runtime_checkable
class Source(Protocol):
    def list_submissions(self) -> list[SubmissionRef]: ...
    def read_bytes(self, ref: SubmissionRef) -> bytes: ...


class LocalSource:
    """Submissions as files in a directory. No network, no credentials, no OAuth."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list_submissions(self) -> list[SubmissionRef]:
        if not self.root.exists():
            raise FileNotFoundError(f"source directory {self.root} does not exist")

        # Group by stem so that one student with two file formats is one submission.
        by_student: dict[str, Path] = {}
        for path in sorted(self.root.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            if is_non_submission(path):
                continue
            student_id = path.stem
            current = by_student.get(student_id)
            if current is None or _rank(path) < _rank(current):
                by_student[student_id] = path

        # Sorted by student ID. Fan-out order is deterministic so that two runs over the
        # same directory dispatch the same work in the same order, which is what makes
        # `diff_runs.py` able to attribute a difference to the change under test.
        return [
            SubmissionRef(student_id=sid, path=by_student[sid], filename=by_student[sid].name)
            for sid in sorted(by_student)
        ]

    def read_bytes(self, ref: SubmissionRef) -> bytes:
        return ref.path.read_bytes()


def is_non_submission(path: Path) -> bool:
    """True for files that belong in a submissions folder without being submissions.

    Matched on the normalized stem so `MANIFEST.md`, `manifest.md`, and `Manifest.MD` are all
    excluded, and dotfiles are skipped outright.
    """
    stem = path.stem.strip().lower().replace("-", "_").replace(" ", "_")
    return path.name.startswith(".") or stem in NON_SUBMISSION_STEMS


def _rank(path: Path) -> int:
    try:
        return SUPPORTED_SUFFIXES.index(path.suffix.lower())
    except ValueError:
        return len(SUPPORTED_SUFFIXES)


def open_source(kind: str, root: Path) -> Source:
    if kind != "local":
        raise ValueError(
            f"unknown source {kind!r}. Only 'local' exists: Drive ingest is cut by "
            f"decision, not unimplemented -- see the module docstring and README "
            f"'Negative decisions'."
        )
    return LocalSource(root)
