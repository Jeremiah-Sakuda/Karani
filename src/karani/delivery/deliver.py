"""Delivery (KAR-406) — the workflow ends where the instructor already lives.

Two artifacts leave the system on ratification: rendered evidence sheets written to one Drive
folder, and a CSV for LMS import.

**The CSV's grade column reads exclusively from `grades/`.** Not from an observation, not from
a derived aggregate, not from anything the pipeline produced — from the collection only the
instructor's authenticated session can write, and which every pipeline service account is
denied. If `grades/` is empty for a student, the column is empty. Karani will export a CSV of
blank grades rather than fill one in, because the export is the last place a verdict could
enter a downstream system and the only correct number of verdicts for it to contribute is
zero.

**The delivery identity can write one folder and nothing else.** Not "is configured to write"
one folder — is *permitted* to write one folder, by a scope the negative-test matrix asserts
(KAR-313). It cannot read submissions, cannot touch `events`, and cannot write `grades/`. This
is the identity that touches the instructor's real Drive, so it is the one whose scope is
worth being pedantic about.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from karani.render import RenderedRun
from karani.schema.events import Event, Step


@dataclass
class DeliveryResult:
    run_id: str
    files: list[str] = field(default_factory=list)
    csv_rows: int = 0
    events: list[Event] = field(default_factory=list)
    destination: str = "local"
    grades_present: int = 0
    grades_absent: int = 0


def build_csv(run: RenderedRun, grades: dict[str, str] | None = None) -> str:
    """The LMS import file.

    `grades` is whatever the instructor wrote into `grades/`, passed in by the caller that read
    it under the instructor's own credentials. This function has no way to obtain it otherwise,
    which is deliberate: a delivery module that could reach the grades database would be an
    identity that could write to it if a bug inverted a condition somewhere.
    """
    grades = grades or {}
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")

    # No column here is derived from an observation. "observations" and "needs_review" are
    # counts of Karani's own bookkeeping -- how much evidence it located and how much it
    # escalated -- and neither orders students or describes their work.
    writer.writerow(["student_id", "grade", "observations", "needs_review", "status", "notes"])

    for sheet in sorted(run.sheets, key=lambda s: s.student_id):
        needs_review = sum(1 for o in sheet.observations if o.get("needs_human"))
        writer.writerow(
            [
                sheet.student_id,
                # Empty unless the instructor wrote one. Never computed, never inferred, never
                # defaulted.
                grades.get(sheet.student_id, ""),
                len(sheet.observations),
                needs_review,
                sheet.status,
                "injection flagged" if sheet.injection_flagged else "",
            ]
        )

    return buffer.getvalue()


def render_sheet_html(run: RenderedRun, student_id: str) -> str:
    """A standalone evidence sheet for the instructor's folder."""
    from karani.docket.render_html import student_page

    return student_page(run, student_id)


def deliver(
    run: RenderedRun,
    *,
    out_dir: Path,
    grades: dict[str, str] | None = None,
    drive_folder_id: str = "",
    ratified: set[str] | None = None,
) -> DeliveryResult:
    """Write ratified sheets and the CSV, and log `ArtifactDelivered`.

    Only ratified students are delivered. Delivering an un-ratified sheet would put a drafted
    observation in front of a student's record before an instructor had looked at it, which is
    the one thing the ratification step exists to prevent.
    """
    grades = grades or {}
    result = DeliveryResult(run_id=run.run_id, destination="drive" if drive_folder_id else "local")
    out_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)

    targets = [s for s in run.sheets if ratified is None or s.student_id in ratified]

    for sheet in targets:
        path = out_dir / f"{sheet.student_id}-evidence.html"
        path.write_text(render_sheet_html(run, sheet.student_id), encoding="utf-8")
        result.files.append(path.name)

        if sheet.student_id in grades:
            result.grades_present += 1
        else:
            result.grades_absent += 1

        result.events.append(
            Event.build(
                run_id=run.run_id,
                step=Step.ARTIFACT_DELIVERED,
                item_id=f"{sheet.student_id}::sheet",
                ts=now,
                payload={
                    "student_id": sheet.student_id,
                    "artifact": path.name,
                    "destination": result.destination,
                    "drive_folder_id": drive_folder_id or None,
                },
            )
        )

    # The morning brief rides with every delivery (KAR-418): the ratified drop is the
    # one place the instructor is guaranteed to look, so the work-list goes there rather
    # than waiting to be visited.
    from karani.docket.brief import brief_page

    brief_path = out_dir / f"{run.run_id}-morning-brief.html"
    brief_path.write_text(brief_page(run), encoding="utf-8")
    result.files.append(brief_path.name)

    csv_text = build_csv(run, grades)
    csv_path = out_dir / f"{run.run_id}-grades.csv"
    csv_path.write_text(csv_text, encoding="utf-8")
    result.files.append(csv_path.name)
    result.csv_rows = len(targets)

    result.events.append(
        Event.build(
            run_id=run.run_id,
            step=Step.ARTIFACT_DELIVERED,
            item_id=f"{run.run_id}::csv",
            ts=now,
            payload={
                "artifact": csv_path.name,
                "destination": result.destination,
                "rows": result.csv_rows,
                # Recorded so the log shows how many grade cells were left empty. A run where
                # every cell is empty is the expected state before the instructor grades, and
                # it should be visible rather than inferred.
                "grades_written_by_instructor": result.grades_present,
                "grades_absent": result.grades_absent,
            },
        )
    )

    if drive_folder_id:
        _upload_to_drive(out_dir, result.files, drive_folder_id)

    return result


def _upload_to_drive(out_dir: Path, filenames: list[str], folder_id: str) -> None:
    """Write to exactly one Drive folder using the delivery identity.

    Scoped to `drive.file`, not `drive`: `drive.file` grants access only to files this
    application itself created, so the credential cannot read the instructor's existing Drive
    even if something asked it to. The broader scope would have been simpler and is the reason
    Drive *ingest* was cut entirely — see the README's negative decisions.
    """
    from google.oauth2 import service_account  # noqa: F401  (import documents the identity)
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    service = build("drive", "v3", cache_discovery=False)
    for name in filenames:
        path = out_dir / name
        service.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=MediaFileUpload(
                str(path),
                mimetype="text/html" if path.suffix == ".html" else "text/csv",
            ),
            fields="id",
        ).execute()


def ratify(run: RenderedRun, student_ids: set[str]) -> dict[str, Any]:
    """Summarise what ratification would deliver, without delivering it."""
    targets = [s for s in run.sheets if s.student_id in student_ids]
    return {
        "run_id": run.run_id,
        "ratifying": sorted(s.student_id for s in targets),
        "still_needing_review": sorted(
            s.student_id for s in targets if any(o.get("needs_human") for o in s.observations)
        ),
        "insufficient": sorted(s.student_id for s in targets if s.status == "INSUFFICIENT"),
    }
