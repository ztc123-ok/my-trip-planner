"""通过 DDGS MCP 的 Bing 图片后端搜索景点图片。"""

import ast
import json
import logging
import os
import sys
from pathlib import Path
from threading import Lock
from typing import Any, Optional
from urllib.parse import urlsplit

from .amap_service import resolve_uvx
from .mcp_client import MCPToolClient

logger = logging.getLogger(__name__)


def _image_results(value: Any) -> list[dict]:
    """Parse structured or text image results returned by the MCP server."""
    if isinstance(value, dict):
        if value.get("isError"):
            raise ValueError(str(value.get("content") or "DDGS 图片搜索失败"))
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
    raise ValueError("DDGS MCP 返回了无法解析的图片结果")


def _valid_image_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


class DDGSPhotoService:
    def __init__(self, mcp_tool: Optional[MCPToolClient] = None):
        if mcp_tool is None:
            runtime_dir = Path(__file__).resolve().parents[2]
            tool_env = {
                "UV_CACHE_DIR": os.getenv("UV_CACHE_DIR") or str(runtime_dir / ".uv-cache"),
                "UV_TOOL_DIR": os.getenv("UV_TOOL_DIR") or str(runtime_dir / ".uv-tools"),
                "UV_TOOL_BIN_DIR": os.getenv("UV_TOOL_BIN_DIR") or str(runtime_dir / ".uv-bin"),
            }
            if os.getenv("DDGS_PROXY"):
                tool_env["DDGS_PROXY"] = os.environ["DDGS_PROXY"]
            mcp_tool = MCPToolClient(
                server_command=[
                    resolve_uvx(), "--offline", "--python", sys.executable,
                    "--from", "ddgs[mcp]==9.16.0", "ddgs", "mcp",
                ],
                env=tool_env,
            )
        available = set(mcp_tool.available_tools)
        if "search_images" not in available:
            raise RuntimeError("DDGS MCP 未发现 search_images 工具")
        self.mcp_tool = mcp_tool
        self._cache: dict[str, str] = {}
        self._cache_lock = Lock()

    def _search_image(self, query: str) -> Optional[str]:
        raw = self.mcp_tool.call_tool("search_images", {
                "query": query,
                "backend": "bing",
                "region": "cn-zh",
                "safesearch": "moderate",
                "max_results": 5,
        })
        for item in _image_results(raw):
            # Bing thumbnails are served by its image CDN; source sites may block hotlinks.
            for field in ("thumbnail", "image"):
                image_url = _valid_image_url(item.get(field))
                if image_url:
                    return image_url
        return None

    def get_photo_url(self, name: str, city: str = "") -> Optional[str]:
        queries = [
            " ".join(part for part in (city.strip(), name.strip(), "景点 实景") if part),
            " ".join(part for part in (city.strip(), name.strip()) if part),
        ]
        # 去除重复和空 query
        unique_queries = []
        for q in queries:
            if q and q not in unique_queries:
                unique_queries.append(q)

        for query in unique_queries:
            with self._cache_lock:
                if query in self._cache:
                    return self._cache[query]

            try:
                image_url = self._search_image(query)
            except Exception as exc:
                logger.warning("景点图片搜索不可用 (%s): %s", query, exc)
                continue

            if image_url:
                with self._cache_lock:
                    self._cache[query] = image_url
                logger.info("景点图片搜索成功 (bing): %s", query)
                return image_url
        return None


_photo_service: Optional[DDGSPhotoService] = None
_service_lock = Lock()


def get_ddgs_photo_service() -> DDGSPhotoService:
    global _photo_service
    with _service_lock:
        if _photo_service is None:
            _photo_service = DDGSPhotoService()
        return _photo_service
