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
    backend = "cache" if args.offline else settings.model_backend
    client = open_client(backend, cache, project=settings.project, location=settings.location)
    scanner = open_scanner(
        template=settings.armor_template, project=settings.project
    )

    run_id = args.run_id or f"run-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    store = open_store(settings)

    print(f"run       {run_id}")
    print(f"source    {source_dir}")
    print(f"models    analysis={MODEL_ANALYSIS}  verify={MODEL_VERIFY}  backend={backend}")
    print(f"scanner   {scanner.name}")
    print(f"store     {settings.store_backend}")
    print()

    try:
        summary = run_pipeline(
            run_id=run_id,
            source=open_source("local", source_dir),
            criteria=criteria,
            store=store,
            client=client,
            cache=cache,
            scanner=scanner,
            max_workers=args.workers,
        )
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
            serve(render(golden[0].run_id if golden else "run-golden", golden), port=int(args.port))
        return 3

    rendered = render(run_id, store.read_run(run_id))
    out_dir = REPO_ROOT / "out" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rendered.json").write_text(rendered.to_json(), encoding="utf-8")

    print(f"completed {len(summary.completed)}   failed {len(summary.failed)}   "
          f"abandoned {len(summary.abandoned)}")
    print(f"events    {summary.events_written}")
    print(f"model     {summary.model_calls} calls ({summary.cached_calls} from cache)")
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

        serve(rendered, port=int(args.port))
    return 0


def cmd_docket(args: argparse.Namespace) -> int:
    from karani.docket.server import serve

    settings = Settings.from_env()
    if args.golden:
        path = Path(args.golden)
        events = read_jsonl_log(path)
        run_id = events[0].run_id if events else "run-golden"
        print(f"serving the committed golden log: {path} ({len(events)} events)")
    else:
        store = open_store(settings)
        run_id = args.run_id or (store.list_runs() or [""])[-1]
        if not run_id:
            print("no runs found; try --golden fixtures/golden-log.jsonl", file=sys.stderr)
            return 1
        events = store.read_run(run_id)

    serve(render(run_id, events), port=int(args.port))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Re-fold an artifact from its own event range and compare (KAR-504)."""
    artifact = json.loads(Path(args.artifact).read_text(encoding="utf-8"))
    events = read_jsonl_log(Path(args.log))
    rebuilt = render(artifact["run_id"], events)

    claimed = artifact["generated_from"]["range_hash"]
    actual = rebuilt.range_hash
    if claimed == actual:
        print(f"OK   artifact matches a re-fold of its events (range hash {actual[:16]}…)")
        return 0
    print("FAIL artifact does not match a re-fold of its events")
    print(f"  claimed {claimed}")
    print(f"  actual  {actual}")
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

    client = genai.Client(vertexai=True, project=settings.project, location=settings.location)
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
    run.add_argument("--offline", action="store_true", help="replay the committed cache; never call a model")
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
