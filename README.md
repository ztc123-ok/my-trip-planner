# 智能旅行助手

参考 `helloagents-trip-planner` 逐步实现的旅行规划应用。后端使用 FastAPI、HelloAgents 和高德地图 MCP；前端使用 Vue 3、TypeScript、Vite 和 Ant Design Vue。

## 功能

- 根据城市、日期、交通、住宿和旅行偏好生成多日行程
- 多 Agent 搜索景点、天气和酒店，再汇总景点、餐饮、住宿、天气与预算
- 查询 POI、天气、路线和景点照片
- 地图展示行程，编辑景点顺序，导出图片或 PDF

## 运行

需要 Python 3.10+、Node.js 18+、高德地图 Web 服务和 JavaScript API 密钥、可用的 LLM API 密钥。景点图片通过 DuckDuckGo MCP 搜索，无需 Unsplash 密钥；高德和 DuckDuckGo MCP 服务由 `uvx` 启动。若无法直连 DuckDuckGo，可在 `backend/.env` 配置 `DDGS_PROXY`。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 填写 .env 中的密钥
python run.py
```

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
# 填写 .env 中的高德 JS API Key
npm run dev
```

打开 `http://localhost:5173`，后端接口文档在 `http://localhost:8000/docs`。请勿提交 `.env`。

参考项目：`helloagents-trip-planner`，其 README 标注 CC BY-NC-SA 4.0。此项目保留其技术方案与界面结构，并针对占位实现和集成问题作了完善。
