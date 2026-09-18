"""无需 API 密钥的模型与高德响应转换测试。"""

import json
import os
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.agents.trip_planner_agent import (
    MultiAgentTripPlanner, planner_llm_options, MAX_PLAN_RETRIES, _should_retry,
    calculate_distance_km, format_nearest_attraction_distance,
)
from app.api.main import app as api_app
from app.models.schemas import POIInfo, TripRequest, TripPlan, WeatherInfo, Location
from app.services.amap_service import AmapService, create_amap_tool
from app.services.ddgs_photo_service import DDGSPhotoService
from app.services.photo_service import (
    UnifiedPhotoService, get_photo_service, extract_parent_attraction,
)
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

    def test_validate_failure_retries_planner_up_to_twice(self):
        """校验前两次失败后第三次成功，planner 被调用 3 次。"""
        call_count = {"plan": 0, "validate": 0}
        plan_responses = []

        class FakeLLM:
            provider = "other"
            model = "test"
            timeout = 60
            def generate(self, system_prompt, user_prompt, **opts):
                return "已整理"

        valid_plan = json.dumps({
            "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-01",
            "days": [{
                "date": "2026-10-01", "day_index": 0, "description": "游览",
                "transportation": "公共交通", "accommodation": "经济型酒店",
                "attractions": [{"name": "故宫", "address": "北京",
                    "location": {"longitude": 116.397, "latitude": 39.916},
                    "visit_duration": 120, "description": "游览"}],
                "meals": [{"type": t, "name": t} for t in ("breakfast", "lunch", "dinner")],
            }],
            "weather_info": [], "overall_suggestions": "建议",
        }, ensure_ascii=False)

        original_generate_plan = MultiAgentTripPlanner._generate_plan
        original_validate_plan = MultiAgentTripPlanner._validate_plan

        def tracking_generate(self_agent, state):
            call_count["plan"] += 1
            # First two calls return invalid JSON, third returns valid
            if call_count["plan"] <= 2:
                return {"planner_response": "无效的 JSON 响应"}
            return {"planner_response": valid_plan}

        def tracking_validate(self_agent, state):
            call_count["validate"] += 1
            return original_validate_plan(self_agent, state)

        amap = unittest.mock.Mock()
        amap.search_poi.return_value = [
            POIInfo(id="1", name="故宫", type="景点", address="北京")
        ]
        amap.get_weather.side_effect = ValueError("UNKNOWN")

        with patch.object(MultiAgentTripPlanner, "_generate_plan", tracking_generate), \
             patch.object(MultiAgentTripPlanner, "_validate_plan", tracking_validate), \
             patch("app.services.weather_service.get_open_meteo_forecast", side_effect=ValueError):
            planner = MultiAgentTripPlanner(
                llm=FakeLLM(),
                amap_service=amap,
            )
            plan = planner.plan_trip(request(end_date="2026-10-01", travel_days=1))

        self.assertEqual(call_count["plan"], 3)
        self.assertEqual(call_count["validate"], 3)
        self.assertIsInstance(plan, TripPlan)
        self.assertEqual(plan.city, "北京")

    def test_validate_failure_exceeds_max_retries_raises(self):
        """校验始终失败，超过最大重试次数后抛出异常。"""
        class FakeLLM:
            provider = "other"
            model = "test"
            timeout = 60
            def generate(self, system_prompt, user_prompt, **opts):
                return "已整理"

        def always_invalid(_self, state):
            return {"planner_response": "这不是有效的 JSON"}

        amap = unittest.mock.Mock()
        amap.search_poi.return_value = [
            POIInfo(id="1", name="故宫", type="景点", address="北京")
        ]
        amap.get_weather.side_effect = ValueError("UNKNOWN")

        with patch.object(MultiAgentTripPlanner, "_generate_plan", always_invalid), \
             patch("app.services.weather_service.get_open_meteo_forecast", side_effect=ValueError):
            planner = MultiAgentTripPlanner(llm=FakeLLM(), amap_service=amap)
            with self.assertRaisesRegex(ValueError, f"{MAX_PLAN_RETRIES + 1} 次尝试"):
                planner.plan_trip(request(end_date="2026-10-01", travel_days=1))

    def test_retry_includes_error_feedback_in_planner_prompt(self):
        """重试时 planner 的 prompt 包含上次校验失败原因。"""
        prompts_received = []

        valid_plan = json.dumps({
            "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-01",
            "days": [{
                "date": "2026-10-01", "day_index": 0, "description": "游览",
                "transportation": "公共交通", "accommodation": "经济型酒店",
                "attractions": [{"name": "故宫", "address": "北京",
                    "location": {"longitude": 116.397, "latitude": 39.916},
                    "visit_duration": 120, "description": "游览"}],
                "meals": [{"type": t, "name": t} for t in ("breakfast", "lunch", "dinner")],
            }],
            "weather_info": [], "overall_suggestions": "建议",
        }, ensure_ascii=False)

        class TrackingLLM:
            provider = "other"
            model = "test"
            timeout = 60
            planner_calls = 0
            def generate(self, system_prompt, user_prompt, **opts):
                prompts_received.append(user_prompt)
                # Attraction/hotel summarization calls (run in parallel threads)
                # Use unique role identifiers to avoid matching planner prompt
                if "景点搜索专家" in system_prompt or "酒店推荐专家" in system_prompt:
                    return "已整理"
                # Planner calls (sequential, after fan-in)
                self.planner_calls += 1
                if self.planner_calls <= 1:
                    return "不是JSON"
                return valid_plan

        amap = unittest.mock.Mock()
        amap.search_poi.return_value = [
            POIInfo(id="1", name="故宫", type="景点", address="北京")
        ]
        amap.get_weather.side_effect = ValueError("UNKNOWN")

        with patch("app.services.weather_service.get_open_meteo_forecast", side_effect=ValueError):
            planner = MultiAgentTripPlanner(llm=TrackingLLM(), amap_service=amap)
            plan = planner.plan_trip(request(end_date="2026-10-01", travel_days=1))

        # The retry prompt should contain the error from the first failed validation
        planner_prompts = [p for p in prompts_received if "旅行计划" in p]
        self.assertGreaterEqual(len(planner_prompts), 2)
        self.assertIn("上次生成的计划未通过校验", planner_prompts[1])
        self.assertIsInstance(plan, TripPlan)

    def test_conditional_edge_routes_to_end_on_success(self):
        """校验通过时条件路由函数返回 END。"""
        from langgraph.graph import END
        self.assertEqual(_should_retry({"trip_plan": TripPlan(
            city="北京", start_date="2026-10-01", end_date="2026-10-01",
            days=[], overall_suggestions="测试",
        )}), END)
        # 校验失败且重试次数未超限时应返回 "planner"
        self.assertEqual(_should_retry({"retry_count": 1}), "planner")
        # 校验失败且重试次数已超限时应返回 END
        self.assertEqual(_should_retry({"retry_count": MAX_PLAN_RETRIES + 1}), END)

    def test_weather_skips_llm_when_unavailable(self):
        """天气不可用时不调用 LLM generate。"""
        llm = unittest.mock.Mock()
        llm.provider = "other"
        llm.model = "test"
        amap = unittest.mock.Mock()

        agent = MultiAgentTripPlanner.__new__(MultiAgentTripPlanner)
        agent.llm = llm
        agent.amap_service = amap

        # 直接 patch get_trip_forecast 抛异常，测试 except 分支跳过 LLM
        with patch("app.agents.trip_planner_agent.get_trip_forecast", side_effect=ValueError("测试错误")):
            result = agent._get_weather({"request": request(end_date="2026-10-01", travel_days=1)})

        self.assertEqual(result["weather_data"], [])
        self.assertIn("天气查询不可用", result["weather_response"])
        llm.generate.assert_not_called()

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
            "app.api.routes.poi.get_photo_service", return_value=service
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

    def test_amap_service_get_poi_photo_extracts_first_photo(self):
        mock_response = unittest.mock.Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "1",
            "pois": [{
                "id": "B000A83M61",
                "name": "故宫博物院",
                "photos": [
                    {"url": "https://store.is.autonavi.com/showpic/photo1.jpg"},
                    {"url": "https://store.is.autonavi.com/showpic/photo2.jpg"},
                ]
            }]
        }
        service = AmapService(mcp_tool=FakeMCP({}), api_key="fake_key")
        with patch("requests.get", return_value=mock_response) as mock_get:
            photo = service.get_poi_photo("故宫博物院", "北京")
            self.assertEqual(photo, "https://store.is.autonavi.com/showpic/photo1.jpg")
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            self.assertEqual(kwargs["params"]["keywords"], "故宫博物院")
            self.assertEqual(kwargs["params"]["extensions"], "all")

    def test_unified_photo_service_prefers_amap_poi_photo(self):
        fake_amap = unittest.mock.Mock()
        fake_amap.get_poi_photo.return_value = "https://store.is.autonavi.com/showpic/amap_photo.jpg"
        fake_ddgs = unittest.mock.Mock()

        svc = UnifiedPhotoService(amap_service=fake_amap, ddgs_service=fake_ddgs)
        result = svc.get_photo_url("西湖", "杭州")

        self.assertEqual(result, "https://store.is.autonavi.com/showpic/amap_photo.jpg")
        fake_amap.get_poi_photo.assert_called_once_with(name="西湖", city="杭州")
        fake_ddgs.get_photo_url.assert_not_called()

    def test_unified_photo_service_falls_back_to_bing_when_amap_has_no_photo(self):
        fake_amap = unittest.mock.Mock()
        fake_amap.get_poi_photo.return_value = None
        fake_ddgs = unittest.mock.Mock()
        fake_ddgs.get_photo_url.return_value = "https://bing.com/images/bing_photo.jpg"

        svc = UnifiedPhotoService(amap_service=fake_amap, ddgs_service=fake_ddgs)
        result = svc.get_photo_url("特色胡同", "北京")

        self.assertEqual(result, "https://bing.com/images/bing_photo.jpg")
        fake_amap.get_poi_photo.assert_called_once_with(name="特色胡同", city="北京")
        fake_ddgs.get_photo_url.assert_called_once_with(name="特色胡同", city="北京")

    def test_unified_photo_service_returns_none_when_both_fail(self):
        fake_amap = unittest.mock.Mock()
        fake_amap.get_poi_photo.side_effect = Exception("Amap timeout")
        fake_ddgs = unittest.mock.Mock()
        fake_ddgs.get_photo_url.return_value = None

        svc = UnifiedPhotoService(amap_service=fake_amap, ddgs_service=fake_ddgs)
        result = svc.get_photo_url("未知小众景点", "某地")

        self.assertIsNone(result)

    def test_extract_parent_attraction_rules(self):
        self.assertEqual(extract_parent_attraction("玉渊潭公园-留春园"), "玉渊潭公园")
        self.assertEqual(extract_parent_attraction("故宫博物院-堆秀山"), "故宫博物院")
        self.assertEqual(extract_parent_attraction("什刹海-前海"), "什刹海")
        self.assertEqual(extract_parent_attraction("北海公园(荷花湖)"), "北海公园")
        self.assertEqual(extract_parent_attraction("太庙-神柏"), "太庙")
        self.assertIsNone(extract_parent_attraction("白袍将军"))
        self.assertIsNone(extract_parent_attraction("西湖"))
        self.assertIsNone(extract_parent_attraction(""))

    def test_unified_photo_service_parent_fallback_to_amap(self):
        fake_amap = unittest.mock.Mock()
        # 原名查询无图，母体查询命中
        def amap_side_effect(name, city):
            if name == "玉渊潭公园-留春园":
                return None
            if name == "玉渊潭公园":
                return "https://store.is.autonavi.com/showpic/yuyuantan.jpg"
            return None
        fake_amap.get_poi_photo.side_effect = amap_side_effect

        fake_ddgs = unittest.mock.Mock()
        fake_ddgs.get_photo_url.return_value = None

        svc = UnifiedPhotoService(amap_service=fake_amap, ddgs_service=fake_ddgs)
        result = svc.get_photo_url("玉渊潭公园-留春园", "北京")

        self.assertEqual(result, "https://store.is.autonavi.com/showpic/yuyuantan.jpg")
        self.assertEqual(fake_amap.get_poi_photo.call_count, 2)
        fake_amap.get_poi_photo.assert_any_call(name="玉渊潭公园-留春园", city="北京")
        fake_amap.get_poi_photo.assert_any_call(name="玉渊潭公园", city="北京")

    def test_unified_photo_service_parent_fallback_to_bing(self):
        fake_amap = unittest.mock.Mock()
        fake_amap.get_poi_photo.return_value = None

        fake_ddgs = unittest.mock.Mock()
        # 原名查询无图，母体查询命中
        def ddgs_side_effect(name, city):
            if name == "西海湿地公园-景观平台":
                return None
            if name == "西海湿地公园":
                return "https://bing.com/images/xihai.jpg"
            return None
        fake_ddgs.get_photo_url.side_effect = ddgs_side_effect

        svc = UnifiedPhotoService(amap_service=fake_amap, ddgs_service=fake_ddgs)
        result = svc.get_photo_url("西海湿地公园-景观平台", "北京")

        self.assertEqual(result, "https://bing.com/images/xihai.jpg")
        self.assertEqual(fake_ddgs.get_photo_url.call_count, 2)
        fake_ddgs.get_photo_url.assert_any_call(name="西海湿地公园-景观平台", city="北京")
        fake_ddgs.get_photo_url.assert_any_call(name="西海湿地公园", city="北京")


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
            "app.api.routes.poi.get_photo_service", return_value=service
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


    def test_hitl_prepare_interrupts_before_planner_and_saves_candidates(self):
        """HITL 阶段一：在 planner 节点前挂起，并返回候选景点、酒店和天气。"""
        fake_attractions = [POIInfo(id="p1", name="天安门", type="风景名胜", address="北京")]
        fake_hotels = [POIInfo(id="h1", name="北京饭店", type="商务出行", address="王府井")]

        class FakeSearchLLM:
            def generate(self, system_prompt, user_prompt, **opts):
                return '模拟搜索整理'

        planner = MultiAgentTripPlanner(llm=FakeSearchLLM(), amap_service=AmapService(mcp_tool=FakeMCP({})))
        with patch.object(planner.amap_service, "search_poi", side_effect=[fake_attractions, fake_hotels]), \
             patch("app.agents.trip_planner_agent.get_trip_forecast", return_value=([], "")):
            result = planner.prepare_trip_plan(request(city="北京"))

        self.assertTrue(result["thread_id"].startswith("trip_"))
        self.assertEqual(result["city"], "北京")
        self.assertEqual(len(result["candidate_attractions"]), 1)
        self.assertEqual(result["candidate_attractions"][0].name, "天安门")
        self.assertEqual(len(result["candidate_hotels"]), 1)
        self.assertEqual(result["candidate_hotels"][0].name, "北京饭店")

        # 检查图确实在 planner 前挂起
        state = planner.graph_hitl.get_state({"configurable": {"thread_id": result["thread_id"]}})
        self.assertEqual(state.next, ("planner",))

    def test_hitl_resume_updates_user_choices_and_completes_plan(self):
        """HITL 阶段二：接收用户确认的景点和建议，在 planner query 中生效并生成最终计划。"""
        fake_attractions = [POIInfo(id="p1", name="天安门", type="风景名胜", address="北京")]
        fake_hotels = [POIInfo(id="h1", name="北京饭店", type="商务出行", address="王府井")]

        captured_queries = []
        valid_plan = json.dumps({
            "city": "北京", "start_date": "2026-10-01", "end_date": "2026-10-01",
            "days": [{
                "date": "2026-10-01", "day_index": 0, "description": "游览",
                "transportation": "公共交通", "accommodation": "经济型酒店",
                "hotel": {"name": "北京饭店", "address": "王府井", "location": {"longitude": 116.4, "latitude": 39.9}, "price_range": "500", "rating": "4.8", "distance": "1km", "type": "高档", "estimated_cost": 600},
                "attractions": [{"name": "天安门", "address": "北京", "location": {"longitude": 116.4, "latitude": 39.9}, "visit_duration": 60, "description": "广场", "category": "景点", "ticket_price": 0}],
                "meals": [
                    {"type": "breakfast", "name": "早点", "description": "豆浆油条", "estimated_cost": 20},
                    {"type": "lunch", "name": "炸酱面", "description": "老北京炸酱面", "estimated_cost": 40},
                    {"type": "dinner", "name": "烤鸭", "description": "全聚德烤鸭", "estimated_cost": 150}
                ]
            }],
            "weather_info": [],
            "overall_suggestions": "祝旅途愉快",
            "budget": {"total_attractions": 0, "total_hotels": 600, "total_meals": 210, "total_transportation": 50, "total": 860}
        })

        class FakeLLM:
            provider = "other"
            model = "test"
            timeout = 60
            def generate(self, system_prompt, user_prompt, **opts):
                captured_queries.append(user_prompt)
                return valid_plan

        planner = MultiAgentTripPlanner(llm=FakeLLM(), amap_service=AmapService(mcp_tool=FakeMCP({})))
        with patch.object(planner.amap_service, "search_poi", side_effect=[fake_attractions, fake_hotels]), \
             patch("app.agents.trip_planner_agent.get_trip_forecast", return_value=([], "")):
            prep = planner.prepare_trip_plan(request(city="北京", travel_days=1, end_date="2026-10-01"))

        # 阶段二恢复执行
        thread_id = prep["thread_id"]
        plan = planner.resume_trip_plan(
            thread_id=thread_id,
            selected_attractions=["天安门"],
            selected_hotel="北京饭店",
            user_feedback="希望早上去看升旗",
        )

        self.assertEqual(plan.city, "北京")
        self.assertEqual(len(captured_queries), 3)
        planner_query = captured_queries[-1]
        self.assertIn("天安门", planner_query)
        self.assertIn("北京饭店", planner_query)
        self.assertIn("希望早上去看升旗", planner_query)


    def test_hitl_prepare_and_confirm_endpoints(self):
        """测试 /api/trip/plan/prepare 和 /api/trip/plan/confirm 端点"""
        class FakeHITLAgent:
            def prepare_trip_plan(self, req):
                return {
                    "thread_id": "test_thread_123",
                    "city": req.city,
                    "travel_days": req.travel_days,
                    "candidate_attractions": [{"id": "1", "name": "故宫", "type": "景点", "address": "北京"}],
                    "candidate_hotels": [{"id": "2", "name": "北京饭店", "type": "酒店", "address": "北京"}],
                    "weather_info": [],
                }

            def resume_trip_plan(self, thread_id, selected_attractions=None, selected_hotel=None, user_feedback=None):
                return TripPlan(
                    city="北京",
                    start_date="2026-10-01",
                    end_date="2026-10-02",
                    days=[],
                    overall_suggestions=f"已选景点: {selected_attractions}, 反馈: {user_feedback}",
                )

        with patch("app.api.main.validate_config"), patch(
            "app.api.routes.trip.get_trip_planner_agent", return_value=FakeHITLAgent()
        ), TestClient(api_app) as client:
            # 1. prepare
            res1 = client.post("/api/trip/plan/prepare", json=request().model_dump())
            self.assertEqual(res1.status_code, 200)
            data1 = res1.json()["data"]
            self.assertEqual(data1["thread_id"], "test_thread_123")
            self.assertEqual(data1["candidate_attractions"][0]["name"], "故宫")

            # 2. confirm
            res2 = client.post("/api/trip/plan/confirm", json={
                "thread_id": "test_thread_123",
                "selected_attractions": ["故宫"],
                "selected_hotel": "北京饭店",
                "user_feedback": "优先上午游览故宫",
            })
            self.assertEqual(res2.status_code, 200)
            self.assertTrue(res2.json()["success"])
            self.assertIn("故宫", res2.json()["data"]["overall_suggestions"])


    def test_hotel_meta_inference_and_candidate_enrichment(self):
        """测试候选酒店决策元数据推断与丰富"""
        p1, r1, t1 = MultiAgentTripPlanner._infer_hotel_meta("北京北平国际青年旅舍", "经济型酒店")
        self.assertEqual(t1, "青旅民宿")
        self.assertIn("¥90", p1)

        p2, r2, t2 = MultiAgentTripPlanner._infer_hotel_meta("北京希尔顿酒店", "高档酒店")
        self.assertEqual(t2, "豪华高档")
        self.assertIn("¥800", p2)

        p3, r3, t3 = MultiAgentTripPlanner._infer_hotel_meta("如家快捷酒店(王府井店)", "经济型酒店")
        self.assertEqual(t3, "经济快捷")
        self.assertIn("¥180", p3)

        p4, r4, t4 = MultiAgentTripPlanner._infer_hotel_meta("普通商旅宾馆", "高档/豪华型酒店")
        self.assertEqual(t4, "高档优选")
        self.assertIn("¥800", p4)

    def test_nearest_attraction_distance_calculation(self):
        """测试酒店与候选景点的最近距离计算与标签生成"""
        loc_tiananmen = Location(longitude=116.397, latitude=39.908)
        loc_gugong = Location(longitude=116.397, latitude=39.918)
        
        # 验证距离计算合理性
        dist = calculate_distance_km(loc_tiananmen, loc_gugong)
        self.assertTrue(1.0 <= dist <= 1.3)

        attractions = [
            POIInfo(id="1", name="天安门广场", type="景点", address="北京", location=loc_tiananmen),
            POIInfo(id="2", name="故宫博物院", type="景点", address="北京", location=loc_gugong),
        ]

        # 酒店距离天安门极近 (约 200m)
        hotel_near_tiananmen = Location(longitude=116.397, latitude=39.906)
        label1 = format_nearest_attraction_distance(hotel_near_tiananmen, attractions)
        self.assertIn("近天安门", label1)
        self.assertIn("m)", label1)

        # 酒店离天安门约 2km
        hotel_far = Location(longitude=116.397, latitude=39.890)
        label2 = format_nearest_attraction_distance(hotel_far, attractions)
        self.assertIn("距天安门", label2)
        self.assertIn("km", label2)

        # 长景点名称保留完整语义，不再出现 '..' 截断
        attractions_long = [
            POIInfo(id="3", name="中国国家博物馆", type="景点", address="北京", location=loc_tiananmen),
        ]
        label3 = format_nearest_attraction_distance(hotel_far, attractions_long)
        self.assertEqual(label3, "距中国国家博物馆 2.0km")
        self.assertNotIn("..", label3)

        # 缺少坐标兜底
        self.assertIsNone(format_nearest_attraction_distance(None, attractions))
        self.assertIsNone(format_nearest_attraction_distance(hotel_near_tiananmen, []))


if __name__ == "__main__":
    unittest.main()
