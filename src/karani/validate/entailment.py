"""Entailment (KAR-310) — layer 4 of the citation checks, and the only one that costs money.

The question it answers is the one the three deterministic layers cannot: the citation points
at a real span, quotes it verbatim, and quotes it from the right place — but does that passage
actually *support* the claim made about it? A model can cite impeccably and still describe the
passage as doing something it does not do.

**Disagreements route straight to `NEEDS_HUMAN`. They are never retried.** This is the single
most important line in the module and it is a deliberate asymmetry with the other layers. A
referential or positional failure is a *mechanical* error — the model named the wrong span,
and telling it so is actionable. An entailment failure means the model and the checker
disagree about what a passage means. Sending that back with "try again" does not resolve a
disagreement about meaning; it applies pressure to produce something that gets past the
checker. That pressure is how fabrication happens, and it would be applied at exactly the
moment the system is least sure of itself.

So the escalation is the answer, not a fallback from one.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from karani.analysis.cache import CacheKey, ResponseCache
from karani.analysis.client import ModelClient
from karani.analysis.prompts import ENTAILMENT_SYSTEM, build_entailment_prompt
from karani.canon import sha256_text
from karani.config import MODEL_VERIFY, PROMPT_VERSION, TEMPERATURE


@dataclass(frozen=True)
class EntailmentResult:
    supported: bool
    reason: str
    checked: bool = True
    model_id: str = MODEL_VERIFY

    @property
    def disagreement(self) -> bool:
        return self.checked and not self.supported


def check_entailment(
    *,
    claim: str,
    passage: str,
    client: ModelClient,
    cache: ResponseCache,
    rendition_id: str,
) -> EntailmentResult:
    """Run one entailment check on the verification-tier model.

    Cached on the claim/passage pair rather than on the observation, so that two observations
    making the same claim about the same passage — which happens across re-runs and across
    the retry path — are checked once.
    """
    key = CacheKey(
        rendition_id=rendition_id,
        prompt_version=f"{PROMPT_VERSION}-entail",
        model_id=MODEL_VERIFY,
        temperature=TEMPERATURE,
        attempt=0,
        feedback_hash=sha256_text(f"{claim}␟{passage}")[:32],
        criterion_scope="entailment",
    )

    response = client.generate(
        system=ENTAILMENT_SYSTEM,
        prompt=build_entailment_prompt(claim, passage),
        model_id=MODEL_VERIFY,
        key=key,
    )

    try:
        parsed = json.loads(_strip_fence(response.text))
        supported = bool(parsed["supported"])
        reason = str(parsed.get("reason", ""))
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        # An unparseable verdict is not a passing verdict. Treating a malformed response as
        # "supported" would let every parse failure silently become an approval, which is the
        # direction a check must never fail in.
        return EntailmentResult(
            supported=False,
            reason=f"entailment response could not be parsed ({type(exc).__name__}); "
            f"routing to human review rather than assuming support",
            checked=True,
        )

    return EntailmentResult(supported=supported, reason=reason, checked=True)


def _strip_fence(text: str) -> str:
    """Tolerate a markdown fence around JSON.

    The prompt asks for bare JSON and the request pins a JSON response type, but models
    occasionally fence anyway. Failing the whole check over three backticks would turn a
    formatting quirk into a human-review item and bury the queue in noise.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped
