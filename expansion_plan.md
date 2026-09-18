# my-trip-planner 拓展方案

## 一、现状总结

### 当前技术栈
| 层 | 技术 |
|---|---|
| 后端框架 | FastAPI + Pydantic |
| 智能体编排 | LangGraph StateGraph（线性：景点→天气→酒店→规划→校验） |
| 模型调用 | OpenAI SDK（兼容千问等） |
| 工具接入 | MCP SDK stdio_client（高德地图 + DDGS 图片） |
| 天气 | 高德 MCP + Open-Meteo 补齐 |
| 前端 | Vue 3 + TypeScript + Vite + Ant Design Vue |
| 地图 | 高德 JS API / Leaflet 回退 |
| 导出 | html2canvas + jsPDF |
| 测试 | unittest 22 项 |

### 当前功能
- 表单收集偏好，一次性生成多日行程
- 四 Agent 串行协作（景点/天气/酒店/规划）
- 高德 POI 搜索、天气、路线规划
- Bing 景点图片搜索
- 地图标记 + 弹窗展示
- 景点编辑（删除/排序）、预算编辑
- 导出图片/PDF

### 现有不足（简历视角）
1. **图是线性的**：无并行、无条件分支、无循环重试
2. **无对话界面**：纯表单，不能追问或修改
3. **无流式输出**：等全部完成才返回，体验差
4. **无记忆**：不保存历史偏好
5. **工具调用是硬编码的**：LLM 不参与工具选择决策
6. **无可观测性**：缺少 Trace 追踪

---

## 二、拓展方案（按优先级排序）

### Phase 1：LangGraph 高级特性（核心亮点）

#### 1.1 并行执行（Fan-out / Fan-in）
景点、天气、酒店三个节点互不依赖，改为并行执行后汇总到 planner。

```
START → [attractions, weather, hotels] → planner → validate → END
```

**简历关键词**：LangGraph 并行节点、Fan-out/Fan-in

#### 1.2 条件路由与循环重试
- validate 失败时，条件边回到 planner 重新生成（最多 2 次）
- 天气不可用时跳过天气摘要节点

```
planner → validate → (通过 → END, 失败 → planner)
```

**简历关键词**：条件边、自修复循环

#### 1.3 Human-in-the-Loop
在 planner 节点前设置 `interrupt_before`，将景点和酒店候选列表推送给用户确认后再生成行程。

**简历关键词**：人机协作、interrupt 中断点

#### 1.4 状态持久化（Checkpointer）
使用 LangGraph 的 `SqliteSaver` 或 `MemorySaver` 保存每次运行的状态快照，支持断点恢复和历史回溯。

**简历关键词**：状态检查点、断点续跑

---

### Phase 2：对话式交互 + 流式输出

#### 2.1 SSE 流式推送
用 LangGraph 的 `astream_events` 将每个节点的中间结果实时推送到前端。

后端：
- 新增 `POST /api/trip/plan/stream` 接口，返回 SSE
- 每个节点完成时推送事件（如 `attractions_done`、`weather_done`）

前端：
- EventSource 接收并逐步渲染（进度条 + 节点状态卡片）

**简历关键词**：SSE 流式推送、astream_events

#### 2.2 对话式行程修改
新增 Chat 界面，用户可通过自然语言修改已生成的行程：
- "把第二天的故宫换成颐和园"
- "帮我加一个素食午餐"
- "预算控制在 3000 以内"

实现：
- 新增 `chat_modify` LangGraph 子图
- 接收用户消息 + 当前 TripPlan，LLM 决策修改并返回新计划
- 前端在 Result 页右侧加聊天面板

**简历关键词**：多轮对话、子图编排

---

### Phase 3：LLM 自主工具调用（ReAct）

#### 3.1 将 MCP 工具暴露给 LLM
当前是在节点函数中硬编码调用 `amap_service.search_poi()`。改为：
- 用 `bind_tools` 将高德工具绑定到 LLM
- 使用 LangGraph 的 `ToolNode` 自动执行工具调用
- LLM 根据用户需求自主决定搜什么、搜几次

