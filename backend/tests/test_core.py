"""无需 API 密钥的模型与高德响应转换测试。"""

import json
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.trip_planner_agent import MultiAgentTripPlanner, planner_llm_options
from app.api.main import app as api_app
from app.models.schemas import POIInfo, TripRequest, TripPlan, WeatherInfo
from app.services.amap_service import AmapService, create_amap_tool
from app.services.ddgs_photo_service import DDGSPhotoService
from app.services.weather_service import (
    get_open_meteo_forecast, get_trip_forecast,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError


class FakeMCP:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.available_tools = []

    def call_tool(self, name, arguments):
        self.calls.append({"tool_name": name, "arguments": arguments})
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
    def test_langgraph_runs_independent_queries_in_parallel_before_planning(self):
        started = threading.Barrier(3)
        finished = set()
        finish_lock = threading.Lock()
        test_case = self

        def query(field, value):
            def run(_agent, state):
                test_case.assertEqual(state["request"].city, "北京")
                started.wait(timeout=10)
                with finish_lock:
                    finished.add(field)
                return {field: value}
            return run

        def plan(_agent, state):
            test_case.assertEqual(finished, {"attraction_response", "weather_data", "hotel_response"})
            test_case.assertEqual(state["attraction_response"], "景点")
            test_case.assertEqual(state["weather_data"], [])
            test_case.assertEqual(state["hotel_response"], "酒店")
            return {"planner_response": "已汇总"}

        def validate(_agent, state):
            test_case.assertEqual(state["planner_response"], "已汇总")
            return {"trip_plan": "已校验"}

        with patch.object(MultiAgentTripPlanner, "_search_attractions", query("attraction_response", "景点")), \
             patch.object(MultiAgentTripPlanner, "_get_weather", query("weather_data", [])), \
             patch.object(MultiAgentTripPlanner, "_search_hotels", query("hotel_response", "酒店")), \
             patch.object(MultiAgentTripPlanner, "_generate_plan", plan), \
             patch.object(MultiAgentTripPlanner, "_validate_plan", validate):
            planner = MultiAgentTripPlanner(llm=object(), amap_service=object())
            result = planner.plan_trip(request())

        self.assertEqual(result, "已校验")

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

    def test_langgraph_preserves_verified_weather_and_plan_schema(self):
        class FakeLLM:
            provider = "qwen"
            model = "qwen3.8-flash"
            timeout = 60

            def __init__(self, response):
                self.response = response
                self.calls = []

            def generate(self, system_prompt, user_prompt, **options):
                self.calls.append((system_prompt, user_prompt, options))
                return self.response if len(self.calls) == 3 else "已根据地图结果整理"

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
            "weather_info": [{"date": "2026-10-01", "day_weather": "晴"}],
            "overall_suggestions": "建议",
        }
        llm = FakeLLM(json.dumps(plan_data, ensure_ascii=False))
        amap = unittest.mock.Mock()
        amap.search_poi.side_effect = lambda keywords, city: (
            [POIInfo(id="2", name="北京酒店", type="酒店", address="北京")]
            if keywords == "酒店" else
            [POIInfo(id="1", name="故宫", type="景点", address="北京")]
        )
        amap.get_weather.side_effect = ValueError("UNKNOWN_ERROR")
        planner = MultiAgentTripPlanner(llm=llm, amap_service=amap)
        with patch("app.services.weather_service.get_open_meteo_forecast", side_effect=ValueError("城市查询失败")):
            plan = planner.plan_trip(trip_request)
        self.assertEqual(plan.weather_info, [])
        self.assertIn("天气预报", plan.overall_suggestions)
        self.assertCountEqual([call.args[0] for call in amap.search_poi.call_args_list], ["历史文化", "酒店"])
        self.assertEqual(len(llm.calls), 3)
        self.assertEqual(llm.calls[-1][2]["extra_body"], {"enable_thinking": False})
        self.assertIn("planner", planner.graph.get_graph().nodes)


