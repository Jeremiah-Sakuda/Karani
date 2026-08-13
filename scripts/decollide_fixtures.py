#!/usr/bin/env python3
"""Break residual cross-essay convergence in the fixture corpus.

A blind reviewer given the fifteen essays and told nothing about their provenance found that
forcing divergence of *position, sources, and structure* still left convergence underneath:
three invented town names reused across essay pairs, one anecdote told twice, four essays
opening with the same word, and one incidental figure ("seven years" of electronics life)
independently arrived at by four writers.

None of that changes what the corpus tests — every planted behaviour still fires, and the
registers are genuinely distinct — but a fixture corpus is read by judges as well as by
software, and two synthetic students citing the same invented town under different fabricated
researchers reads as exactly what it is.

Repairs are mechanical, deterministic, and minimal: substitutions only, no rewriting. The
first essay (by ID) keeps the shared term and later ones take a distinct replacement, so a
re-run is idempotent. Convergence this pass does *not* fix is disclosed in
`fixtures/MANIFEST.md` rather than quietly left in place.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Place names: first essay by ID keeps the name; the collider is renamed.
PLACE_RENAMES: dict[str, dict[str, str]] = {
    "s10": {"Amberton": "Verrick"},
    "s14": {"Calder Springs": "Thurlow Falls", "Calder": "Thurlow"},
    "s12": {"Quarry Bend": "Marlowe Bend"},
    # Caught on the verification pass: "Calder" also appeared in s07, which the first
    # sweep missed because it was looking for the two-word form.
    "s07": {"Calder Springs": "Hensley Point", "Calder": "Hensley"},
}

# The same incidental figure reached independently by four writers. Varied per essay; each
# replacement is internally consistent within its own essay.
FIGURE_RENAMES: dict[str, dict[str, str]] = {
    "s09": {"seven years": "eight years", "seven-year": "eight-year"},
    "s13": {"seven years": "a decade", "seven-year": "ten-year"},
    "s14": {"seven years": "six years", "seven-year": "six-year"},
}

# Convergent phrasing for the same idea.
PHRASE_RENAMES: dict[str, dict[str, str]] = {
    "s02": {
        "the electronics at either end": "the switching gear on both ends",
        "the electronics at each end": "the switching gear on both ends",
    },
    "s09": {
        "the electronics at either end": "the active equipment in the cabinets",
        "the electronics at each end": "the active equipment in the cabinets",
    },
}

# Four essays opened with the same word. Substitutions are sentence-initial only.
OPENER_RENAMES: dict[str, tuple[str, str]] = {
    "s06": ("Almost ", "Nearly "),
    "s09": ("Almost ", "Very nearly "),
    "s10": ("Almost ", "Practically "),
}

# s11 and s13 told the same anecdote -- the indispensable utility operator whose departure
# breaks the institution -- in the two essays meant to be the most personally idiosyncratic.
# s13's version is redirected to a different institution so the shape stops rhyming.
ANECDOTE_RENAMES: dict[str, dict[str, str]] = {
    # The collision is s09/s11, not s13 as first assumed -- the verification pass located it.
    # s11 keeps the anecdote (it is that essay's entire evidentiary basis); s09's passing
    # reference is redirected so the two stop rhyming.
    "s09": {
        "water treatment": "storm drainage",
        "water plant": "drainage system",
        "treatment plant": "pumping station",
    },
    "s13": {
        "water treatment": "records office",
        "water plant": "records office",
        "treatment plant": "records office",
    },
}


def apply_to(sid: str, body: str) -> tuple[str, list[str]]:
    applied: list[str] = []
    for table, label in (
        (PLACE_RENAMES, "place"),
        (FIGURE_RENAMES, "figure"),
        (PHRASE_RENAMES, "phrase"),
        (ANECDOTE_RENAMES, "anecdote"),
    ):
        for old, new in table.get(sid, {}).items():
            if old in body:
                body = body.replace(old, new)
                applied.append(f"{label}: {old!r} -> {new!r}")

    if sid in OPENER_RENAMES:
        old, new = OPENER_RENAMES[sid]
        # Sentence-initial only: after a newline or a sentence-ending mark.
        pattern = re.compile(rf"(^|[.!?]\s+|\n\n){re.escape(old)}")
        if pattern.search(body):
            body = pattern.sub(lambda m: m.group(1) + new, body)
            applied.append(f"opener: {old!r} -> {new!r}")

    return body, applied


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/karani_essays_v2.json")
    essays = json.loads(path.read_text(encoding="utf-8"))

    total = 0
    for sid in sorted(essays):
        body, applied = apply_to(sid, essays[sid]["body"])
        essays[sid]["body"] = body
        for line in applied:
            print(f"  {sid}  {line}")
            total += 1

    path.write_text(json.dumps(essays, indent=1), encoding="utf-8")
    print(f"\n{total} substitutions applied to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
