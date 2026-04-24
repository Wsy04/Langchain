from typing import Any

from app.graph.state import PlanState
from app.services.runtime_logger import elapsed_ms, log_event, start_timer


def validate_plan_node(state: PlanState) -> PlanState:
    started_at = start_timer()
    task_id = state.get("task_id", "-")
    log_event(task_id, "validator", "start")
    requirement = state.get("analyzed_requirement", {})
    draft_plan = state.get("draft_plan", {})
    focus_areas = _as_text_list(requirement.get("focus_areas", []))
    plan_text = _stringify_plan(draft_plan)

    issues: list[str] = []
    suggestions: list[str] = []

    phases = draft_plan.get("phases", [])
    weekly_plan = draft_plan.get("weekly_plan", [])

    if not isinstance(phases, list) or len(phases) < 2:
        issues.append("阶段数量少于 2，计划结构不完整")

    if not isinstance(weekly_plan, list) or len(weekly_plan) < min(4, int(requirement.get("duration_weeks", 4) or 4)):
        issues.append("每周计划覆盖不足，至少需要覆盖前 4 周")

    missing_focus_areas = [area for area in focus_areas if area not in plan_text]
    if missing_focus_areas:
        issues.append(f"计划未覆盖薄弱项：{', '.join(missing_focus_areas)}")

    if "复盘" not in plan_text:
        issues.append("计划缺少复盘安排")

    if "真题" not in plan_text and "模拟" not in plan_text:
        suggestions.append("建议在冲刺阶段加入真题训练或综合模拟")

    daily_hours = float(requirement.get("daily_hours", 0) or 0)
    if daily_hours > 4:
        suggestions.append("每日学习时间较长，建议加入缓冲任务，避免过载")

    if focus_areas:
        suggestions.append(f"建议每天保留固定时间处理薄弱项：{', '.join(focus_areas[:3])}")

    validation_result = {
        "passed": not issues,
        "issues": issues,
        "suggestions": suggestions,
    }
    log_event(
        task_id,
        "validator",
        "checked",
        passed=validation_result["passed"],
        issue_count=len(issues),
        suggestion_count=len(suggestions),
    )

    final_plan = draft_plan if validation_result["passed"] else state.get("final_plan", {})
    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "计划校验 Agent",
            "status": "completed",
            "message": "计划校验 Agent 完成",
            "output": validation_result,
        }
    )

    status = "validated" if validation_result["passed"] else "validation_failed"
    log_event(
        task_id,
        "validator",
        "end",
        status=status,
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        **state,
        "validation_result": validation_result,
        "final_plan": final_plan,
        "trace": trace,
        "status": status,
    }


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _stringify_plan(plan: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        else:
            parts.append(str(value))

    walk(plan)
    return "\n".join(parts)