class AmapServiceTests(unittest.TestCase):
    def service(self, payload):
        mcp = FakeMCP(payload)
        return AmapService(mcp_tool=mcp), mcp

    def test_discovery_uses_backend_python(self):
        tool = FakeMCP(None)
        tool.available_tools = ["maps_text_search", "maps_weather"]
        with patch.dict(os.environ, {
            "UV_CACHE_DIR": "", "UV_TOOL_DIR": "", "UV_TOOL_BIN_DIR": "",
        }), patch("app.services.amap_service.MCPToolClient", return_value=tool) as factory:
            self.assertIs(create_amap_tool("test-key"), tool)
        command = factory.call_args.kwargs["server_command"]
        self.assertEqual(command[1], "--offline")
        self.assertEqual(command[3], sys.executable)
        self.assertEqual(command[-1], "amap-mcp-server==0.1.11")
        self.assertTrue(Path(command[0]).is_file())
        self.assertTrue(factory.call_args.kwargs["env"]["UV_CACHE_DIR"].endswith(".uv-cache"))

    def test_empty_discovery_fails_before_agent_runs(self):
        tool = FakeMCP(None)
        tool.available_tools = []
        with patch("app.services.amap_service.MCPToolClient", return_value=tool):
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
    def test_all_cities_use_same_fallback_when_amap_fails(self):
        amap = unittest.mock.Mock()
        amap.get_weather.side_effect = ValueError("UNKNOWN_ERROR")
        weather = [WeatherInfo(date="2026-09-20", source="Open-Meteo")]
        for city in ("香港", "杭州"):
            with self.subTest(city=city), patch(
                "app.services.weather_service.get_open_meteo_forecast", return_value=weather
            ) as fallback:
                result, source = get_trip_forecast(
                    amap, city, "2026-09-20", "2026-09-24"
                )
                self.assertEqual(result, weather)
                self.assertEqual(source, "Open-Meteo")
                fallback.assert_called_once_with(city)

    def test_administrative_suffix_uses_generic_geocoding(self):
        location = unittest.mock.Mock()
        location.json.return_value = {"results": [{
            "name": "香港", "population": 7396076,
            "latitude": 22.2783, "longitude": 114.1747,
            "timezone": "Asia/Hong_Kong",
        }]}
        forecast = unittest.mock.Mock()
        forecast.json.return_value = {"daily": {
            "time": ["2026-09-20"],
            "temperature_2m_max": [29.4],
            "temperature_2m_min": [25.2],
            "weather_code": [61],
        }}
        for city, search_name in (("香港特别行政区", "香港"), ("Hong Kong", "Hong Kong")):
            with self.subTest(city=city), patch(
                "app.services.weather_service.requests.get", side_effect=[location, forecast]
            ) as get:
                weather = get_open_meteo_forecast(city)
                self.assertEqual(weather[0].source, "Open-Meteo")
                self.assertEqual(weather[0].day_weather, "小雨")
                self.assertEqual(get.call_args_list[0].kwargs["params"]["name"], search_name)
                self.assertEqual(get.call_args_list[1].kwargs["params"]["latitude"], 22.2783)

    def test_short_amap_forecast_is_completed_for_trip_dates(self):
        amap = unittest.mock.Mock()
        amap.get_weather.return_value = [
            WeatherInfo(date=f"2026-09-{day:02d}", source="高德地图", day_temp=30)
            for day in range(17, 21)
        ]
        supplement = [
            WeatherInfo(date=f"2026-09-{day:02d}", source="Open-Meteo", day_temp=25)
            for day in range(20, 25)
        ]
        with patch("app.services.weather_service.get_open_meteo_forecast", return_value=supplement) as fallback:
            result, source = get_trip_forecast(amap, "杭州", "2026-09-20", "2026-09-24")
        self.assertEqual([item.date for item in result], [f"2026-09-{day:02d}" for day in range(20, 25)])
        self.assertEqual(result[0].source, "高德地图")
        self.assertTrue(all(item.source == "Open-Meteo" for item in result[1:]))
        self.assertEqual(source, "高德地图 + Open-Meteo")
        fallback.assert_called_once_with("杭州")

    def test_open_meteo_resolves_city_before_forecast(self):
        location = unittest.mock.Mock()
        location.json.return_value = {"results": [{
            "name": "杭州", "population": 9236032,
            "latitude": 30.29365, "longitude": 120.16142,
            "timezone": "Asia/Shanghai",
        }]}
        forecast = unittest.mock.Mock()
        forecast.json.return_value = {"daily": {
            "time": ["2026-09-24"],
            "temperature_2m_max": [32.4],
            "temperature_2m_min": [24.1],
            "weather_code": [61],
        }}
        with patch("app.services.weather_service.requests.get", side_effect=[location, forecast]) as get:
            result = get_open_meteo_forecast("杭州市")
        self.assertEqual(result[0].date, "2026-09-24")
        self.assertEqual(result[0].source, "Open-Meteo")
        self.assertEqual(get.call_args_list[0].kwargs["params"]["name"], "杭州")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["forecast_days"], 16)


