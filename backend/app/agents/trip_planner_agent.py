# -*- coding: utf-8 -*-
"""LangGraph 多角色旅行规划工作流。"""

import asyncio
import json
import math
import re
import threading
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
from ..services.knowledge_service import get_knowledge_service
from ..services.mcp_tool_adapter import create_amap_langchain_tools
from ..models.schemas import TripRequest, TripPlan, WeatherInfo, POIInfo, Location, ChatIntentRouteData
from ..config import get_settings

# ============ Agent提示词 ============

ATTRACTION_AGENT_PROMPT = """你是景点搜索专家。根据高德地图 MCP 已返回的真实景点资料，
整理适合目的地和用户偏好的景点。保留名称、地址与坐标，不要编造未提供的地点。"""

WEATHER_AGENT_PROMPT = """你是天气查询专家。只根据已取得的真实预报简要说明天气。
不得添加不存在的日期或编造温度。"""

HOTEL_AGENT_PROMPT = """你是酒店推荐专家。根据高德地图 MCP 已返回的真实酒店资料，
整理适合用户住宿偏好的酒店。保留名称、地址与坐标，不要编造未提供的酒店。"""

PLANNER_AGENT_PROMPT = """你是行程规划专家。你的任务是根据景点信息、天气信息与官方知识库深度攻略,生成详细且务实的旅行计划。

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
          "ticket_price": 60,
          "booking_tips": "官方预约与放票规则（从提供的知识库攻略中提取，如：提前7天20:00微信抢票，周一闭馆）",
          "tips": "实用避坑与动线建议（从知识库提取，如：由午门进神武门出，避开黑车野导）"
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
  "knowledge_highlights": [
    "【故宫预约】提前7天20:00在微信小程序预约，周一闭馆；必须带二代身份证刷闸机进门",
    "【避坑指南】端门广场与地铁口黄牛所谓'不用排队低价票'均为诈骗，切勿轻信"
  ],
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
8. **知识库深度融合 (RAG 增强)**:
   - 严格参考已提供的官方知识库攻略。若知识库指出某景点周一闭馆或特定时段不开放，绝对不可在对应日期安排游玩！
   - 为每个景点提炼 booking_tips（预约规则与放票时间）和 tips（避坑防骗与游玩动线）；
   - 在 knowledge_highlights 数组中列出 2-4 条全案最具实用价值的权威避坑与放票要点。
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
    knowledge_context: str                 # RAG 检索提炼的官方深度攻略、预约放票规则与避坑指南
    knowledge_docs: list[dict]             # 知识库召回的原始文档片段
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
    """Five specialist LangGraph nodes with validated TripPlan output and HITL support."""

    agent_names = ("景点搜索专家", "天气查询专家", "酒店推荐专家", "知识检索专家", "行程规划专家")

    def __init__(self, llm=None, amap_service: AmapService | None = None, checkpointer=None):
        settings = get_settings()
        self.llm = llm if llm is not None else get_llm()
        self.amap_service = (
            amap_service if amap_service is not None
            else AmapService(mcp_tool=create_amap_tool(settings.amap_api_key))
        )
        self.checkpointer = checkpointer if checkpointer is not None else get_checkpointer()
        self.tools = create_amap_langchain_tools(self.amap_service)

        builder = StateGraph(TripGraphState)
        builder.add_node("attractions", self._search_attractions)
        builder.add_node("weather", self._get_weather)
        builder.add_node("hotels", self._search_hotels)
        builder.add_node("retrieval", self._retrieve_knowledge)
        builder.add_node("planner", self._generate_plan)
        builder.add_node("validate", self._validate_plan)
        for node in ("attractions", "weather", "hotels"):
            builder.add_edge(START, node)
        builder.add_edge(["attractions", "weather", "hotels"], "retrieval")
        builder.add_edge("retrieval", "planner")
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

    async def astream_plan_trip(self, request: TripRequest, thread_id: str | None = None):
        """流式运行多智能体图 (SSE)，逐个节点产生更新事件。
        
        通过后台工作线程执行同步图的 stream 方法，利用 asyncio.Queue 实现
        跨线程向异步生成器逐个推送事件。这样既支持 SqliteSaver 持久化（避免 SqliteSaver
        不支持 astream 的 NotImplementedError 限制），又保证 FastAPI 事件循环不被阻塞。
        """
        tid = thread_id or getattr(request, "thread_id", None) or f"trip_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": tid}}
        print(f">> [Stream] LangGraph 开始流式规划 {request.city} 的 {request.travel_days} 天行程 (thread_id={tid})")

        start_time = time.time()
        yield {
            "event": "start",
            "thread_id": tid,
            "progress": 5,
            "elapsed_seconds": 0.0,
            "message": f"开始为 {request.city} 规划 {request.travel_days} 天行程...",
            "data": {
                "city": request.city,
                "travel_days": request.travel_days,
                "start_date": request.start_date,
                "end_date": request.end_date,
            }
        }

        final_plan = None
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _run_stream_worker():
            try:
                for chunk in self.graph.stream({"request": request}, config=config, stream_mode="updates"):
                    loop.call_soon_threadsafe(queue.put_nowait, ("chunk", chunk))
                state = self.graph.get_state(config)
                saved_plan = state.values.get("trip_plan") if hasattr(state, "values") else None
                loop.call_soon_threadsafe(queue.put_nowait, ("done", saved_plan))
            except Exception as exc:
                loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))

        worker_thread = threading.Thread(target=_run_stream_worker, daemon=True)
        worker_thread.start()

        # 跟踪并行搜索完成状态与候选情报
        collected_attractions = []
        collected_weather = []
        collected_hotels = []
        parallel_nodes_done = set()
        planner_started = False
        planner_finished = False

        # 规划耗时阶段细粒度推进序列
        planner_substeps = [
            ("动线拓扑建模", "基于高德经纬度分析景点空间拓扑网络，测算景点间地表通勤距离...", 74),
            ("游览节奏规划", "测算各景区建议游览时长与通行缓冲窗口，按上下午合理编排...", 78),
            ("餐饮美食匹配", "结合游览动线搜寻周边地道特色美食，匹配早中晚餐标...", 81),
            ("住宿接驳联运", "测算每日末尾景点至候选酒店的最佳交通动线与接驳方案...", 84),
            ("多维预算精算", "综合门票价格、交通出行、餐饮标准与酒店费用精算总体预算...", 87),
            ("防疲劳与规则校验", "校验每日游玩闭环与开放时段，生成个性化出行贴士与避坑指南...", 89),
            ("方案终稿组装", "正在组织结构化旅行计划与每日详尽行程说明...", 91),
        ]
        substep_idx = 0

        try:
            while True:
                try:
                    # 使用 4.5 秒超时轮询，在 LLM 生成大 JSON 的漫长等待周期内持续输出阶段性演进
                    msg_type, payload = await asyncio.wait_for(queue.get(), timeout=4.5)
                except asyncio.TimeoutError:
                    # 如果前置三专家已完成，且 planner 尚未结束，动态广播推演进度
                    if len(parallel_nodes_done) >= 3 and not planner_finished:
                        if not planner_started:
                            planner_started = True
                            poi_names = [p.name for p in collected_attractions[:3]]
                            poi_desc = "、".join(poi_names) if poi_names else "精选核心地标"
                            yield {
                                "event": "node_start",
                                "node": "planner",
                                "name": "行程规划专家",
                                "status": "running",
                                "stage": "情报汇集建模",
                                "progress": 72,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已锁定 {len(collected_attractions)} 个景点({poi_desc}等)、{len(collected_weather)} 天天气预报，进入多维时空规划模型...",
                                "data": {
                                    "attractions_count": len(collected_attractions),
                                    "weather_count": len(collected_weather),
                                    "hotels_count": len(collected_hotels),
                                }
                            }
                        elif substep_idx < len(planner_substeps):
                            stage_name, stage_desc, stage_prog = planner_substeps[substep_idx]
                            yield {
                                "event": "node_progress",
                                "node": "planner",
                                "name": "行程规划专家",
                                "status": "running",
                                "stage": stage_name,
                                "progress": stage_prog,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": stage_desc,
                                "data": {
                                    "stage_name": stage_name,
                                    "step": substep_idx + 1,
                                    "total_steps": len(planner_substeps),
                                }
                            }
                            if substep_idx < len(planner_substeps) - 1:
                                substep_idx += 1
                    continue

                if msg_type == "chunk":
                    chunk = payload
                    for node_name, node_output in chunk.items():
                        if node_name == "attractions":
                            pois = node_output.get("candidate_attractions", [])
                            collected_attractions = pois
                            parallel_nodes_done.add("attractions")
                            poi_samples = [
                                p.model_dump(mode="json") if hasattr(p, "model_dump") else p
                                for p in pois[:4]
                            ]
                            yield {
                                "event": "node_finish",
                                "node": "attractions",
                                "name": "景点搜索专家",
                                "status": "completed",
                                "stage": "景点挖掘检索",
                                "progress": 30,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已检索并整理 {len(pois)} 个热门景点",
                                "data": {
                                    "count": len(pois),
                                    "samples": poi_samples,
                                }
                            }
                        elif node_name == "weather":
                            w_data = node_output.get("weather_data", [])
                            collected_weather = w_data
                            parallel_nodes_done.add("weather")
                            source = node_output.get("weather_source", "")
                            w_samples = [
                                w.model_dump(mode="json") if hasattr(w, "model_dump") else w
                                for w in w_data
                            ]
                            yield {
                                "event": "node_finish",
                                "node": "weather",
                                "name": "天气查询专家",
                                "status": "completed",
                                "stage": "气象环境锁定",
                                "progress": 50,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已获取 {len(w_data)} 天天气预报 ({source or '实时气象'})",
                                "data": {
                                    "count": len(w_data),
                                    "source": source,
                                    "samples": w_samples,
                                }
                            }
                        elif node_name == "hotels":
                            hotels = node_output.get("candidate_hotels", [])
                            collected_hotels = hotels
                            parallel_nodes_done.add("hotels")
                            hotel_samples = [
                                h.model_dump(mode="json") if hasattr(h, "model_dump") else h
                                for h in hotels[:4]
                            ]
                            yield {
                                "event": "node_finish",
                                "node": "hotels",
                                "name": "酒店推荐专家",
                                "status": "completed",
                                "stage": "优质住宿匹配",
                                "progress": 70,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已筛选匹配 {len(hotels)} 家高分住宿",
                                "data": {
                                    "count": len(hotels),
                                    "samples": hotel_samples,
                                }
                            }

                        elif node_name == "retrieval":
                            k_docs = node_output.get("knowledge_docs", [])
                            spot_names = list(dict.fromkeys([d.get("spot_name") for d in k_docs if d.get("spot_name")]))
                            spot_desc = "、".join(spot_names[:3]) if spot_names else request.city
                            yield {
                                "event": "node_finish",
                                "node": "retrieval",
                                "name": "知识检索增强专家",
                                "status": "completed",
                                "stage": "城市深度攻略检索",
                                "progress": 72,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已从本地向量知识库召回【{spot_desc}】等 {len(k_docs)} 条权威放票规则与避坑贴士",
                                "data": {
                                    "count": len(k_docs),
                                    "spots": spot_names,
                                }
                            }

                        # 若前置并行专家与检索专家就绪，触发 planner 启动事件
                        if len(parallel_nodes_done) >= 3 and not planner_started:
                            planner_started = True
                            poi_names = [p.name for p in collected_attractions[:3]]
                            poi_desc = "、".join(poi_names) if poi_names else "精选地标"
                            yield {
                                "event": "node_start",
                                "node": "planner",
                                "name": "行程规划专家",
                                "status": "running",
                                "stage": "情报汇集建模",
                                "progress": 75,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": f"已锁定 {len(collected_attractions)} 个景点({poi_desc}等)、{len(collected_weather)} 天天气预报及权威攻略，进入多维时空规划模型...",
                                "data": {
                                    "attractions_count": len(collected_attractions),
                                    "weather_count": len(collected_weather),
                                    "hotels_count": len(collected_hotels),
                                }
                            }

                        if node_name == "planner":
                            planner_finished = True
                            yield {
                                "event": "node_finish",
                                "node": "planner",
                                "name": "行程规划专家",
                                "status": "completed",
                                "stage": "时空动线与预算完成",
                                "progress": 93,
                                "elapsed_seconds": round(time.time() - start_time, 1),
                                "message": "已完成每日行程动线、交通与预算测算，进入质量校验",
                                "data": {}
                            }
                        elif node_name == "validate":
                            plan = node_output.get("trip_plan")
                            if plan is not None:
                                final_plan = plan
                                yield {
                                    "event": "node_finish",
                                    "node": "validate",
                                    "name": "质量校验专家",
                                    "status": "completed",
                                    "stage": "质量闭环通过",
                                    "progress": 98,
                                    "elapsed_seconds": round(time.time() - start_time, 1),
                                    "message": "旅行计划校验通过，所有指标完备，即将呈现！",
                                    "data": {}
                                }
                            else:
                                retry_cnt = node_output.get("retry_count", 1)
                                err = node_output.get("validation_error", "")
                                planner_finished = False
                                substep_idx = 0
                                yield {
                                    "event": "retry",
                                    "node": "validate",
                                    "name": "质量校验自修复",
                                    "status": "running",
                                    "stage": "自愈微调修复",
                                    "progress": 75,
                                    "elapsed_seconds": round(time.time() - start_time, 1),
                                    "message": f"第 {retry_cnt} 次规划发现轻微瑕疵，正在自动重试修复...",
                                    "data": {"error": err}
                                }
                elif msg_type == "done":
                    if not final_plan and payload:
                        final_plan = payload
                    break
                elif msg_type == "error":
                    raise payload

            if not final_plan:
                state = self.graph.get_state(config)
                final_plan = state.values.get("trip_plan") if hasattr(state, "values") else None

            if final_plan:
                plan_dict = final_plan.model_dump(mode="json") if hasattr(final_plan, "model_dump") else final_plan
                yield {
                    "event": "plan_complete",
                    "thread_id": tid,
                    "progress": 100,
                    "stage": "规划成功",
                    "elapsed_seconds": round(time.time() - start_time, 1),
                    "message": "旅行计划生成成功！",
                    "data": plan_dict
                }
            else:
                yield {
                    "event": "error",
                    "thread_id": tid,
                    "progress": 0,
                    "elapsed_seconds": round(time.time() - start_time, 1),
                    "message": "未能生成有效的行程计划",
                }

        except Exception as exc:
            import traceback
            traceback.print_exc()
            yield {
                "event": "error",
                "thread_id": tid,
                "progress": 0,
                "elapsed_seconds": round(time.time() - start_time, 1),
                "message": f"流式规划执行失败: {str(exc)}",
            }


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

        k_docs = values.get("knowledge_docs", [])
        knowledge_highlights = [
            f"【{d.get('spot_name')}·{d.get('section_type')}】{d.get('content', '')[:100].replace(chr(10), ' ')}..."
            for d in k_docs[:4]
        ]

        return {
            "thread_id": tid,
            "city": request.city,
            "travel_days": request.travel_days,
            "start_date": request.start_date,
            "end_date": request.end_date,
            "candidate_attractions": candidate_attractions,
            "candidate_hotels": enriched_hotels,
            "weather_info": values.get("weather_data", []),
            "knowledge_highlights": knowledge_highlights,
        }

    def resume_trip_plan(
        self,
        thread_id: str,
        selected_attractions: list[str] | None = None,
        selected_hotel: str | None = None,
        user_feedback: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
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

        # 若用户在人机协同卡片中校准或补充了真实日期，更新 request 状态与游玩天数
        current_req = state.values.get("request")
        if current_req and (start_date or end_date):
            from datetime import date
            new_start = start_date or current_req.start_date
            new_end = end_date or current_req.end_date
            calc_days = current_req.travel_days
            try:
                d1 = date.fromisoformat(new_start)
                d2 = date.fromisoformat(new_end)
                calc_days = max(1, (d2 - d1).days + 1)
            except Exception:
                pass
            updated_req = current_req.model_copy(update={
                "start_date": new_start,
                "end_date": new_end,
                "travel_days": calc_days,
            })
            updates["request"] = updated_req

        if updates:
            # 标记为前驱节点写入，保证后续正常执行待处理节点 planner
            self.graph_hitl.update_state(config, updates, as_node="retrieval")

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

    def _retrieve_knowledge(self, state: TripGraphState) -> dict:
        request = state["request"]
        print(f"📚 知识检索专家: 正在为 {request.city} 检索向量知识库攻略...")
        try:
            ks = get_knowledge_service()
            candidate_pois = state.get("candidate_attractions", [])

            all_hits = []
            seen_spot_sections = set()

            # 1. 优先针对候选景点检索官方预约放票与避坑规则
            for poi in candidate_pois[:6]:
                spot_name = poi.name.split("-")[0].split("·")[0].split("(")[0].split("（")[0].strip()
                hits = ks.search_knowledge(city=request.city, query=spot_name, top_k=2)
                for h in hits:
                    key = (h.get("spot_name"), h.get("section_type"))
                    if key not in seen_spot_sections and h.get("content"):
                        seen_spot_sections.add(key)
                        all_hits.append(h)

            # 2. 结合偏好或自由诉求检索城市综合攻略贴士
            pref_terms = [request.city] + (request.preferences or [])
            if request.free_text_input:
                pref_terms.append(request.free_text_input)
            general_query = " ".join(pref_terms)
            general_hits = ks.search_knowledge(city=request.city, query=general_query, top_k=2)
            for h in general_hits:
                key = (h.get("spot_name"), h.get("section_type"))
                if key not in seen_spot_sections and h.get("content"):
                    seen_spot_sections.add(key)
                    all_hits.append(h)

            if all_hits:
                context_blocks = []
                for h in all_hits[:8]:
                    context_blocks.append(
                        f"【{h.get('spot_name')} - {h.get('section_type')}】\n{h.get('content')}"
                    )
                knowledge_context = "\n\n".join(context_blocks)
                print(f"✅ 知识检索完成，共命中 {len(all_hits)} 个权威切片")
            else:
                knowledge_context = "暂无特定景点的官方专有切片，请按常规时空逻辑规划并注明以景区实时公告为准。"
                print("ℹ️ 知识库暂未命中特定切片")

            return {
                "knowledge_context": knowledge_context,
                "knowledge_docs": all_hits[:8],
            }
        except Exception as exc:
            print(f"⚠️ [知识检索] 发生异常: {exc}")
            return {
                "knowledge_context": "知识库暂不可用，请按常规常识规划。",
                "knowledge_docs": [],
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
            knowledge_context=state.get("knowledge_context", ""),
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

        # 补齐并校验每日推荐酒店与最近景点的真实空间距离描述
        all_attractions = state.get("candidate_attractions", [])
        for day in plan.days:
            if day.hotel and day.hotel.location:
                # 优先匹配当天的景点，若无则使用全局候选景点
                day_pois = [
                    POIInfo(id=f"att_{idx}", name=a.name, type=a.category or "", address=a.address, location=a.location)
                    for idx, a in enumerate(day.attractions)
                    if a.location
                ]
                calc_pois = day_pois if day_pois else all_attractions
                if not day.hotel.distance or day.hotel.distance in ("距离景点2公里", "位置距离"):
                    dist_desc = format_nearest_attraction_distance(day.hotel.location, calc_pois)
                    if dist_desc:
                        day.hotel.distance = dist_desc

        # RAG 知识库后置补齐与强化
        k_docs = state.get("knowledge_docs", [])
        if not plan.knowledge_highlights and k_docs:
            plan.knowledge_highlights = [
                f"【{d.get('spot_name')}·{d.get('section_type')}】{d.get('content', '')[:100].replace(chr(10), ' ')}..."
                for d in k_docs[:3]
            ]
        if k_docs:
            for day in plan.days:
                for att in day.attractions:
                    clean_att_name = att.name.split("-")[0].split("·")[0].split("(")[0].split("（")[0].strip()
                    for d in k_docs:
                        d_spot = (d.get("spot_name") or "").strip()
                        if d_spot and (d_spot in clean_att_name or clean_att_name in d_spot):
                            if not att.booking_tips and "预约" in d.get("section_type", ""):
                                lines = [l.strip() for l in d.get("content", "").split("\n") if l.strip()]
                                att.booking_tips = "；".join(lines[:2]).replace("**", "").replace("- ", "")
                            if not att.tips and any(k in d.get("section_type", "") for k in ("贴士", "动线", "机位", "路线")):
                                lines = [l.strip() for l in d.get("content", "").split("\n") if l.strip()]
                                att.tips = "；".join(lines[:2]).replace("**", "").replace("- ", "")

        if retry_count > 0:
            print(f"✅ 第 {retry_count + 1} 次尝试校验通过")
        return {"trip_plan": plan, "validation_error": ""}

    def _build_planner_query(
        self,
        request: TripRequest,
        attractions: str,
        weather: str,
        hotels: str = "",
        knowledge_context: str = "",
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
        if knowledge_context:
            query += f"\n**官方知识库权威攻略与避坑指南 (RAG 增强):**\n{knowledge_context}\n"
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


def parse_natural_language_trip(text: str, llm=None) -> TripRequest:
    """使用 LLM 或启发式提取将自然语言意图转换为 TripRequest 对象"""
    from datetime import date, timedelta

    today = date.today()
    tomorrow = today + timedelta(days=1)
    weekday_names = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    current_weekday_str = weekday_names[today.weekday()]

    prompt = f"""你是一个专业的智能旅行规划助手。当前系统基准时间为：{today.isoformat()}（{current_weekday_str}）。
