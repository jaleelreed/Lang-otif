"""Explainer node: LLM writes a short narrative around the already-computed
numbers. Every figure must come from OtifResult verbatim (enforced by test)."""
from otif_graph.state import GraphState, audit

PROMPT = """TASK: narrate
Write a narrative of at most 150 words summarizing this OTIF scorecard for
{carrier}. Every figure must be copied verbatim from RESULT below — do not
compute, round, or invent any number.

RESULT:
{result_json}"""


def make_explainer(llm):
    def explainer(state: GraphState) -> dict:
        if state.result is None:
            text = "No score was produced; the request could not be parsed."
        else:
            text = llm.complete(PROMPT.format(carrier=state.batch.carrier_name,
                                              result_json=state.result.model_dump_json()))
        return {"narrative": text,
                "audit_log": state.audit_log + [audit("explainer", f"wrote {len(text.split())}-word narrative")]}
    return explainer
