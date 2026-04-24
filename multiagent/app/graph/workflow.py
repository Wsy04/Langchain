from langgraph.graph import END, StateGraph

from app.agents.analyzer import analyze_requirement_node
from app.agents.optimizer import optimize_plan_node
from app.agents.planner import generate_plan_node
from app.agents.validator import validate_plan_node
from app.graph.state import PlanState


def should_optimize(state: PlanState) -> str:
    validation = state.get("validation_result", {})
    if validation.get("passed"):
        return "end"
    if state.get("retry_count", 0) >= 2:
        return "end"
    return "optimize"


def build_workflow():
    graph = StateGraph(PlanState)

    graph.add_node("analyzer", analyze_requirement_node)
    graph.add_node("planner", generate_plan_node)
    graph.add_node("validator", validate_plan_node)
    graph.add_node("optimizer", optimize_plan_node)

    graph.set_entry_point("analyzer")
    graph.add_edge("analyzer", "planner")
    graph.add_edge("planner", "validator")
    graph.add_conditional_edges(
        "validator",
        should_optimize,
        {
            "optimize": "optimizer",
            "end": END,
        },
    )
    graph.add_edge("optimizer", "validator")

    return graph.compile()
