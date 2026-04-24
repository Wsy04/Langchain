# 基于 LangGraph 的多智能体学习计划生成系统 Demo 实现计划

## 1. 项目目标

在 1 天内完成一个可演示的 Demo：用户通过 FastAPI 提交学习目标、当前水平、学习周期、每日可投入时长等信息，系统通过 LangGraph 编排多个 Agent，自动生成结构化学习计划，并展示需求分析、计划生成、计划校验、计划优化的完整流程。

Demo 重点不是完成生产级系统，而是证明以下能力：

- 能接收结构化学习需求。
- 能通过 LangGraph 串联多个 Agent。
- 能生成分阶段、每周任务、风险提示和优化建议。
- 能通过接口返回最终学习计划。
- 能查看中间执行过程，体现多智能体协作。

---

## 2. Demo 范围

### 2.1 必须完成

- FastAPI 后端服务。
- `POST /api/v1/plan/generate` 生成学习计划接口。
- LangGraph 工作流：需求分析 Agent → 计划生成 Agent → 计划校验 Agent → 可选计划优化 Agent。
- 统一状态对象 `PlanState`。
- 结构化请求与响应模型。
- 至少 1 个完整测试用例。
- 可运行的 Swagger 接口演示。

### 2.2 可选完成

- `GET /api/v1/plan/{task_id}/trace` 查看执行过程。
- 简单内存存储任务结果。
- 简单前端页面或接口调用脚本。
- 流式输出。

### 2.3 不在 Demo 范围

- 用户登录。
- 数据库持久化。
- 复杂前端。
- 多用户并发管理。
- 真实学习资源推荐。
- 长期打卡、提醒、复盘系统。

---

## 3. 一天实现节奏总览

| 时间段 | 阶段 | 目标 |
|---|---|---|
| 09:00 - 10:00 | 项目初始化 | 搭建 FastAPI + LangGraph 基础工程 |
| 10:00 - 11:30 | 数据结构与接口 | 完成请求、响应、状态模型 |
| 11:30 - 13:00 | Agent 实现 | 完成需求分析、计划生成、校验、优化 Agent |
| 14:00 - 15:30 | LangGraph 编排 | 完成工作流节点、条件路由和最终输出 |
| 15:30 - 16:30 | API 联调 | 接入 FastAPI，跑通生成接口 |
| 16:30 - 17:30 | Trace 与演示增强 | 展示中间状态、准备 Demo 数据 |
| 17:30 - 18:30 | 测试与修复 | 完成端到端测试、修复异常 |
| 18:30 - 19:00 | Demo 交付整理 | 准备 README、运行命令、演示话术 |

---

## 4. 技术选型

| 模块 | 技术 |
|---|---|
| 后端框架 | FastAPI |
| 多智能体编排 | LangGraph |
| LLM 调用封装 | LangChain / OpenAI-compatible API |
| 数据校验 | Pydantic |
| 存储 | 内存字典，Demo 阶段暂不接数据库 |
| 接口文档 | FastAPI Swagger |
| 运行方式 | Uvicorn |

---

## 5. 项目目录结构

```text
app/
├── main.py
├── api/
│   └── plan.py
├── graph/
│   ├── state.py
│   ├── workflow.py
│   └── router.py
├── agents/
│   ├── analyzer.py
│   ├── planner.py
│   ├── validator.py
│   └── optimizer.py
├── schemas/
│   ├── request.py
│   └── response.py
├── services/
│   └── llm_service.py
├── storage/
│   └── memory_store.py
└── prompts/
    ├── analyzer.md
    ├── planner.md
    ├── validator.md
    └── optimizer.md
```

### 完成标准

- 项目目录创建完成。
- `python -m app.main` 或 `uvicorn app.main:app --reload` 能正常启动。
- 访问 `/docs` 可以看到 Swagger 页面。

---

## 6. 分步骤实施计划

## Step 1：初始化项目环境

### 任务

1. 创建 Python 项目目录。
2. 安装依赖：
   - `fastapi`
   - `uvicorn`
   - `pydantic`
   - `langchain`
   - `langgraph`
   - `python-dotenv`
