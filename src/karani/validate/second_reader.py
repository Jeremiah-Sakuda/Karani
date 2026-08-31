"""The second reader (KAR-417): Gemma cross-examines what Gemini accepted.

Layer 5, and the first layer where the checker is a **different model family** from the
model being checked. The four layers below establish that a citation is real, verbatim,
correctly located, and — per `gemini-3.5-flash-lite` — actually supports the claim. This
layer asks the same entailment question of `gemma3:4b`, running locally, and routes a
disagreement to the human queue.

Why a second family matters: entailment is the one check where the checker could share the
generator's blind spots. Gemini checking Gemini is a proofreader from the same newsroom —
better than nothing, correlated where it matters least to be. Gemma was trained separately,
runs on different weights, and is hosted on different silicon (the instructor's own machine,
via Ollama). Agreement across families is evidence; agreement within one is consistency.

The claim this layer buys, stated carefully: **no single model's judgment turns a draft into
evidence.** Not "two models are always right" — two models can share an error. The layer
narrows the class of unexamined mistakes; the human queue remains where disagreements go.

Honesty rules, in the house style:

- Disagreement escalates and is NEVER retried, exactly like entailment (KAR-310) and for
  the same reason: pressure to get past a disagreeing checker is how fabrication happens.
- Unavailability is recorded as `None` — not run — never as a pass. An instructor reading
  `second_reader: null` on a verification block knows Gemma did not weigh in; reading
  `true` means it did and agreed.
- A response Gemma produces that cannot be parsed is also `checked=False`: the reader did
  not deliver a verdict, so nothing was confirmed or denied. This is deliberately WEAKER
  than entailment's fail-closed parse handling, and the asymmetry is the design: entailment
  is the gate, and a gate must fail toward review; the second reader is an additional
  cross-check whose absence is already an honestly-recorded state, and letting a 4B model's
  formatting noise flood the human queue would bury the disagreements that matter.
- Every response is cached through the same `ResponseCache` as everything else, keyed by
  model and claim/passage pair, so the offline demo replays real Gemma output and a retried
  worker gets byte-identical answers.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from karani.analysis.cache import CacheKey, ResponseCache
from karani.analysis.prompts import ENTAILMENT_SYSTEM, build_entailment_prompt
from karani.canon import sha256_text
from karani.config import MODEL_TRIAGE, PROMPT_VERSION, TEMPERATURE
from karani.validate.entailment import _strip_fence


@dataclass(frozen=True)
class SecondReaderResult:
    confirmed: bool
    reason: str
    checked: bool
    model_id: str = MODEL_TRIAGE

    @property
    def disagreement(self) -> bool:
        return self.checked and not self.confirmed


def second_reader_enabled() -> bool:
    """Explicit opt-in via KARANI_SECOND_READER.

    Off by default so that the recorded main-corpus run, its published numbers, its
    screenshots, and the deployed nightly job (which has no Ollama) are all unchanged.
    Where it is on, its work is recorded per-observation in `verification.second_reader`;
    where it is off, that field is None and reads as exactly what it is: not run.
    """
    return os.environ.get("KARANI_SECOND_READER", "").strip() in ("1", "true", "yes")


def check_second_reader(
    *,
    claim: str,
    passage: str,
    submission: str = "",
    cache: ResponseCache,
    rendition_id: str,
) -> SecondReaderResult:
    key = CacheKey(
        rendition_id=rendition_id,
        prompt_version=f"{PROMPT_VERSION}-second-reader",
        model_id=MODEL_TRIAGE,
        temperature=TEMPERATURE,
        attempt=0,
        feedback_hash=sha256_text(f"{claim}␟{passage}␟{submission}")[:32],
        criterion_scope="second-reader",
    )

    text = cache.get(key)
    cached = text is not None
    if text is None:
        text = _ollama_generate(build_entailment_prompt(claim, passage, submission))
        if text is None:
            return SecondReaderResult(
                confirmed=False,
                reason="second reader unavailable (no Ollama endpoint and no cached response)",
                checked=False,
            )
        cache.put(key, text)

    try:
        parsed = json.loads(_strip_fence(text))
        supported = bool(parsed["supported"])
        reason = str(parsed.get("reason", ""))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # Not run, not failed -- see the module docstring for why this is weaker than
        # entailment's fail-closed handling, on purpose.
        if not cached:
            # An unparseable live response must not poison the cache as if it were an
            # answer; the next run should ask again.
            pass
        return SecondReaderResult(
            confirmed=False,
            reason=f"second reader response could not be parsed ({type(exc).__name__})",
            checked=False,
        )

    return SecondReaderResult(confirmed=supported, reason=reason, checked=True)


def _ollama_generate(prompt: str) -> str | None:
    """One local Gemma call. Returns None when the endpoint is unreachable."""
    url = os.environ.get("KARANI_OLLAMA_URL", "http://localhost:11434").rstrip("/")
    body = json.dumps(
        {
            "model": MODEL_TRIAGE,
            "system": ENTAILMENT_SYSTEM,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": TEMPERATURE},
        }
    ).encode()
    request = urllib.request.Request(
        f"{url}/api/generate", data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    text = str(payload.get("response", "")).strip()
    return text or None
