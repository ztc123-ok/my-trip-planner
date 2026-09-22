# -*- coding: utf-8 -*-
"""Phase 4: RAG 知识检索增强与 LangChain 工具集成测试。"""

import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.api.main import app
from app.models.schemas import TripRequest, Location, POIInfo, TripPlan, DayPlan, Meal, Hotel, Attraction
from app.services.knowledge_tool import create_knowledge_langchain_tool
from app.agents.trip_planner_agent import MultiAgentTripPlanner, TripGraphState


class TestRAGPipeline(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_knowledge_langchain_tool(self):
        """测试知识库 LangChain Tool (search_travel_knowledge) 能正常调用并返回结构化数据"""
        tool = create_knowledge_langchain_tool()
        self.assertEqual(tool.name, "search_travel_knowledge")

        # 模拟检索北京故宫放票
        result_json = tool.invoke({"query": "故宫 门票放票时间与预约", "city": "北京"})
        self.assertIn("故宫", result_json)
        self.assertIn("status", result_json)

    def test_knowledge_api_routes(self):
        """测试 /api/knowledge 路由端点"""
        # 测试城市列表
        res_cities = self.client.get("/api/knowledge/cities")
        self.assertEqual(res_cities.status_code, 200)
        data = res_cities.json()
        self.assertTrue(data["success"])
        self.assertGreater(data["total_cities"], 0)
        city_names = [c["city"] for c in data["cities"]]
        self.assertIn("北京", city_names)

        # 测试语义搜索
        res_search = self.client.get("/api/knowledge/search", params={"city": "西安", "query": "兵马俑 防骗野导"})
        self.assertEqual(res_search.status_code, 200)
        s_data = res_search.json()
        self.assertTrue(s_data["success"])
        self.assertGreater(len(s_data["data"]), 0)

    def test_retrieval_node_in_trip_planner(self):
        """测试 LangGraph 中的 _retrieve_knowledge 节点"""
        mock_llm = MagicMock()
        mock_amap = MagicMock()
        planner = MultiAgentTripPlanner(llm=mock_llm, amap_service=mock_amap)

        req = TripRequest(
            city="成都",
            start_date="2026-10-01",
            end_date="2026-10-02",
            travel_days=2,
            transportation="公共交通",
            accommodation="舒适型酒店",
            preferences=["大熊猫", "美食"],
        )
        state: TripGraphState = {
            "request": req,
            "candidate_attractions": [
                POIInfo(id="poi1", name="成都大熊猫繁育研究基地", type="景点", address="成华区熊猫大道1375号"),
                POIInfo(id="poi2", name="宽窄巷子", type="景点", address="青羊区长顺上街"),
            ],
        }

        output = planner._retrieve_knowledge(state)
        self.assertIn("knowledge_context", output)
        self.assertIn("knowledge_docs", output)
        self.assertGreater(len(output["knowledge_docs"]), 0)
        self.assertIn("大熊猫", output["knowledge_context"])

    def test_validate_plan_enriches_rag_fields(self):
        """测试校验节点自动补齐 booking_tips, tips 与 knowledge_highlights"""
        mock_llm = MagicMock()
        mock_amap = MagicMock()
        planner = MultiAgentTripPlanner(llm=mock_llm, amap_service=mock_amap)

        req = TripRequest(
            city="北京",
            start_date="2026-10-01",
            end_date="2026-10-01",
            travel_days=1,
            transportation="公共交通",
            accommodation="快捷酒店",
            preferences=["历史文化"],
        )

        plan_json = """{
  "city": "北京",
  "start_date": "2026-10-01",
  "end_date": "2026-10-01",
  "days": [
    {
      "date": "2026-10-01",
      "day_index": 0,
      "description": "北京历史文化经典一日游",
      "transportation": "地铁",
      "accommodation": "快捷酒店",
      "hotel": {
        "name": "北京王府井酒店",
        "address": "东城区王府井大街",
        "price_range": "300-500元",
        "rating": "4.5",
        "distance": "距故宫 1.5km",
        "type": "经济型酒店",
        "estimated_cost": 400
      },
      "attractions": [
        {
          "name": "故宫博物院",
          "address": "东城区景山前街4号",
          "location": {"longitude": 116.397, "latitude": 39.916},
          "visit_duration": 180,
          "description": "明清两代皇家宫殿",
          "category": "历史古迹",
          "ticket_price": 60
        }
      ],
      "meals": [
        {"type": "breakfast", "name": "北京早点", "estimated_cost": 25},
        {"type": "lunch", "name": "老北京炸酱面", "estimated_cost": 45},
        {"type": "dinner", "name": "全聚德烤鸭", "estimated_cost": 120}
      ]
    }
  ],
  "overall_suggestions": "提前准备身份证件",
  "budget": {
    "total_attractions": 60,
    "total_hotels": 400,
    "total_meals": 190,
    "total_transportation": 30,
    "total": 680
  }
}"""

        state: TripGraphState = {
            "request": req,
            "planner_response": plan_json,
            "knowledge_docs": [
                {
                    "spot_name": "故宫博物院",
                    "section_type": "基础信息与预约规则",
                    "content": "- **放票规则**：提前 7 天 20:00 放票，每日限流 4 万人，周一闭馆。\n- **官方途径**：微信小程序。",
                },
                {
                    "spot_name": "故宫博物院",
                    "section_type": "避坑与实用贴士",
                    "content": "- **单向通行**：一律由午门进，神武门出。\n- **防骗提示**：严禁购买端门附近黄牛票。",
                }
            ],
            "retry_count": 0,
        }

        result = planner._validate_plan(state)
        self.assertIn("trip_plan", result)
        plan: TripPlan = result["trip_plan"]
        self.assertGreater(len(plan.knowledge_highlights), 0)
        # 验证故宫的 booking_tips 和 tips 已被知识库丰富补齐
        att = plan.days[0].attractions[0]
        self.assertTrue(bool(att.booking_tips))
        self.assertIn("提前 7 天 20:00 放票", att.booking_tips)
        self.assertTrue(bool(att.tips))


if __name__ == "__main__":
    unittest.main()
