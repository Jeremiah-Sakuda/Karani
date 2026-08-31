"""The Gemma triage tier (KAR-315).

Three questions asked of every submission *before* the expensive analysis model sees it:

    is this text, or a scan?      -> decides whether anchoring can be exact or degrades
    what language is it in?       -> a submission the rubric cannot be applied to
    is this a submission at all?  -> the assignment sheet, the rubric, the syllabus

**Gemma is deliberately not load-bearing.** It is a bonus item, and a bonus item must never
take a mandatory item hostage. If Gemma is unavailable — no Ollama locally, no Vertex endpoint
deployed — triage falls back to deterministic heuristics that run under **their own name**,
the run proceeds normally, and the `TriageDecided` event records which tier actually answered.
Nothing downstream depends on Gemma having run.

**On the word "local".** The dev tier runs against a local Ollama daemon and is labelled
`gemma (local, ollama)`. The Vertex tier is labelled `gemma (vertex endpoint)`. These are
never used interchangeably, and the tier that actually answered is recorded on the event —
because "we used Gemma" is a claim a judge can check, and it should be true in the specific
sense it is made.

The non-submission check here is the *ambiguous* case only. Certain names — `rubric.md`,
`syllabus.docx` — are excluded deterministically at the source (`karani.ingest.source`),
because ingest must not depend on a model call being available.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Literal

from karani.config import MODEL_TRIAGE

DocumentKind = Literal["submission", "non_submission", "unreadable"]
TextTier = Literal["text_layer", "scanned", "mixed"]


@dataclass(frozen=True)
class TriageDecision:
    kind: DocumentKind
    text_tier: TextTier
    language: str
    reason: str
    # Which tier actually answered. Never inferred from configuration -- recorded from what
    # ran, so the event log cannot claim Gemma answered when the fallback did.
    decided_by: str
    gemma_available: bool

    @property
    def should_analyze(self) -> bool:
        """Non-submissions are skipped. Everything else proceeds.

        Note what does *not* stop analysis: a scan, an unexpected language, or an injection
        detection. Karani flags those and analyses anyway, because a submission excluded by
        an automated pre-check is a student penalised by a system that never explained itself.
        """
        return self.kind == "submission"


TRIAGE_SYSTEM = """\
You classify a document before it is analysed. You do not read it for content and you never
evaluate its quality.

Answer three questions:
1. kind: is this a student's submission for an assignment ("submission"), or is it course
   material such as an assignment sheet, rubric, syllabus, roster, or template
   ("non_submission")? If the text is too garbled to tell, answer "unreadable".
2. text_tier: does this have a real text layer ("text_layer"), does it read like OCR or a
   scan with broken words and stray characters ("scanned"), or both ("mixed")?
3. language: the ISO 639-1 code of the dominant language.