请从用户输入的自然语言中提取旅行意图参数，并由你严格评估用户是否明确指定了出发时间与行程时长。

用户输入: "{text}"

请严格输出如下 JSON 格式，不得包含其它说明：
```json
{{
  "city": "目的地城市名称，如：北京、上海、成都、西安等",
  "travel_days": 4,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "has_explicit_start_date": false,
  "has_explicit_duration": true,
  "has_explicit_city": true,
  "clarification_prompt": "已为您锁定 4 天行程，请问您打算哪天出发前往目的地？",
  "transportation": "公共交通 / 自驾 / 步行 / 混合",
  "accommodation": "经济型酒店 / 舒适型酒店 / 豪华酒店 / 民宿",
  "preferences": ["历史文化", "美食"],
  "free_text_input": "用户的具体诉求或预算备注"
}}
```
核心规则：
1. 【出发时间判定 has_explicit_start_date】：用户是否在输入中指明了何时启程/出发？
   - 指明了明确日期或相对时间（如"明天"、"后天"、"下周五"、"10月1日"、"国庆假期"、"这周末"等）=> 设为 true，并根据基准时间准确换算为 YYYY-MM-DD 格式。
   - 完全没有指明何时出发（例如用户仅说"成都4天吃货休闲路线"、"想去北京玩"、"三日游"、"自驾游"）=> 必须设为 false！start_date 暂设为 {(tomorrow).isoformat()}。
