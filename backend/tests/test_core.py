"""无需 API 密钥的模型与高德响应转换测试。"""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import requests

from app.agents.trip_planner_agent import MultiAgentTripPlanner, planner_llm_options
from app.api.main import app as api_app
from app.models.schemas import TripRequest, TripPlan
from app.services.amap_service import AmapService, create_amap_tool
from app.services.weather_service import (
    get_hong_kong_forecast, get_open_meteo_hong_kong_forecast, get_trip_forecast,
)
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
    def test_qwen_planner_disables_default_thinking(self):
        qwen = unittest.mock.Mock(provider="qwen", model="qwen3.8-flash", timeout=60)
        self.assertEqual(planner_llm_options(qwen), {
            "extra_body": {"enable_thinking": False}, "timeout": 90,
        })
        other = unittest.mock.Mock(provider="openai", model="other", timeout=60)
        self.assertEqual(planner_llm_options(other), {})

    def test_rejects_inconsistent_dates(self):
        with self.assertRaises(ValidationError):
            request(travel_days=3)

    def test_rejects_invalid_agent_output_instead_of_fabricating_plan(self):
        agent = MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)
        with self.assertRaises(ValueError):
            agent._parse_response("没有 JSON", request())

    def test_unavailable_weather_is_not_invented(self):
        class FakeAgent:
            def __init__(self, response):
                self.response = response
                self.calls = 0

            def run(self, _query, **_kwargs):
                self.calls += 1
                return self.response

        trip_request = request(end_date="2026-10-01", travel_days=1)
        plan_data = {
            "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-01",
            "days": [{
                "date": "2026-10-01", "day_index": 0, "description": "行程",
                "transportation": "公共交通", "accommodation": "经济型酒店",
                "attractions": [{
                    "name": "故宫", "address": "北京",
                    "location": {"longitude": 116.397, "latitude": 39.916},
                    "visit_duration": 120, "description": "游览",
                }],
                "meals": [
                    {"type": kind, "name": kind}
                    for kind in ("breakfast", "lunch", "dinner")
                ],
            }],
            "weather_info": [{
                "date": "2026-10-01", "day_weather": "晴",
            }],
            "overall_suggestions": "建议",
        }
        agent = MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)
        agent.amap_tool = object()
        agent.attraction_agent = FakeAgent("景点")
        agent.weather_agent = FakeAgent("天气")
        agent.hotel_agent = FakeAgent("酒店")
        agent.planner_agent = FakeAgent(json.dumps(plan_data, ensure_ascii=False))
        with patch("app.agents.trip_planner_agent.AmapService") as amap:
            amap.return_value.get_weather.side_effect = ValueError("UNKNOWN_ERROR")
            plan = agent.plan_trip(trip_request)
        self.assertEqual(plan.weather_info, [])
        self.assertEqual(agent.weather_agent.calls, 0)
        self.assertIn("天气预报", plan.overall_suggestions)


