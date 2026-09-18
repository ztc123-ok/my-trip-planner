"""通过 DDGS 自带的 DuckDuckGo MCP 工具搜索景点图片。"""

import ast
import json
import logging
import os
import sys
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Any, Optional
from urllib.parse import urlsplit

from hello_agents.tools import MCPTool

from .amap_service import resolve_uvx

logger = logging.getLogger(__name__)
DUCKDUCKGO_RETRY_SECONDS = 300


def _image_results(value: Any) -> list[dict]:
    """HelloAgents 会给 MCP 结果加文字前缀，兼容 JSON 和 Python 列表格式。"""
    if isinstance(value, dict):
        if value.get("isError"):
            raise ValueError(str(value.get("content") or "DuckDuckGo 图片搜索失败"))
        for key in ("results", "result", "content"):
            if key in value:
                return _image_results(value[key])
        return [value] if "image" in value or "thumbnail" in value else []
    if isinstance(value, list):
        return [item for part in value for item in _image_results(part)]
    if not isinstance(value, str):
        return []

    payload = value.split("执行结果:\n", 1)[-1].strip()
    for parser in (json.loads, ast.literal_eval):
        try:
            return _image_results(parser(payload))
        except (SyntaxError, ValueError, TypeError, json.JSONDecodeError):
            continue
    if "失败" in payload or "Error" in payload:
        raise ValueError(payload[:300])
    raise ValueError("DuckDuckGo MCP 返回了无法解析的图片结果")


def _valid_image_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


class DuckDuckGoPhotoService:
    def __init__(self, mcp_tool: Optional[MCPTool] = None):
        if mcp_tool is None:
            runtime_dir = Path(__file__).resolve().parents[2]
            tool_env = {
                "UV_CACHE_DIR": os.getenv("UV_CACHE_DIR") or str(runtime_dir / ".uv-cache"),
                "UV_TOOL_DIR": os.getenv("UV_TOOL_DIR") or str(runtime_dir / ".uv-tools"),
                "UV_TOOL_BIN_DIR": os.getenv("UV_TOOL_BIN_DIR") or str(runtime_dir / ".uv-bin"),
            }
            if os.getenv("DDGS_PROXY"):
                tool_env["DDGS_PROXY"] = os.environ["DDGS_PROXY"]
            mcp_tool = MCPTool(
                name="duckduckgo",
                description="DuckDuckGo 景点图片搜索",
                server_command=[
                    resolve_uvx(), "--python", sys.executable,
                    "--from", "ddgs[mcp]==9.16.0", "python", "-u",
                    str(Path(__file__).with_name("ddgs_mcp_launcher.py")),
                ],
                env=tool_env,
                auto_expand=True,
            )
        available = {
            item.get("name") for item in mcp_tool._available_tools if isinstance(item, dict)
        }
        if "search_images" not in available:
            raise RuntimeError("DuckDuckGo MCP 未发现 search_images 工具")
        self.mcp_tool = mcp_tool
        self._cache: dict[str, str] = {}
        self._cache_lock = Lock()
        self._duckduckgo_retry_after = 0.0

    def _search_image(self, query: str, backend: str) -> Optional[str]:
        raw = self.mcp_tool.run({
            "action": "call_tool",
            "tool_name": "search_images",
            "arguments": {
                "query": query,
                "backend": backend,
                "region": "cn-zh",
                "safesearch": "moderate",
                "max_results": 5,
            },
        })
        for item in _image_results(raw):
            # Bing thumbnails are served by its image CDN; source sites may block hotlinks.
            fields = ("thumbnail", "image") if backend == "bing" else ("image", "thumbnail")
            for field in fields:
                image_url = _valid_image_url(item.get(field))
                if image_url:
                    return image_url
        return None

    def get_photo_url(self, name: str, city: str = "") -> Optional[str]:
        query = " ".join(part for part in (city.strip(), name.strip(), "景点 实景") if part)
        with self._cache_lock:
            if query in self._cache:
                return self._cache[query]
            try_duckduckgo = monotonic() >= self._duckduckgo_retry_after

        failures = []
        for backend in (("duckduckgo", "bing") if try_duckduckgo else ("bing",)):
            try:
                image_url = self._search_image(query, backend)
            except Exception as exc:
                failures.append(f"{backend}: {exc}")
                logger.warning("景点图片搜索失败 (%s): %s", backend, exc)
                image_url = None
            if image_url:
                with self._cache_lock:
                    self._cache[query] = image_url
                logger.info("景点图片搜索成功 (%s): %s", backend, query)
                return image_url
            if backend == "duckduckgo":
                with self._cache_lock:
                    self._duckduckgo_retry_after = monotonic() + DUCKDUCKGO_RETRY_SECONDS

        if failures:
            raise RuntimeError("景点图片搜索不可用: " + "; ".join(failures))
        return None


_photo_service: Optional[DuckDuckGoPhotoService] = None
_service_lock = Lock()


def get_duckduckgo_photo_service() -> DuckDuckGoPhotoService:
    global _photo_service
    with _service_lock:
        if _photo_service is None:
            _photo_service = DuckDuckGoPhotoService()
        return _photo_service
