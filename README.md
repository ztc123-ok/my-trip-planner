# 智能旅行助手

后端使用 FastAPI、LangGraph、OpenAI 兼容模型客户端和高德地图 MCP；前端使用 Vue 3、TypeScript、Vite 和 Ant Design Vue。

## 功能

- 根据城市、日期、交通、住宿和旅行偏好生成多日行程
- 多 Agent 搜索景点、天气和酒店，再汇总景点、餐饮、住宿、天气与预算
- 查询 POI、天气、路线和景点照片
- 地图展示行程，编辑景点顺序，导出图片或 PDF

## 工作流

LangGraph 从 `START` 并行执行景点搜索、天气查询和酒店推荐，等待三个节点全部完成后汇总到行程规划节点，最后校验结果。景点、天气、酒店和图片继续使用原有的高德、Open-Meteo 与 DDGS MCP 数据源；行程接口及前端数据格式保持一致。模型通过 OpenAI 兼容接口连接，可沿用 `LLM_MODEL_ID`、`LLM_API_KEY`、`LLM_BASE_URL` 配置。

## 运行

需要 Python 3.10+、Node.js 18+、高德地图 Web 服务和 JavaScript API 密钥、可用的 LLM API 密钥。景点图片通过 DDGS MCP 的 Bing 图片后端搜索，无需 Unsplash 密钥。高德和 DDGS MCP 服务由 `uvx` 使用本地缓存启动，避免运行时因 PyPI 暂时不可用而中断规划。首次安装依赖时仍需能够访问包源；如需图片搜索代理，可在 `backend/.env` 配置 `DDGS_PROXY`。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:UV_CACHE_DIR = (Join-Path (Get-Location) '.uv-cache')
$env:UV_TOOL_DIR = (Join-Path (Get-Location) '.uv-tools')
$env:UV_TOOL_BIN_DIR = (Join-Path (Get-Location) '.uv-bin')
uv tool install --python (Get-Command python).Source --with 'pydantic>=2.11,<2.14' 'amap-mcp-server==0.1.11'
uv tool install --python (Get-Command python).Source --with 'pydantic>=2.11,<2.14' 'ddgs[mcp]==9.16.0'
Copy-Item .env.example .env
# 填写 .env 中的密钥
python run.py
```

MCP 工具使用独立于 `backend/.venv` 的环境，后端的依赖约束不会自动应用到工具环境。安装时通过 `--with` 限制 Pydantic 版本，避免旧版 MCP 导入已在 Pydantic 2.14 移除的 `eval_type_backport` 而失败。已有安装需要修复时，使用相同命令加上 `--force` 重新安装对应工具，并保留上述 `UV_*` 目录配置。

```powershell
cd frontend
npm ci
Copy-Item .env.example .env
# 填写 .env 中的高德 JS API Key
npm run dev
```

打开 `http://localhost:5173`，后端接口文档在 `http://localhost:8000/docs`。
