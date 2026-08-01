# otif-langgraph

Agents are for orchestration and language; deterministic code is for anything a
client audits. This repo rebuilds the orchestration slice of my OTIF (On-Time
In-Full) scoring demo in LangGraph as an apples-to-apples comparison with my
cron + headless Claude Code + plain-text-ledger harness. The LLM parses messy
carrier emails into typed records and writes the narrative around the results —
but every number comes from a pure-Python engine with no LLM anywhere in the
call path, enforced by a test that fails the build if `engine.py` or the
scoring node ever imports an LLM, HTTP, or framework module.

## Architecture

```mermaid
flowchart TD
    START([start]) --> intake["intake\nLLM: messy text -> typed ShipmentBatch\n(1 retry with validation error)"]
    intake -->|parsed| scoring["scoring\ndeterministic engine only"]
    intake -->|parse failed twice| escalation
    scoring -->|"otif < 85% or critical flags"| escalation["escalation\ninterrupt(): human review"]
    scoring -->|clean| explainer["explainer\nLLM: narrative around the numbers"]
    escalation -->|approve| explainer
    escalation -->|reject| END([end])
    escalation -->|rescore| intake
    explainer --> END
```

State is a pydantic `GraphState` checkpointed to SQLite by thread_id; every
node appends one line to `audit_log` (my decision-ledger pattern), so node
visit order is assertable in tests and readable in the CLI output.

## Quickstart

**Runs entirely free**: no API keys, no accounts, no telemetry. The default
`FakeLLM` is deterministic and offline; tests and the demo never touch the
network. Ollama is optional if you want a real local model (`--local`).

```bash
pip install -e ".[dev]"
pytest
python -m otif_graph.cli demo
```

The demo runs all three fixtures: a clean pass, a low-OTIF batch that trips
the human-approval interrupt (then resumes with `approve`), and a garbled OCR
scan that fails validation once and exercises the intake retry.

Interrupted runs survive process death. Run to the interrupt, kill the
process, resume from another process — the SQLite checkpoint carries the
state (captured transcript in [docs/resumability-proof.txt](docs/resumability-proof.txt)):

```bash
python -m otif_graph.cli --db proof.sqlite run meridian --thread-id proof-1
python -m otif_graph.cli --db proof.sqlite resume proof-1 approve
```

## Honest comparison: LangGraph vs cron + plain-text ledger

The other side of this comparison is my original harness: cron launching
headless Claude Code sessions with plain-text ledger files as state.

| Dimension | LangGraph build | cron + text-ledger harness |
|---|---|---|
| State/audit visibility | Typed pydantic state; audit_log lives inside the checkpoint, needs code or CLI to read | Ledger is a text file; `cat` is the debugger. TODO(jaleel) |
| Resumability | First-class: SqliteSaver + `interrupt()`, resume by thread_id across processes | Re-run picks up from the ledger, but "where was I" logic is hand-rolled. TODO(jaleel) |
| Human approval gates | `interrupt()` is genuinely good — pause, inspect payload, resume with a decision | A sentinel line in the ledger plus a human editing it; works, but nothing enforces it. TODO(jaleel) |
| Replay/debugging | Checkpoint history per thread; can inspect any step after the fact | Ledger is the replay — linear, greppable, no tooling required. TODO(jaleel) |
| Ceremony/boilerplate | Node factories, routers, checkpointer wiring, serializer allowlist — real overhead before the first useful line | Near zero to start; the cost arrives later as conventions only I remember. TODO(jaleel) |
| Vendor surface | `langgraph` + `langchain-core` + checkpoint libs; API churn is a real maintenance tax | cron, files, and one CLI tool; nothing to version-chase. TODO(jaleel) |

Where LangGraph earned its complexity: the interrupt/resume cycle and
cross-process checkpointing worked exactly as documented and would have taken
real effort to hand-roll correctly. Typed state caught two wiring mistakes at
development time that a text ledger would have surfaced at runtime, if at all.

Where it was ceremony: four nodes and three routers to express what is
ultimately "parse, compute, maybe ask a human, narrate" — a ~40-line script in
the harness version. The serializer allowlist for custom pydantic types is
pure framework tax. For a pipeline this size, the graph abstraction documents
the flow more than it enables it. TODO(jaleel): replace this paragraph with
firsthand judgment after running both side by side for a few weeks.

## Layout

```
src/otif_graph/
  state.py       # pydantic models + audit-line helper
  engine.py      # deterministic scoring; no LLM/HTTP/framework imports allowed
  nodes/         # intake (LLM), scoring (engine only), escalation, explainer (LLM)
  graph.py       # wiring + SqliteSaver checkpointer
  llm.py         # FakeLLM (default) + optional OllamaLLM
  cli.py         # run | resume | demo
tests/           # engine rules, flow/interrupt/restart, headline pins, no-LLM-in-math
fixtures/        # 3 messy requests + pinned expected outputs
```
