#!/usr/bin/env python3
"""KAR-007: the compliance checker.

Property this proves: every requirement ID that any document *relies on* is a requirement
that actually *exists*, and coverage is enumerated rather than asserted.

Two failure modes it exists to catch, both of which are ways a submission can look complete
while being hollow:

1. **Orphans.** An ID cited in the §2 compliance matrix, in the README, in a commit message,
   or anywhere else, that is defined nowhere in PRD §4. The matrix then claims coverage that
   no requirement backs. Deleting a requirement from §4 makes this fail, which is KAR-007's
   stated acceptance criterion.

2. **Range notation.** `KAR-601-608` asserts eight requirements without naming them, and a
   reader cannot tell whether the middle six exist. §2's own preamble forbids it. Ranges are
   how coverage gets rounded up.

Exits nonzero on either. This runs in CI and as `make compliance`.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRD = REPO / "docs" / "PRD.md"

# A requirement ID. Exactly three digits — KAR-1 and KAR-0001 are typos, not requirements.
ID_RE = re.compile(r"\bKAR-(\d{3})\b")

# A definition in §4 looks like:  - **KAR-101** Observation, rendition, ...
DEF_RE = re.compile(r"^\s*[-*]\s*\*\*(KAR-\d{3})\*\*", re.MULTILINE)

# Range notation in any of the forms that show up in practice:
#   KAR-601–608   KAR-601-608   KAR-601—608   KAR-501–KAR-507   KAR-620 – 624
RANGE_RE = re.compile(r"\bKAR-\d{3}\s*[-–—]\s*(?:KAR-)?\d{3}\b")

# Files that are allowed to contain range notation because they are quoting a finding
# about range notation rather than committing one.
RANGE_EXEMPT = {"docs/DEVIATIONS.md", "docs/BUILD-LOG.md", "scripts/compliance.py"}

SCAN_SUFFIXES = {".md", ".py", ".sh", ".toml", ".yaml", ".yml", ".json", ".html", ".mmd"}
SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", "fixtures/scale"}


@dataclass
class Report:
    defined: set[str] = field(default_factory=set)
    referenced: dict[str, set[str]] = field(default_factory=dict)
    ranges: list[tuple[str, int, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def note_reference(self, req_id: str, where: str) -> None:
        self.referenced.setdefault(req_id, set()).add(where)


def section_four(text: str) -> str:
    """Return the text of PRD §4 (Phased requirements).

    Sections are delimited by top-level `## N.` headings. If §4 cannot be located the check
    fails loudly rather than silently scanning an empty string and reporting success — a
    checker that passes because it found nothing to check is the failure mode this whole
    script exists to prevent.
    """
    start = re.search(r"^##\s*4\.\s", text, re.MULTILINE)
    if not start:
        raise SystemExit("FATAL: could not locate PRD §4 heading ('## 4. ...') in docs/PRD.md")
    rest = text[start.end() :]
    end = re.search(r"^##\s*5\.\s", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def section_two(text: str) -> str:
    start = re.search(r"^##\s*2\.\s", text, re.MULTILINE)
    if not start:
        raise SystemExit("FATAL: could not locate PRD §2 heading ('## 2. ...') in docs/PRD.md")
    rest = text[start.end() :]
    end = re.search(r"^##\s*3\.\s", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def repo_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO.rglob("*"):
        if not p.is_file() or p.suffix not in SCAN_SUFFIXES:
            continue
        rel = p.relative_to(REPO).as_posix()
        if any(rel.startswith(d) or f"/{d}/" in f"/{rel}" for d in SKIP_DIRS):
            continue
        out.append(p)
    return sorted(out)


def main() -> int:
    if not PRD.exists():
        raise SystemExit(f"FATAL: {PRD} not found")

    prd_text = PRD.read_text(encoding="utf-8")
    rep = Report()

    # --- 1. What §4 actually defines -------------------------------------------------
    s4 = section_four(prd_text)
    rep.defined = {m.group(1) for m in DEF_RE.finditer(s4)}
    if not rep.defined:
        rep.errors.append("PRD §4 defines no requirements at all — the parse is wrong or §4 is empty.")

    # --- 2. What §2's matrix claims ---------------------------------------------------
    s2 = section_two(prd_text)
    for m in ID_RE.finditer(s2):
        rep.note_reference(f"KAR-{m.group(1)}", "docs/PRD.md §2")

    # --- 3. What anything else in the repo relies on ----------------------------------
    for path in repo_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for m in ID_RE.finditer(text):
            rep.note_reference(f"KAR-{m.group(1)}", rel)

        if rel in RANGE_EXEMPT:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for m in RANGE_RE.finditer(line):
                rep.ranges.append((rel, lineno, m.group(0)))

    # --- 4. Diff ----------------------------------------------------------------------
    orphans = {rid: srcs for rid, srcs in rep.referenced.items() if rid not in rep.defined}
    unreferenced = rep.defined - set(rep.referenced)

    # --- Report -----------------------------------------------------------------------
    print(f"Requirements defined in PRD §4 : {len(rep.defined)}")
    print(f"Distinct IDs referenced        : {len(rep.referenced)}")
    print(f"Range notations found          : {len(rep.ranges)}")
    print()

    if orphans:
        print(f"ORPHANS — referenced but defined nowhere in §4 ({len(orphans)}):")
        for rid in sorted(orphans):
            where = ", ".join(sorted(orphans[rid])[:4])
            print(f"  {rid}  cited in: {where}")
        print()
        rep.errors.append(f"{len(orphans)} orphaned requirement ID(s)")

    if rep.ranges:
        print(f"RANGE NOTATION — coverage asserted rather than enumerated ({len(rep.ranges)}):")
        for rel, lineno, txt in rep.ranges:
            print(f"  {rel}:{lineno}  {txt}")
        print()
        rep.errors.append(f"{len(rep.ranges)} range notation(s)")

    if unreferenced:
        # Not fatal. A requirement can legitimately exist before anything cites it. It is
        # still worth surfacing: a requirement nothing references is a requirement nothing
        # is holding you to.
        print(f"NOTE — defined but referenced nowhere else ({len(unreferenced)}):")
        print("  " + ", ".join(sorted(unreferenced)))
        print()

    if rep.errors:
        print("FAIL: " + "; ".join(rep.errors))
        return 1

    print("PASS: every referenced requirement is defined, and coverage is enumerated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