Return exactly one JSON object, no prose, no fence:
{"kind": "...", "text_tier": "...", "language": "..", "reason": "<one short sentence>"}
"""

# Deterministic fallback signals. Each is a surface pattern, which is why this tier is named
# for what it is rather than presented as a classifier.
_COURSE_MATERIAL = re.compile(
    r"\b(?:this assignment|your essay should|due (?:date|by)|word count:|grading (?:rubric|criteria)"
    r"|office hours|course (?:description|policies)|learning outcomes|submit your"
    r"|points possible|late (?:work|policy))\b",
    re.IGNORECASE,
)
# OCR debris: isolated single letters, broken hyphenation, stray punctuation runs.
_OCR_NOISE = re.compile(r"(?:\b[a-z]\b\s+){4,}|[|~^]{2,}|\w-\s\w")


def heuristic_triage(text: str) -> TriageDecision:
    """Deterministic fallback, named as itself. Never presented as Gemma."""
    sample = text[:4000]
    words = sample.split()

    course_hits = len(_COURSE_MATERIAL.findall(sample))
    kind: DocumentKind = "submission"
    reason = "prose of submission length with no course-material markers"

    if len(words) < 40:
        kind = "unreadable"
        reason = f"only {len(words)} words extracted; too little to classify"
    elif course_hits >= 2:
        kind = "non_submission"
        reason = f"{course_hits} course-material phrases present ('due date', 'rubric', …)"

    noise = len(_OCR_NOISE.findall(sample))
    text_tier: TextTier = "scanned" if noise >= 3 else "text_layer"

    # Language detection is deliberately not attempted by pattern. Claiming a language from a
    # regex would be a made-up answer, and this module's whole point is that the fallback says
    # what it actually knows.
    return TriageDecision(
        kind=kind,
        text_tier=text_tier,
        language="und",
        reason=reason,
        decided_by="Karani heuristic triage (deterministic, offline)",
        gemma_available=False,
    )


def _parse(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return json.loads(text)


def gemma_triage_ollama(
    text: str, *, model: str = MODEL_TRIAGE, host: str = ""
) -> TriageDecision | None:
    """The dev tier: a genuinely local Ollama daemon. Returns None if it is not running.

    The host honours KARANI_OLLAMA_URL, and that override exists because of a real incident:
    the endpoint was hardcoded, the probe had failed instantly for the project's whole life
    (no Ollama installed), and the moment an Ollama daemon appeared on the machine, every
    "offline" pipeline test and `make demo` silently went live — thirty-plus seconds of
    real Gemma generation per submission, in a suite whose promise is "no model calls", with
    a nondeterministic model deciding triage in what is supposed to be a byte-stable replay.
    Auto-detection that changes behaviour based on which daemons happen to be running is
    spooky action; the offline paths now pin the URL to an unreachable port on purpose.
    """
    host = host or os.environ.get("KARANI_OLLAMA_URL", "http://localhost:11434")
    try:
        import urllib.error
        import urllib.request

        payload = json.dumps(
            {
                "model": model,
                "prompt": f"{TRIAGE_SYSTEM}\n\nDOCUMENT\n{text[:6000]}\n",
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{host}/api/generate", data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
        parsed = _parse(str(body.get("response", "")))
    except Exception:  # noqa: BLE001 - unavailable is a normal state, not an error
        return None

    return TriageDecision(
        kind=parsed.get("kind", "submission"),
        text_tier=parsed.get("text_tier", "text_layer"),
        language=str(parsed.get("language", "und")),
        reason=str(parsed.get("reason", "")),
        decided_by=f"gemma (local, ollama: {model})",
        gemma_available=True,
    )


def gemma_triage_vertex(
    text: str, *, project: str, location: str = "us-central1", model: str = MODEL_TRIAGE
) -> TriageDecision | None:
    """The Vertex tier (KAR-623). Created and torn down within the hour, per KAR-008."""
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(vertexai=True, project=project, location=location)
        response = client.models.generate_content(
            model=model,
            contents=f"DOCUMENT\n{text[:6000]}\n",
            config=types.GenerateContentConfig(
                system_instruction=TRIAGE_SYSTEM,
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        parsed = _parse(response.text or "")
    except Exception:  # noqa: BLE001
        return None

    return TriageDecision(
        kind=parsed.get("kind", "submission"),
        text_tier=parsed.get("text_tier", "text_layer"),
        language=str(parsed.get("language", "und")),
        reason=str(parsed.get("reason", "")),
        decided_by=f"gemma (vertex endpoint: {model})",
        gemma_available=True,
    )


def triage(text: str, *, project: str = "", prefer: str = "auto") -> TriageDecision:
    """Ollama, then Vertex, then the deterministic fallback. Always answers.

    Ordered cheapest-first, and it never raises: triage is a bonus tier, and a bonus tier that
    can stop a run has taken a mandatory item hostage.
    """
    if prefer in ("auto", "ollama"):
        decision = gemma_triage_ollama(text)
        if decision is not None:
            return decision

    if prefer in ("auto", "vertex") and project:
        decision = gemma_triage_vertex(text, project=project)
        if decision is not None:
            return decision

    return heuristic_triage(text)
