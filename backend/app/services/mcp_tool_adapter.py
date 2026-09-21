# -*- coding: utf-8 -*-
"""MCP 工具动态适配器与高德地图 LangChain 工具标准实现。

支持两种模式：
1. 预设标准工具套件（create_amap_langchain_tools）：针对高德地图常用 POI、天气、路线搜索进行强类型优化与输出序列化。
2. MCP 动态工具转换器（convert_mcp_to_langchain_tools）：利用 MCP Client 的 list_tools 与 inputSchema 动态反射生成 LangChain StructuredTool，实现无需改码动态接入新 MCP 工具。
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import BaseTool, StructuredTool, tool
from pydantic import BaseModel, Field, create_model

from ..models.schemas import POIInfo
from .amap_service import AmapService

logger = logging.getLogger(__name__)


def create_amap_langchain_tools(amap_service: AmapService) -> List[BaseTool]:
    """为 LLM 绑定标准高德地图工具套件。"""

    @tool
    def amap_search_poi(keywords: str, city: str) -> str:
        """搜索指定城市内的景点、美食、餐厅、酒店、咖啡馆或地标。
        返回真实地点名称、地址、经纬度坐标、类别及联系电话等结构化信息。
        如果需要根据用户喜好换景点、换餐厅或换酒店，务必调用此工具以获取真实经纬度。
        """
        try:
            pois = amap_service.search_poi(keywords=keywords, city=city)
            if not pois:
                return json.dumps({"status": "empty", "message": f"在高德地图未搜索到 {city} 的 '{keywords}' 相关地点"}, ensure_ascii=False)
            data = [
                {
                    "id": p.id,
                    "name": p.name,
                    "type": p.type,
                    "address": p.address,
                    "location": {"longitude": p.location.longitude, "latitude": p.location.latitude} if p.location else None,
                    "tel": p.tel,
                }
                for p in pois[:6]
            ]
            return json.dumps({"status": "success", "city": city, "keywords": keywords, "pois": data}, ensure_ascii=False)
        except Exception as exc:
            logger.warning("amap_search_poi 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    @tool
    def amap_get_weather(city: str) -> str:
        """查询指定城市的实时天气及未来几天的天气预报。
        当用户关心旅行日期的下雨、降温或安排室内/室外活动时调用。
        """
        try:
            weather_list = amap_service.get_weather(city=city)
            if not weather_list:
                return json.dumps({"status": "empty", "message": f"未获取到 {city} 的天气数据"}, ensure_ascii=False)
            data = [
                {
                    "date": w.date,
                    "day_weather": w.day_weather,
                    "night_weather": w.night_weather,
                    "day_temp": w.day_temp,
                    "night_temp": w.night_temp,
                    "wind": f"{w.wind_direction} {w.wind_power}",
                }
                for w in weather_list
            ]
            return json.dumps({"status": "success", "city": city, "forecasts": data}, ensure_ascii=False)
        except Exception as exc:
            logger.warning("amap_get_weather 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    @tool
    def amap_plan_route(origin: str, destination: str, route_type: str = "walking", city: str = "") -> str:
        """规划两个地点之间的路线和耗时。
        route_type 参数支持: 'walking'(步行), 'driving'(驾车/打车), 'transit'(公共交通)。
        当用户询问景点之间距离、交通耗时或推荐交通方式时调用。
        """
        try:
            route = amap_service.plan_route(
                origin_address=origin,
                destination_address=destination,
                origin_city=city or None,
                destination_city=city or None,
                route_type=route_type if route_type in ("walking", "driving", "transit") else "walking",
            )
            return json.dumps({
                "status": "success",
                "origin": origin,
                "destination": destination,
                "route_type": route.route_type,
                "distance_meters": route.distance,
                "duration_seconds": route.duration,
                "duration_minutes": round(route.duration / 60, 1),
                "summary": route.description,
            }, ensure_ascii=False)
        except Exception as exc:
            logger.warning("amap_plan_route 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    @tool
    def amap_search_around(keywords: str, center_address: str, city: str) -> str:
        """以某个已知地标、酒店或景点为中心，搜索其周边的餐厅、咖啡馆、便利店或景点。
        例如在用户要求 '找一家酒店旁边的特色烤鸭店' 或 '离住处不远的安静公园' 时调用。
        """
        try:
            # 组合查询中心地标和目标关键词
            combined_query = f"{center_address} {keywords}"
            pois = amap_service.search_poi(keywords=combined_query, city=city)
            if not pois:
                # 兜底直接搜索关键词
                pois = amap_service.search_poi(keywords=keywords, city=city)
            data = [
                {
                    "name": p.name,
                    "type": p.type,
                    "address": p.address,
                    "location": {"longitude": p.location.longitude, "latitude": p.location.latitude} if p.location else None,
                    "tel": p.tel,
                }
                for p in pois[:5]
            ]
            return json.dumps({"status": "success", "center": center_address, "keywords": keywords, "results": data}, ensure_ascii=False)
        except Exception as exc:
            logger.warning("amap_search_around 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    @tool
    def amap_get_poi_detail(poi_id: str) -> str:
        """根据 POI ID 查询特定地点的详细信息，例如具体电话、特色标签或深层业务属性。"""
        try:
            detail = amap_service.get_poi_detail(poi_id=poi_id)
            return json.dumps({"status": "success", "poi_id": poi_id, "detail": detail}, ensure_ascii=False)
        except Exception as exc:
            logger.warning("amap_get_poi_detail 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    return [
        amap_search_poi,
        amap_get_weather,
        amap_plan_route,
        amap_search_around,
        amap_get_poi_detail,
    ]


def convert_mcp_to_langchain_tools(mcp_client: Any) -> List[BaseTool]:
    """将 MCP Client 发现的工具列表动态反射转换为 LangChain StructuredTool 集合。
    
    实现新增 MCP 服务时无需改写业务代码即可暴露给 LLM（Phase 3.2 动态工具注册）。
    """
    tools: List[BaseTool] = []
    if mcp_client is None:
        return tools

    available_names = getattr(mcp_client, "available_tools", [])
    if not available_names:
        return tools

    for tool_name in available_names:
        # 创建捕获当前 tool_name 闭包的执行函数
        def make_executor(name: str):
            def execute_tool(**kwargs) -> str:
                try:
                    res = mcp_client.call_tool(name, kwargs)
                    if isinstance(res, (dict, list)):
                        return json.dumps(res, ensure_ascii=False)
                    return str(res)
                except Exception as err:
                    logger.warning("MCP 动态工具 %s 执行失败: %s", name, err)
                    return json.dumps({"error": str(err)}, ensure_ascii=False)
            return execute_tool

        executor = make_executor(tool_name)
        # 构建动态 StructuredTool
        lc_tool = StructuredTool.from_function(
            func=executor,
            name=f"mcp_{tool_name}",
            description=f"动态 MCP 工具: {tool_name}。通过 Model Context Protocol 协议直接调用底层服务接口。",
        )
        tools.append(lc_tool)

    return tools
