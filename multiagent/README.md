# LangGraph 多 Agent 学习计划生成 Demo

这是一个基于 FastAPI + LangGraph 的学习计划生成 Demo。用户提交学习目标、当前水平、学习周期、每日投入时间和薄弱项后，系统通过多个 Agent 协作生成结构化学习计划，并展示每个 Agent 的执行过程。

## 当前能力

- FastAPI 后端服务
- LangGraph 工作流编排
- Analyzer / Planner / Validator / Optimizer 多 Agent 流程
- DeepSeek / OpenAI-compatible LLM 调用
- LLM 调用失败时自动回退到本地规则
- Swagger 接口文档
- 前端验证页面
- 内存级任务结果查询

## 工作流

```text
Analyzer -> Planner -> Validator
                    ├─ 校验通过 -> END
                    └─ 校验失败 -> Optimizer -> Validator -> END
```

说明：

- Analyzer 负责需求分析、目标改写、学习类型识别、约束和薄弱项提取。
- Planner 负责生成阶段计划、每周任务、建议和风险。
- Validator 负责检查计划结构、薄弱项覆盖、复盘、真题/模拟等要求。
- Optimizer 只在 Validator 不通过时运行，用于根据校验意见修正计划。

因此，正常完整流程中如果 Validator 一次通过，Optimizer 会显示为 skipped，这是预期行为。

## 项目结构

```text
app/
  main.py
  api/
    analyzer.py
    plan.py
  agents/
    analyzer.py
    planner.py
    validator.py
    optimizer.py
  graph/
    state.py
    workflow.py
  schemas/
    request.py
    response.py
  services/
    llm_service.py
    runtime_logger.py
  storage/
    memory_store.py
  static/
    analyzer_demo.html
    workflow_demo.html
examples/
  demo_request.json
  call_generate_plan.ps1
```

## 安装依赖

建议在已有的 `langchain` conda 环境中运行：

```powershell
cd E:\pythonProject\Langchain\multiagent
conda activate langchain
pip install -r requirements.txt
```

## 环境变量

当前项目会优先读取：

```text
multiagent/.env
multiagent/.env.example
```

常用配置：

```env
DEEPSEEK_API_KEY=your_api_key
DEEPSEEK_API_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
LLM_MODE=real
APP_PORT=18010
```

如果希望不调用真实模型，可以临时使用 Mock 模式：

```powershell
$env:LLM_MODE="mock"
```

Mock 模式下 Analyzer / Planner / Optimizer 会尝试调用统一 LLM 服务，但模型返回不满足结构要求时会走本地兜底策略。

## 启动服务

推荐直接运行：

```powershell
cd E:\pythonProject\Langchain
conda activate langchain
D:/Anaconda3/envs/langchain/python.exe e:/pythonProject/Langchain/multiagent/app/main.py
```

启动后控制台会打印类似：

```text
Analyzer demo: http://127.0.0.1:18010/analyzer-demo
Workflow demo: http://127.0.0.1:18010/workflow-demo
```

如果 `18010` 不可用，程序会自动向后寻找可用端口。

也可以用 uvicorn 启动：

```powershell
cd E:\pythonProject\Langchain\multiagent
uvicorn app.main:app --host 127.0.0.1 --port 18010
```

## 前端验证页

### Analyzer 单 Agent 验证

```text
http://127.0.0.1:18010/analyzer-demo
```

用于快速查看需求分析 Agent 的输出：

- 学习目标
- 学习类型
- 学习周期周数
- 薄弱项
- trace

### 完整工作流验证

```text
http://127.0.0.1:18010/workflow-demo
```

页面支持两个按钮：

- 运行完整流程：执行 Analyzer -> Planner -> Validator，必要时进入 Optimizer。
- 验证优化路径：构造一个简化计划，强制触发 Validator -> Optimizer -> Validator。

页面会展示：

- 每个 Agent 的 trace
- LLM 或本地兜底来源
- Optimizer 是 executed 还是 skipped
- 数据是否从上一个 Agent 传到下一个 Agent
- 最终计划 JSON

## API

### 健康检查

```http
GET /health
```

返回：

```json
{"status": "ok"}
```

### 生成学习计划

```http
POST /api/v1/plan/generate
```

请求示例见：

```text
examples/demo_request.json
```

响应中包含：

- `task_id`
- `status`
- `plan`
- `validation_result`
- `trace`
- `workflow_summary`

### 查询执行过程

```http
GET /api/v1/plan/{task_id}/trace
```

### 查询最终结果

```http
GET /api/v1/plan/{task_id}/result
```

### 强制验证优化路径

```http
POST /api/v1/plan/debug/optimizer
```

该接口用于 Demo 调试，会人为构造一个不完整计划，使 Validator 失败，从而触发 Optimizer。

## PowerShell 示例

启动服务后运行：

```powershell
cd E:\pythonProject\Langchain\multiagent
.\examples\call_generate_plan.ps1
```

如果服务端口不是 `18010`：

```powershell
$env:APP_BASE_URL="http://127.0.0.1:18011"
.\examples\call_generate_plan.ps1
```

## 日志与排查

后端会在控制台打印每个任务的执行信息，例如：

```text
task=... stage=analyzer start
task=... stage=analyzer.llm request-start
task=... stage=planner selected-plan source=llm
task=... stage=validator checked passed=True
task=... stage=api.generate request-end status=validated
```

如果前端等待时间较长，可以看最后停在哪一行：

- `analyzer.llm request-start`：Analyzer 正在等待 LLM。
- `planner.llm request-start`：Planner 正在等待 LLM。
- `optimizer.llm request-start`：Optimizer 正在等待 LLM。
- `api.generate request-end`：后端已经完成。

## 关于持久化

当前项目不做数据库持久化，这是 Demo 阶段的设计选择。

任务结果保存在内存中：

```text
app/storage/memory_store.py
```

影响：

- 服务运行期间，可以通过 `task_id` 查询 trace 和 result。
- 服务重启后，内存数据会清空。
- 旧的 `task_id` 会返回 404。

这符合当前 Demo 目标：验证多 Agent 协作、LangGraph 编排和接口演示，而不是构建生产级历史任务系统。

## 当前限制

- 无用户登录
- 无数据库持久化
- 无多用户任务管理
- 无长期打卡/提醒/复盘系统
- 前端页面只用于 Demo 验证
- LLM 输出质量依赖模型和网络状态，但系统已提供本地兜底

## 验收口径

在 `/workflow-demo` 或 Swagger 中提交学习目标后，系统能返回：

- 需求分析结果
- 阶段计划
- 每周计划
- 风险提示
- 优化建议
- Agent trace
- LLM / fallback 来源

即可认为 Demo 主流程可用。
