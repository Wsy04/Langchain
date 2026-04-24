from datetime import date
from math import ceil
from typing import Any

from app.graph.state import PlanState


def analyze_requirement_node(state: PlanState) -> PlanState:
    user_input = state.get("user_input", {})
    duration_weeks = _calculate_duration_weeks(
        user_input.get("start_date"),
        user_input.get("end_date"),
    )
    focus_areas = _build_focus_areas(user_input)

    analyzed_requirement = {
        "goal": user_input.get("goal", ""),
        "current_level": user_input.get("current_level", ""),
        "plan_type": user_input.get("plan_type", "general_learning"),
        "duration_weeks": duration_weeks,
        "daily_hours": float(user_input.get("daily_hours", 0) or 0),
        "focus_areas": focus_areas,
        "extra_constraints": user_input.get("extra_constraints"),
        "suggested_phase_count": _suggest_phase_count(duration_weeks),
    }

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "需求分析 Agent",
            "status": "completed",
            "message": "需求分析 Agent 完成",
            "output": analyzed_requirement,
        }
    )

    return {
        **state,
        "analyzed_requirement": analyzed_requirement,
        "trace": trace,
        "status": "analyzed",
    }


def _calculate_duration_weeks(start_date: Any, end_date: Any) -> int:
    try:
        start = date.fromisoformat(str(start_date))
        end = date.fromisoformat(str(end_date))
    except ValueError:
        return 1

    if end < start:
        return 1

    return max(1, ceil((end - start).days / 7))


def _build_focus_areas(user_input: dict[str, Any]) -> list[str]:
    weak_subjects = user_input.get("weak_subjects") or []
    focus_areas = [str(subject) for subject in weak_subjects if str(subject).strip()]

    goal = str(user_input.get("goal", ""))
    plan_type = str(user_input.get("plan_type", ""))

    if not focus_areas and "exam" in plan_type:
        focus_areas.extend(["知识框架", "真题训练", "复盘"])

    if "软考" in goal:
        for area in ["软件工程", "系统设计", "算法"]:
            if area not in focus_areas:
                focus_areas.append(area)

    return focus_areas or ["基础知识", "实践练习", "阶段复盘"]


def _suggest_phase_count(duration_weeks: int) -> int:
    if duration_weeks <= 4:
        return 2
    return 3