3. 创建 `.env.example`，预留模型配置。
4. 创建 FastAPI 最小启动文件。

### 建议命令

```bash
pip install fastapi uvicorn pydantic langchain langgraph python-dotenv
```

### 完成标准

- 执行以下命令可以启动服务：

```bash
uvicorn app.main:app --reload
```

- 浏览器访问 `http://127.0.0.1:8000/docs` 可以看到接口文档。
- `/health` 接口返回：

```json
{
  "status": "ok"
}
```

---

## Step 2：定义请求与响应模型

### 任务

在 `schemas/request.py` 中定义 `PlanRequest`：

```python
from pydantic import BaseModel, Field
from typing import Optional, List

class PlanRequest(BaseModel):
    goal: str = Field(..., description="学习目标")
    current_level: str = Field(..., description="当前水平")
    start_date: str = Field(..., description="开始日期")
    end_date: str = Field(..., description="结束日期")
    daily_hours: float = Field(..., description="每日学习时长")
    plan_type: str = Field(..., description="学习类型")
    weak_subjects: Optional[List[str]] = []
    extra_constraints: Optional[str] = None
```

在 `schemas/response.py` 中定义：

```python
from pydantic import BaseModel
from typing import List, Dict

class PhaseItem(BaseModel):
    phase_name: str
    weeks: str
    target: str
    tasks: List[str]

class PlanResponse(BaseModel):
    summary: str
    phases: List[PhaseItem]
    weekly_plan: List[Dict]
    suggestions: List[str]
    risks: List[str] = []

class ApiResponse(BaseModel):
    code: int
    message: str
    data: PlanResponse
```

### 完成标准

- 请求字段能通过 Pydantic 校验。
- 缺少 `goal`、`current_level`、`start_date`、`end_date`、`daily_hours` 时，接口返回 422。
- 响应结构固定包含：`summary`、`phases`、`weekly_plan`、`suggestions`。

---

## Step 3：定义 LangGraph 状态对象

### 任务

在 `graph/state.py` 中定义 `PlanState`：

```python
from typing import TypedDict, List, Dict, Any

class PlanState(TypedDict):
    task_id: str
    user_input: Dict[str, Any]
    analyzed_requirement: Dict[str, Any]
    draft_plan: Dict[str, Any]
    validation_result: Dict[str, Any]
    final_plan: Dict[str, Any]
    trace: List[Dict[str, Any]]
    status: str
    retry_count: int
```

### 字段说明

| 字段 | 说明 |
|---|---|
| `task_id` | 当前任务 ID |
| `user_input` | 用户原始输入 |
| `analyzed_requirement` | 需求分析结果 |
| `draft_plan` | 初版学习计划 |
| `validation_result` | 校验结果 |
| `final_plan` | 最终学习计划 |
| `trace` | 中间执行记录 |
| `status` | 当前流程状态 |
| `retry_count` | 优化重试次数 |

### 完成标准

- 每个 Agent 节点都接收并返回 `PlanState`。
- 每个节点执行后向 `trace` 追加一条记录。
- `status` 能反映当前执行阶段，例如：`analyzed`、`planned`、`validated`、`optimized`、`finished`。

---

## Step 4：实现 LLM 服务封装

### 任务

在 `services/llm_service.py` 中封装统一模型调用。

Demo 可以采用两种模式：

### 模式 A：真实 LLM 模式

通过环境变量读取 API Key 和模型名。

```python
import os
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
    api_key=os.getenv("OPENAI_API_KEY")
)
```

### 模式 B：Mock 模式

如果当天 Demo 不想依赖真实模型，可以先写死返回结构化结果，保证流程可演示。

```python
def mock_llm_json(prompt: str) -> dict:
    return {
        "summary": "Mock 生成结果",
        "items": []
    }
```

### 推荐策略

优先实现 Mock 模式，确保 Demo 一定跑通；如果时间允许，再接入真实 LLM。

### 完成标准

