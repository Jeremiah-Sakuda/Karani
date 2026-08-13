#!/usr/bin/env python3
"""Generate the scale corpus (KAR-206) — ~150 submissions, reproducible from a committed seed.

**What this corpus is for, and what it is not for.** The scale run measures *system*
behaviour: does the fan-out complete, does the join hold under load, what does the retry
distribution look like, what does it cost. Every claim made from it is a claim about Karani.
None is a claim about the essays, because these are parameterised recombinations, not
writing, and describing them as a sample of student work would be a lie about what they are.

That distinction is why this generator is a template engine rather than a model call. A
generated corpus that *looked* like fifteen more authored essays would invite exactly the
claim it cannot support. This one is visibly combinatorial when you read it, which is honest
about its own nature.

**Byte-identical on regeneration.** Seeded `random.Random`, sorted iteration everywhere, no
clock, no environment. The acceptance criterion is that re-running produces no diff, which is
what makes the scale run's inputs auditable rather than merely asserted.

The output is git-ignored: a corpus reproducible from a seed does not belong in history, and
committing 150 files would bury the fifteen authored fixtures that actually matter.
"""

from __future__ import annotations

import argparse
import hashlib
import random
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SEED = 20260812

TOPICS = [
    ("municipal broadband", "the city", "a fiber network", "subscription rates"),
    ("curbside composting", "the county", "an organics program", "diversion rates"),
    ("bus rapid transit", "the transit authority", "a dedicated lane", "ridership"),
    ("public library hours", "the library board", "extended weekend service", "visit counts"),
    ("residential solar permitting", "the planning office", "a permit fast-track", "install times"),
    ("school start times", "the district", "a later first bell", "attendance"),
]

REGISTERS = [
    ("formal", "It is evident that", "Consequently,", "In conclusion,"),
    ("plain", "The record shows that", "So", "Overall,"),
    ("conversational", "Here's the thing:", "And", "Anyway,"),
    ("bureaucratic", "It should be noted that", "Accordingly,", "In summation,"),
]

STRUCTURES = ["five_paragraph", "enumerated", "narrative_frame", "point_counterpoint"]

# Each generated submission carries one or two of these, so the scale run exercises the same
# routing paths as the authored corpus rather than being 150 clean documents.
ERROR_PATTERNS = [
    "no_counterargument",   # drives kind=no_evidence on c4
    "unattributed_quote",   # drives a citation the validator can reject
    "orphan_question",      # the s09 over-read shape
    "under_length",         # a short submission
    "citation_no_page",     # sloppy sourcing
    "none",
]

BODY = """{opener} {topic} has become a recurring item before {actor}. This paper argues that
{actor} should {position} {thing}.

{connector} the strongest evidence concerns cost. A {year} review of comparable programs put
first-year {metric} at {pct} percent, against a projection of {proj} percent ({cite}). The gap
is not evidence of failure so much as evidence that the projection was built on the wrong
comparison class.

{connector} the operational question is separable from the political one. {actor} already
maintains {thing_alt}, and the staff who would run {thing} are the staff who already run that.
The marginal capability required is smaller than the debate suggests ({cite2}).

{counter_block}

{closer} the case for {position_noun} rests less on enthusiasm than on the absence of a
workable alternative. {actor} can act, or it can wait for someone else to, and waiting has a
cost that does not appear on any balance sheet.
"""

COUNTER_BLOCKS = {
    "present": """The obvious objection is that {actor} lacks the technical depth to operate
{thing} over a full replacement cycle. That objection has force, and the failures on record
mostly involve jurisdictions that treated the build as a construction project rather than as an
ongoing operation. The distinction matters: the programs that met their obligations separated
the durable layer from the perishable one and financed each on its own schedule.""",
    "orphan_question": """But can {actor} really be trusted to operate {thing} competently over
twenty years?

{connector} the second argument concerns equity of access across the service area.""",
    "absent": """{connector} the third argument concerns equity of access, which the current
arrangement handles poorly across the outer service area.""",
}


def generate(index: int, rng: random.Random) -> tuple[str, str]:
    topic, actor, thing, metric = TOPICS[index % len(TOPICS)]
    register, opener, connector, closer = REGISTERS[rng.randrange(len(REGISTERS))]
    structure = STRUCTURES[rng.randrange(len(STRUCTURES))]
    errors = rng.sample(ERROR_PATTERNS, k=rng.choice([1, 1, 2]))

    stance = rng.choice(["build and operate", "decline to build", "study before committing"])
    stance_noun = {"build and operate": "public operation",
                   "decline to build": "restraint",
                   "study before committing": "a study period"}[stance]

    if "no_counterargument" in errors:
        counter = COUNTER_BLOCKS["absent"]
    elif "orphan_question" in errors:
        counter = COUNTER_BLOCKS["orphan_question"]
    else:
        counter = COUNTER_BLOCKS["present"]

    surname = f"{rng.choice('BCDFGHKLMNPRSTVW')}{rng.choice(['aldwin','ernier','orley','anta','ilburn','oxley','underson','ashiro','elmar','ovic'])}"
    page = rng.randrange(11, 399)
    cite = f"({surname} {page})"
    cite2 = f"({surname} {page + rng.randrange(2, 9)})" if "citation_no_page" not in errors else f"({surname})"

    body = BODY.format(
        opener=opener, topic=topic, actor=actor, thing=thing, metric=metric,
        position=stance, position_noun=stance_noun, connector=connector, closer=closer,
        year=2021 + (index % 5), pct=rng.randrange(28, 88), proj=rng.randrange(40, 95),
        cite=cite, cite2=cite2, thing_alt=rng.choice(["a water utility", "a fleet garage",
                                                      "a records office", "a street department"]),
        counter_block=counter.format(actor=actor, thing=thing, connector=connector),
    )

    if "unattributed_quote" in errors:
        body += (
            '\n\nOne assessment described the arrangement as "an arrangement that survives '
            'because no one has priced the alternative," a judgement the record supports.\n'
        )
    if "under_length" in errors:
        body = "\n\n".join(body.split("\n\n")[:2])

    title = f"{topic.title()}: A Case for {stance_noun.title()}"
    header = f"# {title}\n\n"
    meta = f"<!-- generated: register={register} structure={structure} errors={','.join(sorted(errors))} -->\n\n"
    return title, header + meta + body.strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(REPO / "fixtures" / "scale"))
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for existing in out.glob("g*.md"):
        existing.unlink()

    rng = random.Random(args.seed)
    digest = hashlib.sha256()
    for index in range(args.count):
        _, content = generate(index, rng)
        path = out / f"g{index:04d}.md"
        path.write_text(content, encoding="utf-8")
        digest.update(content.encode("utf-8"))

    (out / "rubric.json").write_text(
        (REPO / "fixtures" / "rubric.json").read_text(encoding="utf-8"), encoding="utf-8"
    )

    print(f"wrote {args.count} submissions to {out}")
    print(f"seed              {args.seed}")
    print(f"corpus digest     {digest.hexdigest()}")
    print("\nRegeneration from the same seed is byte-identical; the digest above is the check.")
    print("This corpus is generated, is disclosed as generated, and supports claims about")
    print("system behaviour only -- never claims about the writing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
