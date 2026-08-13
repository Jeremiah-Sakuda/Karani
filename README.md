# Karani

```bash
make demo
```

Zero credentials. Zero Java. Zero Docker. Runs the whole pipeline over committed fixtures
and opens the docket.

---

*"Clerks prepare the case. Judges decide it. Karani is only ever the clerk."*

Karani is an autonomous overnight batch agent that prepares grading **evidence** for
instructors and is architecturally incapable of issuing a grade.

**Build status: in progress.** This README is written section by section as each section
becomes true. A section that is absent is absent because the thing it would describe does
not exist yet — it is not an oversight, and it will not be filled with a plausible
description in the meantime. The full README is specified in
[docs/PRD.md](docs/PRD.md) KAR-502.

Current state:

- [x] Phase 0 — foundations, compliance tooling, gates
- [ ] Phase 1 — spine: schema, append-only log, `render()` fold, citation validator
- [ ] Phase 2 — fixtures
- [ ] Phase 3 — core pipeline
- [ ] Phase 4 — docket, delivery, deploy
- [ ] Phase 5 — reproducibility and documentation
- [ ] Phase 6 — video, bonus, submission

## Documents

| Document | What it is |
|---|---|
| [docs/PRD.md](docs/PRD.md) | The governing specification. 72 numbered requirements, each with an acceptance criterion naming the property it proves |
| [AGENTS.md](AGENTS.md) | Standing build context: invariants, guardrails, non-goals, language discipline |
| [docs/GATE.md](docs/GATE.md) | Three dated gates with consequences pre-committed before the evidence arrives |
| [docs/DEVIATIONS.md](docs/DEVIATIONS.md) | Every departure from the PRD, with what was rejected and why |
| [docs/FINDINGS.md](docs/FINDINGS.md) | Measured numbers and toolchain findings, appended every build day |
| [docs/metrics.json](docs/metrics.json) | The measurement contract. Every published number exists here first, or reads "not yet measured" |
| [docs/compliance.md](docs/compliance.md) | Contest eligibility answers, with open items marked open |

## License

Apache 2.0. See [LICENSE](LICENSE).
