from typing import Any

from pydantic import BaseModel, Field


class PhaseItem(BaseModel):
    phase_name: str = Field(..., description="阶段名称")
    weeks: str = Field(..., description="阶段覆盖周数")
    target: str = Field(..., description="阶段目标")
    tasks: list[str] = Field(..., description="阶段任务")


class PlanResponse(BaseModel):
    summary: str = Field(..., description="学习计划摘要")
    phases: list[PhaseItem] = Field(..., description="阶段计划")
    weekly_plan: list[dict[str, Any]] = Field(..., description="每周计划")
    suggestions: list[str] = Field(..., description="优化建议")
    risks: list[str] = Field(default_factory=list, description="风险提示")


class ApiResponse(BaseModel):
    code: int = Field(..., description="业务状态码")
    message: str = Field(..., description="响应消息")
    data: PlanResponse = Field(..., description="学习计划数据")