- Agent 不直接依赖具体模型 SDK。
- 替换真实 LLM 或 Mock LLM 时，不需要修改 Agent 主逻辑。
- 模型异常时返回可读错误信息，不导致服务崩溃。

---

## Step 5：实现需求分析 Agent

### 任务

在 `agents/analyzer.py` 中实现 `analyze_requirement_node(state)`。

职责：

- 提取学习目标。
- 识别学习类型。
- 计算周期周数。
- 提取薄弱项。
- 推断阶段数量。

### 示例输出

```json
{
  "goal": "3个月通过软考中级软件设计师考试",
  "plan_type": "exam_preparation",
  "duration_weeks": 12,
  "daily_hours": 2,
  "focus_areas": ["算法", "系统设计"],
  "suggested_phase_count": 3
}
```

### 完成标准

- 输入 Demo 案例后，可以输出结构化 `analyzed_requirement`。
- `duration_weeks` 为可用数字。
- 如果用户填写 `weak_subjects`，结果中必须体现这些薄弱项。
- `trace` 中记录 `需求分析 Agent 完成`。

---

## Step 6：实现计划生成 Agent

### 任务

在 `agents/planner.py` 中实现 `generate_plan_node(state)`。

职责：

- 根据 `analyzed_requirement` 生成阶段计划。
- 默认分为基础阶段、强化阶段、冲刺阶段。
- 生成每阶段目标与任务。
- 生成每周任务建议。

### 输出结构

```json
{
  "summary": "为期12周的软考中级备考计划",
  "phases": [
    {
      "phase_name": "基础阶段",
      "weeks": "第1-4周",
      "target": "建立知识框架，补齐基础概念",
      "tasks": ["学习数据结构基础", "梳理软件工程知识点"]
    }
  ],
  "weekly_plan": [
    {
      "week": 1,
      "focus": "数据结构与软件工程基础",
      "tasks": ["学习线性表", "完成基础题20道"]
    }
  ],
  "suggestions": []
}
```

### 完成标准

- 至少生成 3 个阶段。
- 每个阶段包含 `phase_name`、`weeks`、`target`、`tasks`。
- `weekly_plan` 至少覆盖前 4 周；理想情况下覆盖完整周期。
- 对薄弱项有明确倾斜，例如算法、系统设计出现在阶段任务或周任务中。
- `trace` 中记录 `计划生成 Agent 完成`。

---

## Step 7：实现计划校验 Agent

### 任务

在 `agents/validator.py` 中实现 `validate_plan_node(state)`。

校验维度：

1. 时间是否可行。
2. 阶段是否完整。
3. 是否体现薄弱项。
4. 是否有复习和缓冲安排。
5. 是否有过度安排风险。

### 输出结构

```json
{
  "passed": true,
  "issues": [],
  "suggestions": [
    "建议每两周安排一次模拟测试",
    "算法薄弱，建议每天至少30分钟专项练习"
  ]
}
```

### 完成标准

- 校验结果必须包含 `passed`、`issues`、`suggestions`。
- 如果阶段数量少于 2，必须判定为不通过。
- 如果计划未覆盖薄弱项，必须判定为不通过。
- 如果通过，`status` 更新为 `validated`。
- `trace` 中记录 `计划校验 Agent 完成`。

---

## Step 8：实现计划优化 Agent

### 任务

在 `agents/optimizer.py` 中实现 `optimize_plan_node(state)`。

触发条件：

- `validation_result.passed = false`
- 且 `retry_count < 2`

优化策略：

- 增加薄弱项任务。
- 减少过载任务。
- 增加复盘周或缓冲任务。
- 调整阶段比例。

### 完成标准

- 校验不通过时能进入优化节点。
- 优化后 `retry_count` 增加 1。
- 优化后的计划重新进入校验节点。
- 最多优化 2 次，避免死循环。
- `trace` 中记录 `计划优化 Agent 完成`。

---

## Step 9：实现 LangGraph 工作流

### 任务

在 `graph/workflow.py` 中构建工作流：

