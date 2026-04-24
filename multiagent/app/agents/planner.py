import json
from typing import Any

from app.graph.state import PlanState
from app.services import invoke_llm_json
from app.services.runtime_logger import elapsed_ms, log_event, start_timer


def generate_plan_node(state: PlanState) -> PlanState:
    started_at = start_timer()
    task_id = state.get("task_id", "-")
    log_event(task_id, "planner", "start")
    requirement = state.get("analyzed_requirement", {})
    duration_weeks = max(1, int(requirement.get("duration_weeks", 1) or 1))
    focus_areas = _normalize_focus_areas(requirement.get("focus_areas", []))

    local_plan = _build_local_plan(requirement, duration_weeks, focus_areas)
    log_event(
        task_id,
        "planner",
        "local-plan-ready",
        duration_weeks=duration_weeks,
        phase_count=len(local_plan["phases"]),
        weekly_count=len(local_plan["weekly_plan"]),
    )
    llm_plan = _generate_plan_with_llm(task_id, requirement, local_plan)

    if _is_valid_plan(llm_plan):
        draft_plan = _normalize_llm_plan(llm_plan, local_plan, duration_weeks, focus_areas)
        source = "llm"
        llm_error = None
    else:
        draft_plan = local_plan
        source = "local_fallback"
        llm_error = _extract_llm_error(llm_plan)
    log_event(
        task_id,
        "planner",
        "selected-plan",
        source=source,
        llm_error=llm_error,
        phase_count=len(draft_plan["phases"]),
        weekly_count=len(draft_plan["weekly_plan"]),
    )

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "计划生成 Agent",
            "status": "completed",
            "message": "计划生成 Agent 完成",
            "source": source,
            "llm_error": llm_error,
            "output": {
                "phase_count": len(draft_plan["phases"]),
                "weekly_plan_count": len(draft_plan["weekly_plan"]),
            },
        }
    )

    log_event(
        task_id,
        "planner",
        "end",
        status="planned",
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        **state,
        "draft_plan": draft_plan,
        "trace": trace,
        "status": "planned",
    }