这是 **Agent ≠ 工作流** 的核心区别，对简历有显著加分。

**简历关键词**：ReAct、ToolNode、Function Calling、自主决策

#### 3.2 动态工具注册
MCP 发现的工具列表动态转换为 LangChain Tool 格式，新增 MCP 服务时无需改代码。

---

### Phase 4：RAG 知识增强

#### 4.1 旅行知识库
构建向量知识库，内容包括：
- 各城市热门景点的详细攻略、最佳游览季节
- 餐厅推荐和人均消费
- 交通指南（如何从机场到市区）

技术选型：
- 向量库：ChromaDB（轻量本地）或 FAISS
- Embedding：text-embedding-v3（阿里云）或 bge-m3
- 在 planner 节点前增加 retrieval 节点

**简历关键词**：RAG、向量检索、知识增强生成

---

### Phase 5：记忆与个性化

#### 5.1 短期记忆
同一会话内保持对话历史，支持上下文连续修改行程。用 LangGraph 的 `messages` 状态字段管理。

#### 5.2 长期记忆
- SQLite 存储用户历史偏好（喜欢的城市、饮食偏好、预算范围）
- 新规划时自动注入用户画像到 system prompt

**简历关键词**：短期/长期记忆、用户画像

---

### Phase 6：可观测性与评估

#### 6.1 LangSmith 集成
- 每次规划生成完整 Trace（包括每个节点的输入输出、耗时、Token 消耗）
- 可视化查看 Agent 决策链路

#### 6.2 结构化评估
- 计划完整性（是否有景点/三餐/酒店）
- 地理合理性（景点间距离是否合理）
- 预算准确性

**简历关键词**：LangSmith Tracing、Agent 评估

---

## 三、技术栈变化汇总

| 新增技术 | 用途 | 对应 Phase |
|---|---|---|
| LangGraph 并行/条件边/interrupt | 高级图编排 | 1 |
| LangGraph SqliteSaver | 状态持久化 | 1 |
| SSE (EventSource) | 流式推送 | 2 |
| LangGraph ToolNode + bind_tools | LLM 自主工具调用 | 3 |
| ChromaDB / FAISS | 向量知识库 | 4 |
| Embedding Model (bge-m3) | 文本向量化 | 4 |
| LangSmith | 可观测性 | 6 |

---

## 四、简历项目描述建议

完成 Phase 1-3 后，项目描述可以这样写：

> **智能旅行规划助手** — 基于 LangGraph 的多智能体旅行规划系统
>
> - 使用 LangGraph 构建多智能体协作工作流，景点/天气/酒店三个专家 Agent **并行执行**，规划 Agent 汇总生成行程，校验失败**自动重试**
> - 实现 **Human-in-the-Loop** 中断机制，用户可在规划前确认候选景点；支持**多轮对话**修改已生成行程
> - 基于 MCP 协议接入高德地图、DuckDuckGo 图片等外部工具，通过 **Function Calling** 让 LLM 自主决策工具调用
> - 使用 **SSE 流式推送**实时展示各节点执行进度；LangGraph **Checkpointer** 实现状态持久化与断点恢复
> - 前端 Vue 3 + TypeScript，地图标记与路线展示，行程编辑与 PDF 导出

完成 Phase 4-6 后可追加：

> - 基于 **ChromaDB + RAG** 检索城市攻略知识库，增强行程推荐质量
> - 集成 **LangSmith** 实现全链路 Trace 追踪与 Agent 质量评估

---

## 五、实施建议

| 建议 | 说明 |
|---|---|
| 优先做 Phase 1 | 并行 + 条件边 + checkpoint 是 LangGraph 最核心的能力，改动量不大但简历含金量最高 |
| Phase 2 的 SSE 流式是体验提升最大的 | 面试演示时效果远好于等 50 秒白屏 |
| Phase 3 的 ReAct 要慎重 | 自主工具调用需要模型能力较强，千问 flash 可能不够稳定，建议用 qwen-plus 或 GPT-4o-mini |
| 每个 Phase 独立可交付 | 不必全部完成，做到 Phase 1-2 已经能在简历上显著区分度 |
