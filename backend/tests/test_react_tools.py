# -*- coding: utf-8 -*-
"""Phase 3 ReAct 范式与工具体系单元测试。

验证：
1. 高德地图标准 LangChain 工具（create_amap_langchain_tools）的调用与输出序列化
2. MCP 动态工具转换器（convert_mcp_to_langchain_tools）的反射构建与执行
3. 基于 ToolNode 与 tools_condition 的 ChatModifyAgent 多轮 ReAct 闭环流程
4. 对话修改在无工具调用时的直接问答（modified: false）
"""

import json
import unittest
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.agents.chat_modify_agent import ChatModifyAgent
from app.models.schemas import (
    ChatMessage,
    ChatModifyRequest,
    Location,
    POIInfo,
    RouteInfo,
    TripPlan,
    WeatherInfo,
)
from app.services.amap_service import AmapService
from app.services.llm_service import ChatLLM, get_chat_model
from app.services.mcp_tool_adapter import (
    convert_mcp_to_langchain_tools,
    create_amap_langchain_tools,
)


class FakeMCPClient:
    """Mock MCP Client 支持 available_tools 与 call_tool"""

    def __init__(self, tools=None):
        self.available_tools = tools or ["maps_text_search", "maps_weather"]
        self.called = []

    def call_tool(self, name: str, arguments: dict):
        self.called.append((name, arguments))
        return {"status": "ok", "name": name, "echo_args": arguments}