def _generate_plan_with_llm(task_id: str, requirement: dict[str, Any], local_plan: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是学习计划系统中的计划生成 Agent。请根据需求分析结果生成结构化学习计划，并只返回一个 JSON 对象，不要返回 Markdown。

你需要用推理完成：
1. _build_phases：生成阶段名称、阶段目标和任务列表。
2. _build_weekly_plan：生成每周具体任务描述。
3. 保证薄弱项 focus_areas 出现在阶段任务或周任务中。
4. 保证至少包含复盘安排；考试备考类计划需要包含真题或模拟训练。

输出 JSON 字段必须包含：
summary: string
phases: array，元素包含 phase_name、weeks、target、tasks
weekly_plan: array，元素包含 week、focus、tasks
suggestions: string[]
risks: string[]

需求分析结果：
{json.dumps(requirement, ensure_ascii=False)}

本地兜底计划，可用于参考结构但不要照抄：
{json.dumps(local_plan, ensure_ascii=False)}
"""
    log_event(task_id, "planner.llm", "request-start")
    started_at = start_timer()
    result = invoke_llm_json(prompt)
    log_event(
        task_id,
        "planner.llm",
        "request-end",
        elapsed_ms=elapsed_ms(started_at),
        keys=list(result.keys()) if isinstance(result, dict) else type(result).__name__,
    )
    return result


def _build_local_plan(requirement: dict[str, Any], duration_weeks: int, focus_areas: list[str]) -> dict[str, Any]:
    goal = requirement.get("goal", "学习目标")
    phases = _build_phases(duration_weeks, focus_areas)
    weekly_plan = _build_weekly_plan(duration_weeks, focus_areas)
    return {
        "summary": f"围绕「{goal}」制定的 {duration_weeks} 周学习计划",
        "phases": phases,
        "weekly_plan": weekly_plan,
        "suggestions": [
            "每两周进行一次复盘，检查进度、错题和薄弱项变化",
            "每天保留固定时间处理薄弱项，避免只推进新内容",
            "冲刺阶段增加真题模拟，并记录失分原因",
        ],
        "risks": [
            "学习周期较紧时，容易压缩复盘和错题整理时间",
            "薄弱项需要持续投入，短期集中学习可能不够稳定",
        ],
    }


def _normalize_llm_plan(
    llm_plan: dict[str, Any],
    local_plan: dict[str, Any],
    duration_weeks: int,
    focus_areas: list[str],
) -> dict[str, Any]:
    plan = {
        "summary": str(llm_plan.get("summary") or local_plan["summary"]),
        "phases": llm_plan.get("phases") if isinstance(llm_plan.get("phases"), list) else local_plan["phases"],
        "weekly_plan": llm_plan.get("weekly_plan")
        if isinstance(llm_plan.get("weekly_plan"), list)
        else local_plan["weekly_plan"],
        "suggestions": _as_text_list(llm_plan.get("suggestions")) or local_plan["suggestions"],
        "risks": _as_text_list(llm_plan.get("risks")) or local_plan["risks"],
    }

    if len(plan["phases"]) < 2:
        plan["phases"] = local_plan["phases"]
    if len(plan["weekly_plan"]) < min(4, duration_weeks):
        plan["weekly_plan"] = local_plan["weekly_plan"]

    plan_text = json.dumps(plan, ensure_ascii=False)
    if any(area not in plan_text for area in focus_areas) or "复盘" not in plan_text:
        plan = _blend_missing_local_items(plan, local_plan, focus_areas)

    return plan


def _blend_missing_local_items(plan: dict[str, Any], local_plan: dict[str, Any], focus_areas: list[str]) -> dict[str, Any]:
    plan_text = json.dumps(plan, ensure_ascii=False)
    missing_areas = [area for area in focus_areas if area not in plan_text]
    if missing_areas and plan["weekly_plan"]:
        first_week = plan["weekly_plan"][0]
        tasks = first_week.setdefault("tasks", [])
        tasks.append(f"补充薄弱项专项练习：{'、'.join(missing_areas)}")

    if "复盘" not in json.dumps(plan, ensure_ascii=False):
        plan["suggestions"].append("每两周安排一次复盘，整理错题、问题和下一阶段调整动作")

    if "真题" not in json.dumps(plan, ensure_ascii=False) and "模拟" not in json.dumps(plan, ensure_ascii=False):
        plan["suggestions"].append("冲刺阶段加入真题或综合模拟训练")
        plan["weekly_plan"][-1].setdefault("tasks", []).append("完成真题训练或综合模拟")

    if not plan["phases"]:
        plan["phases"] = local_plan["phases"]
    return plan


def _normalize_focus_areas(focus_areas: object) -> list[str]:
    if not isinstance(focus_areas, list):
        return ["基础知识", "实践练习", "阶段复盘"]

    normalized = [str(area).strip() for area in focus_areas if str(area).strip()]
    return normalized or ["基础知识", "实践练习", "阶段复盘"]


def _build_phases(duration_weeks: int, focus_areas: list[str]) -> list[dict]:
    ranges = _phase_ranges(duration_weeks)
    focus_text = "、".join(focus_areas[:3])
    phase_defs = [
        (
            "基础阶段",
            "建立知识框架，补齐核心概念和基础方法",
            [
                f"梳理 {focus_text} 的基础知识点",
                "建立错题和问题清单",
                "完成基础练习并标记不熟练内容",
            ],
        ),
        (
            "强化阶段",
            "围绕薄弱项做专项训练，提高解题和应用能力",
            [
                f"针对 {focus_text} 做专项练习",
                "每周完成一次阶段小测",
                "复盘错题并更新重点清单",
            ],
        ),
        (
            "冲刺阶段",
            "通过真题模拟和复盘稳定输出，完成考前查漏补缺",
            [
                "完成真题或综合模拟训练",
                f"回看 {focus_text} 的高频错误",
                "整理最终复盘清单和应试节奏",
            ],
        ),
    ]

    phases = []
    for (start, end), (name, target, tasks) in zip(ranges, phase_defs):
        phases.append(
            {
                "phase_name": name,
                "weeks": _format_weeks(start, end),
                "target": target,
                "tasks": tasks,
            }
        )
    return phases


def _build_weekly_plan(duration_weeks: int, focus_areas: list[str]) -> list[dict]:
    weekly_plan = []
    for week in range(1, duration_weeks + 1):
        focus = focus_areas[(week - 1) % len(focus_areas)]
        tasks = [
            f"学习并整理 {focus} 的核心知识点",
            f"完成 {focus} 相关练习，记录错题和疑问",
        ]

        if week % 2 == 0:
            tasks.append("进行阶段复盘，调整下两周学习重点")
        if week >= max(1, duration_weeks - 3):
            tasks.append("加入真题训练或综合模拟，检查时间分配")

        weekly_plan.append(
            {
                "week": week,
                "focus": focus,
                "tasks": tasks,
            }
        )
    return weekly_plan


def _phase_ranges(duration_weeks: int) -> list[tuple[int, int]]:
    first_end = max(1, duration_weeks // 3)
    second_end = max(first_end, (duration_weeks * 2) // 3)
    return [
        (1, first_end),
        (min(first_end + 1, duration_weeks), second_end),
        (min(second_end + 1, duration_weeks), duration_weeks),
    ]


def _format_weeks(start: int, end: int) -> str:
    if start == end:
        return f"第 {start} 周"
    return f"第 {start}-{end} 周"


def _is_valid_plan(value: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or value.get("error") or value.get("warning"):
        return False
    return isinstance(value.get("phases"), list) and isinstance(value.get("weekly_plan"), list)


def _extract_llm_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "LLM response is not a JSON object"
    return value.get("error") or value.get("warning")


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