2. 【行程时长判定 has_explicit_duration】：用户是否指明了玩几天或大致时长？
   - 明确指明（如"4天"、"玩3天"、"周末两天"、"五日游"）=> 设为 true，travel_days 提取为对应的天数整数。
   - 未指明（如用户仅说"我想去成都吃火锅"、"想去西安"）=> 设为 false，travel_days 默认设为 3 天。
3. 【反问引导语 clarification_prompt】：
   - 若 has_explicit_start_date 为 false，生成一句最自然贴切的反问确认语（如"已为您锁定【{text}】中的 X 天行程，请问您打算哪天出发？"）。
   - 若 has_explicit_start_date 为 true，设为 null。
4. 【目的地判定 has_explicit_city】：用户明确提到了城市名称则为 true；若未提及（如"我想去海边度假"），则为 false 且 city 给出合理推测。
"""

    agent_llm = llm or get_llm()
    try:
        options = {}
        if getattr(agent_llm, "provider", "") == "qwen" and str(getattr(agent_llm, "model", "")).startswith("qwen3."):
            options["extra_body"] = {"enable_thinking": False}

        resp = agent_llm.generate("你是旅行参数提取与意图判断助手，只返回严格的 JSON。", prompt, **options)

        cleaned = resp.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        else:
            s = cleaned.find("{")
            e = cleaned.rfind("}") + 1
            if s != -1 and e > s:
                cleaned = cleaned[s:e]

        data = json.loads(cleaned)

        days = int(data.get("travel_days") or 3)
        days = max(1, min(30, days))

        start_str = data.get("start_date")
        try:
            start_d = date.fromisoformat(start_str) if start_str else tomorrow
        except Exception:
            start_d = tomorrow

        end_d = start_d + timedelta(days=days - 1)

        city = str(data.get("city") or "").strip()
        if not city:
            city = "北京"

        # 核心意图维度提取
        has_explicit_start_date = bool(data.get("has_explicit_start_date", False))
        has_explicit_duration = bool(data.get("has_explicit_duration", False))
        has_city = bool(data.get("has_explicit_city", True))
        clarification_prompt = data.get("clarification_prompt")

        return TripRequest(
            city=city,
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            travel_days=days,
            transportation=data.get("transportation") or "公共交通",
            accommodation=data.get("accommodation") or "舒适型酒店",
            preferences=data.get("preferences") or ["历史文化", "美食"],
            free_text_input=data.get("free_text_input") or text,
            has_explicit_dates=has_explicit_start_date,
            has_explicit_start_date=has_explicit_start_date,
            has_explicit_duration=has_explicit_duration,
            has_explicit_city=has_city,
            clarification_prompt=clarification_prompt,
        )
    except Exception as exc:
        print(f"⚠️ 自然语言参数提取异常，使用规则提取兜底: {exc}")
        city = "北京"
        popular_cities = [
            "北京", "上海", "广州", "深圳", "成都", "杭州", "西安", "南京",
            "重庆", "武汉", "苏州", "厦门", "青岛", "三亚", "昆明", "大理", "丽江", "哈尔滨"
        ]
        has_city = False
        for c in popular_cities:
            if c in text:
                city = c
                has_city = True
                break

        days = 3
        has_explicit_duration = False
        m = re.search(r"(\d+)\s*(?:天|日)", text)
        if m:
            try:
                days = int(m.group(1))
                has_explicit_duration = True
            except Exception:
                days = 3

        # 显式出发日期判定（仅当提及明确日期词时才为 True）
        has_explicit_start_date = bool(re.search(r"(明天|后天|下周|周末|国庆|元旦|五一|\d+月\d+日?|\d+号)", text))

        days = max(1, min(30, days))
        start_d = tomorrow
        end_d = start_d + timedelta(days=days - 1)

        prefs = []
        if "文化" in text or "历史" in text or "故宫" in text or "古迹" in text:
            prefs.append("历史文化")
        if "美食" in text or "吃" in text or "火锅" in text:
            prefs.append("美食")
        if "自然" in text or "山" in text or "湖" in text or "风光" in text:
            prefs.append("自然风光")
        if not prefs:
            prefs = ["休闲", "美食"]

        prompt_tip = None
        if not has_explicit_start_date:
            prompt_tip = f"已为您识别【{city}】{days}日游，请问您计划哪天出发？"

        return TripRequest(
            city=city,
            start_date=start_d.isoformat(),
            end_date=end_d.isoformat(),
            travel_days=days,
            transportation="公共交通",
            accommodation="舒适型酒店",
            preferences=prefs,
            free_text_input=text,
            has_explicit_dates=has_explicit_start_date,
            has_explicit_start_date=has_explicit_start_date,
            has_explicit_duration=has_explicit_duration,
            has_explicit_city=has_city,
            clarification_prompt=prompt_tip,
        )


def classify_chat_intent(
    text: str,
    has_current_plan: bool = False,
    current_city: str = "",
    chat_history: list = None,
    llm=None,
) -> ChatIntentRouteData:
    """利用大模型进行顶层对话意图分类（语义路由 Semantic Router）。

    分类规则：
    - 'new_plan': 用户希望开启全新的城市旅行，或明确要求推倒重做/重新规划新城市。
    - 'modify_plan': 用户在已有行程基础上微调（增删改替换、周边搜索、第X天调整），或针对当前行程进行提问咨询。
    """
    if not has_current_plan:
        parsed_trip = parse_natural_language_trip(text, llm=llm)
        return ChatIntentRouteData(
            intent="new_plan",
            reason="当前无进行中的旅行计划，初始化为新建行程规划",
            parsed_form_data=parsed_trip,
        )

    agent_llm = llm or get_llm()
    prompt = f"""你是一个智能旅行助手的语义路由专家。请分析用户在当前多轮会话中的输入，判断其真实意图。

