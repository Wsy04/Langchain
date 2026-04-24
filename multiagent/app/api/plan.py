from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.agents import analyze_requirement_node, optimize_plan_node, validate_plan_node
from app.graph.state import PlanState
from app.graph.workflow import build_workflow
from app.schemas import PlanRequest
from app.services.runtime_logger import elapsed_ms, log_event, start_timer
from app.storage import get_task, save_task

router = APIRouter(prefix="/api/v1/plan", tags=["plan"])


@router.post("/generate")
def generate_plan(request: PlanRequest) -> dict:
    started_at = start_timer()
    task_id = str(uuid4())
    log_event(
        task_id,
        "api.generate",
        "request-start",
        goal=request.goal,
        plan_type=request.plan_type,
    )
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
    workflow_summary = _build_workflow_summary(result)
    log_event(
        task_id,
        "api.generate",
        "request-end",
        status=result.get("status"),
        trace_count=len(result.get("trace", [])),
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": task_id,
            "status": result["status"],
            "plan": result.get("final_plan") or result.get("draft_plan"),
            "validation_result": result.get("validation_result", {}),
            "trace": result.get("trace", []),
            "workflow_summary": workflow_summary,
        },
    }


@router.post("/debug/optimizer")
def debug_optimizer(request: PlanRequest) -> dict:
    started_at = start_timer()
    task_id = str(uuid4())
    log_event(
        task_id,
        "api.debug_optimizer",
        "request-start",
        goal=request.goal,
        plan_type=request.plan_type,
    )
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

    analyzed_state = analyze_requirement_node(state)
    focus_areas = analyzed_state["analyzed_requirement"].get("focus_areas", [])
    first_focus = focus_areas[0] if focus_areas else "基础知识"
    analyzed_state["draft_plan"] = {
        "summary": "用于验证优化路径的简化计划",
        "phases": [
            {
                "phase_name": "基础阶段",
                "weeks": "第 1 周",
                "target": "先处理部分基础内容",
                "tasks": [f"学习 {first_focus} 基础"],
            }
        ],
        "weekly_plan": [
            {
                "week": 1,
                "focus": first_focus,
                "tasks": [f"完成 {first_focus} 练习"],
            }
        ],
        "suggestions": [],
        "risks": [],
    }
    analyzed_state["status"] = "planned"

    failed_state = validate_plan_node(analyzed_state)
    optimized_state = optimize_plan_node(failed_state)
    result = validate_plan_node(optimized_state)
    save_task(task_id, result)
    workflow_summary = _build_workflow_summary(result)
    log_event(
        task_id,
        "api.debug_optimizer",
        "request-end",
        status=result.get("status"),
        retry_count=result.get("retry_count", 0),
        trace_count=len(result.get("trace", [])),
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        "code": 0,
        "message": "ok",
        "data": {
            "task_id": task_id,
            "status": result["status"],
            "plan": result.get("final_plan") or result.get("draft_plan"),
            "validation_result": result.get("validation_result", {}),
            "trace": result.get("trace", []),
            "workflow_summary": workflow_summary,
            "debug": {
                "purpose": "force_optimizer_path",
                "initial_validation": failed_state.get("validation_result", {}),
                "retry_count": result.get("retry_count", 0),
            },
        },
    }


def _build_workflow_summary(state: dict) -> dict:
    trace = state.get("trace", [])
    nodes = [item.get("node") for item in trace]
    optimizer_executed = any("优化" in str(node) for node in nodes)
    return {
        "optimizer_executed": optimizer_executed,
        "agent_count": len(trace),
        "nodes": nodes,
        "data_flow": {
            "analyzer_to_planner": bool(state.get("analyzed_requirement")),
            "planner_to_validator": bool(state.get("draft_plan")),
            "validator_completed": bool(state.get("validation_result")),
            "validator_to_optimizer": optimizer_executed,
            "optimizer_to_validator": optimizer_executed and state.get("retry_count", 0) > 0,
        },
        "retry_count": state.get("retry_count", 0),
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
