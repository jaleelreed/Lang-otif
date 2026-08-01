"""Enforces the core rule: no LLM in any code path that produces a number.

1. engine.py and nodes/scoring.py may not import llm, ollama, requests,
   langchain, or langgraph (AST check).
2. Every numeric figure in the explainer narrative must appear in OtifResult.
"""
import ast
import pathlib
import re

import pytest

from langgraph.types import Command

from conftest import raw_request

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "otif_graph"
FORBIDDEN = ("llm", "ollama", "requests", "langchain", "langgraph")


def imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


@pytest.mark.parametrize("relpath", ["engine.py", "nodes/scoring.py"])
def test_math_files_have_no_llm_imports(relpath):
    for mod in imported_modules(SRC / relpath):
        parts = mod.split(".")
        for forbidden in FORBIDDEN:
            assert forbidden not in parts, f"{relpath} imports {mod}"


def result_numbers(result) -> set[str]:
    nums = {f"{v}" for v in (result.on_time_pct, result.in_full_pct, result.otif_pct)}
    # also allow integer renderings like "100" for 100.0
    nums |= {str(int(v)) for v in (result.on_time_pct, result.in_full_pct, result.otif_pct)
             if v == int(v)}
    return nums


@pytest.mark.parametrize("name,needs_resume", [
    ("blue_ridge", False), ("meridian", True), ("cascade", False)])
def test_narrative_numbers_come_from_result(graph, name, needs_resume):
    config = {"configurable": {"thread_id": f"nar-{name}"}}
    out = graph.invoke({"raw_request": raw_request(name)}, config=config)
    if needs_resume:
        out = graph.invoke(Command(resume="approve"), config=config)
    narrative, result = out["narrative"], out["result"]
    assert narrative and len(narrative.split()) <= 150
    allowed = result_numbers(result)
    for figure in re.findall(r"\d+(?:\.\d+)?", narrative):
        assert figure in allowed, (
            f"narrative figure {figure!r} not present in OtifResult {allowed}")
