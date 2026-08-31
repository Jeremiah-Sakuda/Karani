#!/usr/bin/env python3
"""Render the golden run to static HTML (KAR-411).

Two jobs, one artifact:

1. **The hosted docket serves this**, pre-rendered, at `min-instances=0`. A judge hitting a
   cold Cloud Run instance gets a static file rather than a container boot plus a fold, and
   the load-time target stops depending on how warm the instance happens to be.

2. **It is what the README's screenshots are of.** A judge who does not clone the repository
   still sees the product, and the screenshots are generated from the same fold that produces
   the live docket rather than being captured by hand and going stale.

    ./scripts/render_static_docket.py --out out/static-docket
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from karani.docket.render_html import (  # noqa: E402
    challenge_answer,
    challenge_page,
    overview_page,
    student_page,
)
from karani.render import render  # noqa: E402
from karani.store.local import read_jsonl_log  # noqa: E402


def rewrite_links(html: str) -> str:
    """Turn the app's routes into relative file paths for static hosting."""
    html = html.replace('href="/"', 'href="index.html"')
    html = html.replace('href="/challenge"', 'href="challenge.html"')
    html = html.replace('action="/challenge"', 'action="challenge.html"')
    html = html.replace('href="/student/', 'href="student-')
    html = html.replace('href="/appeal/', 'href="appeal-')
    # Static pages cannot accept a supersession write. Rather than render a form that
    # silently does nothing when clicked -- which would be a worse lie than omitting it --
    # the edit control is replaced with a note saying where it does work.
    html = html.replace(
        '<button type="submit" style="margin-top:.5rem">Record supersession</button>',
        '<p class="sub">Editing is live on the hosted docket and in <code>make demo</code>. '
        "This static export is read-only.</p>",
    )
    for suffix in ('">', '"'):
        html = html.replace(f".html/{suffix}", f".html{suffix}")
    return html.replace('student-s01"', 'student-s01.html"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # The reference log by default, because this renders *every* page shape, including
    # the abandonment path the recorded run does not reach. The Makefile target
    # described this as "the committed recorded run" for a long time; it is not.
    # Pass --log fixtures/recorded-run.jsonl for real model output.
    parser.add_argument("--log", default=str(REPO / "fixtures" / "golden-log.jsonl"))
    parser.add_argument("--out", default=str(REPO / "out" / "static-docket"))
    args = parser.parse_args()

    events = read_jsonl_log(Path(args.log).resolve())
    run_id = events[0].run_id if events else "run-golden"
    run = render(run_id, events)

    # The documented invocation passes a relative output directory.  Resolve it before the
    # completion message so a successful render cannot crash after writing every artifact.
    out = Path(args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    pages: dict[str, str] = {"index.html": overview_page(run)}
    for sheet in run.sheets:
        pages[f"student-{sheet.student_id}.html"] = student_page(run, sheet.student_id)
    pages["challenge.html"] = challenge_page(
        answer=challenge_answer("what grade would s01 get?"),
        asked="what grade would s01 get?",
    )

    for name, html in pages.items():
        fixed = rewrite_links(html)
        for sheet in run.sheets:
            fixed = fixed.replace(
                f'href="student-{sheet.student_id}"', f'href="student-{sheet.student_id}.html"'
            )
            fixed = fixed.replace(
                f'href="appeal-{sheet.student_id}"', f'href="appeal-{sheet.student_id}.json"'
            )
        (out / name).write_text(fixed, encoding="utf-8")

    (out / "artifact.json").write_text(run.to_json(), encoding="utf-8")

    display_out = out.relative_to(REPO) if out.is_relative_to(REPO) else out
    print(f"wrote {len(pages) + 1} files to {display_out}")
    for name in sorted(pages):
        print(f"  {name:<26} {len(pages[name]):>7,} bytes")
    print(
        f"\nrun {run_id} · {len(run.sheets)} sheets · "
        f"{len(run.source_events)} events · range hash {run.range_hash[:16]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
