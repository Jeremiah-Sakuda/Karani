#!/usr/bin/env python3
"""Diff two runs (KAR-316).

The acceptance criterion is two-sided and both halves matter: two runs over identical fixtures
must diff **empty**, and a run over an edited fixture must diff **non-empty**. A differ that
only satisfies the first is satisfied by returning nothing.

What it compares is the *claims projection*, not the raw artifact. Run IDs, timestamps, and
event IDs legitimately differ between two runs of the same inputs; what must not differ is
what Karani found. Diffing the whole artifact would report a difference every time and would
therefore report nothing useful.

This is also the tool that makes the exemplar loop checkable (KAR-403): bump `prompt_version`
as the only variable and the diff shows whether ratified edits actually moved the drafting.

    ./scripts/diff_runs.py out/run-a/rendered.json out/run-b/rendered.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def claim_key(claim: dict[str, Any]) -> tuple[str, str]:
    return (str(claim.get("student_id", "")), str(claim.get("criterion_id", "")))


def claim_shape(claim: dict[str, Any]) -> dict[str, Any]:
    """The part of a claim that two runs over identical inputs must agree on.

    Deliberately excludes `observation_id` (carries the attempt number), `created_at`, and
    `run_id`. Including them would make every comparison differ and make the tool useless,
    which is a subtler way of failing the acceptance criterion than returning nothing.
    """
    citation = claim.get("citation") or {}
    return {
        "kind": claim.get("kind"),
        "text": claim.get("text"),
        "span_id": citation.get("span_id"),
        "quote": citation.get("quote"),
        "search_notes": claim.get("search_notes"),
        "needs_human": bool(claim.get("needs_human")),
        "anchor_confidence": claim.get("anchor_confidence"),
        "model_id": (claim.get("provenance") or {}).get("model_id"),
        "prompt_version": (claim.get("provenance") or {}).get("prompt_version"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    left, right = load(Path(args.left)), load(Path(args.right))
    lc = {claim_key(c): claim_shape(c) for c in left.get("claims", [])}
    rc = {claim_key(c): claim_shape(c) for c in right.get("claims", [])}

    only_left = sorted(set(lc) - set(rc))
    only_right = sorted(set(rc) - set(lc))
    changed = sorted(k for k in set(lc) & set(rc) if lc[k] != rc[k])

    print(f"left   {args.left}  ({len(lc)} claims, run {left.get('run_id')})")
    print(f"right  {args.right}  ({len(rc)} claims, run {right.get('run_id')})")
    print()

    if not (only_left or only_right or changed):
        print("IDENTICAL — the two runs found the same things.")
        return 0

    if only_left:
        print(f"ONLY IN LEFT ({len(only_left)}):")
        for student, criterion in only_left:
            print(f"  {student} {criterion}: {lc[(student, criterion)]['kind']}")
        print()

    if only_right:
        print(f"ONLY IN RIGHT ({len(only_right)}):")
        for student, criterion in only_right:
            print(f"  {student} {criterion}: {rc[(student, criterion)]['kind']}")
        print()

    if changed and not args.quiet:
        print(f"CHANGED ({len(changed)}):")
        for key in changed:
            student, criterion = key
            print(f"  {student} {criterion}")
            for field in sorted(set(lc[key]) | set(rc[key])):
                before, after = lc[key].get(field), rc[key].get(field)
                if before != after:
                    print(f"      {field}:")
                    print(f"        - {_trim(before)}")
                    print(f"        + {_trim(after)}")
        print()

    total = len(only_left) + len(only_right) + len(changed)
    print(f"DIFFERENT — {total} claim(s) differ.")
    return 1


def _trim(value: Any, width: int = 96) -> str:
    text = str(value)
    return text if len(text) <= width else text[: width - 1] + "…"


if __name__ == "__main__":
    sys.exit(main())
