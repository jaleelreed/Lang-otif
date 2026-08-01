# otif-langgraph

[![ci](https://github.com/jaleelreed/Lang-otif/actions/workflows/ci.yml/badge.svg)](https://github.com/jaleelreed/Lang-otif/actions/workflows/ci.yml)

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

The demo runs four scenarios: a clean pass, a low-OTIF batch that trips the
human-approval interrupt (then resumes with `approve`), a garbled OCR scan
that fails validation once and exercises the intake retry, and the same OCR
data rescored under a stricter customer policy — where the clean pass becomes
a mandatory review.

## Contract terms are data, not code

Real OTIF programs differ per customer and change at renegotiation, so grade
bands, review thresholds, critical tolerances, and weighting (by shipment
count vs by units) live in a versioned `ScoringPolicy`, not in the engine:

```bash
python -m otif_graph.cli run cascade --policy bigbox-retail
```

Cascade Carriers scores 87.5% (grade C, no review) under the standard policy,
but 85.1% (grade D, mandatory review) under `bigbox-retail/2026-Q3`, which
weights by units and reviews anything under 95%. Every result and audit line
is stamped with the policy id/version that produced it, and the escalation
payload includes `miss_drivers` — each failed shipment's weighted share of
the score — so the reviewer sees what drove the miss, not just the number.
The engine stays pure: domain complexity grows, the LLM surface doesn't.

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
| State/audit visibility | Typed pydantic state; audit_log rides inside the SQLite checkpoint — structured, but readable only through code or the CLI | Ledger is a plain text file; any editor shows the full history. Low-tech, zero friction, no schema to enforce consistency |
| Resumability | First-class: SqliteSaver + `interrupt()`, resume by thread_id from any process — proven by test and captured transcript | Re-runs recover by re-reading the ledger; it works, but the "where was I" logic is hand-rolled and every new step must remember to honor it |
| Human approval gates | `interrupt()` is the standout feature — pause, surface a structured payload, resume with a decision, all enforced by the framework | A sentinel line a human edits; simple and auditable, but purely conventional — nothing stops a step from ignoring it |
| Replay/debugging | Checkpoint history per thread; any step is inspectable after the fact, at the cost of tooling to read it | The ledger *is* the replay: linear, greppable, diffable with git. For a single pipeline this is hard to beat |
| Ceremony/boilerplate | Node factories, routers, checkpointer wiring, serializer allowlist — ~450 lines and real setup before the first useful result | Near zero to start; the cost arrives later, as unwritten conventions a second maintainer would have to reverse-engineer |
| Vendor surface | `langgraph` + `langchain-core` + checkpoint libs; API churn (the serializer allowlist below appeared mid-version) is a real maintenance tax | cron, files, and one CLI tool; nothing to version-chase |

Where LangGraph earned its complexity: the interrupt/resume cycle and
cross-process checkpointing worked exactly as documented and would have taken
real effort to hand-roll correctly — those two features are the honest case
for the framework. Typed state moves malformed input to a defined failure
path (validate, retry once, escalate) instead of whatever a free-form script
happens to do.

Where it was ceremony: four nodes and three routers to express what is
ultimately "parse, compute, maybe ask a human, narrate" — a ~40-line script in
the harness version. The serializer allowlist for custom pydantic types is
pure framework tax. Provisional verdict: for one pipeline with one approval
gate, the harness wins on simplicity and transparency; LangGraph starts paying
for itself when the approval gate must be *enforced* rather than followed, or
when runs must survive process death without hand-rolled recovery. The graph
abstraction itself mostly documents the flow rather than enabling it.

## Layout

```
src/otif_graph/
  state.py       # pydantic models incl. versioned ScoringPolicy + audit helper
  engine.py      # deterministic scoring; no LLM/HTTP/framework imports allowed
  nodes/         # intake (LLM), scoring (engine only), escalation, explainer (LLM)
  graph.py       # wiring + checkpointer factory (SQLite default, Postgres via env)
  llm.py         # FakeLLM (default) + optional OllamaLLM
  cli.py         # run | resume | demo, --policy to pick contract terms
  fixtures/      # 3 messy requests, 2 policies, pinned outputs (ships in the wheel)
tests/           # engine rules, flow/interrupt/restart, pins, policy, no-LLM-in-math
```

## Deploying elsewhere

The package installs and runs from anywhere — fixtures ship as package data
and the CLI is a console script:

```bash
pip install "git+https://github.com/jaleelreed/Lang-otif"
otif-graph demo
otif-graph run cascade --policy bigbox-retail
```

The checkpoint backend is selectable by environment. Local SQLite is the
default; for shared or concurrent deployments (a service, serverless workers),
point `OTIF_CHECKPOINT_DSN` at Postgres and install the extra:

```bash
pip install "otif-langgraph[postgres] @ git+https://github.com/jaleelreed/Lang-otif"
```

```bash
OTIF_CHECKPOINT_DSN=postgresql://user:pass@host/db otif-graph run meridian
```

(The Postgres path is code-only in this repo — exercised for its error
handling but not against a live server, same convention as `OllamaLLM`.)

For reuse in another codebase entirely: `engine.py` and `state.py` depend on
nothing but pydantic — lift them as-is and the no-LLM-in-math guarantee comes
along. The `LLM` protocol in `llm.py` is a single `complete(prompt) -> str`
method, so pointing intake/explainer at any hosted model is a ~15-line class.