class Phase3ReActTests(unittest.TestCase):
    def setUp(self):
        self.mock_amap = MagicMock(spec=AmapService)
        self.mock_amap.search_poi.return_value = [
            POIInfo(
                id="poi_1",
                name="颐和园",
                type="风景名胜",
                address="新建宫门路19号",
                location=Location(longitude=116.27, latitude=39.99),
                tel="010-62881144",
            )
        ]
        self.mock_amap.get_weather.return_value = [
            WeatherInfo(
                date="2026-10-01",
                source="高德地图",
                day_weather="晴",
                night_weather="多云",
                day_temp=24,
                night_temp=14,
                wind_direction="北风",
                wind_power="1-3级",
            )
        ]
        self.mock_amap.plan_route.return_value = RouteInfo(
            distance=1500.0,
            duration=1200,
            route_type="walking",
            description="沿新建宫门路步行1.5公里",
        )
        self.mock_amap.get_poi_detail.return_value = {
            "id": "poi_1",
            "name": "颐和园",
            "rating": "4.8",
        }

    def test_create_amap_langchain_tools(self):
        """测试高德工具套件的创建与执行结果"""
        tools = create_amap_langchain_tools(self.mock_amap)
        tool_names = [t.name for t in tools]
        self.assertIn("amap_search_poi", tool_names)
        self.assertIn("amap_get_weather", tool_names)
        self.assertIn("amap_plan_route", tool_names)
        self.assertIn("amap_search_around", tool_names)
        self.assertIn("amap_get_poi_detail", tool_names)

        # 测试 search_poi 工具调用
        search_tool = next(t for t in tools if t.name == "amap_search_poi")
        result_json = search_tool.invoke({"keywords": "颐和园", "city": "北京"})
        data = json.loads(result_json)
        self.assertEqual(data["status"], "success")
        self.assertEqual(len(data["pois"]), 1)
        self.assertEqual(data["pois"][0]["name"], "颐和园")
        self.mock_amap.search_poi.assert_called_with(keywords="颐和园", city="北京")

        # 测试 plan_route 工具调用
        route_tool = next(t for t in tools if t.name == "amap_plan_route")
        route_res = route_tool.invoke({"origin": "故宫", "destination": "天安门", "route_type": "walking"})
        route_data = json.loads(route_res)
        self.assertEqual(route_data["status"], "success")
        self.assertEqual(route_data["distance_meters"], 1500.0)

    def test_convert_mcp_to_langchain_tools(self):
        """测试 MCP 动态反射工具转换为 LangChain StructuredTool"""
        mcp_client = FakeMCPClient(tools=["maps_geo", "maps_search_around"])
        lc_tools = convert_mcp_to_langchain_tools(mcp_client)
        self.assertEqual(len(lc_tools), 2)
        self.assertEqual(lc_tools[0].name, "mcp_maps_geo")
        self.assertEqual(lc_tools[1].name, "mcp_maps_search_around")

        # 执行动态工具
        res = lc_tools[0].invoke({"address": "北京市海淀区"})
        parsed = json.loads(res)
        self.assertEqual(parsed["name"], "maps_geo")
        self.assertEqual(mcp_client.called[0][0], "maps_geo")

    def test_chat_modify_react_loop_with_tool_call(self):
        """测试 ChatModifyAgent 完整的 ReAct 闭环：
        Turn 1: Agent 发起 tool_call
        Turn 2: ToolNode 自动执行并将结果反馈给 Agent
        Turn 3: Agent 接收 Observation 并输出修改后的最终 JSON 行程
        """
        sample_plan = {
            "city": "北京",
            "start_date": "2026-10-01",
            "end_date": "2026-10-01",
            "days": [
                {
                    "date": "2026-10-01",
                    "day_index": 0,
                    "description": "游览故宫",
                    "transportation": "公共交通",
                    "accommodation": "酒店",
                    "hotel": {
                        "name": "北京饭店",
                        "address": "东长安街",
                        "location": {"longitude": 116.4, "latitude": 39.9},
                        "price_range": "500-800元",
                        "rating": "4.5",
                        "distance": "市中心",
                        "type": "高档型",
                        "estimated_cost": 600,
                    },
                    "attractions": [
                        {
                            "name": "故宫",
                            "address": "景山前街4号",
                            "location": {"longitude": 116.39, "latitude": 39.91},
                            "visit_duration": 180,
                            "description": "紫禁城",
                            "category": "古迹",
                            "ticket_price": 60,
                        }
                    ],
                    "meals": [
                        {"type": "breakfast", "name": "早餐", "description": "早餐", "estimated_cost": 30},
                        {"type": "lunch", "name": "午餐", "description": "午餐", "estimated_cost": 60},
                        {"type": "dinner", "name": "晚餐", "description": "晚餐", "estimated_cost": 80},
                    ],
                }
            ],
            "weather_info": [],
            "overall_suggestions": "游玩顺利",
            "budget": {
                "total_attractions": 60,
                "total_hotels": 600,
                "total_meals": 170,
                "total_transportation": 200,
                "total": 1030,
            },
        }

        # 构建模拟两轮决策的 ReAct Mock LLM
        class TwoTurnReActLLM:
            def __init__(self):
                self.calls = 0

            def bind_tools(self, tools):
                return self

            def invoke(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    # 第一轮：大模型自主决定调用 amap_search_poi
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "amap_search_poi",
                                "args": {"keywords": "颐和园", "city": "北京"},
                                "id": "call_poi_001",
                            }
                        ],
                    )
                else:
                    # 第二轮：看到 ToolNode 返回的真实地点后，生成最终修改方案
                    updated_plan = json.loads(json.dumps(sample_plan))
                    updated_plan["days"][0]["attractions"] = [
                        {
                            "name": "颐和园",
                            "address": "新建宫门路19号",
                            "location": {"longitude": 116.27, "latitude": 39.99},
                            "visit_duration": 180,
                            "description": "皇家园林",
                            "category": "风景名胜",
                            "ticket_price": 50,
                        }
                    ]
                    response_payload = {
                        "reply": "已为您将第1天的故宫换成颐和园，门票50元，地址为新建宫门路19号。",
                        "modified": True,
                        "changes_summary": "故宫替换为颐和园",
                        "updated_plan": updated_plan,
                    }
                    return AIMessage(content=f"```json\n{json.dumps(response_payload, ensure_ascii=False)}\n```")

        mock_llm = TwoTurnReActLLM()
        agent = ChatModifyAgent(llm=mock_llm, amap_service=self.mock_amap)

        req = ChatModifyRequest(
            thread_id="test_react_thread",
            message="把故宫换成颐和园",
            trip_plan=TripPlan(**sample_plan),
            chat_history=[ChatMessage(role="user", content="把故宫换成颐和园")],
        )

        res = agent.modify_plan(req)

        # 验证：
        # 1. LLM 被连续调用了 2 轮（ReAct 循环）
        self.assertEqual(mock_llm.calls, 2)
        # 2. ToolNode 确实自动调用了高德地图工具
        self.mock_amap.search_poi.assert_called_with(keywords="颐和园", city="北京")
        # 3. 最终行程更新成功，门票与预算自动重算
        self.assertTrue(res.modified)
        self.assertEqual(res.changes_summary, "故宫替换为颐和园")
        self.assertEqual(res.updated_plan.days[0].attractions[0].name, "颐和园")
        self.assertEqual(res.updated_plan.budget.total_attractions, 50)
        self.assertEqual(res.updated_plan.budget.total, 1020)

    def test_chat_modify_pure_question_no_tools(self):
        """测试纯咨询时模型无需调工具，直接回答，modified: false"""
        sample_plan = {
            "city": "北京",
            "start_date": "2026-10-01",
            "end_date": "2026-10-01",
            "days": [],
            "weather_info": [],
            "overall_suggestions": "好",
            "budget": {"total": 0},
        }

        class PureQALLM:
            def bind_tools(self, tools):
                return self

            def invoke(self, messages, **kwargs):
                return AIMessage(
                    content=json.dumps({
                        "reply": "第一天的行程整体比较宽松，非常适合老年人或带小孩游玩。",
                        "modified": False,
                        "changes_summary": "解答咨询",
                        "updated_plan": sample_plan,
                    }, ensure_ascii=False)
                )

        agent = ChatModifyAgent(llm=PureQALLM(), amap_service=self.mock_amap)
        req = ChatModifyRequest(
            thread_id="test_qa",
            message="第一天行程会不会太累？",
            trip_plan=TripPlan(**sample_plan),
            chat_history=[],
        )
        res = agent.modify_plan(req)
        self.assertFalse(res.modified)
        self.assertIn("适合", res.reply)
        self.mock_amap.search_poi.assert_not_called()

    def test_classify_chat_intent_modify_plan(self):
        """测试已有行程时微调意图（如第2天替换）精准识别为 modify_plan"""
        from app.agents.trip_planner_agent import classify_chat_intent

        class MockRouterLLM:
            def generate(self, sys, user, **kwargs):
                return json.dumps({"intent": "modify_plan", "reason": "用户要求替换第2天行程，属于行程微调"})

        route_res = classify_chat_intent(
            text="把第2天的行程替换为更小众文化景致",
            has_current_plan=True,
            current_city="成都",
            llm=MockRouterLLM(),
        )
        self.assertEqual(route_res.intent, "modify_plan")
        self.assertIn("微调", route_res.reason)

    def test_classify_chat_intent_new_plan_when_empty(self):
        """测试无行程时自动初始化为 new_plan 并提取表单数据"""
        from app.agents.trip_planner_agent import classify_chat_intent

        class MockExtractLLM:
            def generate(self, sys, user, **kwargs):
                return json.dumps({
                    "city": "杭州",
                    "travel_days": 3,
                    "transportation": "高铁",
                    "accommodation": "舒适型酒店",
                    "preferences": ["自然风光", "美食"],
                    "has_explicit_start_date": True,
                    "start_date": "2026-10-01",
                })

        route_res = classify_chat_intent(
            text="我想去杭州玩3天",
            has_current_plan=False,
            llm=MockExtractLLM(),
        )
        self.assertEqual(route_res.intent, "new_plan")
        self.assertIsNotNone(route_res.parsed_form_data)
        self.assertEqual(route_res.parsed_form_data.city, "杭州")

    def test_api_chat_intent_endpoint(self):
        """测试 POST /api/trip/chat/intent 接口响应"""
        from fastapi.testclient import TestClient
        from app.api.main import app
        from unittest.mock import patch

        client = TestClient(app)
        with patch("app.api.routes.trip.classify_chat_intent") as mock_classify:
            from app.models.schemas import ChatIntentRouteData
            mock_classify.return_value = ChatIntentRouteData(
                intent="modify_plan",
                reason="替换第2天行程",
            )
            resp = client.post("/api/trip/chat/intent", json={
                "text": "把第2天的行程替换为更小众文化景致",
                "has_current_plan": True,
                "current_city": "成都",
                "chat_history": [],
            })
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["intent"], "modify_plan")


if __name__ == "__main__":
    unittest.main()

