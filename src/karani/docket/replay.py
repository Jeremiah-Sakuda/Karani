"""The glass-box replay (KAR-416): the night's run, watched settling.

"It ran unattended" is an assertion; this page is the receipt. It steps through the run's
event log in fold order — drafts appearing, rejections feeding back, retries landing,
escalations queueing, the injection flag firing while analysis proceeds — with the terminal
outcome tiles accumulating live. Forty seconds of watching is worth more than any paragraph
claiming autonomy, because the viewer sees the *consequences differ*, which is the actual
claim.

Honesty constraints, because a replay is a dramatization of a record and must not become
more than that:

- Only event **metadata** ships to the browser: step name, item id, attempt, timestamp.
  Payloads never leave the server — they contain generated text, and every generated-text
  surface goes through the verdict lint. A step name cannot carry a verdict.
- The clock is the log's own timestamps, compressed to fit the viewing window and labelled
  as compressed. Real elapsed time is printed beside it.
- The events are the committed log, in the same total order `render()` folds them in.
  Nothing is reordered for drama.
"""

from __future__ import annotations

import json

from karani.docket.render_html import _e, page
from karani.schema.events import Event

# Steps whose arrival should visibly bump an outcome tile. Everything else scrolls the
# ticker only.
_TILE_STEPS = {
    "ObservationAccepted",
    "NoEvidenceRecorded",
    "NeedsHumanReview",
    "InjectionDetected",
    "TaskAbandoned",
}


def replay_events_json(run_id: str, events: list[Event]) -> str:
    """Metadata-only event sequence, in fold order."""
    ordered = sorted((e for e in events if e.run_id == run_id), key=lambda e: e.sort_key)
    rows = [
        {
            "step": e.step.value,
            "item": e.item_id,
            "attempt": e.attempt,
            "ts": e.ts.isoformat(),
        }
        for e in ordered
    ]
    return json.dumps({"run_id": run_id, "events": rows})


def replay_page(run_id: str, events: list[Event]) -> str:
    data = replay_events_json(run_id, events)
    body = f"""
<header class="top">
  <h1>The night, replayed</h1>
  <p class="sub mono">run {_e(run_id)} · every event of the committed log, in fold order ·
     timestamps compressed to ~40s and labelled</p>
  <p class="thesis">Six kinds of consequence from one unattended run — watched, not asserted.</p>
</header>

<div class="notice">This is a replay of the append-only event log, not a simulation. Only
step names, item ids, and timestamps are shown; event payloads carry generated text and do
not leave the server. <a href="/">Back to the docket</a>.</div>

<div class="panel" style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap">
  <button id="play" style="font-size:1.05rem;padding:.45rem 1.1rem">&#9654; Replay the night</button>
  <span class="mono sub" id="clock">--:--:--</span>
  <span class="sub" id="speed"></span>
  <span class="mono sub" id="progress"></span>
</div>

<div id="tiles" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:.7rem;margin:1rem 0">
</div>

<div class="panel scroll" style="max-height:19rem;overflow-y:auto">
  <table style="width:100%"><thead><tr><th>log time</th><th>event</th><th>unit of work</th>
  <th>attempt</th></tr></thead><tbody id="ticker"></tbody></table>
</div>

<script>
const DATA = {data};
const TILE_STEPS = {json.dumps(sorted(_TILE_STEPS))};
const LABELS = {{
  ObservationAccepted: "accepted",
  NoEvidenceRecorded: "no evidence located",
  NeedsHumanReview: "needs human review",
  InjectionDetected: "injection flagged",
  TaskAbandoned: "abandoned",
  ObservationRejected: "rejected, feedback returned",
}};
const counts = {{}};
const tiles = document.getElementById("tiles");
const ticker = document.getElementById("ticker");
const clock = document.getElementById("clock");
const progress = document.getElementById("progress");

for (const step of TILE_STEPS) {{
  counts[step] = 0;
  const d = document.createElement("div");
  d.className = "panel"; d.id = "tile-" + step;
  d.innerHTML = `<div style="font-size:1.7rem" class="mono" id="n-${{step}}">0</div>
                 <div class="sub">${{LABELS[step] || step}}</div>`;
  tiles.appendChild(d);
}}

const events = DATA.events;
const t0 = new Date(events[0].ts).getTime();
const t1 = new Date(events[events.length - 1].ts).getTime();
const realSpan = Math.max(t1 - t0, 1);
const PLAY_MS = 40000;
document.getElementById("speed").textContent =
  "real span " + (realSpan / 1000).toFixed(1) + "s, compressed " +
  (realSpan / PLAY_MS).toFixed(1) + "x";

let timer = null, idx = 0;
function fmt(ts) {{ return new Date(ts).toISOString().slice(11, 19); }}

function show(e) {{
  clock.textContent = fmt(e.ts);
  progress.textContent = (idx + 1) + " / " + events.length + " events";
  const tr = document.createElement("tr");
  tr.innerHTML = `<td class="mono sub">${{fmt(e.ts)}}</td><td>${{LABELS[e.step] || e.step}}</td>
                  <td class="mono">${{e.item}}</td><td class="mono sub">${{e.attempt}}</td>`;
  ticker.prepend(tr);
  while (ticker.children.length > 60) ticker.removeChild(ticker.lastChild);
  if (counts[e.step] !== undefined) {{
    counts[e.step] += 1;
    const n = document.getElementById("n-" + e.step);
    n.textContent = counts[e.step];
    const tile = document.getElementById("tile-" + e.step);
    tile.style.outline = "2px solid var(--accent)";
    setTimeout(() => tile.style.outline = "", 350);
  }}
}}

document.getElementById("play").addEventListener("click", () => {{
  if (timer) return;
  idx = 0; ticker.innerHTML = "";
  for (const s of TILE_STEPS) {{ counts[s] = 0; document.getElementById("n-" + s).textContent = 0; }}
  const t0v = events.length > 1 ? t0 : 0;
  function tick() {{
    if (idx >= events.length) {{ timer = null; return; }}
    show(events[idx]);
    const cur = new Date(events[idx].ts).getTime();
    idx += 1;
    if (idx >= events.length) {{ timer = null; return; }}
    const next = new Date(events[idx].ts).getTime();
    const delay = Math.min(Math.max((next - cur) / realSpan * PLAY_MS, 15), 1500);
    timer = setTimeout(tick, delay);
  }}
  tick();
}});
</script>
"""
    return page("Karani — replay", body)
