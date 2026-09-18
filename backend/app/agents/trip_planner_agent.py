"""LangGraph 多角色旅行规划工作流。"""

import json
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from ..services.llm_service import get_llm
from ..services.amap_service import AmapService, create_amap_tool
from ..services.weather_service import get_trip_forecast
from ..models.schemas import TripRequest, TripPlan, WeatherInfo
from ..config import get_settings

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。根据高德地图 MCP 已返回的真实景点资料，
整理适合目的地和用户偏好的景点。保留名称、地址与坐标，不要编造未提供的地点。"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。只根据已取得的真实预报简要说明天气。
不得添加不存在的日期或编造温度。"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。根据高德地图 MCP 已返回的真实酒店资料，
整理适合用户住宿偏好的酒店。保留名称、地址与坐标，不要编造未提供的酒店。"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息和天气信息,生成详细的旅行计划。

请严格按照以下JSON格式返回旅行计划:
```json
{
  "city": "城市名称",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "day_index": 0,
      "description": "第1天行程概述",
      "transportation": "交通方式",
      "accommodation": "住宿类型",
      "hotel": {
        "name": "酒店名称",
        "address": "酒店地址",
        "location": {"longitude": 116.397128, "latitude": 39.916527},
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距离景点2公里",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "景点名称",
          "address": "详细地址",
          "location": {"longitude": 116.397128, "latitude": 39.916527},
          "visit_duration": 120,
          "description": "景点详细描述",
          "category": "景点类别",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "早餐推荐", "description": "早餐描述", "estimated_cost": 30},
        {"type": "lunch", "name": "午餐推荐", "description": "午餐描述", "estimated_cost": 50},
        {"type": "dinner", "name": "晚餐推荐", "description": "晚餐描述", "estimated_cost": 80}
      ]
    }
  ],
  "weather_info": [
    {
      "date": "YYYY-MM-DD",
      "day_weather": "晴",
      "night_weather": "多云",
      "day_temp": 25,
      "night_temp": 15,
      "wind_direction": "南风",
      "wind_power": "1-3级"
    }
  ],
  "overall_suggestions": "总体建议",
  "budget": {
    "total_attractions": 180,
    "total_hotels": 1200,
    "total_meals": 480,
    "total_transportation": 200,
    "total": 2060
  }
}
```

**重要提示:**
1. weather_info只能包含已提供的真实天气数据；如果某天没有预报则省略，不得编造
2. 温度必须是纯数字(不要带°C等单位)
3. 每天安排2-3个景点
4. 考虑景点之间的距离和游览时间
5. 每天必须包含早中晚三餐
6. 提供实用的旅行建议
7. **必须包含预算信息**:
   - 景点门票价格(ticket_price)
   - 餐饮预估费用(estimated_cost)
   - 酒店预估费用(estimated_cost)
   - 预算汇总(budget)包含各项总费用
