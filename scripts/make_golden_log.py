#!/usr/bin/env python3
"""Write `fixtures/golden-log.jsonl` — the committed run the docket serves offline.

The golden log is what `make docket-golden` renders, what the hosted docket serves, and what
appears on camera. It is committed rather than generated at demo time so that the demo does
not depend on a model call, a network, or a credential.

Regeneration is byte-identical: the factory it draws from uses no randomness, no clock, and
no environment. If this script produces a diff, something in the schema or the factory
changed, and that is worth seeing in review rather than absorbing silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO))

from tests.factories import golden_log_jsonl  # noqa: E402

OUT = REPO / "fixtures" / "golden-log.jsonl"


def main() -> int:
    payload = golden_log_jsonl()
    previous = OUT.read_text(encoding="utf-8") if OUT.exists() else None

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(payload, encoding="utf-8")

    lines = payload.count("\n")
    if previous is None:
        print(f"wrote {OUT.relative_to(REPO)} ({lines} events)")
    elif previous == payload:
        print(f"{OUT.relative_to(REPO)} unchanged ({lines} events) — regeneration is byte-identical")
    else:
        print(f"UPDATED {OUT.relative_to(REPO)} ({lines} events) — content changed since last write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