class AmapServiceTests(unittest.TestCase):
    def service(self, payload):
        mcp = FakeMCP(payload)
        return AmapService(mcp_tool=mcp), mcp

    def test_discovery_uses_backend_python(self):
        tool = FakeMCP(None)
        tool._available_tools = [
            {"name": "maps_text_search"}, {"name": "maps_weather"}
        ]
        with patch.dict(os.environ, {
            "UV_CACHE_DIR": "", "UV_TOOL_DIR": "", "UV_TOOL_BIN_DIR": "",
        }), patch("app.services.amap_service.MCPTool", return_value=tool) as factory:
            self.assertIs(create_amap_tool("test-key"), tool)
        self.assertEqual(factory.call_args.kwargs["server_command"][2], sys.executable)
        self.assertTrue(Path(factory.call_args.kwargs["server_command"][0]).is_file())
        self.assertTrue(factory.call_args.kwargs["env"]["UV_CACHE_DIR"].endswith(".uv-cache"))
        self.assertTrue(tool.expandable)

    def test_empty_discovery_fails_before_agent_runs(self):
        tool = FakeMCP(None)
        tool._available_tools = []
        with patch("app.services.amap_service.MCPTool", return_value=tool):
            with self.assertRaisesRegex(RuntimeError, "工具发现失败"):
                create_amap_tool("test-key")

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

    def test_actual_mcp_response_shapes(self):
        search, _ = self.service({"pois": [{
            "id": "B000A8UIN8", "name": "故宫博物院",
            "address": "景山前街4号", "typecode": "110201",
        }]})
        pois = search.search_poi("故宫", "北京")
        self.assertEqual(len(pois), 1)
        self.assertIsNone(pois[0].location)
        self.assertEqual(pois[0].type, "110201")

        weather, _ = self.service({"forecasts": [{
            "date": "2026-09-16", "dayweather": "晴", "nightweather": "多云",
            "daytemp": "30", "nighttemp": "17", "daywind": "南",
            "daypower": "1-3",
        }]})
        self.assertEqual(weather.get_weather("北京")[0].day_temp, 30)

    def test_api_error_is_not_reported_as_empty_success(self):
        service, _ = self.service({"status": "0", "info": "INVALID_USER_KEY"})
        with self.assertRaisesRegex(ValueError, "INVALID_USER_KEY"):
            service.search_poi("故宫", "北京")
        service, _ = self.service({"error": "Get weather failed: UNKNOWN_ERROR"})
        with self.assertRaisesRegex(ValueError, "UNKNOWN_ERROR"):
            service.get_weather("香港")


class WeatherServiceTests(unittest.TestCase):
    def test_hong_kong_forecast_uses_official_daily_values(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"weatherForecast": [{
            "forecastDate": "20260920", "forecastWeather": "多云有雨",
            "forecastMaxtemp": {"value": 30},
            "forecastMintemp": {"value": 25},
            "forecastWind": "东风4级",
        }]}
        with patch("app.services.weather_service.requests.get", return_value=response) as get:
            weather = get_hong_kong_forecast()
        self.assertEqual(weather[0].date, "2026-09-20")
        self.assertEqual(weather[0].day_temp, 30)
        self.assertEqual(weather[0].night_temp, 25)
        self.assertEqual(get.call_args.kwargs["params"]["dataType"], "fnd")

    def test_hong_kong_uses_official_fallback_when_amap_fails(self):
        amap = unittest.mock.Mock()
        amap.get_weather.side_effect = ValueError("UNKNOWN_ERROR")
        weather = [unittest.mock.Mock(date="2026-09-20")]
        with patch("app.services.weather_service.get_hong_kong_forecast", return_value=weather):
            result, source = get_trip_forecast(
                amap, "香港", "2026-09-20", "2026-09-24"
            )
        self.assertEqual(result, weather)
        self.assertEqual(source, "香港天文台")

    def test_hong_kong_forecast_retries_transient_timeout(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"weatherForecast": [{
            "forecastDate": "20260920", "forecastWeather": "多云",
            "forecastMaxtemp": {"value": 29},
            "forecastMintemp": {"value": 24},
        }]}
        with patch("app.services.weather_service.requests.get", side_effect=[
            requests.ReadTimeout("temporary"), response,
        ]) as get:
            self.assertEqual(len(get_hong_kong_forecast()), 1)
        self.assertEqual(get.call_count, 2)

    def test_open_meteo_fallback_after_hko_failure(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"daily": {
            "time": ["2026-09-20"],
            "temperature_2m_max": [29.4],
            "temperature_2m_min": [25.2],
            "weather_code": [61],
        }}
        with patch("app.services.weather_service.requests.get", return_value=response):
            weather = get_open_meteo_hong_kong_forecast()
        self.assertEqual(weather[0].day_weather, "小雨")
        self.assertEqual(weather[0].day_temp, 29)

        amap = unittest.mock.Mock()
        amap.get_weather.side_effect = ValueError("UNKNOWN_ERROR")
        with patch("app.services.weather_service.get_hong_kong_forecast", side_effect=requests.ReadTimeout()), \
                patch("app.services.weather_service.get_open_meteo_hong_kong_forecast", return_value=weather):
            result, source = get_trip_forecast(
                amap, "香港", "2026-09-20", "2026-09-24"
            )
        self.assertEqual(result, weather)
        self.assertEqual(source, "Open-Meteo")


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