```python
from langgraph.graph import StateGraph, END
from app.graph.state import PlanState
from app.agents.analyzer import analyze_requirement_node
from app.agents.planner import generate_plan_node
from app.agents.validator import validate_plan_node
from app.agents.optimizer import optimize_plan_node


def should_optimize(state: PlanState):
    validation = state.get("validation_result", {})
    if validation.get("passed"):
        return "end"
    if state.get("retry_count", 0) >= 2:
        return "end"
    return "optimize"


def build_workflow():
    graph = StateGraph(PlanState)
    graph.add_node("analyzer", analyze_requirement_node)
    graph.add_node("planner", generate_plan_node)
    graph.add_node("validator", validate_plan_node)
    graph.add_node("optimizer", optimize_plan_node)

    graph.set_entry_point("analyzer")
    graph.add_edge("analyzer", "planner")
    graph.add_edge("planner", "validator")
    graph.add_conditional_edges(
        "validator",
        should_optimize,
        {
            "optimize": "optimizer",
            "end": END
        }
    )
    graph.add_edge("optimizer", "validator")

    return graph.compile()
```

### 完成标准

- 工作流能从 `analyzer` 执行到 `validator`。
- 校验通过时直接结束。
- 校验失败时进入 `optimizer`，再回到 `validator`。
- 不会出现无限循环。
- 最终状态中包含 `final_plan`。

---

## Step 10：实现 FastAPI 接口

### 任务

在 `api/plan.py` 中实现核心接口：

### 1. 生成学习计划

```http
POST /api/v1/plan/generate
```

职责：

- 接收 `PlanRequest`。
- 初始化 `PlanState`。
- 调用 LangGraph 工作流。
- 保存结果到内存存储。
- 返回最终计划。

### 2. 查看执行过程

```http
GET /api/v1/plan/{task_id}/trace
```

职责：

- 根据 `task_id` 返回 trace。
- 用于 Demo 展示多 Agent 协作过程。

### 3. 查看最终结果

```http
GET /api/v1/plan/{task_id}/result
```

职责：

- 根据 `task_id` 返回最终学习计划。

### 完成标准

- `POST /api/v1/plan/generate` 可以返回结构化学习计划。
- 响应中包含 `task_id`，便于查询 trace 和 result。
- `GET /api/v1/plan/{task_id}/trace` 能返回至少 3 个节点记录。
- Swagger 页面可以直接完成接口测试。

---

## Step 11：实现内存存储

### 任务

在 `storage/memory_store.py` 中实现简单存储：

```python
TASK_STORE = {}

def save_task(task_id: str, state: dict):
    TASK_STORE[task_id] = state


def get_task(task_id: str):
    return TASK_STORE.get(task_id)
```

### 完成标准

- 生成计划后可以通过 `task_id` 查询结果。
- 服务重启后数据丢失可以接受，因为 Demo 不要求持久化。
- 查询不存在的 `task_id` 时返回 404。

---

## Step 12：准备 Demo 测试数据

### 测试输入

```json
{
  "goal": "我想在3个月内通过软考中级软件设计师考试",
  "current_level": "基础一般，做题经验少",
  "start_date": "2026-03-01",
  "end_date": "2026-05-31",
  "daily_hours": 2,
  "plan_type": "exam_preparation",
  "weak_subjects": ["算法", "系统设计"],
  "extra_constraints": "工作日每天2小时，周末每天4小时，希望每两周有一次复盘"
}
```

### 预期输出

- 总体计划：12 周软考备考计划。
- 阶段划分：基础、强化、冲刺。
- 每周任务：覆盖算法、系统设计、真题训练、复盘。
- 风险提示：时间紧、薄弱项需要持续投入。
- 优化建议：每两周复盘一次，冲刺阶段增加真题模拟。

### 完成标准

- 使用 Swagger 提交测试输入，可以获得完整 JSON 响应。
- 响应结果中必须出现：`算法`、`系统设计`、`真题`、`复盘`。
- Trace 中能看到至少以下节点：
  - 需求分析 Agent
  - 计划生成 Agent
  - 计划校验 Agent
  - 计划优化 Agent，如触发

