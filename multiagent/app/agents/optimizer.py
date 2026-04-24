from copy import deepcopy
import json
from typing import Any

from app.graph.state import PlanState
from app.services import invoke_llm_json
from app.services.runtime_logger import elapsed_ms, log_event, start_timer


def optimize_plan_node(state: PlanState) -> PlanState:
    started_at = start_timer()
    task_id = state.get("task_id", "-")
    log_event(task_id, "optimizer", "start", retry_count=state.get("retry_count", 0))

    draft_plan = deepcopy(state.get("draft_plan", {}))
    requirement = state.get("analyzed_requirement", {})
    validation_result = state.get("validation_result", {})
    focus_areas = _as_text_list(requirement.get("focus_areas", []))

    local_plan = _optimize_locally(draft_plan, requirement, focus_areas)
    llm_plan = _optimize_with_llm(task_id, draft_plan, requirement, validation_result, local_plan)

    if _is_valid_optimized_plan(llm_plan):
        draft_plan = _normalize_optimized_plan(llm_plan, local_plan, requirement, focus_areas)
        source = "llm"
        llm_error = None
    else:
        draft_plan = local_plan
        source = "local_fallback"
        llm_error = _extract_llm_error(llm_plan)

    log_event(
        task_id,
        "optimizer",
        "selected-plan",
        source=source,
        llm_error=llm_error,
        validation_issues=validation_result.get("issues"),
    )
    log_event(
        task_id,
        "optimizer",
        "optimized",
        phase_count=len(draft_plan.get("phases", [])),
        weekly_count=len(draft_plan.get("weekly_plan", [])),
        fixed_focus_areas=focus_areas,
    )

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "计划优化 Agent",
            "status": "completed",
            "message": "计划优化 Agent 完成",
            "source": source,
            "llm_error": llm_error,
            "output": {
                "retry_count": state.get("retry_count", 0) + 1,
                "fixed_focus_areas": focus_areas,
                "phase_count": len(draft_plan.get("phases", [])),
                "weekly_plan_count": len(draft_plan.get("weekly_plan", [])),
            },
        }
    )

    log_event(
        task_id,
        "optimizer",
        "end",
        status="optimized",
        retry_count=state.get("retry_count", 0) + 1,
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        **state,
        "draft_plan": draft_plan,
        "trace": trace,
        "status": "optimized",
        "retry_count": state.get("retry_count", 0) + 1,
    }


def _optimize_with_llm(
    task_id: str,
    draft_plan: dict[str, Any],
    requirement: dict[str, Any],
    validation_result: dict[str, Any],
    local_plan: dict[str, Any],
) -> dict[str, Any]:
    prompt = f"""
你是学习计划系统中的计划优化 Agent。请根据校验意见修正计划，并只返回一个 JSON 对象，不要返回 Markdown。

你要代替本地 _ensure_phases 和 _ensure_weekly_plan 的核心逻辑，重点决定：
1. 阶段名称、阶段目标和任务列表应如何调整。
2. 每周任务中应该添加哪些薄弱项练习、复盘、真题或模拟训练。
3. 如何根据 validator 的 issues 和 suggestions 修复失败原因。
4. 保留原计划中合理内容，但必须补齐缺失结构。

输出 JSON 字段必须包含：
summary: string
phases: array，元素包含 phase_name、weeks、target、tasks
weekly_plan: array，元素包含 week、focus、tasks
suggestions: string[]
risks: string[]
optimization_notes: string[]

需求分析：
{json.dumps(requirement, ensure_ascii=False)}

校验结果：
{json.dumps(validation_result, ensure_ascii=False)}

待优化计划：
{json.dumps(draft_plan, ensure_ascii=False)}

本地兜底优化结果，可参考结构但不要照抄：
{json.dumps(local_plan, ensure_ascii=False)}
"""
    log_event(task_id, "optimizer.llm", "request-start")
    started_at = start_timer()
    result = invoke_llm_json(prompt)
    log_event(
        task_id,
        "optimizer.llm",
        "request-end",
        elapsed_ms=elapsed_ms(started_at),
        keys=list(result.keys()) if isinstance(result, dict) else type(result).__name__,
    )
    return result


def _optimize_locally(
    draft_plan: dict[str, Any],
    requirement: dict[str, Any],
    focus_areas: list[str],
) -> dict[str, Any]:
    optimized_plan = deepcopy(draft_plan)
    optimized_plan.setdefault("summary", "优化后的学习计划")
    optimized_plan["phases"] = _ensure_phases(optimized_plan.get("phases"), focus_areas)
    optimized_plan["weekly_plan"] = _ensure_weekly_plan(
        optimized_plan.get("weekly_plan"),
        int(requirement.get("duration_weeks", 4) or 4),
        focus_areas,
    )
    optimized_plan["suggestions"] = _append_unique(
        optimized_plan.get("suggestions", []),
        [
            "已根据校验结果补充薄弱项任务",
            "每两周保留一次复盘，冲刺阶段加入真题或模拟训练",
        ],
    )
    optimized_plan["risks"] = _append_unique(
        optimized_plan.get("risks", []),
        ["优化后仍需关注时间过载和薄弱项投入不足的风险"],
    )
    return optimized_plan


def _is_valid_optimized_plan(value: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or value.get("error") or value.get("warning"):
        return False
    return isinstance(value.get("phases"), list) and isinstance(value.get("weekly_plan"), list)


def _normalize_optimized_plan(
    llm_plan: dict[str, Any],
    local_plan: dict[str, Any],
    requirement: dict[str, Any],
    focus_areas: list[str],
) -> dict[str, Any]:
    target_weeks = max(4, int(requirement.get("duration_weeks", 4) or 4))
    plan = {
        "summary": str(llm_plan.get("summary") or local_plan.get("summary") or "优化后的学习计划"),
        "phases": llm_plan.get("phases") if isinstance(llm_plan.get("phases"), list) else local_plan["phases"],
        "weekly_plan": llm_plan.get("weekly_plan")
        if isinstance(llm_plan.get("weekly_plan"), list)
        else local_plan["weekly_plan"],
        "suggestions": _as_text_list(llm_plan.get("suggestions")) or local_plan.get("suggestions", []),
        "risks": _as_text_list(llm_plan.get("risks")) or local_plan.get("risks", []),
    }

    if len(plan["phases"]) < 2:
        plan["phases"] = local_plan["phases"]
    if len(plan["weekly_plan"]) < min(4, target_weeks):
        plan["weekly_plan"] = local_plan["weekly_plan"]

    plan_text = json.dumps(plan, ensure_ascii=False)
    if any(area not in plan_text for area in focus_areas) or "复盘" not in plan_text:
        plan["phases"] = _ensure_phases(plan.get("phases"), focus_areas)
        plan["weekly_plan"] = _ensure_weekly_plan(plan.get("weekly_plan"), target_weeks, focus_areas)

    plan_text = json.dumps(plan, ensure_ascii=False)
    if "真题" not in plan_text and "模拟" not in plan_text:
        plan["weekly_plan"] = _ensure_weekly_plan(plan.get("weekly_plan"), target_weeks, focus_areas)
        plan["suggestions"] = _append_unique(plan["suggestions"], ["冲刺阶段加入真题或综合模拟训练"])

    if llm_plan.get("optimization_notes"):
        plan["optimization_notes"] = _as_text_list(llm_plan.get("optimization_notes"))

    return plan


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


def _extract_llm_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "LLM response is not a JSON object"
    return value.get("error") or value.get("warning")
