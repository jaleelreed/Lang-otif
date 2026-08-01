"""Full graph runs on each fixture: node order, interrupt/resume routing, and
resumability across a real process restart."""
import subprocess
import sys

from langgraph.types import Command

from conftest import node_order, raw_request


def invoke(graph, name, thread_id):
    return graph.invoke({"raw_request": raw_request(name)},
                        config={"configurable": {"thread_id": thread_id}})


def resume(graph, thread_id, decision):
    return graph.invoke(Command(resume=decision),
                        config={"configurable": {"thread_id": thread_id}})


def test_clean_pass_node_order(graph):
    out = invoke(graph, "blue_ridge", "t-clean")
    assert node_order(out["audit_log"]) == ["intake", "scoring", "explainer"]
    assert "__interrupt__" not in out
    assert out["result"].grade == "A"
    assert out["narrative"]


def test_retry_path_node_order(graph):
    out = invoke(graph, "cascade", "t-retry")
    assert node_order(out["audit_log"]) == ["intake", "scoring", "explainer"]
    assert "(attempt 2)" in out["audit_log"][0]
    assert out["result"].grade == "C"


def test_escalation_interrupt_fires(graph):
    out = invoke(graph, "meridian", "t-esc")
    assert "__interrupt__" in out
    payload = out["__interrupt__"][0].value
    assert payload["score"]["otif_pct"] == 33.3
    assert set(payload["critical_flags"]) == {"M-002", "M-003"}
    assert payload["proposed_action"]
    # graph paused before explainer
    assert node_order(out["audit_log"]) == ["intake", "scoring"]


def test_resume_approve_routes_to_explainer(graph):
    invoke(graph, "meridian", "t-approve")
    out = resume(graph, "t-approve", "approve")
    assert node_order(out["audit_log"]) == ["intake", "scoring", "escalation", "explainer"]
    assert out["review_decision"] == "approve"
    assert out["narrative"]


def test_resume_reject_ends_without_narrative(graph):
    invoke(graph, "meridian", "t-reject")
    out = resume(graph, "t-reject", "reject")
    assert node_order(out["audit_log"]) == ["intake", "scoring", "escalation"]
    assert out["review_decision"] == "reject"
    assert out.get("narrative") is None


def test_resume_rescore_loops_to_intake(graph):
    invoke(graph, "meridian", "t-rescore")
    out = resume(graph, "t-rescore", "rescore")
    # rescore re-runs intake+scoring; the numbers are still bad, so the graph
    # interrupts again for a second review
    assert "__interrupt__" in out
    assert node_order(out["audit_log"]) == [
        "intake", "scoring", "escalation", "intake", "scoring"]
    assert "[reviewer note:" in out["raw_request"]


def test_resume_survives_process_restart(tmp_path):
    """Run to the interrupt in one process, resume in a brand-new process."""
    db = str(tmp_path / "restart.sqlite")

    def cli(*args):
        proc = subprocess.run(
            [sys.executable, "-m", "otif_graph.cli", "--db", db, *args],
            capture_output=True, text=True, timeout=120)
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    first = cli("run", "meridian", "--thread-id", "restart-proof")
    assert "INTERRUPTED" in first

    second = cli("resume", "restart-proof", "approve")
    assert "human decision: approve" in second
    assert "grade F" in second
    assert "narrative:" in second
