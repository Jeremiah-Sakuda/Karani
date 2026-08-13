"""The verdict lint (KAR-309) — layer 4 of 4, and the weakest of the four.

Karani says so out loud, including on the public challenge page, because a system that
presents its weakest defence as its strongest is inviting exactly the attack that defeats it.
The four layers, in order of how much weight they actually carry:

    1. Schema      -- there is no field a verdict could occupy. Structural.
    2. IAM         -- `grades/` is unwritable by every pipeline identity. Structural.
    3. Gate        -- uncited and unsupported claims never reach an artifact. Procedural.
    4. Lint        -- verdict-shaped *language* is masked at render time. Cosmetic.

The lint catches a model that says "excellent work" in prose. It cannot catch a model that
says the same thing in a sentence no token list anticipated, and it is not asked to: if
layers 1 and 2 fail, nothing here matters, and if they hold, nothing here is load-bearing.

**The split, which is the whole subtlety.** The lint treats two kinds of text completely
differently, because they are two different speakers:

- **Generated text** is Karani speaking. Verdict language here is masked, visibly, with a
  notice saying so.
- **`citation.quote` is the student speaking.** It is never masked. Redacting a student's own
  words inside the evidence for a claim about their work would be indefensible — it hides the
  thing the instructor is supposed to be evaluating, on the grounds that the student used a
  word Karani has opinions about.

The one exception: if the source span carries `InjectionDetected`, the quote is masked with
the injection notice. At that point the "student's words" premise no longer holds — the text
may be an instruction aimed at the reader rather than prose the student wrote.

**And the false-positive class this cost us once.** A student who writes *"this policy is
excellent"* in earnest is evaluating a policy, not their own essay. An earlier version
flagged that, which would have put a review chip on honest student prose for using an
ordinary adjective. So a flagged quote requires the verdict term to attach to a
**work-referent** — essay, paper, submission, work, assignment — not to whatever the student
happens to be arguing about. The remaining boundary is stated rather than hidden: paraphrase
gets through. *"The writer has done what the assignment asked, and done it well"* expresses a
level of quality and matches nothing here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REDACTION_NOTICE = "[verdict token redacted — Karani will not display a grade]"
INJECTION_NOTICE = "[quote masked — source passage flagged for injected instructions]"

# Nouns that refer to the student's work itself. A quality word attached to one of these is
# a verdict about the submission; attached to anything else it is the student's argument.
_WORK_REFERENT = r"(?:essay|paper|submission|work|assignment|response|writing|piece|draft|composition)"

_QUALITY = (
    r"excellent|outstanding|exemplary|superior|exceptional|flawless|masterful|"
    r"poor|weak|inadequate|deficient|unsatisfactory|mediocre|subpar|lacking|"
    r"strong|solid|competent|satisfactory|proficient|adequate|accomplished"
)

_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Letter grades. Bounded so that "a B in the diagram" or a stray capital does not match:
    # the letter must be grade-shaped *and* grade-positioned. Three positions, because a
    # single pattern kept letting one of them through — see the fixed-point note below.
    (
        "letter_grade",
        re.compile(
            # "a grade of B+", "scored a C"
            r"\b(?:grade|mark|score)[ds]?\s+(?:of\s+|a[n]?\s+)?(?<![A-Za-z])[A-DF][+-]?(?![A-Za-z])"
            # "an A on this paper", "a B- for the essay"
            r"|\b(?:an?)\s+(?<![A-Za-z])[A-DF][+-]?(?![A-Za-z])"
            r"(?=\s*(?:grade|range|work|paper|essay|level|for|on|[.,;)])|$)"
            # bare, in grade position: "B+ work", "C."
            r"|\b(?<![A-Za-z])[A-DF][+-]?(?![A-Za-z])"
            r"(?=\s*(?:grade|range|work|paper|essay|level|[.,;)])|$)",
        ),
    ),
    # Numeric scores in every shape a model reaches for.
    ("percentage_score", re.compile(r"\b\d{1,3}\s?%(?:\s*(?:grade|score|mark))?", re.IGNORECASE)),
    ("fraction_score", re.compile(r"\b\d{1,3}\s*(?:/|out\s+of)\s*\d{1,3}\b", re.IGNORECASE)),
    ("points_awarded", re.compile(r"\b\d{1,3}\s*(?:points?|pts?|marks?)\b", re.IGNORECASE)),
    # Rubric-level enums -- verdicts in costume, and the reason `meets`/`exceeds`/`below`
    # are banned as schema fields too.
    (
        "rubric_level",
        re.compile(
            r"\b(?:meets|exceeds|below|approaching|not\s+meeting)\s+(?:expectations?|standards?|"
            r"the\s+standard|criteri(?:on|a))\b|\b(?:needs\s+improvement|developing|emerging|"
            r"beginning|mastery|distinction|merit|pass|fail(?:ing)?)\b",
            re.IGNORECASE,
        ),
    ),
    # A quality judgement attached to the student's work.
    (
        "quality_verdict",
        re.compile(
            rf"\b(?:{_QUALITY})\b[^.\n]{{0,30}}?\b{_WORK_REFERENT}\b|"
            rf"\b{_WORK_REFERENT}\b[^.\n]{{0,30}}?\b(?:is|was|are|were|remains)\b[^.\n]{{0,20}}?\b(?:{_QUALITY})\b",
            re.IGNORECASE,
        ),
    ),
    # Explicit recommendation of an outcome.
    (
        "recommendation",
        re.compile(
            r"\b(?:deserves?|merits?|warrants?|should\s+(?:receive|get|be\s+(?:given|awarded))|"
            r"I\s+would\s+(?:give|award|assign)|recommend\s+(?:a|an))\b[^.\n]{0,30}?"
            r"\b(?:grade|mark|score|[A-DF][+-]?|full\s+credit|credit)\b",
            re.IGNORECASE,
        ),
    ),
)


@dataclass
class LintResult:
    text: str
    masked: bool = False
    rules_fired: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.masked


@dataclass
class QuoteLintResult:
    text: str
    masked: bool = False
    flagged: bool = False
    rules_fired: list[str] = field(default_factory=list)


def lint_generated_text(text: str) -> LintResult:
    """Mask verdict language in text Karani wrote. Visibly, never silently.

    The notice is left in place of the token rather than the token being deleted. A silent
    deletion would leave a sentence that reads as though it was always phrased that way,
    which hides that the lint fired — and an instructor who cannot see that something was
    removed cannot judge whether the removal was right.
    """
    fired: list[str] = []
    result = text

    # Applied to a fixed point rather than in a single pass.
    #
    # This is not defensive tidiness; it fixes a real defect. One rule's replacement can
    # consume the *lead-in* to a verdict while leaving the verdict itself on screen: masking
    # "I would award a" out of "I would award a grade of B+ for this work" leaves the B+
    # rendered, which is precisely the thing this layer exists to prevent. Re-running until
    # the text stops changing closes that gap without needing every rule to anticipate every
    # other rule's replacement.
    #
    # Termination: each pass either changes the text or ends the loop, and the notice itself
    # matches no rule (the rules require an uppercase grade letter or a quality word, and the
    # notice contains neither in a matching position). The iteration cap is a backstop
    # against a future rule edit breaking that property, not a load-bearing bound.
    for _ in range(5):
        changed = False
        for rule_name, pattern in _RULES:
            if pattern.search(result):
                fired.append(rule_name)
                result = pattern.sub(REDACTION_NOTICE, result)
                changed = True
        if not changed:
            break

    return LintResult(text=result, masked=bool(fired), rules_fired=sorted(set(fired)))


def lint_quote(quote: str, *, injection_flagged: bool = False) -> QuoteLintResult:
    """Handle a student's own words. Flag at most; mask only for a flagged source span.

    The flag is deliberately narrow. It fires when the student's text evaluates *their own
    work* — the case where a reader skimming an evidence sheet could mistake the quotation
    for Karani's assessment. It does not fire when the student evaluates the thing they are
    arguing about, which is what students spend entire essays doing.
    """
    if injection_flagged:
        # The premise "these are the student's words" no longer holds: the passage may be an
        # instruction aimed at whatever is reading the document.
        return QuoteLintResult(text=INJECTION_NOTICE, masked=True, flagged=True,
                               rules_fired=["injection_flagged_span"])

    fired = [
        name
        for name, pattern in _RULES
        if name in ("quality_verdict", "rubric_level", "letter_grade", "recommendation")
        and pattern.search(quote)
    ]

    # Never masked. The text is returned exactly as the student wrote it, chip or no chip.
    return QuoteLintResult(text=quote, masked=False, flagged=bool(fired),
                           rules_fired=sorted(set(fired)))


def lint_observation(observation_text: str, quote: str | None, *, injection_flagged: bool = False):
    """Apply the split to one observation. Returns `(generated, quote_result_or_None)`."""
    generated = lint_generated_text(observation_text)
    quote_result = (
        lint_quote(quote, injection_flagged=injection_flagged) if quote is not None else None
    )
    return generated, quote_result
