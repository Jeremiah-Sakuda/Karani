#!/usr/bin/env python3
"""Write the measurements that can honestly be taken without a cloud (KAR-504).

The measurement contract says every published number must exist in `metrics.json` first,
written by an instrumented run, with its method named. That does **not** mean every number
has to wait for a deployment — corpus size, span counts, planted-problem detection, and the
scale corpus's reproducibility digest are all measurable offline, right now, and stating them
as "not yet measured" would be its own kind of inaccuracy.

What this script will not do is guess. It writes only what it computed in this process, stamps
each entry with `surface: local`, and leaves every deployed or cost measurement exactly as it
found it. In-process numbers are never promoted to deployed ones.

    ./scripts/update_metrics.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from karani.armor.scan import LocalPatternScanner  # noqa: E402
from karani.ingest.extract import UnparseableSource  # noqa: E402
from karani.ingest.freeze import freeze  # noqa: E402
from karani.ingest.source import LocalSource  # noqa: E402
from karani.render import render  # noqa: E402
from karani.store.local import read_jsonl_log  # noqa: E402

NOW = datetime.now(UTC).isoformat()

# The planted challenges from fixtures/MANIFEST.md, each with a check that determines whether
# the system actually exhibits the designed behaviour. "Found N of N planted problems" is a
# claim the README makes, so it is computed rather than asserted.
PLANTS = {
    "s07-injection": lambda f, scan: scan.detected,
    "s16-unparseable": lambda f, scan: f is None,
    "s06-pdf-chart": lambda f, scan: f is not None and f.rendition.source_projection == "pdf_text",
    "s11-pdf": lambda f, scan: f is not None and f.rendition.source_projection == "pdf_text",
    "s14-outlier": lambda f, scan: f is not None and len(f.rendition.text.split()) < 500,
    "s08-under-length": lambda f, scan: f is not None and len(f.rendition.text.split()) < 600,
}


def measure() -> dict:
    scanner = LocalPatternScanner()
    frozen: dict[str, object] = {}
    scans: dict[str, object] = {}
    words = spans = parsed = unparseable = 0

    for ref in LocalSource(REPO / "fixtures").list_submissions():
        try:
            f = freeze(ref)
        except UnparseableSource:
            frozen[ref.student_id] = None
            scans[ref.student_id] = scanner.scan("")
            unparseable += 1
            continue
        frozen[ref.student_id] = f
        scans[ref.student_id] = scanner.scan(f.rendition.text)
        words += len(f.rendition.text.split())
        spans += len(f.registry.spans)
        parsed += 1

    found = 0
    detail: dict[str, bool] = {}
    for name, check in PLANTS.items():
        sid = name.split("-")[0]
        ok = bool(check(frozen.get(sid), scans.get(sid)))
        detail[name] = ok
        found += int(ok)

    golden = render("run-golden", read_jsonl_log(REPO / "fixtures" / "golden-log.jsonl"))

    # Inherit the environment rather than constructing a minimal one: a stripped PATH made
    # pytest exit before collecting, and the count silently came back 0 -- a measurement
    # reporting zero because it failed is worse than one that is absent.
    import os

    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    tests = subprocess.run(
        [str(REPO / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "--collect-only"],
        capture_output=True,
        text=True,
        cwd=REPO,
        env=env,
    )
    # `pytest -q --collect-only` emits one "path: N" line per test file and, in this
    # version, no summary total -- so the total is the sum, not a line to grep for.
    collected = 0
    for line in tests.stdout.splitlines():
        if line.startswith("tests/") and ":" in line:
            tail = line.rsplit(":", 1)[1].strip()
            if tail.isdigit():
                collected += int(tail)
    if collected == 0:
        raise RuntimeError(
            "pytest collected 0 tests; refusing to record that as a measurement.\n"
            + tests.stdout[-800:]
            + tests.stderr[-400:]
        )

    return {
        "corpus": {
            "submissions_parseable": parsed,
            "submissions_unparseable": unparseable,
            "words_total": words,
            "citable_spans_total": spans,
        },
        "plants": {"total": len(PLANTS), "exhibited": found, "detail": detail},
        "golden_run": {
            "events": len(golden.source_events),
            "sheets": len(golden.sheets),
            "terminal_outcomes": golden.overview["terminal_outcomes"],
            "range_hash": golden.range_hash,
        },
        "tests_collected": collected,
    }


def entry(value, unit: str, method: str) -> dict:
    return {"value": value, "unit": unit, "method": method, "measured_at": NOW, "surface": "local"}


def main() -> int:
    m = measure()
    path = REPO / "docs" / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))

    metrics["fixtures"] = {
        "_note": (
            "Measured offline by scripts/update_metrics.py. These are properties of the "
            "committed corpus and of the local pipeline, and they are labelled surface=local. "
            "They are never quoted as deployed measurements."
        ),
        "submissions_parseable": entry(
            m["corpus"]["submissions_parseable"],
            "count",
            "counted by freezing every file the local source discovers",
        ),
        "submissions_unparseable": entry(
            m["corpus"]["submissions_unparseable"],
            "count",
            "files that raised UnparseableSource during freeze",
        ),
        "words_total": entry(
            m["corpus"]["words_total"], "count", "whitespace-split over normalized rendition text"
        ),
        "citable_spans_total": entry(
            m["corpus"]["citable_spans_total"],
            "count",
            "span registries minted from the frozen renditions",
        ),
        "planted_problems_total": entry(
            m["plants"]["total"], "count", "enumerated in fixtures/MANIFEST.md"
        ),
        "planted_problems_found": entry(
            m["plants"]["exhibited"],
            "count",
            "each plant re-checked against live pipeline behaviour, not against the manifest",
        ),
        "planted_problems_detail": entry(
            m["plants"]["detail"], "map", "per-plant behavioural check"
        ),
    }

    metrics["golden_run"] = {
        "_note": "The committed reference run. Its event log is hand-constructed, not model output.",
        "events": entry(
            m["golden_run"]["events"], "count", "folded from fixtures/golden-log.jsonl"
        ),
        "sheets": entry(m["golden_run"]["sheets"], "count", "evidence sheets produced by the fold"),
        "terminal_outcomes": entry(
            m["golden_run"]["terminal_outcomes"],
            "map",
            "counted by render(); all six must be non-zero (asserted by tests/test_replay.py)",
        ),
        "range_hash": entry(
            m["golden_run"]["range_hash"],
            "sha256",
            "hash over the content hashes of every consumed event",
        ),
    }

    metrics["suite"] = {
        "tests_collected": entry(
            m["tests_collected"],
            "count",
            "pytest --collect-only, default markers (no credentials, no emulator, no model calls)",
        ),
    }

    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {path.relative_to(REPO)}")
    print(
        f"  corpus            {m['corpus']['submissions_parseable']} parseable + "
        f"{m['corpus']['submissions_unparseable']} unparseable, "
        f"{m['corpus']['words_total']:,} words, {m['corpus']['citable_spans_total']} spans"
    )
    print(f"  planted problems  {m['plants']['exhibited']} of {m['plants']['total']} exhibited")
    for name, ok in m["plants"]["detail"].items():
        print(f"      {'yes' if ok else 'NO '}  {name}")
    print(
        f"  golden run        {m['golden_run']['events']} events, "
        f"{m['golden_run']['sheets']} sheets"
    )
    print(f"  tests             {m['tests_collected']} collected")
    print("\nDeployed and cost measurements untouched -- they stay 'not yet measured' until")
    print("an instrumented run on the deployed path produces them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
