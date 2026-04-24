from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.graph.state import PlanState
from app.graph.workflow import build_workflow
from app.schemas import PlanRequest
from app.storage import get_task, save_task

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.post("/generate")
def generate_plan(request: PlanRequest) -> dict:
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

    result = build_workflow().invoke(state)
    save_task(task_id, result)

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": task_id,
            "status": result["status"],
            "plan": result.get("final_plan") or result.get("draft_plan"),
            "validation_result": result.get("validation_result", {}),
            "trace": result.get("trace", []),
        },
    }


@router.get("/{task_id}/trace")
def get_plan_trace(task_id: str) -> dict:
    state = get_task(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task_id not found")

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": task_id,
            "status": state.get("status"),
            "trace": state.get("trace", []),
        },
    }


@router.get("/{task_id}/result")
def get_plan_result(task_id: str) -> dict:
    state = get_task(task_id)
    if state is None:
        raise HTTPException(status_code=404, detail="task_id not found")

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": task_id,
            "status": state.get("status"),
            "plan": state.get("final_plan") or state.get("draft_plan"),
            "validation_result": state.get("validation_result", {}),
        },
    }
