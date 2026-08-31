# Scholarship corpus — the second domain

Three synthetic personal statements for an invented scholarship (the Makena Community Fund),
analysed by the **same pipeline, unchanged**, under `fixtures/scholarship/rubric.json`. This
corpus exists to prove a claim about the architecture rather than about essays: the
verdict-incapable pattern is domain-independent. Change the rubric and the pattern holds —
evidence is located and cited, absence is recorded as a finding, and there is still no field
anywhere that could rank one applicant against another.

Everything here is invented: the fund, the towns, the colleges, the programs, the people.
No real applicant's writing, no real entity.

| ID | Built to exercise |
|---|---|
| `a01` | Specifics everywhere: arithmetic of need, named and verifiable involvement, a mechanism for what the award changes. The citation layers have the most to find. |
| `a02` | The generic statement — sincere, fluent, and specific about nothing. **Expected:** `no_evidence` on financial need (c2) and community involvement (c3), because there is genuinely nothing to cite. Tests that vagueness produces *absence of findable evidence*, never a low opinion. |
| `a03` | The reticence case, and the reason humans ratify. The applicant **explicitly declines** to detail family finances and says so, with a verifiable proxy (Pell eligibility, a $4,100 gap). What should evidence-of-need look like here? Karani's answer is to cite the refusal itself and let the committee judge it — which is precisely the judgment a machine must not make. |

**Recorded run:** `fixtures/scholarship-run.jsonl` — live Gemini analysis + entailment, plus
ten real `gemma3:4b` second-reader verdicts (KAR-417), all responses committed to
`fixtures/cache/`. `make demo-scholarship` replays it offline; observation content is
identical to the live recording across all 12 observations.

**Observed vs designed (in the house tradition of publishing the misses):** a02 drew
`no_evidence` on c2 and c3 exactly as designed. Its c1 and c4 observations were accepted on
citations that are honest but thin — "states a goal of pursuing a STEM degree" — which is
itself the demonstration: the evidence sheet shows a committee *how little* is there without
anyone having to say "weak."
