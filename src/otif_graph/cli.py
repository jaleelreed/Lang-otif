"""CLI: python -m otif_graph.cli run|resume|demo

FakeLLM by default; --local uses Ollama if a server is reachable.
"""
import argparse
import json
import os
import pathlib
import sys
import uuid

# No telemetry: make sure LangSmith tracing is off before langchain imports.
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ.pop("LANGCHAIN_API_KEY", None)

from langgraph.types import Command

from otif_graph.graph import build_graph
from otif_graph.llm import OLLAMA_HELP, FakeLLM, OllamaLLM, ollama_reachable

FIXTURES_DIR = pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "sample_requests"
DEFAULT_DB = "otif_checkpoints.sqlite"


def get_llm(local: bool):
    if not local:
        return FakeLLM()
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    if not ollama_reachable(base):
        print(OLLAMA_HELP)
        sys.exit(1)
    return OllamaLLM(base_url=base)


def print_outcome(out: dict, thread_id: str) -> None:
    print(f"\nthread_id: {thread_id}")
    print("audit log:")
    for line in out.get("audit_log", []):
        print(f"  {line}")
    interrupts = out.get("__interrupt__")
    if interrupts:
        payload = interrupts[0].value
        print("\n*** INTERRUPTED — human review required ***")
        print(json.dumps(payload, indent=2))
        print(f"\nresume with: python -m otif_graph.cli resume {thread_id} "
              "approve|reject|rescore")
        return
    result = out.get("result")
    if result is not None:
        print(f"\nresult: OTIF {result.otif_pct}% (on-time {result.on_time_pct}%, "
              f"in-full {result.in_full_pct}%) grade {result.grade}")
        if result.per_shipment_flags:
            print(f"flags: {result.per_shipment_flags}")
    if out.get("narrative"):
        print(f"\nnarrative:\n{out['narrative']}")


def cmd_run(args) -> dict:
    path = FIXTURES_DIR / f"{args.fixture}.txt"
    if not path.exists():
        options = ", ".join(sorted(p.stem for p in FIXTURES_DIR.glob("*.txt")))
        sys.exit(f"unknown fixture {args.fixture!r}; options: {options}")
    thread_id = args.thread_id or uuid.uuid4().hex[:8]
    graph = build_graph(get_llm(args.local), args.db)
    out = graph.invoke({"raw_request": path.read_text(encoding="utf-8")},
                       config={"configurable": {"thread_id": thread_id}})
    print_outcome(out, thread_id)
    return out


def cmd_resume(args) -> dict:
    graph = build_graph(get_llm(args.local), args.db)
    out = graph.invoke(Command(resume=args.decision),
                       config={"configurable": {"thread_id": args.thread_id}})
    print_outcome(out, args.thread_id)
    return out


def cmd_demo(args) -> None:
    graph = build_graph(get_llm(args.local), args.db)

    def run(fixture: str, thread_id: str) -> dict:
        text = (FIXTURES_DIR / f"{fixture}.txt").read_text(encoding="utf-8")
        return graph.invoke({"raw_request": text},
                            config={"configurable": {"thread_id": thread_id}})

    print("=" * 70)
    print("DEMO 1/3 — blue_ridge: clean pass (intake -> scoring -> explainer)")
    print_outcome(run("blue_ridge", "demo-clean"), "demo-clean")

    print("\n" + "=" * 70)
    print("DEMO 2/3 — meridian: low OTIF triggers escalation interrupt")
    print_outcome(run("meridian", "demo-escalation"), "demo-escalation")
    print("\n--- resuming demo-escalation with decision: approve ---")
    out = graph.invoke(Command(resume="approve"),
                       config={"configurable": {"thread_id": "demo-escalation"}})
    print_outcome(out, "demo-escalation")

    print("\n" + "=" * 70)
    print("DEMO 3/3 — cascade: malformed request exercises the intake retry path")
    print_outcome(run("cascade", "demo-retry"), "demo-retry")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="otif_graph.cli")
    parser.add_argument("--local", action="store_true",
                        help="use a local Ollama model instead of FakeLLM")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="path to the SQLite checkpoint database")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="run a sample request")
    p_run.add_argument("fixture")
    p_run.add_argument("--thread-id")
    p_run.set_defaults(func=cmd_run)

    p_resume = sub.add_parser("resume", help="resume an interrupted run")
    p_resume.add_argument("thread_id")
    p_resume.add_argument("decision", choices=["approve", "reject", "rescore"])
    p_resume.set_defaults(func=cmd_resume)

    p_demo = sub.add_parser("demo", help="run all three fixtures")
    p_demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
