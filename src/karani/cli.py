"""Karani's command line.

karani run       ingest -> analyse -> validate -> render, over a source directory
karani docket    serve the docket over a run, or over the committed golden log
karani verify    re-fold an artifact from its events and compare
karani preflight resolve the pinned model IDs against the live publisher catalogue
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from karani.analysis.cache import MissingCacheEntry, ResponseCache
from karani.analysis.client import open_client
from karani.analysis.prompts import Criterion
from karani.armor.scan import open_scanner
from karani.canon import canonical_json
from karani.config import MODEL_ANALYSIS, MODEL_VERIFY, REPO_ROOT, Settings
from karani.ingest.source import open_source
from karani.render import render
from karani.store import open_store
from karani.store.local import read_jsonl_log


def load_criteria(rubric_path: Path) -> list[Criterion]:
    payload = json.loads(rubric_path.read_text(encoding="utf-8"))
    return [
        Criterion(
            criterion_id=c["criterion_id"],
            name=c["name"],
            description=c["description"],
        )
        for c in payload["criteria"]
    ]


def cmd_run(args: argparse.Namespace) -> int:
    from karani.analysis.dispatcher import run_pipeline

    settings = Settings.from_env()
    source_dir = Path(args.source)
    rubric = Path(args.rubric) if args.rubric else source_dir / "rubric.json"
    if not rubric.exists():
        rubric = REPO_ROOT / "fixtures" / "rubric.json"

    criteria = load_criteria(rubric)
    cache = ResponseCache(settings.cache_dir)
    # --offline and --live both DECIDE the backend. `--live` used to be decorative: it was
    # declared, never read, and the backend came only from KARANI_MODEL_BACKEND (default
    # "cache"). So `karani run --live` silently replayed the committed cache while printing
    # nothing to contradict the operator -- and RUNBOOK beat 2 is "trigger it live" on camera.
    # A cache replay narrated as a live call is precisely the substitution this project's
    # thesis forbids, so the flag now means what it says.
    if args.offline and args.live:
        print("--offline and --live are mutually exclusive", file=sys.stderr)
        return 2
    if args.live:
        backend = "vertex"
    elif args.offline:
        backend = "cache"
    else:
        backend = settings.model_backend
    client = open_client(backend, cache, project=settings.project, location=settings.location)
    scanner = open_scanner(template=settings.armor_template, project=settings.project)

    run_id = args.run_id or f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    store = open_store(settings)

    print(f"run       {run_id}")
    print(f"source    {source_dir}")
    print(f"models    analysis={MODEL_ANALYSIS}  verify={MODEL_VERIFY}  backend={backend}")
    print(f"scanner   {scanner.name}")
    print(f"store     {settings.store_backend}")
    print()

    # The run executes through the ADK topology -- dispatcher, analyst+validator, anomaly
    # triage -- rather than calling run_pipeline directly. That is what makes "Google ADK" a
    # statement about the execution path instead of about a module that exists.
    context: dict = {
        "run_id": run_id,
        "source": open_source("local", source_dir),
        "criteria": criteria,
        "store": store,
        "client": client,
        "cache": cache,
        "scanner": scanner,
        "max_workers": args.workers,
        "project": settings.project,
    }

    try:
        if args.no_adk:
            summary = run_pipeline(
                **{k: v for k, v in context.items() if k != "project"}
                | {"project": settings.project}
            )
        else:
            import asyncio

            from karani.analysis.adk_agents import run_with_adk

            shared = asyncio.run(run_with_adk(context))
            assert shared.summary is not None
            summary = shared.summary
            print("agent trace")
            for line in shared.trace:
                print(f"  {line}")
            print()
    except MissingCacheEntry as exc:
        # The offline path never invents a model response, so an empty cache stops the run.
        # What matters here is what the operator is told: this is a setup state, not a broken
        # system and not a problem with anyone's submission. Then fall through to something
        # that actually works, because a demo that prints a stack trace and exits is worse
        # than no demo.
        print("\n" + "─" * 78)
        print("The offline cache has no recorded model responses for these submissions.")
        print("─" * 78)
        print(
            "\nEverything up to the model boundary ran: submissions were discovered, frozen\n"
            "into immutable renditions, span registries were minted, and the injection scan\n"
            "completed. What is missing is the recorded output of a real model run.\n"
            "\nKarani will not fabricate one. A stubbed response would make this demo a\n"
            "different system from the one in the video, which is the one thing an offline\n"
            "demo must never be.\n"
        )
        print("To record a real run once and make this path work offline forever:\n")
        print("    gcloud auth application-default login")
        print("    export GOOGLE_CLOUD_PROJECT=<your-project>")
        print("    make record-cache      # runs live, writes fixtures/cache/, then commit it\n")
        print("Meanwhile, the committed reference run will serve. Stated precisely, because")
        print("it matters: its event log is hand-constructed, not the output of a model run.")
        print("It exercises all six terminal outcomes and every rendering path, with no model")
        print("and no cloud — but the observations in it were authored, not drafted:\n")
        print("    make docket-golden\n")
        print(f"(detail: {exc.args[0].splitlines()[0] if exc.args else exc})")
        print("─" * 78 + "\n")

        if args.open_docket:
            from karani.docket.server import serve

            golden = read_jsonl_log(settings.golden_log)
            serve(
                render(golden[0].run_id if golden else "run-golden", golden),
                port=int(args.port),
                store=store,
            )
        return 3

    rendered = render(run_id, store.read_run(run_id))
    out_dir = REPO_ROOT / "out" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rendered.json").write_text(rendered.to_json(), encoding="utf-8")

    print(
        f"completed {len(summary.completed)}   failed {len(summary.failed)}   "
        f"abandoned {len(summary.abandoned)}"
    )
    print(f"events    {summary.events_written}")
    served = (
        "LIVE Vertex AI"
        if backend == "vertex" and summary.cached_calls < summary.model_calls
        else "committed cache (no model was called)"
        if summary.cached_calls == summary.model_calls
        else "mixed"
    )
    print(f"model     {summary.model_calls} calls ({summary.cached_calls} from cache) -- {served}")
    print()
    print("terminal outcomes")
    for name, count in sorted(rendered.overview["terminal_outcomes"].items()):
        if count:
            print(f"  {name:<26} {count}")
    if rendered.anomalies:
        print("\nanomaly queue")
        kinds: dict[str, int] = {}
        for item in rendered.anomalies:
            kinds[item.kind] = kinds.get(item.kind, 0) + 1
        for kind, count in sorted(kinds.items()):
            print(f"  {kind:<26} {count}")
    print(f"\nartifact  {out_dir / 'rendered.json'}")

    if args.open_docket:
        from karani.docket.server import serve

        # The store is passed so edit-as-supersession works. Without it the /edit route
        # returns early and the instructor-disagrees flow -- the whole point of ratification
        # -- silently does nothing.
        serve(rendered, port=int(args.port), store=store)

    # The artifact is on disk and the log is durable. If a worker never returned, exit rather
    # than letting the interpreter's atexit join hold a finished Cloud Run Job open until its
    # task timeout. Returns normally when nothing is outstanding.
    if summary.threads_outstanding:
        from karani.runtime import hard_exit

        hard_exit(0, reason=f"T_max reached with {summary.threads_outstanding} worker(s) blocked")
    return 0


def cmd_docket(args: argparse.Namespace) -> int:
    """Serve the docket over the most recent completed run.

    The default is deliberately *the store*, not a fixture. On the deployed path the store is
    Firestore, so the hosted docket shows what the nightly Cloud Run Job actually produced --
    which is the whole Taskmaster narrative: the unattended overnight run is what the
    instructor finds in the morning.

    A review caught this pointing the wrong way. The Job wrote Firestore while the docket
    service was deployed with a local backend and a `--golden fixtures/...` command, so the
    two were separate chains: the public UI served a committed fixture and the live analysis
    went somewhere nobody could see.

    The committed run is the *fallback*, for a fresh clone with no runs yet, and it is
    labelled as a recorded run on the page rather than passed off as live.
    """
    from karani.docket.server import serve

    settings = Settings.from_env()
    store = None

    if args.golden:
        path = Path(args.golden)
        events = read_jsonl_log(path)
        run_id = events[0].run_id if events else "run-golden"
        print(f"serving the committed recorded run: {path} ({len(events)} events)")
    else:
        try:
            store = open_store(settings)
            runs = store.list_runs()
        except Exception as exc:  # noqa: BLE001 - an unreachable store falls back, not crashes
            print(
                f"store unavailable ({type(exc).__name__}); falling back to the recorded run",
                file=sys.stderr,
            )
            store, runs = None, []

        run_id = args.run_id or (runs[-1] if runs else "")
        if run_id and store is not None:
            # A run that cannot be read or rendered must not take the docket down with it.
            # This is the container's entrypoint: an exception here is not a stack trace an
            # operator sees, it is the hosted docket going dark -- during judging, over one
            # malformed document. Fall back to the committed run and say so.
            try:
                events = store.read_run(run_id)
                render(run_id, events)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"run {run_id} failed to load ({type(exc).__name__}); "
                    f"falling back to the recorded run",
                    file=sys.stderr,
                )
                events = read_jsonl_log(settings.golden_log)
                run_id = events[0].run_id if events else "run-recorded"
            else:
                print(
                    f"serving run {run_id} from the {settings.store_backend} store "
                    f"({len(events)} events)"
                )
        else:
            events = read_jsonl_log(settings.golden_log)
            run_id = events[0].run_id if events else "run-recorded"
            print(
                f"no runs in the store; serving the committed recorded run ({len(events)} events)"
            )

    serve(render(run_id, events), port=int(args.port), store=store)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-fold an artifact from its own event range and compare (KAR-504).

    The comparison is over the **whole artifact**, not over its provenance block. Comparing
    only `range_hash` would be circular: that hash is computed from the event log, so a
    re-fold of the same log reproduces it no matter what the artifact body says. An artifact
    whose every observation had been rewritten to "this paper earns an A" would verify OK.

    So the artifact is re-serialised through the same canonical encoder that wrote it and
    compared byte-for-byte, and the provenance block is checked separately — an artifact can
    diverge either by claiming the wrong events or by not being the fold of the right ones.
    """
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    events = read_jsonl_log(Path(args.log))
    rebuilt = render(artifact["run_id"], events)
    expected = rebuilt.to_dict()

    claimed = artifact.get("generated_from", {}).get("range_hash")
    actual = rebuilt.range_hash

    if claimed != actual:
        print("FAIL artifact does not match a re-fold of its events (event range differs)")
        print(f"  claimed {claimed}")
        print(f"  actual  {actual}")
        return 1

    if canonical_json(artifact) == canonical_json(expected):
        print(f"OK   artifact matches a re-fold of its events (range hash {actual[:16]}…)")
        return 0

    print("FAIL artifact does not match a re-fold of its events (content differs)")
    print(f"  the event range hashes equal ({actual[:16]}…), so the log is the one claimed,")
    print("  but folding it does not reproduce this artifact. It has been altered in place.")
    for section in sorted(set(artifact) | set(expected)):
        if canonical_json(artifact.get(section)) != canonical_json(expected.get(section)):
            print(f"  differs: {section}")
    return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Resolve every pinned model ID against the live catalogue.

    Exists because the PRD pinned a model that does not exist (`gemini-3.5-pro`), and the
    failure would otherwise have surfaced at the first live call — after the architecture
    was frozen. A pinned ID is a claim about the world, so it gets checked like one.
    """
    settings = Settings.from_env()
    if not settings.project:
        print("GOOGLE_CLOUD_PROJECT is not set; cannot resolve model IDs", file=sys.stderr)
        return 2

    from google import genai

    from karani.analysis.client import _resolve_credentials

    # The same credential resolution as the live pipeline: ADC when present, the gcloud
    # CLI's own token otherwise. This check ran on deploy day with neither wired in and
    # reported both pinned models as failures -- with advice to "fix config.py" -- when the
    # models were fine and the preflight itself was the only thing that couldn't
    # authenticate. A check that fails for a reason its subject doesn't have is worse than
    # no check: it sends the operator to fix the wrong thing, on the day there is no time.
    client = genai.Client(
        vertexai=True,
        project=settings.project,
        location=settings.location,
        credentials=_resolve_credentials(),
    )
    failures = 0
    for role, model_id in (("analysis", MODEL_ANALYSIS), ("verify", MODEL_VERIFY)):
        try:
            client.models.generate_content(
                model=model_id,
                contents="ok",
                config={"temperature": 0, "max_output_tokens": 4},
            )
            print(f"  OK   {role:<9} {model_id}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"  FAIL {role:<9} {model_id}: {type(exc).__name__}: {exc}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="karani", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="ingest, analyse, validate, render")
    run.add_argument("--source", default="fixtures")
    run.add_argument("--rubric", default="")
    run.add_argument("--run-id", default="")
    run.add_argument("--workers", type=int, default=8)
    run.add_argument(
        "--offline", action="store_true", help="replay the committed cache; never call a model"
    )
    run.add_argument(
        "--no-adk", action="store_true", help="bypass the ADK topology (fallback path)"
    )
    run.add_argument("--live", action="store_true", help="call Vertex AI; costs money")
    run.add_argument("--open-docket", action="store_true")
    run.add_argument("--port", default="8080")
    run.set_defaults(func=cmd_run)

    docket = sub.add_parser("docket", help="serve the docket")
    docket.add_argument("--golden", default="")
    docket.add_argument("--run-id", default="")
    docket.add_argument("--port", default="8080")
    docket.set_defaults(func=cmd_docket)

    verify = sub.add_parser("verify", help="re-fold an artifact and compare")
    verify.add_argument("--artifact", required=True)
    verify.add_argument("--log", required=True)
    verify.set_defaults(func=cmd_verify)

    pre = sub.add_parser("preflight", help="resolve pinned model IDs against the catalogue")
    pre.set_defaults(func=cmd_preflight)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