---

## 7. 验收清单

| 验收项 | 完成标准 | 是否必须 |
|---|---|---|
| 服务启动 | `uvicorn app.main:app --reload` 正常运行 | 必须 |
| Swagger 可用 | `/docs` 能访问 | 必须 |
| 生成接口可用 | `POST /api/v1/plan/generate` 返回计划 | 必须 |
| LangGraph 串联 Agent | 至少 3 个 Agent 节点被执行 | 必须 |
| 状态流转可见 | trace 中能看到中间状态 | 必须 |
| 结构化输出 | 返回 summary、phases、weekly_plan、suggestions | 必须 |
| 校验机制 | validator 能判断计划是否通过 | 必须 |
| 优化机制 | 校验失败时可进入 optimizer | 建议 |
| Mock 模型兜底 | 无 API Key 时 Demo 仍可跑 | 必须 |
| README | 有启动命令和接口示例 | 必须 |

---

## 8. Demo 演示流程

### 8.1 启动服务

```bash
uvicorn app.main:app --reload
```

### 8.2 打开接口文档

```text
http://127.0.0.1:8000/docs
```

### 8.3 调用生成接口

调用：

```http
POST /api/v1/plan/generate
```

展示内容：

- 用户输入。
- 最终学习计划。
- 阶段划分。
- 每周计划。
- 风险提示和优化建议。

### 8.4 调用 Trace 接口

调用：

```http
GET /api/v1/plan/{task_id}/trace
```

重点展示：

- 需求分析 Agent 如何提取目标。
- 计划生成 Agent 如何生成初稿。
- 计划校验 Agent 如何检查问题。
- 计划优化 Agent 如何修正。

---

## 9. 风险与应对

| 风险 | 影响 | 应对方案 |
|---|---|---|
| LLM 输出 JSON 不稳定 | 接口解析失败 | Demo 优先使用 Mock，真实 LLM 后接 |
| LangGraph 调试耗时 | 影响进度 | 先跑通线性流程，再加条件路由 |
| 优化循环复杂 | 出现死循环 | 限制 `retry_count <= 2` |
| 时间不足 | Demo 无法完整 | 保留核心接口，Trace 和前端作为可选 |
| 依赖安装问题 | 无法启动 | 固定 requirements.txt |

---

## 10. 当天交付物

### 必须交付

1. 可运行后端代码。
2. `requirements.txt`。
3. `README.md`。
4. Swagger 可测试接口。
5. 一组 Demo 输入和输出示例。
6. 本实现计划文档。

### 建议交付

1. `curl` 调用脚本。
2. Postman Collection。
3. 简单流程图截图。
4. Trace 接口演示结果。

---

## 11. README 建议内容

```md
# LangGraph 多智能体学习计划生成 Demo

## 启动

pip install -r requirements.txt
uvicorn app.main:app --reload

## 接口文档

http://127.0.0.1:8000/docs

## 核心接口

POST /api/v1/plan/generate
GET /api/v1/plan/{task_id}/trace
GET /api/v1/plan/{task_id}/result

## Demo 输入

见 examples/demo_request.json
```

---

## 12. 最小可行版本优先级

如果时间非常紧，按以下优先级实现：

### P0：必须完成

- FastAPI 启动。
- `POST /plan/generate` 接口。
- Mock Agent。
- LangGraph 串联 3 个节点。
- 返回结构化学习计划。

### P1：建议完成

- 校验失败后进入优化节点。
- Trace 接口。
- README。

### P2：有时间再做

- 真实 LLM 接入。
- 流式输出。
- 简单前端。
- 数据库存储。

---

## 13. 最终验收口径

Demo 完成的判断标准是：

> 在 Swagger 中输入一个学习目标后，系统能够通过 LangGraph 多 Agent 工作流，返回一份包含总体规划、阶段划分、每周任务、风险提示和优化建议的结构化学习计划，并且能够展示每个 Agent 的中间执行过程。

只要满足上述标准，即可认为一日 Demo 达成。
