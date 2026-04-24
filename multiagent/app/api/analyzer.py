from uuid import uuid4

from fastapi import APIRouter

from app.agents.analyzer import analyze_requirement_node
from app.graph.state import PlanState
from app.schemas import PlanRequest

router = APIRouter(prefix="/api/v1/analyzer", tags=["analyzer"])


@router.post("/run")
def run_analyzer(request: PlanRequest) -> dict:
    task_id = str(uuid4())
    state: PlanState = {
        "task_id": task_id,
        "user_input": request.model_dump(),
        "analyzed_requirement": {},
        "draft_plan": {},
        "validation_result": {},
        "final_plan": {},
        "trace": [],
        "status": "created",
        "retry_count": 0,
    }
    result = analyze_requirement_node(state)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": result["task_id"],
            "status": result["status"],
            "analyzed_requirement": result["analyzed_requirement"],
            "trace": result["trace"],
        },
    }