"""


def planner_llm_options(llm) -> dict:
    """长 JSON 规划关闭千问 3 默认思考，减少等待和超时。"""
    if getattr(llm, "provider", "") == "qwen" and str(getattr(llm, "model", "")).startswith("qwen3."):
        return {
            "extra_body": {"enable_thinking": False},
            "timeout": max(90, getattr(llm, "timeout", 60)),
        }
    return {}


class TripGraphState(TypedDict, total=False):
    request: TripRequest
    attraction_response: str
    weather_data: list[WeatherInfo]
    weather_source: str
    weather_response: str
    hotel_response: str
    planner_response: str
    trip_plan: TripPlan


class MultiAgentTripPlanner:
    """Four specialist LangGraph nodes with a validated TripPlan output."""

    agent_names = ("景点搜索专家", "天气查询专家", "酒店推荐专家", "行程规划专家")

    def __init__(self, llm=None, amap_service: AmapService | None = None):
        settings = get_settings()
        self.llm = llm if llm is not None else get_llm()
        self.amap_service = (
            amap_service if amap_service is not None
            else AmapService(mcp_tool=create_amap_tool(settings.amap_api_key))
        )
        builder = StateGraph(TripGraphState)
        builder.add_node("attractions", self._search_attractions)
        builder.add_node("weather", self._get_weather)
        builder.add_node("hotels", self._search_hotels)
        builder.add_node("planner", self._generate_plan)
        builder.add_node("validate", self._validate_plan)
        builder.add_edge(START, "attractions")
        builder.add_edge("attractions", "weather")
        builder.add_edge("weather", "hotels")
        builder.add_edge("hotels", "planner")
        builder.add_edge("planner", "validate")
        builder.add_edge("validate", END)
        self.graph = builder.compile()

    def plan_trip(self, request: TripRequest) -> TripPlan:
        print(f"🚀 LangGraph 开始规划 {request.city} 的 {request.travel_days} 天行程")
        result = self.graph.invoke({"request": request})
        print("✅ LangGraph 旅行计划生成完成")
        return result["trip_plan"]

    def _search_attractions(self, state: TripGraphState) -> dict:
        request = state["request"]
        keywords = request.preferences[0] if request.preferences else "景点"
        print("📍 步骤1: 搜索景点...")
        pois = self.amap_service.search_poi(keywords, request.city)
        if not pois:
            raise ValueError(f"高德地图未找到 {request.city} 的{keywords}景点")
        verified = json.dumps([poi.model_dump(mode="json") for poi in pois], ensure_ascii=False)
        summary = self.llm.generate(
            ATTRACTION_AGENT_PROMPT,
            f"城市：{request.city}；偏好：{', '.join(request.preferences) or '无'}。已检索景点：{verified}",
        )
        return {"attraction_response": f"高德地图真实景点：{verified}\n专家整理：{summary}"}

    def _get_weather(self, state: TripGraphState) -> dict:
        request = state["request"]
        print("🌤️  步骤2: 查询天气...")
        try:
            weather_data, weather_source = get_trip_forecast(
                self.amap_service, request.city, request.start_date, request.end_date
            )
        except Exception as exc:
            weather_data, weather_source = [], ""
            weather_response = f"天气查询不可用：{exc}。请勿编造天气数据。"
        else:
            if not weather_data:
                weather_response = "旅行日期内暂无可靠的天气预报，请勿编造天气数据。"
            elif weather_source != "高德地图":
                weather_response = f"已取得 {weather_source} 的 {len(weather_data)} 天预报。"
            else:
                verified = json.dumps(
                    [item.model_dump(mode="json") for item in weather_data], ensure_ascii=False
                )
                try:
                    weather_response = self.llm.generate(
                        WEATHER_AGENT_PROMPT, f"城市：{request.city}；已取得预报：{verified}"
                    )
                except Exception as exc:
                    weather_response = f"天气摘要不可用：{exc}。使用已获取的真实预报。"
        return {
            "weather_data": weather_data,
            "weather_source": weather_source,
            "weather_response": weather_response,
        }

    def _search_hotels(self, state: TripGraphState) -> dict:
        request = state["request"]
        print("🏨 步骤3: 搜索酒店...")
        pois = self.amap_service.search_poi("酒店", request.city)
        if not pois:
            raise ValueError(f"高德地图未找到 {request.city} 的酒店")
        verified = json.dumps([poi.model_dump(mode="json") for poi in pois], ensure_ascii=False)
        summary = self.llm.generate(
            HOTEL_AGENT_PROMPT,
            f"城市：{request.city}；住宿偏好：{request.accommodation}。已检索酒店：{verified}",
        )
        return {"hotel_response": f"高德地图真实酒店：{verified}\n专家整理：{summary}"}

    def _generate_plan(self, state: TripGraphState) -> dict:
        request = state["request"]
        print("📋 步骤4: 生成行程计划...")
        weather_data = state["weather_data"]
        verified_weather = (
            json.dumps([item.model_dump(mode="json") for item in weather_data], ensure_ascii=False)
            if weather_data else state["weather_response"]
        )
        query = self._build_planner_query(
            request, state["attraction_response"], verified_weather, state["hotel_response"]
        )
        started = time.monotonic()
        try:
            response = self.llm.generate(
                PLANNER_AGENT_PROMPT, query, **planner_llm_options(self.llm)
            )
        finally:
            print(f"步骤4 模型调用耗时: {time.monotonic() - started:.1f} 秒")
        return {"planner_response": response}

    def _validate_plan(self, state: TripGraphState) -> dict:
        plan = self._parse_response(state["planner_response"], state["request"])
        weather_data = state["weather_data"]
        weather_source = state["weather_source"]
        plan.weather_info = weather_data
        if not weather_data:
            plan.overall_suggestions += " 旅行日期暂无可靠天气预报，请临行前再次查询。"
        elif weather_source != "高德地图":
            plan.overall_suggestions += (
                f" 天气来源：{weather_source}；Open-Meteo 的温度为当日最高/最低气温，"
                "请在临行前复查。"
            )
        return {"trip_plan": plan}

    def _build_planner_query(self, request: TripRequest, attractions: str, weather: str, hotels: str = "") -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
{attractions}

**天气信息:**
{weather}

**酒店信息:**
{hotels}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
3. 考虑景点之间的距离和交通方式
4. 返回完整的JSON格式数据
5. 景点的经纬度坐标要真实准确
6. weather_info只能使用上文真实天气数据，若不可用则返回空数组
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query
    
    def _parse_response(self, response: str, request: TripRequest) -> TripPlan:
        """
        解析Agent响应
        
        Args:
            response: Agent响应文本
            request: 原始请求
            
        Returns:
            旅行计划
        """
        try:
            # 尝试从响应中提取JSON
            # 查找JSON代码块
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                json_str = response[json_start:json_end].strip()
            elif "{" in response and "}" in response:
                # 直接查找JSON对象
                json_start = response.find("{")
                json_end = response.rfind("}") + 1
                json_str = response[json_start:json_end]
            else:
                raise ValueError("响应中未找到JSON数据")
            
            # 解析JSON
            data = json.loads(json_str)
            
            # 转换为TripPlan对象
            trip_plan = TripPlan(**data)
            if (
                trip_plan.city != request.city
                or trip_plan.start_date != request.start_date
                or trip_plan.end_date != request.end_date
                or len(trip_plan.days) != request.travel_days
            ):
                raise ValueError("计划的城市、日期或天数与请求不一致")

            from datetime import date, timedelta
            start = date.fromisoformat(request.start_date)
            for index, day in enumerate(trip_plan.days):
                if day.date != (start + timedelta(days=index)).isoformat():
                    raise ValueError("计划中的每日日期不连续")
                if not day.attractions or not {"breakfast", "lunch", "dinner"}.issubset(
                    {meal.type for meal in day.meals}
                ):
                    raise ValueError("计划缺少景点或三餐")
            
            return trip_plan
            
        except Exception as e:
            print(f"⚠️  解析响应失败: {str(e)}")
            raise ValueError("行程规划 Agent 未返回有效的旅行计划 JSON") from e
    
# 全局多智能体系统实例
_multi_agent_planner = None


def get_trip_planner_agent() -> MultiAgentTripPlanner:
    """获取多智能体旅行规划系统实例(单例模式)"""
    global _multi_agent_planner

    if _multi_agent_planner is None:
        _multi_agent_planner = MultiAgentTripPlanner()

    return _multi_agent_planner