class DDGSPhotoServiceTests(unittest.TestCase):
    def test_discovery_uses_cached_mcp_package(self):
        tool = FakeMCP(None)
        tool.available_tools = ["search_images"]
        with patch("app.services.ddgs_photo_service.MCPToolClient", return_value=tool) as factory:
            DDGSPhotoService()
        command = factory.call_args.kwargs["server_command"]
        self.assertEqual(command[1], "--offline")
        self.assertEqual(command[3], sys.executable)
        self.assertIn("ddgs[mcp]==9.16.0", command)

    def test_searches_bing_images_and_reuses_successful_url(self):
        tool = FakeMCP("工具 'search_images' 执行结果:\n" + json.dumps([
            {"title": "网页", "url": "https://example.com/page"},
            {"title": "西湖实景", "image": "https://example.com/blocked.jpg",
             "thumbnail": "https://example.com/west-lake.jpg"},
        ], ensure_ascii=False))
        tool.available_tools = ["search_images"]
        service = DDGSPhotoService(mcp_tool=tool)

        self.assertEqual(
            service.get_photo_url("西湖", "杭州"), "https://example.com/west-lake.jpg"
        )
        self.assertEqual(
            service.get_photo_url("西湖", "杭州"), "https://example.com/west-lake.jpg"
        )
        self.assertEqual(len(tool.calls), 1)
        self.assertEqual(tool.calls[0]["tool_name"], "search_images")
        self.assertEqual(tool.calls[0]["arguments"]["backend"], "bing")
        self.assertIn("杭州 西湖", tool.calls[0]["arguments"]["query"])

    def test_mcp_error_returns_no_image(self):
        tool = FakeMCP("异步操作失败: Error executing tool search_images")
        tool.available_tools = ["search_images"]
        self.assertIsNone(DDGSPhotoService(mcp_tool=tool).get_photo_url("西湖"))

    def test_photo_endpoint_returns_empty_result_when_search_is_unavailable(self):
        service = unittest.mock.Mock()
        service.get_photo_url.return_value = None
        with patch("app.api.main.validate_config"), patch(
            "app.api.routes.poi.get_ddgs_photo_service", return_value=service
        ), TestClient(api_app) as client:
            response = client.get("/api/poi/photo", params={"name": "西湖", "city": "杭州"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["data"]["photo_url"])

    def test_parses_mcp_list_repr_and_skips_unsafe_image_url(self):
        tool = FakeMCP(
            "工具 'search_images' 执行结果:\n"
            "[{'image': 'javascript:alert(1)'}, "
            "{'thumbnail': 'https://example.com/west-lake-thumb.jpg'}]"
        )
        tool.available_tools = ["search_images"]
        self.assertEqual(
            DDGSPhotoService(mcp_tool=tool).get_photo_url("西湖"),
            "https://example.com/west-lake-thumb.jpg",
        )


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

    def test_photo_endpoint_returns_ddgs_image_url(self):
        service = unittest.mock.Mock()
        service.get_photo_url.return_value = "https://example.com/west-lake.jpg"
        with patch("app.api.main.validate_config"), patch(
            "app.api.routes.poi.get_ddgs_photo_service", return_value=service
        ), TestClient(api_app) as client:
            response = client.get("/api/poi/photo", params={"name": "西湖", "city": "杭州"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["photo_url"], "https://example.com/west-lake.jpg")
        service.get_photo_url.assert_called_once_with("西湖", "杭州")

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
