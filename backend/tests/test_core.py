"""无需 API 密钥的模型与高德响应转换测试。"""

import json
import unittest
from unittest.mock import patch

from app.agents.trip_planner_agent import MultiAgentTripPlanner
from app.api.main import app as api_app
from app.models.schemas import TripRequest, TripPlan
from app.services.amap_service import AmapService
from fastapi.testclient import TestClient
from pydantic import ValidationError


class FakeMCP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def run(self, call):
        self.calls.append(call)
        return self.payload


def request(**overrides):
    data = {
        "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-02",
        "travel_days": 2, "transportation": "公共交通",
        "accommodation": "经济型酒店", "preferences": ["历史文化"],
    }
    data.update(overrides)
    return TripRequest(**data)


class TripModelTests(unittest.TestCase):
    def test_rejects_inconsistent_dates(self):
        with self.assertRaises(ValidationError):
            request(travel_days=3)

    def test_rejects_invalid_agent_output_instead_of_fabricating_plan(self):
        agent = MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)
        with self.assertRaises(ValueError):
            agent._parse_response("没有 JSON", request())


class AmapServiceTests(unittest.TestCase):
    def service(self, payload):
        mcp = FakeMCP(payload)
        return AmapService(mcp_tool=mcp), mcp

    def test_search_poi_parses_mcp_content(self):
        payload = {"content": [{"type": "text", "text": json.dumps({
            "status": "1", "pois": [{
                "id": "123", "name": "故宫", "type": "风景名胜",
                "address": "景山前街", "location": "116.397,39.916",
            }],
        })}]}
        service, mcp = self.service(payload)
        pois = service.search_poi("故宫", "北京")
        self.assertEqual(len(pois), 1)
        self.assertEqual(pois[0].name, "故宫")
        self.assertAlmostEqual(pois[0].location.latitude, 39.916)
        self.assertEqual(mcp.calls[0]["tool_name"], "maps_text_search")

    def test_weather_and_route(self):
        weather, _ = self.service(json.dumps({"forecasts": [{"casts": [{
            "date": "2026-10-01", "dayweather": "晴", "nightweather": "多云",
            "daytemp": "25", "nighttemp": "15", "daywind": "南",
            "daypower": "1-3",
        }]}]}))
        self.assertEqual(weather.get_weather("北京")[0].day_temp, 25)
        route, _ = self.service({"route": {"paths": [{
            "distance": "1200", "duration": "900",
            "steps": [{"instruction": "向东步行"}],
        }]}})
        self.assertEqual(route.plan_route("甲", "乙").distance, 1200)

    def test_api_error_is_not_reported_as_empty_success(self):
        service, _ = self.service({"status": "0", "info": "INVALID_USER_KEY"})
        with self.assertRaisesRegex(ValueError, "INVALID_USER_KEY"):
            service.search_poi("故宫", "北京")


class ApiTests(unittest.TestCase):
    def test_map_endpoint_serializes_parsed_poi(self):
        service = AmapService(mcp_tool=FakeMCP({"pois": [{
            "id": "1", "name": "故宫", "type": "景点",
            "address": "北京", "location": "116.397,39.916",
        }]}))
        with patch("app.api.main.validate_config"), patch(
            "app.api.routes.map.get_amap_service", return_value=service
        ), TestClient(api_app) as client:
            response = client.get("/api/map/poi", params={"keywords": "故宫", "city": "北京"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"][0]["name"], "故宫")

    def test_trip_endpoint_returns_agent_plan(self):
        class FakeAgent:
            def plan_trip(self, trip_request):
                return TripPlan(
                    city=trip_request.city,
                    start_date=trip_request.start_date,
                    end_date=trip_request.end_date,
                    days=[],
                    overall_suggestions="测试建议",
                )

        with patch("app.api.main.validate_config"), patch(
            "app.api.routes.trip.get_trip_planner_agent", return_value=FakeAgent()
        ), TestClient(api_app) as client:
            response = client.post("/api/trip/plan", json=request().model_dump())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertEqual(response.json()["data"]["city"], "北京")


if __name__ == "__main__":
    unittest.main()
