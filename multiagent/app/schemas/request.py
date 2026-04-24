from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    goal: str = Field(..., description="学习目标")
    current_level: str = Field(..., description="当前水平")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    daily_hours: float = Field(..., gt=0, description="每日学习时长")
    plan_type: str = Field(..., description="学习类型")
    weak_subjects: list[str] = Field(default_factory=list, description="薄弱项")
    extra_constraints: str | None = Field(default=None, description="额外约束")

    model_config = {
        "json_schema_extra": {
            "example": {
                "goal": "3个月内通过软考中级软件设计师考试",
                "current_level": "基础一般，做题经验少",
                "start_date": "2026-03-01",
                "end_date": "2026-05-31",
                "daily_hours": 2,
                "plan_type": "exam_preparation",
                "weak_subjects": ["算法", "系统设计"],
                "extra_constraints": "工作日每天2小时，周末每天4小时，每两周复盘一次",
            }
        }
    }
