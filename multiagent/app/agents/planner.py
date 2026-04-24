from app.graph.state import PlanState


def generate_plan_node(state: PlanState) -> PlanState:
    requirement = state.get("analyzed_requirement", {})
    duration_weeks = max(1, int(requirement.get("duration_weeks", 1) or 1))
    focus_areas = _normalize_focus_areas(requirement.get("focus_areas", []))
    goal = requirement.get("goal", "学习目标")

    phases = _build_phases(duration_weeks, focus_areas)
    weekly_plan = _build_weekly_plan(duration_weeks, focus_areas)
    draft_plan = {
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

    trace = list(state.get("trace", []))
    trace.append(
        {
            "node": "计划生成 Agent",
            "status": "completed",
            "message": "计划生成 Agent 完成",
            "output": {
                "phase_count": len(phases),
                "weekly_plan_count": len(weekly_plan),
            },
        }
    )

    return {
        **state,
        "draft_plan": draft_plan,
        "trace": trace,
        "status": "planned",
    }


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
