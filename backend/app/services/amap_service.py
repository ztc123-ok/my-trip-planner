"""高德地图 MCP 服务与数据转换。"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from hello_agents.tools import MCPTool

from ..config import get_settings
from ..models.schemas import Location, POIInfo, RouteInfo, WeatherInfo


def decode_payload(value: Any) -> Any:
    if isinstance(value, dict):
        if value.get("isError"):
            raise ValueError(str(value.get("content", "MCP 工具调用失败")))
        if isinstance(value.get("content"), list):
            texts = [item.get("text", "") for item in value["content"] if isinstance(item, dict)]
            if texts:
                return decode_payload("\n".join(texts))
        return value
    if not isinstance(value, str):
        raise ValueError("无法识别高德地图响应")
    try:
        return decode_payload(json.loads(value))
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for offset, char in enumerate(value):
            if char in "{[":
                try:
                    return decode_payload(decoder.raw_decode(value[offset:])[0])
                except json.JSONDecodeError:
                    continue
    raise ValueError(value.strip() or "高德地图响应中没有有效 JSON")


def parse_location(value: Any) -> Optional[Location]:
    try:
        if isinstance(value, dict):
            return Location(longitude=float(value["longitude"]), latitude=float(value["latitude"]))
        if isinstance(value, str):
            longitude, latitude = value.split(",", 1)
            return Location(longitude=float(longitude), latitude=float(latitude))
    except (KeyError, TypeError, ValueError):
        pass
    return None


def as_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return "" if value is None else str(value)


def resolve_uvx() -> str:
    """优先使用当前 Python 环境安装的 uvx，避免 IDE 未激活 Conda 时找不到命令。"""
    python_dir = Path(sys.executable).resolve().parent
    local_uvx = (
        python_dir / "Scripts" / "uvx.exe"
        if os.name == "nt" else python_dir / "uvx"
    )
    if local_uvx.is_file():
        return str(local_uvx)
    uvx = shutil.which("uvx")
    if uvx:
        return uvx
    raise RuntimeError(
        f"找不到 uvx；请在当前 Python 环境 {sys.executable} 中安装 uv，"
        "或将 uvx 所在目录加入 PATH。"
    )


def create_amap_tool(api_key: str) -> MCPTool:
    """发现并检查高德 MCP 工具，避免空工具被注册给 Agent。"""
    if not api_key:
        raise ValueError("请在 backend/.env 配置 AMAP_API_KEY")
    runtime_dir = Path(__file__).resolve().parents[2]
    tool_env = {
        "AMAP_MAPS_API_KEY": api_key,
        "UV_CACHE_DIR": os.getenv("UV_CACHE_DIR") or str(runtime_dir / ".uv-cache"),
        "UV_TOOL_DIR": os.getenv("UV_TOOL_DIR") or str(runtime_dir / ".uv-tools"),
        "UV_TOOL_BIN_DIR": os.getenv("UV_TOOL_BIN_DIR") or str(runtime_dir / ".uv-bin"),
    }
    tool = MCPTool(
        name="amap",
        description="高德地图服务",
        server_command=[resolve_uvx(), "--python", sys.executable, "amap-mcp-server"],
        env=tool_env,
        auto_expand=True,
    )
    available = {
        item.get("name") for item in tool._available_tools if isinstance(item, dict)
    }
    required = {"maps_text_search", "maps_weather"}
    if not required.issubset(available):
        raise RuntimeError(
            "高德 MCP 工具发现失败，缺少 "
            + ", ".join(sorted(required - available))
            + "。请确认 uvx 可运行、amap-mcp-server 能启动，"
            + f"并检查缓存目录 {tool_env['UV_CACHE_DIR']} 是否可写。"
        )
    tool.expandable = True
    return tool


class AmapService:
    def __init__(self, mcp_tool: Optional[MCPTool] = None):
        if mcp_tool is None:
            mcp_tool = create_amap_tool(get_settings().amap_api_key)
        self.mcp_tool = mcp_tool

    def _call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = decode_payload(self.mcp_tool.run({
            "action": "call_tool", "tool_name": tool_name, "arguments": arguments,
        }))
        if not isinstance(result, dict):
            raise ValueError("高德地图返回格式不正确")
        if str(result.get("status", "1")) == "0":
            raise ValueError(as_text(result.get("info") or "高德地图请求失败"))
        if result.get("error"):
            raise ValueError(as_text(result["error"]))
        return result

    def search_poi(self, keywords: str, city: str, citylimit: bool = True) -> List[POIInfo]:
        pois = self._call("maps_text_search", {
            "keywords": keywords, "city": city, "citylimit": str(citylimit).lower(),
        }).get("pois", [])
        if not isinstance(pois, list):
            raise ValueError("POI 响应缺少 pois 列表")
        result = []
        for poi in pois:
            if not isinstance(poi, dict):
                continue
            result.append(POIInfo(
                id=as_text(poi.get("id")), name=as_text(poi.get("name")),
                type=as_text(poi.get("type") or poi.get("typecode")),
                address=as_text(poi.get("address")),
                location=parse_location(poi.get("location")),
                tel=as_text(poi.get("tel")) or None,
            ))
        return result

    def get_weather(self, city: str) -> List[WeatherInfo]:
        forecasts = self._call("maps_weather", {"city": city}).get("forecasts", [])
        if not isinstance(forecasts, list):
            raise ValueError("天气响应缺少 forecasts 列表")
        result = []
        for forecast in forecasts:
            if not isinstance(forecast, dict):
                continue
            casts = forecast.get("casts", [forecast])
            for cast in casts:
                if isinstance(cast, dict):
                    result.append(WeatherInfo(
                        date=as_text(cast.get("date")),
                        day_weather=as_text(cast.get("dayweather")),
                        night_weather=as_text(cast.get("nightweather")),
                        day_temp=cast.get("daytemp", 0),
                        night_temp=cast.get("nighttemp", 0),
                        wind_direction=as_text(cast.get("daywind")),
                        wind_power=as_text(cast.get("daypower")),
                    ))
        return result

    def plan_route(
        self, origin_address: str, destination_address: str,
        origin_city: Optional[str] = None, destination_city: Optional[str] = None,
        route_type: str = "walking",
    ) -> RouteInfo:
        tools = {
            "walking": "maps_direction_walking_by_address",
            "driving": "maps_direction_driving_by_address",
            "transit": "maps_direction_transit_integrated_by_address",
        }
        if route_type not in tools:
            raise ValueError("route_type 只能是 walking、driving 或 transit")
        arguments = {"origin_address": origin_address, "destination_address": destination_address}
        if origin_city:
            arguments["origin_city"] = origin_city
        if destination_city:
            arguments["destination_city"] = destination_city
        payload = self._call(tools[route_type], arguments)
        route = payload.get("route", payload)
        paths = route.get("paths") or route.get("transits") or []
        if not isinstance(paths, list) or not paths:
            raise ValueError("高德地图未返回可用路线")
        path = paths[0]
        description = "；".join(
            as_text(step.get("instruction")) for step in path.get("steps", [])
            if isinstance(step, dict) and step.get("instruction")
        )
        return RouteInfo(
            distance=float(path.get("distance", route.get("distance", 0))),
            duration=int(float(path.get("duration", 0))),
            route_type=route_type,
            description=description or f"{origin_address} → {destination_address}",
        )

    def geocode(self, address: str, city: Optional[str] = None) -> Optional[Location]:
        arguments = {"address": address}
        if city:
            arguments["city"] = city
        geocodes = self._call("maps_geo", arguments).get("geocodes", [])
        return parse_location(geocodes[0].get("location")) if geocodes else None

    def get_poi_detail(self, poi_id: str) -> Dict[str, Any]:
        payload = self._call("maps_search_detail", {"id": poi_id})
        pois = payload.get("pois", [])
        return pois[0] if isinstance(pois, list) and pois else payload


_amap_service: Optional[AmapService] = None


def get_amap_service() -> AmapService:
    global _amap_service
    if _amap_service is None:
        _amap_service = AmapService()
    return _amap_service