【意图类型】
1. "new_plan": 用户明确表示想放弃当前行程，开启一个全新的城市旅行，或明确要求重新生成全新城市的旅行计划（如："不玩成都了，帮我重新规划去西安"、"换成上海3天"、"重新规划去北京"）。
2. "modify_plan": 用户希望在当前已有的旅行计划基础上进行局部微调、增删、替换、调整天数安排，或对当前行程进行咨询提问（如："把第2天的行程替换为更小众文化景致"、"第二天下午太累了换个安静公园"、"第二天打车去机场要多久"、"帮我推荐离住处近的火锅"、"预算控制在2000以内"）。

【上下文状态】
- 当前已有行程城市: {current_city or "已选目的地"}
- 用户最新输入: "{text}"

【判断铁律】
1. 如果用户提到了"第X天"、"换成"、"替换"、"改为"、"调整"、"去掉"、"增加"、"附近的"或针对当前行程提问，绝对属于 modify_plan，严禁判定为 new_plan！
2. 只有当用户明确出现"去<新城市>"或"重新规划去<新城市>"等明确更换整个目的地的表达时，才判定为 new_plan。

请仅严格返回以下 JSON 格式：
```json
{{
  "intent": "new_plan" 或 "modify_plan",
  "reason": "简明判定理由"
}}
```"""

    try:
        options = {}
        if getattr(agent_llm, "provider", "") == "qwen" and str(getattr(agent_llm, "model", "")).startswith("qwen3."):
            options["extra_body"] = {"enable_thinking": False}

        resp = agent_llm.generate("你是严格的意图分类专家，只输出标准 JSON。", prompt, **options)
        cleaned = resp.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```")[1].split("```")[0].strip()
        else:
            s = cleaned.find("{")
            e = cleaned.rfind("}") + 1
            if s != -1 and e > s:
                cleaned = cleaned[s:e]

        parsed = json.loads(cleaned)
        intent = parsed.get("intent", "modify_plan")
        reason = parsed.get("reason", "模型语义路由判定")
        if intent not in ("new_plan", "modify_plan"):
            intent = "modify_plan"

        parsed_form = None
        if intent == "new_plan":
            parsed_form = parse_natural_language_trip(text, llm=llm)

        return ChatIntentRouteData(
            intent=intent,
            reason=reason,
            parsed_form_data=parsed_form,
        )
    except Exception as exc:
        print(f"⚠️ 大模型意图分类异常，启用语义保底: {exc}")
        return ChatIntentRouteData(
            intent="modify_plan",
            reason=f"分类服务降级保底: {exc}",
            parsed_form_data=None,
        )


