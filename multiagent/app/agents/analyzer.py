import json
from datetime import date
from math import ceil
from typing import Any

from app.graph.state import PlanState
from app.services import invoke_llm_json
from app.services.runtime_logger import elapsed_ms, log_event, start_timer


def analyze_requirement_node(state: PlanState) -> PlanState:
    started_at = start_timer()
    task_id = state.get("task_id", "-")
    log_event(task_id, "analyzer", "start")
    user_input = state.get("user_input", {})
    local_result = _build_local_analysis(user_input)
    log_event(
        task_id,
        "analyzer",
        "local-analysis-ready",
        duration_weeks=local_result.get("duration_weeks"),
        focus_areas=local_result.get("focus_areas"),
    )
    llm_result = _analyze_with_llm(task_id, user_input, local_result)

    if _is_valid_analysis(llm_result):
        analyzed_requirement = _merge_analysis(local_result, llm_result)
        source = "llm"
        llm_error = None
    else:
        analyzed_requirement = local_result
        source = "local_fallback"
        llm_error = _extract_llm_error(llm_result)
    log_event(
        task_id,
        "analyzer",
        "selected-result",
        source=source,
        llm_error=llm_error,
        focus_areas=analyzed_requirement.get("focus_areas"),
    )

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "需求分析 Agent",
            "status": "completed",
            "message": "需求分析 Agent 完成",
            "source": source,
            "llm_error": llm_error,
            "output": analyzed_requirement,
        }
    )

    log_event(
        task_id,
        "analyzer",
        "end",
        status="analyzed",
        elapsed_ms=elapsed_ms(started_at),
    )

    return {
        **state,
        "analyzed_requirement": analyzed_requirement,
        "trace": trace,
        "status": "analyzed",
    }


def _analyze_with_llm(task_id: str, user_input: dict[str, Any], local_result: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
你是学习计划系统中的需求分析 Agent。请根据用户输入完成推理，并只返回一个 JSON 对象，不要返回 Markdown。

任务：
1. 改写并澄清学习目标 goal。
2. 识别学习类型 plan_type，例如 exam_preparation、skill_learning、project_practice、general_learning。
3. 提取关键约束 key_constraints。
4. 提炼薄弱项 focus_areas，必须保留用户显式填写的 weak_subjects。
5. 根据日期和投入时间给出 suggested_phase_count。

输出 JSON 字段必须包含：
goal: string
current_level: string
plan_type: string
duration_weeks: number
daily_hours: number
focus_areas: string[]
key_constraints: string[]
extra_constraints: string | null
suggested_phase_count: number
reasoning_summary: string

本地预计算结果，可用于校验：
{json.dumps(local_result, ensure_ascii=False)}

用户输入：
{json.dumps(user_input, ensure_ascii=False)}
"""
    log_event(task_id, "analyzer.llm", "request-start")
    started_at = start_timer()
    result = invoke_llm_json(prompt)
    log_event(
        task_id,
        "analyzer.llm",
        "request-end",
        elapsed_ms=elapsed_ms(started_at),
        keys=list(result.keys()) if isinstance(result, dict) else type(result).__name__,
    )
    return result


def _build_local_analysis(user_input: dict[str, Any]) -> dict[str, Any]:
    duration_weeks = _calculate_duration_weeks(
        user_input.get("start_date"),
        user_input.get("end_date"),
    )
    focus_areas = _build_focus_areas(user_input)

    return {
        "goal": user_input.get("goal", ""),
        "current_level": user_input.get("current_level", ""),
        "plan_type": _detect_plan_type(user_input),
        "duration_weeks": duration_weeks,
        "daily_hours": float(user_input.get("daily_hours", 0) or 0),
        "focus_areas": focus_areas,
        "key_constraints": _extract_key_constraints(user_input),
        "extra_constraints": user_input.get("extra_constraints"),
        "suggested_phase_count": _suggest_phase_count(duration_weeks),
        "reasoning_summary": "本地规则根据日期、计划类型、薄弱项和目标关键词完成需求分析。",
    }


def _merge_analysis(local_result: dict[str, Any], llm_result: dict[str, Any]) -> dict[str, Any]:
    merged = {**local_result, **llm_result}
    merged["duration_weeks"] = _safe_int(llm_result.get("duration_weeks"), local_result["duration_weeks"])
    merged["daily_hours"] = _safe_float(llm_result.get("daily_hours"), local_result["daily_hours"])
    merged["suggested_phase_count"] = _safe_int(
        llm_result.get("suggested_phase_count"),
        local_result["suggested_phase_count"],
    )

    focus_areas = _merge_unique(
        _as_text_list(llm_result.get("focus_areas")),
        local_result.get("focus_areas", []),
    )
    merged["focus_areas"] = focus_areas
    merged["key_constraints"] = _as_text_list(llm_result.get("key_constraints")) or local_result["key_constraints"]
    return merged


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
    focus_areas = [str(subject).strip() for subject in weak_subjects if str(subject).strip()]

    goal = str(user_input.get("goal", ""))
    plan_type = str(user_input.get("plan_type", ""))

    if not focus_areas and "exam" in plan_type:
        focus_areas.extend(["知识框架", "真题训练", "复盘"])

    if "软考" in goal:
        for area in ["软件工程", "系统设计", "算法"]:
            if area not in focus_areas:
                focus_areas.append(area)

    return focus_areas or ["基础知识", "实践练习", "阶段复盘"]


def _detect_plan_type(user_input: dict[str, Any]) -> str:
    explicit_type = str(user_input.get("plan_type") or "").strip()
    if explicit_type:
        return explicit_type

    goal = str(user_input.get("goal", ""))
    if any(keyword in goal for keyword in ["考试", "备考", "软考", "考研", "证书"]):
        return "exam_preparation"
    if any(keyword in goal for keyword in ["项目", "作品", "上线", "开发"]):
        return "project_practice"
    return "general_learning"


def _extract_key_constraints(user_input: dict[str, Any]) -> list[str]:
    constraints = []
    if user_input.get("start_date") and user_input.get("end_date"):
        constraints.append(f"学习周期：{user_input['start_date']} 到 {user_input['end_date']}")
    if user_input.get("daily_hours"):
        constraints.append(f"每日投入：{user_input['daily_hours']} 小时")
    if user_input.get("extra_constraints"):
        constraints.append(str(user_input["extra_constraints"]))
    return constraints


def _suggest_phase_count(duration_weeks: int) -> int:
    if duration_weeks <= 4:
        return 2
    return 3


def _is_valid_analysis(value: dict[str, Any]) -> bool:
    if not isinstance(value, dict) or value.get("error") or value.get("warning"):
        return False
    required_fields = ["goal", "plan_type", "duration_weeks", "daily_hours", "focus_areas"]
    return all(field in value for field in required_fields) and isinstance(value.get("focus_areas"), list)


def _extract_llm_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "LLM response is not a JSON object"
    return value.get("error") or value.get("warning")


def _as_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _merge_unique(primary: list[str], fallback: list[str]) -> list[str]:
    result = []
    for item in [*primary, *fallback]:
        if item and item not in result:
            result.append(item)
    return result


def _safe_int(value: Any, fallback: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return fallback


def _safe_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback
