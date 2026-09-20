# -*- coding: utf-8 -*-
"""LangGraph 对话式行程修改子图 (chat_modify)"""

import json
import re
import uuid
from typing import TypedDict, Optional, List, Dict, Any

from langgraph.graph import END, START, StateGraph

from .checkpointer import get_checkpointer
from ..services.llm_service import get_llm
from ..services.amap_service import AmapService, create_amap_tool
from ..models.schemas import (
    TripPlan,
    POIInfo,
    Location,
    Budget,
    ChatMessage,
    ChatModifyRequest,
    ChatModifyData,
)
from ..config import get_settings


CHAT_MODIFY_SYSTEM_PROMPT = """你是智能旅行助手的行程修改专家。你的职责是根据用户的自然语言指令，精准调整已有的旅行计划。

用户可能会提出如下修改要求：
1. 替换或增删景点（例如："把第二天的故宫换成颐和园"、"第三天下午加一个798艺术区"、"去掉第二天的某个景点"）
2. 调整餐饮或住宿（例如："帮我加一个素食午餐"、"酒店换成靠近西湖的舒适酒店"）
3. 调整预算或节奏（例如："预算控制在3000以内"、"行程太赶了，每天最多安排2个景点"）
4. 咨询与建议（例如："第一天的行程会不会太累？"）

如果检索工具提供了真实的 POI 信息（包含地址、真实经纬度坐标、门票等），请务必在修改后的行程中使用这些真实信息，切勿编造虚假坐标。

请严格返回以下 JSON 格式：
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
注意：如果用户只是单纯提问而不需要修改行程结构，请设置 `modified: false`，并在 `reply` 中解答，`updated_plan` 保持传入的原行程。
"""


class ChatModifyState(TypedDict, total=False):
    thread_id: str
    message: str
    trip_plan: dict
    chat_history: list[dict]
    city: str
    retrieved_pois: list[dict]
    reply: str
    updated_plan: dict
    modified: bool
    changes_summary: str
    error: str


class ChatModifyAgent:
    """LangGraph 对话式修改行程子图编排器"""

    def __init__(self, llm=None, amap_service: Optional[AmapService] = None, checkpointer=None):
        settings = get_settings()
        self.llm = llm if llm is not None else get_llm()
        self.amap_service = (
            amap_service if amap_service is not None
            else AmapService(mcp_tool=create_amap_tool(settings.amap_api_key))
        )
        self.checkpointer = checkpointer if checkpointer is not None else get_checkpointer()

        builder = StateGraph(ChatModifyState)
        builder.add_node("intent_and_retrieve", self._intent_and_retrieve)
        builder.add_node("modify_planner", self._modify_planner)
        builder.add_node("validate_and_finalize", self._validate_and_finalize)

        builder.add_edge(START, "intent_and_retrieve")
        builder.add_edge("intent_and_retrieve", "modify_planner")
        builder.add_edge("modify_planner", "validate_and_finalize")
        builder.add_edge("validate_and_finalize", END)

        self.graph = builder.compile(checkpointer=self.checkpointer)

    def _extract_potential_entities(self, text: str) -> list[str]:
        """从用户修改指令中粗提潜在新地点名称（如：换成颐和园、去全聚德、住在亚朵）"""
        entities = []
        # 常见动宾搭配模式
        patterns = [
            r"(?:换成|改成|改为|替换为|换到|去|到|增加|添加|安排)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?)(?:吧|啊|呀|，|。|\s|$|做|吃|看|游玩)",
            r"(?:住在|住|选)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?(?:酒店|旅社|宾馆|民宿|客栈))",
            r"(?:吃|去)([\u4e00-\u9fa50-9a-zA-Z]{2,12}?(?:烤鸭|火锅|私房菜|餐厅|酒楼|小吃))",
        ]
        for p in patterns:
            for match in re.finditer(p, text):
                candidate = match.group(1).strip()
                if candidate and len(candidate) >= 2 and candidate not in entities:
                    # 过滤纯动词或泛词
                    if candidate not in {"一个", "这个", "那个", "一下", "地方", "景点", "美食", "餐厅", "酒店", "行程"}:
                        entities.append(candidate)
        return entities

    def _intent_and_retrieve(self, state: ChatModifyState) -> dict:
        """意图分析并在需要时检索真实高德 POI"""
        message = state.get("message", "")
        plan_dict = state.get("trip_plan", {})
        city = plan_dict.get("city") or "北京"

        extracted = self._extract_potential_entities(message)
        retrieved_pois: list[dict] = []

        if extracted:
            print(f"🔍 对话修改识别潜在地点关键词: {extracted} (城市: {city})")
            for keyword in extracted[:2]:
                try:
                    pois = self.amap_service.search_poi(keyword, city)
                    for p in pois[:3]:
                        retrieved_pois.append(p.model_dump(mode="json"))
                except Exception as exc:
                    print(f"⚠️  检索地点 {keyword} 失败: {exc}")

        return {
            "city": city,
            "retrieved_pois": retrieved_pois,
        }

    def _modify_planner(self, state: ChatModifyState) -> dict:
        """调用 LLM 重构行程并生成回复"""
        message = state.get("message", "")
        plan_dict = state.get("trip_plan", {})
        history = state.get("chat_history", [])
        retrieved = state.get("retrieved_pois", [])

        # 构建对话上下文摘要
        history_text = ""
        if history:
            history_lines = []
            for item in history[-6:]:
                role = "用户" if item.get("role") == "user" else "AI助手"
                history_lines.append(f"{role}: {item.get('content', '')}")
            history_text = "\n**近期对话历史:**\n" + "\n".join(history_lines) + "\n"

        retrieved_text = ""
        if retrieved:
            retrieved_text = f"\n**高德地图已检索到的真实候选地点信息:**\n{json.dumps(retrieved, ensure_ascii=False, indent=2)}\n"

        prompt_query = f"""
{history_text}
**当前旅行计划 (JSON):**
```json
{json.dumps(plan_dict, ensure_ascii=False, indent=2)}
```
{retrieved_text}
**用户本次修改指令:**
"{message}"

请根据上述信息更新旅行计划，并输出符合格式要求的 JSON 数据。
"""

        try:
            extra_options = {}
            if getattr(self.llm, "provider", "") == "qwen" and str(getattr(self.llm, "model", "")).startswith("qwen3."):
                extra_options["extra_body"] = {"enable_thinking": False}

            response = self.llm.generate(
                CHAT_MODIFY_SYSTEM_PROMPT,
                prompt_query,
                **extra_options
            )

            # 解析 LLM 输出
            cleaned = response.strip()
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
            updated_plan_dict = parsed.get("updated_plan") or plan_dict

            return {
                "reply": reply,
                "modified": modified,
                "changes_summary": changes_summary,
                "updated_plan": updated_plan_dict,
            }
        except Exception as exc:
            print(f"⚠️  LLM 修改行程解析失败: {exc}")
            return {
                "reply": f"抱歉，在尝试调整行程时遇到了问题：{str(exc)}。我为您保留了原行程。",
                "modified": False,
                "changes_summary": "调整失败，已恢复",
                "updated_plan": plan_dict,
                "error": str(exc),
            }

    def _validate_and_finalize(self, state: ChatModifyState) -> dict:
        """校验更新后的 TripPlan 并自动重新汇总预算"""
        updated_dict = state.get("updated_plan", {})
        original_dict = state.get("trip_plan", {})
        modified = state.get("modified", True)

        if not modified or not updated_dict:
            return {"updated_plan": original_dict}

        try:
            # 校验并转换为 Pydantic 对象
            plan = TripPlan(**updated_dict)

            # 自动重新核算各项预算
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
                total=total_all
            )

            final_plan_dict = plan.model_dump(mode="json")
            return {"updated_plan": final_plan_dict}
        except Exception as exc:
            print(f"⚠️  更新计划校验失败，回退至原行程: {exc}")
            return {
                "updated_plan": original_dict,
                "modified": False,
                "reply": f"{state.get('reply', '')} (注：因数据校验异常已为您保留原计划格式)"
            }

    def modify_plan(self, request: ChatModifyRequest) -> ChatModifyData:
        """对外调用入口：执行行程修改子图"""
        tid = request.thread_id or f"chat_{uuid.uuid4().hex[:12]}"
        config = {"configurable": {"thread_id": tid}}

        plan_dict = request.trip_plan.model_dump(mode="json")
        history_list = [m.model_dump(mode="json") for m in request.chat_history]

        initial_state: ChatModifyState = {
            "thread_id": tid,
            "message": request.message,
            "trip_plan": plan_dict,
            "chat_history": history_list,
        }

        result = self.graph.invoke(initial_state, config=config)

        updated_plan_dict = result.get("updated_plan", plan_dict)
        try:
            validated_plan = TripPlan(**updated_plan_dict)
        except Exception:
            validated_plan = request.trip_plan

        return ChatModifyData(
            reply=result.get("reply", "已为您调整行程！"),
            updated_plan=validated_plan,
            modified=result.get("modified", True),
            thread_id=tid,
            changes_summary=result.get("changes_summary"),
        )


_chat_modify_agent = None


def get_chat_modify_agent() -> ChatModifyAgent:
    """获取行程修改子图单例"""
    global _chat_modify_agent
    if _chat_modify_agent is None:
        _chat_modify_agent = ChatModifyAgent()
    return _chat_modify_agent
