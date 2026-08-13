# Gates

Three dated decisions with consequences pre-committed *before* the evidence arrives. The
point of writing a gate down in advance is that the response is chosen while it is still
cheap to be honest — not on the morning the number comes in bad.

Copied from PRD §6 and §7. Every item on the abort order is a feature or a bonus. No
documentation artifact is ever on the abort list.

---

## Gate 1 — Aug 17 checkpoint

**Question:** how many of the following have passed their acceptance criteria?

| Req | What it proves |
|---|---|
| KAR-301 | Vertex model access, pinned IDs, temperature 0 in `provenance{}`, warm cache makes zero calls |
| KAR-304 | Rendition freeze — the cited artifact cannot drift |
| KAR-305 | Offset-preserving parse — a random span's `sha256` matches the rendition slice |
| KAR-306 | Fan-out completes; first-attempt acceptance instrumented |
| KAR-307 | Validation gate: exactly two retries, then a human-queue item, at observation granularity |
| KAR-309 | Split verdict lint: generated text masked, student's own quote never masked |
| KAR-311 | Injection scan on post-extraction bytes; analysis proceeds |
| KAR-312 | `grades/` IAM boundary holds, in the emulator and on the deployed path |

**Pass bar: 6 of 8.**

**Pre-committed consequence:** if fewer than six have passed by end of day Aug 17, invoke the
§7 cut list **that day**, in the numbered order, without further deliberation. Do not build
past a failed gate. A gate that gets re-argued when it fires was never a gate.

---

## Gate 2 — Aug 24 recording-ready gate

**Question:** *can I record the video from what exists on my machine today?*

**Feature freeze at 23:59 regardless of the answer.** If the answer is no, the video is
recorded from what exists anyway, and the shot list is cut per §8's runtime ladder — the
freeze does not move.

The reasoning is in PRD §4: a complete, reproducible, well-documented 60% product outscores
an undocumented 90% one on criteria that award 30% to demo and documentation.

---

## Gate 3 — the abort order

Invoked in sequence, without further deliberation, when either gate above fires.

1. KAR-316 polish — `diff_runs.py` stays minimal
2. KAR-310 entailment at 100% → sampled; rename "auditor" to "validator" everywhere
3. KAR-403's read half — narration becomes *"these edits are recorded as exemplars"*, which
   is true either way
4. KAR-404 class overview → a static 5s frame
5. KAR-406 delivery → CSV-download-only. The Drive write is the first feature cut and the
   last feature added back
6. KAR-315's Vertex endpoint — Gemma stays visible via the local tier, the diagram, and the
   README; forfeit the bonus if forced
7. KAR-320 scale run → N=50. Never below: the class-overview frame survives at 50
8. KAR-411's live-execution button → serve the static golden docket

### Never on the abort list, at any point

The README · both architecture diagrams · the video · the blog · the social posts ·
`## Findings and learnings` · KAR-309's split lint (**both** halves) · KAR-312's
deployed-path denial · KAR-205's friction measurement.

### Add back only if Phase 3 finishes early, in this order

1. Vertex context caching on the shared rendition prefix
2. Allowlist-shaped verdict lint — template conformance plus a binary
   *"does this express a level of quality, or only describe what the text does?"*
3. KAR-319 debounce hardening

---

## Gate log

Each firing is recorded here with the date, the count, and the actions taken. An empty
section below means the gate has not yet been evaluated — not that it passed.

### Aug 17 checkpoint
Not yet evaluated.

### Aug 24 recording-ready gate
Not yet evaluated.
