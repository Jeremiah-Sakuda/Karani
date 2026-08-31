#!/usr/bin/env bash
# Regenerate the three README screenshots from the committed recorded run.
#
# These went stale: the README's first line tells a judge to run `make demo`, and the
# screenshot 200 lines below it showed different numbers than the run produces. A reader who
# checks one number against the picture and finds it wrong has no way to know which of the
# two is the honest one, which costs more than the picture is worth.
#
# So the pictures are generated rather than captured by hand, from the same committed log the
# docket renders. Re-run after any change to the fold, the docket templates, or the log.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [[ ! -x "$CHROME" ]]; then
  echo "Chrome not found at: $CHROME" >&2
  echo "Set CHROME=/path/to/chrome (any Chromium with --headless=new works)." >&2
  exit 1
fi

STAGE="out/screenshot-docket"
.venv/bin/python scripts/render_static_docket.py \
  --log fixtures/recorded-run.jsonl --out "$STAGE" >/dev/null

# s12 is the `no_evidence` sheet -- the case the README caption describes. Its height is
# pinned so a re-render produces the same framing rather than a diff of the whole image.
shoot() {
  local page="$1" out="$2" height="$3"
  "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
    --window-size=1180,"$height" \
    --screenshot="docs/screenshots/$out" \
    "file://$REPO/$STAGE/$page" >/dev/null 2>&1
  echo "  docs/screenshots/$out"
}

echo "regenerated from fixtures/recorded-run.jsonl:"
shoot index.html        docket-overview.png 1720
shoot student-s12.html  evidence-sheet.png  1400
shoot challenge.html    challenge.png       1500
