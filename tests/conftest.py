import pathlib

import pytest

from otif_graph.graph import build_graph
from otif_graph.llm import FakeLLM

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURES_ROOT = REPO / "src" / "otif_graph" / "fixtures"
FIXTURES = FIXTURES_ROOT / "sample_requests"
EXPECTED = FIXTURES_ROOT / "expected"
POLICIES = FIXTURES_ROOT / "policies"


@pytest.fixture
def graph(tmp_path):
    return build_graph(FakeLLM(), str(tmp_path / "checkpoints.sqlite"))


def raw_request(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")


def node_order(audit_log: list[str]) -> list[str]:
    # audit line format: "<timestamp> <node>: <summary>"
    return [line.split(" ", 1)[1].split(":", 1)[0] for line in audit_log]
