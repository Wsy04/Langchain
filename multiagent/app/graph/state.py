from typing import Any, TypedDict


class PlanState(TypedDict):
    task_id: str
    user_input: dict[str, Any]
    analyzed_requirement: dict[str, Any]
    draft_plan: dict[str, Any]
    validation_result: dict[str, Any]
    final_plan: dict[str, Any]
    trace: list[dict[str, Any]]
    status: str
    retry_count: int
