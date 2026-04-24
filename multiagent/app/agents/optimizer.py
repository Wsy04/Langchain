from copy import deepcopy
from typing import Any

from app.graph.state import PlanState


def optimize_plan_node(state: PlanState) -> PlanState:
    draft_plan = deepcopy(state.get("draft_plan", {}))
    requirement = state.get("analyzed_requirement", {})
    focus_areas = _as_text_list(requirement.get("focus_areas", []))

    draft_plan.setdefault("summary", "优化后的学习计划")
    draft_plan["phases"] = _ensure_phases(draft_plan.get("phases"), focus_areas)
    draft_plan["weekly_plan"] = _ensure_weekly_plan(
        draft_plan.get("weekly_plan"),
        int(requirement.get("duration_weeks", 4) or 4),
        focus_areas,
    )
    draft_plan["suggestions"] = _append_unique(
        draft_plan.get("suggestions", []),
        [
            "已根据校验结果补充薄弱项任务",
            "每两周保留一次复盘，冲刺阶段加入真题或模拟训练",
        ],
    )
    draft_plan["risks"] = _append_unique(
        draft_plan.get("risks", []),
        ["优化后仍需关注时间过载和薄弱项投入不足的风险"],
    )

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "计划优化 Agent",
            "status": "completed",
            "message": "计划优化 Agent 完成",
            "output": {
                "retry_count": state.get("retry_count", 0) + 1,
                "fixed_focus_areas": focus_areas,
            },
        }
    )

    return {
        **state,
        "draft_plan": draft_plan,
        "trace": trace,
        "status": "optimized",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _ensure_phases(value: Any, focus_areas: list[str]) -> list[dict]:
    phases = deepcopy(value) if isinstance(value, list) else []
    focus_text = "、".join(focus_areas[:3]) if focus_areas else "薄弱项"

    if len(phases) < 2:
        phases = [
            {
                "phase_name": "基础补齐阶段",
                "weeks": "第 1-2 周",
                "target": "补齐核心概念，建立学习框架",
                "tasks": [f"梳理 {focus_text} 的基础知识", "建立错题和问题清单"],
            },
            {
                "phase_name": "强化冲刺阶段",
                "weeks": "第 3-4 周",
                "target": "通过专项练习、真题和复盘提升稳定性",
                "tasks": [f"针对 {focus_text} 做专项练习", "完成真题模拟并复盘"],
            },
        ]

    for phase in phases:
        tasks = phase.setdefault("tasks", [])
        if focus_areas and not _contains_all(str(phase), focus_areas):
            tasks.append(f"补充薄弱项专项任务：{focus_text}")
        if "复盘" not in str(phase):
            tasks.append("安排阶段复盘，整理错题和改进动作")
        if "真题" not in str(phase) and "模拟" not in str(phase):
            tasks.append("加入真题或综合模拟训练")

    return phases


def _ensure_weekly_plan(value: Any, duration_weeks: int, focus_areas: list[str]) -> list[dict]:
    weekly_plan = deepcopy(value) if isinstance(value, list) else []
    target_weeks = max(4, duration_weeks)
    focus_areas = focus_areas or ["基础知识", "实践练习", "阶段复盘"]

    existing_weeks = {
        item.get("week")
        for item in weekly_plan
        if isinstance(item, dict)
    }
    for week in range(1, target_weeks + 1):
        if week not in existing_weeks:
            focus = focus_areas[(week - 1) % len(focus_areas)]
            weekly_plan.append(
                {
                    "week": week,
                    "focus": focus,
                    "tasks": [
                        f"完成 {focus} 专项学习",
                        "记录错题和疑问",
                    ],
                }
            )

    weekly_plan.sort(key=lambda item: int(item.get("week", 0) or 0))

    for index, item in enumerate(weekly_plan):
        focus = focus_areas[index % len(focus_areas)]
        item.setdefault("focus", focus)
        tasks = item.setdefault("tasks", [])
        if focus not in str(item):
            tasks.append(f"补充 {focus} 薄弱项练习")
        if int(item.get("week", index + 1)) % 2 == 0 and "复盘" not in str(item):
            tasks.append("进行阶段复盘，更新错题清单")
        if int(item.get("week", index + 1)) >= max(1, target_weeks - 3) and "真题" not in str(item) and "模拟" not in str(item):
            tasks.append("加入真题训练或综合模拟")

    return weekly_plan


def _append_unique(value: Any, items: list[str]) -> list[str]:
    result = [str(item) for item in value] if isinstance(value, list) else []
    for item in items:
        if item not in result:
            result.append(item)
    return result


def _contains_all(text: str, items: list[str]) -> bool:
    return all(item in text for item in items)
