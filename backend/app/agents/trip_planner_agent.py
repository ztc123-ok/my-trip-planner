# -*- coding: utf-8 -*-
"""LangGraph 多角色旅行规划工作流。"""

import json
import math
import time
import uuid
from typing import TypedDict, Literal, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from .checkpointer import get_checkpointer

from ..services.llm_service import get_llm
from ..services.amap_service import AmapService, create_amap_tool
from ..services.weather_service import get_trip_forecast
from ..models.schemas import TripRequest, TripPlan, WeatherInfo, POIInfo, Location
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


def calculate_distance_km(loc1: Location, loc2: Location) -> float:
    """计算两经纬度之间的地表大圆距离 (公里)。"""
    lat1, lon1 = math.radians(loc1.latitude), math.radians(loc1.longitude)
    lat2, lon2 = math.radians(loc2.latitude), math.radians(loc2.longitude)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371.0 * c


def format_nearest_attraction_distance(hotel_loc: Optional[Location], attractions: list[POIInfo]) -> Optional[str]:
    """计算酒店到候选景点中最近的一个，并格式化为精炼标签。例如 '近天安门(800m)' 或 '距故宫 1.8km'。"""
    if not hotel_loc or not attractions:
        return None
    nearest_name = None
    min_dist = float("inf")
    for att in attractions:
        if att.location:
            dist = calculate_distance_km(hotel_loc, att.location)
            if dist < min_dist:
                min_dist = dist
                nearest_name = att.name

    if not nearest_name or min_dist == float("inf"):
        return None

    # 精简景点名称（去除层级或括号说明）
    short_name = nearest_name.split("-")[0].split("·")[0].split("(")[0].split("（")[0].strip()

    if min_dist < 1.0:
        meters = int(round(min_dist * 1000, -1))
        if meters < 50:
            meters = 50
        return f"近{short_name}({meters}m)"
    return f"距{short_name} {min_dist:.1f}km"


class TripGraphState(TypedDict, total=False):
    request: TripRequest
    candidate_attractions: list[POIInfo]  # 并行搜索到的真实候选景点列表
    candidate_hotels: list[POIInfo]        # 并行搜索到的真实候选酒店列表
    selected_attractions: list[str]        # 用户人工挑选/确认的景点名称列表
    selected_hotel: str                    # 用户选定的酒店名称
    user_feedback: str                     # 用户在中断确认时提供的修改/干预意见
    attraction_response: str
    weather_data: list[WeatherInfo]
    weather_source: str
    weather_response: str
    hotel_response: str
    planner_response: str
    trip_plan: TripPlan
    retry_count: int          # 当前重试次数（0=首次尝试）
    validation_error: str     # 校验失败原因，重试时传给 planner 作改进提示


# 最大重试次数：校验失败后最多回到 planner 重新生成的次数
MAX_PLAN_RETRIES = 2


def _should_retry(state: TripGraphState) -> Literal["planner", "__end__"]:
    """条件路由：校验通过 → END，失败且未超限 → planner 重试。"""
    if state.get("trip_plan") is not None:
        return END
    if state.get("retry_count", 0) <= MAX_PLAN_RETRIES:
        return "planner"
    # 超过重试次数，_validate_plan 已抛出异常，此分支理论上不可达
    return END


