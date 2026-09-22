# -*- coding: utf-8 -*-
"""LangGraph 对话式行程修改 ReAct 智能体子图 (chat_modify)"""

import json
import logging
import re
import uuid
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from ..config import get_settings
from ..models.schemas import (
    Budget,
    ChatMessage,
    ChatModifyData,
    ChatModifyRequest,
    Location,
    POIInfo,
    TripPlan,
)
from ..services.amap_service import AmapService, create_amap_tool
from ..services.llm_service import get_chat_model, get_llm
from ..services.observability_service import safe_traceable, record_evaluation_feedback
from ..services.eval_service import evaluate_plan
from ..services.mcp_tool_adapter import (
    convert_mcp_to_langchain_tools,
    create_amap_langchain_tools,
)
from ..services.knowledge_tool import create_knowledge_langchain_tool
from .checkpointer import get_checkpointer

logger = logging.getLogger(__name__)


CHAT_MODIFY_SYSTEM_PROMPT = """你是智能旅行助手的行程修改专家。你的职责是根据用户的自然语言指令，精准调整已有的旅行计划。

你可以自主调用高德地图工具与本地旅行知识库获取真实数据：
- search_travel_knowledge: 检索城市的官方深度攻略、门票预约与放票规则、闭馆时间、最佳机位与避坑防骗贴士（当用户询问门票怎么买、提前几天抢、周几闭馆、防骗避坑或路线建议时优先调用）。
- amap_search_poi: 搜索城市内的真实景点、餐厅、美食、酒店等，获取真实经纬度坐标、地址和门票。
- amap_get_weather: 查询城市的实时天气及未来预报。
- amap_plan_route: 规划两点间路线（步行/驾车/公交）与耗时。
- amap_search_around: 围绕已知地标/酒店搜索周边餐饮设施。
- amap_get_poi_detail: 获取特定地点的详细信息。

【核心决策原则】
1. 增删替换地点时，必须自主调用工具获取真实经纬度与信息，切勿编造虚假坐标；
2. 提问或咨询交通/天气时，自主调用路线或天气工具并直接作答；
3. 如果用户只是提问或闲聊（未要求修改行程结构），请设置 modified: false，并在 reply 中解答，updated_plan 保持原样；
4. 当所有工具信息搜集完毕，不再需要调用工具时，请直接返回符合格式的最终 JSON 数据：

```json
{
  "reply": "面向用户的自然语言回复，清晰说明具体调整了哪些内容（语气亲切、专业、精炼）",
  "modified": true,
  "changes_summary": "一句话修改摘要，如：第2天故宫替换为颐和园",
  "updated_plan": {
    "city": "城市名称",
    "start_date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "days": [
      {
        "date": "YYYY-MM-DD",
        "day_index": 0,
        "description": "当天行程概述",
        "transportation": "交通方式",
        "accommodation": "住宿类型",
        "hotel": {
          "name": "酒店名称",
          "address": "酒店地址",
          "location": {"longitude": 116.397, "latitude": 39.916},
          "price_range": "价格区间",
          "rating": "4.6",
          "distance": "位置距离",
          "type": "酒店类型",
          "estimated_cost": 400
        },
        "attractions": [
          {
            "name": "景点名称",
            "address": "地址",
            "location": {"longitude": 116.397, "latitude": 39.916},
            "visit_duration": 120,
            "description": "游览描述",
            "category": "分类",
            "ticket_price": 60
          }
        ],
        "meals": [
          {"type": "breakfast", "name": "早餐", "description": "描述", "estimated_cost": 30},
          {"type": "lunch", "name": "午餐", "description": "描述", "estimated_cost": 50},
          {"type": "dinner", "name": "晚餐", "description": "描述", "estimated_cost": 80}
        ]
      }
    ],
    "weather_info": [],
    "overall_suggestions": "更新后的建议",
    "budget": {
      "total_attractions": 180,
      "total_hotels": 1200,
      "total_meals": 480,
      "total_transportation": 200,
      "total": 2060
    }
  }
}
```
"""


class ChatModifyState(TypedDict, total=False):
    thread_id: str
    message: str
    trip_plan: dict
    chat_history: list[dict]
    messages: Annotated[list[AnyMessage], add_messages]
    city: str
    reply: str
    updated_plan: dict
    modified: bool
    changes_summary: str
    error: str


class _MockModelAdapter:
    """兼容旧式单元测试中只实现了 generate(sys, user) 的 FakeChatLLM。"""

    def __init__(self, raw_llm: Any):
        self.raw_llm = raw_llm

    def invoke(self, messages: List[AnyMessage], **kwargs) -> AIMessage:
        sys_text = ""
        user_text = ""
        for m in messages:
            if isinstance(m, SystemMessage):
                sys_text = str(m.content)
            elif isinstance(m, (HumanMessage, ToolMessage)):
                user_text += f"\n{m.content}"
        content = self.raw_llm.generate(sys_text, user_text)
        return AIMessage(content=content)


