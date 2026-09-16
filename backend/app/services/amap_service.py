"""高德地图 MCP 服务与数据转换。"""

import json
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


class AmapService:
    def __init__(self, mcp_tool: Optional[MCPTool] = None):
        if mcp_tool is None:
            api_key = get_settings().amap_api_key
            if not api_key:
                raise ValueError("请在 backend/.env 配置 AMAP_API_KEY")
            mcp_tool = MCPTool(
                name="amap",
                description="高德地图服务",
                server_command=["uvx", "amap-mcp-server"],
                env={"AMAP_MAPS_API_KEY": api_key},
                auto_expand=True,
            )
        self.mcp_tool = mcp_tool

    def _call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        result = decode_payload(self.mcp_tool.run({
            "action": "call_tool", "tool_name": tool_name, "arguments": arguments,
        }))
        if not isinstance(result, dict):
            raise ValueError("高德地图返回格式不正确")
        if str(result.get("status", "1")) == "0":
            raise ValueError(as_text(result.get("info") or "高德地图请求失败"))
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
            location = parse_location(poi.get("location"))
            if location:
                result.append(POIInfo(
                    id=as_text(poi.get("id")), name=as_text(poi.get("name")),
                    type=as_text(poi.get("type")), address=as_text(poi.get("address")),
                    location=location, tel=as_text(poi.get("tel")) or None,
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
            for cast in forecast.get("casts", []):
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