class MultiAgentTripPlanner:
    """Four specialist LangGraph nodes with validated TripPlan output and HITL support."""

    agent_names = ("景点搜索专家", "天气查询专家", "酒店推荐专家", "行程规划专家")

    def __init__(self, llm=None, amap_service: AmapService | None = None, checkpointer=None):
        settings = get_settings()
        self.llm = llm if llm is not None else get_llm()
        self.amap_service = (
            amap_service if amap_service is not None
            else AmapService(mcp_tool=create_amap_tool(settings.amap_api_key))
        )
        self.checkpointer = checkpointer if checkpointer is not None else get_checkpointer()

        builder = StateGraph(TripGraphState)
        builder.add_node("attractions", self._search_attractions)
        builder.add_node("weather", self._get_weather)
        builder.add_node("hotels", self._search_hotels)
        builder.add_node("planner", self._generate_plan)
        builder.add_node("validate", self._validate_plan)
        for node in ("attractions", "weather", "hotels"):
            builder.add_edge(START, node)
        builder.add_edge(["attractions", "weather", "hotels"], "planner")
        builder.add_edge("planner", "validate")
        builder.add_conditional_edges("validate", _should_retry)

        # 基础图：无中断，用于一键式调用及既有兼容，保存执行检查点
        self.graph = builder.compile(checkpointer=self.checkpointer)

        # Human-in-the-Loop 图：在 planner 节点前设置中断点，保存状态检查点
        self.graph_hitl = builder.compile(
            checkpointer=self.checkpointer,
            interrupt_before=["planner"]
        )

    def plan_trip(self, request: TripRequest, thread_id: str | None = None) -> TripPlan:
        """一键全自动生成旅行计划（无中断模式，保存执行状态至检查点）。"""
        tid = thread_id or getattr(request, "thread_id", None) or f"trip_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": tid}}
        print(f"🚀 LangGraph 开始规划 {request.city} 的 {request.travel_days} 天行程 (thread_id={tid})")
        result = self.graph.invoke({"request": request}, config=config)
        print("✅ LangGraph 旅行计划生成完成")
        return result["trip_plan"]

    def prepare_trip_plan(self, request: TripRequest, thread_id: str | None = None) -> dict:
        """HITL 阶段一：并行搜索并在 planner 节点前挂起，返回候选数据供用户确认。"""
        tid = thread_id or f"trip_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": tid}}
        print(f"🚀 LangGraph HITL 开始准备 {request.city} 的行程 (thread_id={tid})")
        self.graph_hitl.invoke({"request": request}, config=config)
        state = self.graph_hitl.get_state(config)
        values = state.values
        print(f"⏸️ LangGraph HITL 在 planner 前挂起，等待用户确认候选 POI (next={state.next})")
        candidate_attractions = values.get("candidate_attractions", [])
        raw_hotels = values.get("candidate_hotels", [])
        enriched_hotels = []
        for h in raw_hotels:
            dist_desc = format_nearest_attraction_distance(h.location, candidate_attractions)
            if dist_desc:
                enriched_hotels.append(h.model_copy(update={"distance": dist_desc}))
            else:
                enriched_hotels.append(h)

        return {
            "thread_id": tid,
            "city": request.city,
            "travel_days": request.travel_days,
            "candidate_attractions": candidate_attractions,
            "candidate_hotels": enriched_hotels,
            "weather_info": values.get("weather_data", []),
        }

    def resume_trip_plan(
        self,
        thread_id: str,
        selected_attractions: list[str] | None = None,
        selected_hotel: str | None = None,
        user_feedback: str | None = None,
    ) -> TripPlan:
        """HITL 阶段二：接收用户确认与反馈，更新状态后恢复图执行直至生成有效计划。"""
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph_hitl.get_state(config)
        if not state or not state.next:
            if state and state.values.get("trip_plan"):
                return state.values["trip_plan"]
            raise ValueError(f"会话 {thread_id} 未找到或未处于待继续状态")

        updates = {}
        if selected_attractions is not None:
            updates["selected_attractions"] = selected_attractions
        if selected_hotel is not None:
            updates["selected_hotel"] = selected_hotel
        if user_feedback is not None:
            updates["user_feedback"] = user_feedback

        if updates:
            # 标记为前驱节点写入，保证后续正常执行待处理节点 planner
            self.graph_hitl.update_state(config, updates, as_node="hotels")

        print(f"▶️ LangGraph HITL 恢复执行 planner 与 validate (thread_id={thread_id})")
        result = self.graph_hitl.invoke(None, config=config)
        plan = result.get("trip_plan") if isinstance(result, dict) else None
        if not plan:
            plan = self.graph_hitl.get_state(config).values.get("trip_plan")
        if not plan:
            raise ValueError(f"会话 {thread_id} 恢复规划后未生成有效旅行计划")
        print("✅ LangGraph HITL 旅行计划生成完成")
        return plan

    def get_trip_state(self, thread_id: str) -> dict | None:
        """获取指定会话当前的图执行状态与中间数据。"""
        config = {"configurable": {"thread_id": thread_id}}
        state = self.graph_hitl.get_state(config)
        if not state or not state.config or not state.config.get("configurable", {}).get("checkpoint_id"):
            state = self.graph.get_state(config)
            if not state or not state.config or not state.config.get("configurable", {}).get("checkpoint_id"):
                return None

        values = state.values or {}
        req = values.get("request")
        city = req.city if hasattr(req, "city") else (req.get("city") if isinstance(req, dict) else None)
        travel_days = req.travel_days if hasattr(req, "travel_days") else (req.get("travel_days") if isinstance(req, dict) else None)
        candidate_attractions = values.get("candidate_attractions", [])
        candidate_hotels = values.get("candidate_hotels", [])
        trip_plan = values.get("trip_plan")
        next_nodes = list(state.next) if state.next else []

        return {
            "thread_id": thread_id,
            "next_nodes": next_nodes,
            "is_interrupted": bool(next_nodes),
            "is_completed": bool(trip_plan is not None or not next_nodes),
            "city": city,
            "travel_days": travel_days,
            "has_plan": trip_plan is not None,
            "candidate_attractions_count": len(candidate_attractions),
            "candidate_hotels_count": len(candidate_hotels),
            "retry_count": values.get("retry_count", 0),
        }

    def get_trip_history(self, thread_id: str) -> list[dict]:
        """获取指定会话的检查点演进历史列表（按时间正序）。"""
        config = {"configurable": {"thread_id": thread_id}}
        snapshots = []
        for state in self.graph_hitl.get_state_history(config):
            cfg = state.config.get("configurable", {})
            cid = cfg.get("checkpoint_id", "")
            if not cid:
                continue
            parent_cfg = (state.parent_config or {}).get("configurable", {})
            parent_cid = parent_cfg.get("checkpoint_id")
            meta = state.metadata or {}
            next_node = state.next[0] if state.next else None
            snapshots.append({
                "checkpoint_id": cid,
                "parent_checkpoint_id": parent_cid,
                "next_node": next_node,
                "step": meta.get("step"),
                "source": meta.get("source"),
            })

        if not snapshots:
            for state in self.graph.get_state_history(config):
                cfg = state.config.get("configurable", {})
                cid = cfg.get("checkpoint_id", "")
                if not cid:
                    continue
                parent_cfg = (state.parent_config or {}).get("configurable", {})
                parent_cid = parent_cfg.get("checkpoint_id")
                meta = state.metadata or {}
                next_node = state.next[0] if state.next else None
                snapshots.append({
                    "checkpoint_id": cid,
                    "parent_checkpoint_id": parent_cid,
                    "next_node": next_node,
                    "step": meta.get("step"),
                    "source": meta.get("source"),
                })

        return list(reversed(snapshots))



    def _search_attractions(self, state: TripGraphState) -> dict:
        request = state["request"]
        keywords = request.preferences[0] if request.preferences else "景点"
        print("📍 并行查询: 搜索景点...")
        pois = self.amap_service.search_poi(keywords, request.city)
        if not pois:
            raise ValueError(f"高德地图未找到 {request.city} 的{keywords}景点")
        verified = json.dumps([poi.model_dump(mode="json") for poi in pois], ensure_ascii=False)
        summary = self.llm.generate(
            ATTRACTION_AGENT_PROMPT,
            f"城市：{request.city}；偏好：{', '.join(request.preferences) or '无'}。已检索景点：{verified}",
        )
        return {
            "candidate_attractions": pois,
            "attraction_response": f"高德地图真实景点：{verified}\n专家整理：{summary}",
        }

    def _get_weather(self, state: TripGraphState) -> dict:
        request = state["request"]
        print("🌤️  并行查询: 查询天气...")
        try:
            weather_data, weather_source = get_trip_forecast(
                self.amap_service, request.city, request.start_date, request.end_date
            )
        except Exception as exc:
            weather_data, weather_source = [], ""
            print(f"⏭️  天气查询失败({exc})，跳过天气摘要生成")
            weather_response = f"天气查询不可用：{exc}。请勿编造天气数据。"
        else:
            if not weather_data:
                print("⏭️  天气不可用，跳过天气摘要生成")
                weather_response = "旅行日期内暂无可靠的天气预报，请勿编造天气数据。"
            elif weather_source != "高德地图":
                print(f"⏭️  天气来源为 {weather_source}，跳过 LLM 天气摘要")
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

    @staticmethod
    def _infer_hotel_meta(name: str, accommodation: str = "") -> tuple[str, str, str]:
        """根据酒店名称与住宿偏好推断参考价格区间、综合评分和特色标签"""
        n = name.lower()
        if any(w in n for w in ("青年旅舍", "青年旅社", "青旅", "胶囊", "客栈", "青舍", "民宿", "太空舱")):
            return ("¥90~180/晚", "4.6", "青旅民宿")
        if any(w in n for w in ("国际", "万豪", "希尔顿", "洲际", "凯宾斯基", "香格里拉", "喜来登", "威斯汀", "豪华", "五星", "丽思")):
            return ("¥800~1500/晚", "4.8", "豪华高档")
        if any(w in n for w in ("快捷", "如家", "汉庭", "锦江之星", "7天", "格林豪泰", "宜必思", "速8", "轻居", "驿站", "住小叮")):
            return ("¥180~280/晚", "4.5", "经济快捷")
        if any(w in n for w in ("度假", "温泉", "庄园", "会馆", "花园")):
            return ("¥600~1000/晚", "4.7", "休闲度假")

        # 结合用户提交的住宿偏好兜底
        acc = accommodation or ""
        if "经济" in acc or "青年" in acc or "背包" in acc:
            return ("¥180~280/晚", "4.5", "经济优选")
        if "高档" in acc or "豪华" in acc or "五星" in acc:
            return ("¥800~1400/晚", "4.8", "高档优选")
        return ("¥320~500/晚", "4.6", "品质舒适")

    def _search_hotels(self, state: TripGraphState) -> dict:
        request = state["request"]
        print("🏨 并行查询: 搜索酒店...")
        pois = self.amap_service.search_poi("酒店", request.city)
        if not pois:
            raise ValueError(f"高德地图未找到 {request.city} 的酒店")
        
        # 丰富候选酒店的决策元数据（价格、评分、标签）供 HITL 确认与展示
        enriched_pois = []
        for poi in pois:
            price_range, rating, tag = self._infer_hotel_meta(poi.name, request.accommodation)
            enriched_poi = poi.model_copy(update={
                "price_range": price_range,
                "rating": rating,
                "tag": tag,
            })
            enriched_pois.append(enriched_poi)

        verified = json.dumps([poi.model_dump(mode="json") for poi in enriched_pois], ensure_ascii=False)
        summary = self.llm.generate(
            HOTEL_AGENT_PROMPT,
            f"城市：{request.city}；住宿偏好：{request.accommodation}。已检索酒店：{verified}",
        )
        return {
            "candidate_hotels": enriched_pois,
            "hotel_response": f"高德地图真实酒店：{verified}\n专家整理：{summary}",
        }

    def _generate_plan(self, state: TripGraphState) -> dict:
        request = state["request"]
        retry_count = state.get("retry_count", 0)
        validation_error = state.get("validation_error", "")
        if validation_error:
            print(f"🔄 第 {retry_count + 1} 次重试规划，上次失败原因: {validation_error}")
        else:
            print("📋 查询汇总完成，生成行程计划...")
        weather_data = state.get("weather_data", [])
        verified_weather = (
            json.dumps([item.model_dump(mode="json") for item in weather_data], ensure_ascii=False)
            if weather_data else state.get("weather_response", "天气不可用")
        )
        query = self._build_planner_query(
            request,
            state["attraction_response"],
            verified_weather,
            state["hotel_response"],
            selected_attractions=state.get("selected_attractions"),
            selected_hotel=state.get("selected_hotel"),
            user_feedback=state.get("user_feedback"),
        )
        if validation_error:
            query += f"\n\n**上次生成的计划未通过校验，请修正以下问题:** {validation_error}"
        started = time.monotonic()
        try:
            response = self.llm.generate(
                PLANNER_AGENT_PROMPT, query, **planner_llm_options(self.llm)
            )
        finally:
            print(f"规划模型调用耗时: {time.monotonic() - started:.1f} 秒")
        return {"planner_response": response}

    def _validate_plan(self, state: TripGraphState) -> dict:
        retry_count = state.get("retry_count", 0)
        try:
            plan = self._parse_response(state["planner_response"], state["request"])
        except (ValueError, Exception) as exc:
            error_msg = str(exc)
            attempt = retry_count + 1
            if retry_count >= MAX_PLAN_RETRIES:
                print(f"❌ 校验失败 (第 {attempt} 次，已达上限): {error_msg}")
                raise ValueError(
                    f"行程规划经 {attempt} 次尝试仍无法生成有效计划: {error_msg}"
                ) from exc
            print(f"⚠️  校验失败 (第 {attempt} 次，将重试): {error_msg}")
            return {
                "retry_count": retry_count + 1,
                "validation_error": error_msg,
            }
        # 校验通过
        weather_data = state.get("weather_data", [])
        weather_source = state.get("weather_source", "")
        plan.weather_info = weather_data
        if not weather_data:
            plan.overall_suggestions += " 旅行日期暂无可靠天气预报，请临行前再次查询。"
        elif weather_source != "高德地图":
            plan.overall_suggestions += (
                f" 天气来源：{weather_source}；Open-Meteo 的温度为当日最高/最低气温，"
                "请在临行前复查。"
            )
        if retry_count > 0:
            print(f"✅ 第 {retry_count + 1} 次尝试校验通过")
        return {"trip_plan": plan, "validation_error": ""}

    def _build_planner_query(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str = "",
        selected_attractions: list[str] | None = None,
        selected_hotel: str | None = None,
        user_feedback: str | None = None,
    ) -> str:
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
"""
        if selected_attractions:
            query += f"\n**用户已明确确认的心仪景点 (请务必优先安排以下景点):** {', '.join(selected_attractions)}\n"
        if selected_hotel:
            query += f"\n**用户已明确选定的酒店 (请在行程中推荐此酒店):** {selected_hotel}\n"
        if user_feedback:
            query += f"\n**用户人工调整要求:** {user_feedback}\n"
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}\n"

        query += """
**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
7. weather_info只能使用上文真实天气数据，若不可用则返回空数组
"""
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
                day.day_index = index  # LLM 可能返回 1-based，强制修正为 0-based
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