class ChatModifyAgent:
    """基于 ReAct 范式的对话式行程修改子图编排器"""

    def __init__(self, llm: Any = None, amap_service: Optional[AmapService] = None, checkpointer: Any = None):
        settings = get_settings()
        self.raw_llm = llm if llm is not None else get_llm()
        self.amap_service = (
            amap_service if amap_service is not None
            else AmapService(mcp_tool=create_amap_tool(settings.amap_api_key))
        )
        self.checkpointer = checkpointer if checkpointer is not None else get_checkpointer()

        # 1. 注册高德地图标准 LangChain 工具套件
        self.tools = create_amap_langchain_tools(self.amap_service)
        # 1.1 注册旅行知识库检索工具 (Phase 4: RAG 知识增强)
        try:
            self.tools.append(create_knowledge_langchain_tool())
        except Exception as exc:
            logger.warning("注册知识库检索工具失败: %s", exc)

        # 2. 动态发现并注册底层 MCP Client 暴露的其他工具
        mcp_client = getattr(self.amap_service, "mcp_tool", None)
        if mcp_client:
            dynamic_tools = convert_mcp_to_langchain_tools(mcp_client)
            existing_names = {t.name for t in self.tools}
            for dt in dynamic_tools:
                if dt.name not in existing_names:
                    self.tools.append(dt)

        # 3. 将工具绑定至 LLM (若为 Mock LLM 则通过适配器兼容)
        if hasattr(self.raw_llm, "bind_tools"):
            self.model_with_tools = self.raw_llm.bind_tools(self.tools)
        elif hasattr(self.raw_llm, "get_chat_model"):
            chat_model = self.raw_llm.get_chat_model()
            self.model_with_tools = chat_model.bind_tools(self.tools)
        else:
            self.model_with_tools = _MockModelAdapter(self.raw_llm)

        # 4. 构建 LangGraph ReAct 循环图
        builder = StateGraph(ChatModifyState)
        builder.add_node("agent", self._agent_step)
        builder.add_node("tools", ToolNode(self.tools))
        builder.add_node("validate_and_finalize", self._validate_and_finalize)

        builder.add_edge(START, "agent")
        builder.add_conditional_edges(
            "agent",
            tools_condition,
            {"tools": "tools", "__end__": "validate_and_finalize"},
        )
        builder.add_edge("tools", "agent")
        builder.add_edge("validate_and_finalize", END)

        self.graph = builder.compile(checkpointer=self.checkpointer)

    def _extract_potential_entities(self, text: str) -> list[str]:
        """辅助函数：从用户修改指令中抽取地点关键词（保持向下兼容与回归测试）。"""
        entities = []
        patterns = [
            r"(?:换成|改成|改为|替换为|换到|去|到|增加|添加|安排)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?)(?:吧|啊|呀|，|。|\s|$|做|吃|看|游玩)",
            r"(?:住在|住|选)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?(?:酒店|旅社|宾馆|民宿|客栈))",
            r"(?:吃|去)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?(?:烤鸭|火锅|私房菜|餐厅|酒楼|小吃))",
        ]
        for p in patterns:
            for match in re.finditer(p, text):
                candidate = match.group(1).strip()
                if candidate and len(candidate) >= 2 and candidate not in entities:
                    if candidate not in {"一个", "这个", "那个", "一下", "地方", "景点", "美食", "餐厅", "酒店", "行程"}:
                        entities.append(candidate)
        return entities

    def _agent_step(self, state: ChatModifyState) -> dict:
        """ReAct 决策节点：LLM 思考并决定是发起工具调用 (Action) 还是输出最终结果 (Answer)。"""
        messages = list(state.get("messages") or [])

        # 第一次进入 agent 节点：构造 Prompt 初始化上下文并持久化到状态中
        if not messages:
            message = state.get("message", "")
            plan_dict = state.get("trip_plan", {})
            history = state.get("chat_history", [])

            history_text = ""
            if history:
                history_lines = []
                for item in history[-6:]:
                    role = "用户" if item.get("role") == "user" else "AI助手"
                    history_lines.append(f"{role}: {item.get('content', '')}")
                history_text = "\n**近期对话历史:**\n" + "\n".join(history_lines) + "\n"

            prompt_query = f"""
{history_text}
**当前旅行计划 (JSON):**
```json
{json.dumps(plan_dict, ensure_ascii=False, indent=2)}
```

**用户本次修改指令:**
"{message}"

请根据用户指令与已有旅行计划，自主判断是否调用工具检索真实 POI / 天气 / 路线。
搜集齐全后，输出最终符合格式规范的 JSON 行程结果。
"""
            init_messages = [
                SystemMessage(content=CHAT_MODIFY_SYSTEM_PROMPT),
                HumanMessage(content=prompt_query),
            ]
            response = self.model_with_tools.invoke(init_messages)
            if not isinstance(response, AIMessage):
                response = AIMessage(content=str(response))

            return {"messages": [*init_messages, response]}

        # 后续进入（已执行完至少一次工具调用）：
        tool_msgs_count = sum(1 for m in messages if isinstance(m, ToolMessage))
        invoke_messages = list(messages)
        if tool_msgs_count >= 2:
            invoke_messages.append(
                HumanMessage(content="已获取所需数据，请不要再调用任何工具，直接严格按照规定的 JSON 格式输出最终旅行计划。")
            )

        # 调用模型获取决策响应
        response = self.model_with_tools.invoke(invoke_messages)
        if not isinstance(response, AIMessage):
            response = AIMessage(content=str(response))

        return {"messages": [response]}

    def _validate_and_finalize(self, state: ChatModifyState) -> dict:
        """校验更新后的 TripPlan 并自动重新汇总预算"""
        original_dict = state.get("trip_plan", {})
        messages = state.get("messages", [])

        # 获取最后一个 AIMessage 的内容
        response_text = ""
        for m in reversed(messages):
            if isinstance(m, AIMessage) and m.content:
                response_text = str(m.content)
                break

        if not response_text:
            return {
                "reply": "未能解析到更新内容，已为您保留原计划。",
                "modified": False,
                "changes_summary": "保留原计划",
                "updated_plan": original_dict,
            }

        try:
            cleaned = response_text.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            else:
                json_start = cleaned.find("{")
                json_end = cleaned.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    cleaned = cleaned[json_start:json_end]

            parsed = json.loads(cleaned)
            reply = parsed.get("reply", "已为您完成行程调整。")
            modified = parsed.get("modified", True)
            changes_summary = parsed.get("changes_summary", "已根据您的要求更新行程")
            updated_dict = parsed.get("updated_plan") or original_dict

            if not modified or not updated_dict:
                return {
                    "reply": reply,
                    "modified": False,
                    "changes_summary": changes_summary,
                    "updated_plan": original_dict,
                }

            # 校验并自动重新核算预算
            plan = TripPlan(**updated_dict)
            total_attractions = sum(
                (a.ticket_price or 0)
                for day in plan.days
                for a in day.attractions
            )
            total_hotels = sum(
                (day.hotel.estimated_cost if day.hotel and day.hotel.estimated_cost else 0)
                for day in plan.days
            )
            total_meals = sum(
                (m.estimated_cost or 0)
                for day in plan.days
                for m in day.meals
            )
            orig_trans = (
                original_dict.get("budget", {}).get("total_transportation")
                if isinstance(original_dict, dict) else 200
            ) or 200
            total_all = total_attractions + total_hotels + total_meals + orig_trans

            plan.budget = Budget(
                total_attractions=total_attractions,
                total_hotels=total_hotels,
                total_meals=total_meals,
                total_transportation=orig_trans,
                total=total_all,
            )

            return {
                "reply": reply,
                "modified": True,
                "changes_summary": changes_summary,
                "updated_plan": plan.model_dump(mode="json"),
            }
        except Exception as exc:
            logger.warning("LLM 修改行程解析失败: %s", exc)
            return {
                "reply": f"在尝试调整行程时遇到了问题：{str(exc)}。已为您保留原行程。",
                "modified": False,
                "changes_summary": "调整失败，已恢复",
                "updated_plan": original_dict,
                "error": str(exc),
            }

    @safe_traceable(name="ChatModifyAgent.modify_plan", run_type="chain")
    def modify_plan(self, request: ChatModifyRequest) -> ChatModifyData:
        """对外调用入口：执行基于 ReAct 循环的行程修改子图"""
        tid = request.thread_id or f"chat_{uuid.uuid4().hex[:12]}"
        config = {
            "configurable": {"thread_id": tid},
            "recursion_limit": 20,
        }

        plan_dict = request.trip_plan.model_dump(mode="json")
        history_list = [m.model_dump(mode="json") for m in request.chat_history]

        initial_state: ChatModifyState = {
            "thread_id": tid,
            "message": request.message,
            "trip_plan": plan_dict,
            "chat_history": history_list,
            "messages": [],
        }

        result = self.graph.invoke(initial_state, config=config)

        updated_plan_dict = result.get("updated_plan", plan_dict)
        try:
            validated_plan = TripPlan(**updated_plan_dict)
        except Exception:
            validated_plan = request.trip_plan

        rep = None
        # 若行程发生了有效调整，执行结构化质量评估并回传反馈
        if result.get("modified", True):
            try:
                rep = evaluate_plan(validated_plan)
                record_evaluation_feedback(rep, thread_id=tid)
            except Exception as eval_err:
                logger.debug("ChatModifyAgent 评估上报跳过: %s", eval_err)

        return ChatModifyData(
            reply=result.get("reply", "已为您调整行程！"),
            updated_plan=validated_plan,
            modified=result.get("modified", True),
            thread_id=tid,
            changes_summary=result.get("changes_summary"),
            evaluation=rep,
        )


_chat_modify_agent = None


def get_chat_modify_agent() -> ChatModifyAgent:
    """获取行程修改子图单例"""
    global _chat_modify_agent
    if _chat_modify_agent is None:
        _chat_modify_agent = ChatModifyAgent()
    return _chat_modify_agent
