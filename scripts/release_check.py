#!/usr/bin/env python3
"""Check Karani's release claims without turning missing cloud proof into a local pass.

This script has two modes.  Its default mode protects facts that are knowable from the
repository: in particular, the grades boundary must be described as a separate Firestore
database everywhere a judge will see it.  ``--submission`` additionally checks the
submission package, and intentionally fails until authenticated deployment, measurement, and
publication evidence is recorded.  A red submission check is more useful than a green one
that silently skips the requirements a judge will score.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
METRICS = ROOT / "docs" / "metrics.json"
DEVPOST = ROOT / "docs" / "submission" / "devpost.md"
COMPLIANCE = ROOT / "docs" / "compliance.md"
DEPLOY = ROOT / "scripts" / "deploy.sh"

# These are submission-facing files.  ``src/karani/grades.py`` deliberately discusses why a
# collection is insufficient, so it is not in this list.
BOUNDARY_SURFACES = (
    ROOT / "README.md",
    ROOT / "docs" / "PRD.md",
    ROOT / "docs" / "RUNBOOK.md",
    ROOT / "docs" / "submission" / "devpost.md",
    ROOT / "docs" / "architecture" / "diagram_a_system.svg",
    ROOT / "docs" / "architecture" / "diagram_b_identity.svg",
    ROOT / "src" / "karani" / "docket" / "render_html.py",
)
FORBIDDEN_BOUNDARY_TERMS = (
    "grades collection",
    "grades/ collection",
    "separate collection",
)
REQUIRED_LOCAL_METRICS = (
    ("validation.observations_total", ("validation", "observations_total")),
    ("validation.first_attempt_acceptance_rate", ("validation", "first_attempt_acceptance_rate")),
    ("validation.entailment_disagreement_rate", ("validation", "entailment_disagreement_rate")),
    ("validation.cache_hit_rate_warm", ("validation", "cache_hit_rate_warm")),
)


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str


def value_at(mapping: object, path: tuple[str, ...]) -> object:
    current = mapping
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def is_measured(metric: object) -> bool:
    return isinstance(metric, dict) and metric.get("value") != "not yet measured"


def local_findings() -> list[Finding]:
    findings: list[Finding] = []
    for path in BOUNDARY_SURFACES:
        text = path.read_text(encoding="utf-8").lower()
        for term in FORBIDDEN_BOUNDARY_TERMS:
            if term in text:
                findings.append(Finding("error", f"{path.relative_to(ROOT)} says '{term}'"))

    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    for label, metric_path in REQUIRED_LOCAL_METRICS:
        if not is_measured(value_at(metrics, metric_path)):
            findings.append(Finding("error", f"required local metric is absent: {label}"))

    if "separate Firestore database" not in (ROOT / "README.md").read_text(encoding="utf-8"):
        findings.append(Finding("error", "README does not state the grades database boundary"))

    deploy = DEPLOY.read_text(encoding="utf-8")
    if "--workers,15" not in deploy:
        findings.append(
            Finding("error", "deployment does not configure the documented 15-worker pool")
        )
    if "Cloud Run task grid" in "\n".join(
        path.read_text(encoding="utf-8") for path in BOUNDARY_SURFACES
    ):
        findings.append(
            Finding("error", "a submission-facing surface promises a Cloud Run task grid")
        )
    return findings


def submission_findings() -> list[Finding]:
    findings: list[Finding] = []
    devpost = DEVPOST.read_text(encoding="utf-8")
    if "[MEASURED:" in devpost:
        findings.append(
            Finding("error", "Devpost draft still contains measured-value placeholders")
        )
    if "[URL]" in devpost:
        findings.append(Finding("error", "Devpost draft still contains URL placeholders"))

    compliance = COMPLIANCE.read_text(encoding="utf-8")
    required_open = (
        "Hosted project URL, loads logged-out",
        "Demo video ≤4:00, public on YouTube or Vimeo, English",
        "Text description in PRD §1.3 order",
    )
    for item in required_open:
        line = next((line for line in compliance.splitlines() if item in line), "")
        if "OPEN" in line:
            findings.append(Finding("error", f"submission evidence is still open: {item}"))

    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    required_live_metrics = (
        ("scale_run.submissions_ingested", ("scale_run", "submissions_ingested")),
        ("scale_run.join_wall_clock", ("scale_run", "join_wall_clock")),
        ("beat_timings.trigger_to_first_event", ("beat_timings", "trigger_to_first_event")),
        (
            "friction.baseline_minutes_per_submission",
            ("friction", "baseline_minutes_per_submission"),
        ),
        (
            "friction.with_karani_minutes_per_submission",
            ("friction", "with_karani_minutes_per_submission"),
        ),
    )
    for label, metric_path in required_live_metrics:
        if not is_measured(value_at(metrics, metric_path)):
            findings.append(Finding("error", f"required submission metric is absent: {label}"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submission",
        action="store_true",
        help="also require authenticated deployment, metric, and publication evidence",
    )
    args = parser.parse_args()

    findings = local_findings()
    if args.submission:
        findings.extend(submission_findings())

    if findings:
        for finding in findings:
            print(f"{finding.severity.upper()}: {finding.message}")
        return 1

    print("PASS: local release claims are internally consistent.")
    if args.submission:
        print("PASS: the submission package has no recorded release blocker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
