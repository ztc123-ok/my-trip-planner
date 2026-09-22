# -*- coding: utf-8 -*-
"""Phase 6: 结构化评估与可观测性单元测试 (Unit Tests for Evaluation & Observability)."""

import unittest
from fastapi.testclient import TestClient

from app.api.main import app
from app.models.schemas import (
    TripPlan,
    DayPlan,
    Attraction,
    Meal,
    Hotel,
    Budget,
    WeatherInfo,
    Location,
    PlanEvaluationRequest,
)
from app.services.eval_service import (
    TripPlanEvaluator,
    haversine_distance,
    evaluate_plan,
)
from app.services.observability_service import (
    get_observability_status,
    safe_traceable,
    record_evaluation_feedback,
)


class TestTripPlanEvaluation(unittest.TestCase):
    """测试结构化评估引擎的三大维度评测逻辑。"""

    def setUp(self):
        self.evaluator = TripPlanEvaluator()
        self.client = TestClient(app)

        # 构造标准高质量行程（北京 2 日游）
        self.valid_plan = TripPlan(
            city="北京",
            start_date="2026-06-01",
            end_date="2026-06-02",
            overall_suggestions="游玩愉快，已为您配备专属动线与放票攻略",
            knowledge_highlights=["【故宫预约】提前7天20:00微信抢票，周一闭馆"],
            weather_info=[
                WeatherInfo(
                    date="2026-06-01",
                    day_weather="晴",
                    night_weather="多云",
                    day_temp=28,
                    night_temp=18,
                    wind_direction="南风",
                    wind_power="1-3级",
                ),
                WeatherInfo(
                    date="2026-06-02",
                    day_weather="多云",
                    night_weather="晴",
                    day_temp=29,
                    night_temp=19,
                    wind_direction="北风",
                    wind_power="1-2级",
                ),
            ],
            days=[
                DayPlan(
                    date="2026-06-01",
                    day_index=0,
                    description="第1天：故宫与景山",
                    transportation="公共交通",
                    accommodation="舒适型酒店",
                    hotel=Hotel(
                        name="北京王府井希尔顿酒店",
                        address="东城区王府井东街8号",
                        location=Location(longitude=116.4116, latitude=39.9145),
                        price_range="600-800元",
                        rating="4.7",
                        distance="距离故宫约1.5公里",
                        type="高档型",
                        estimated_cost=650,
                    ),
                    attractions=[
                        Attraction(
                            name="故宫博物院",
                            address="东城区景山前街4号",
                            location=Location(longitude=116.397128, latitude=39.916527),
                            visit_duration=180,
                            description="世界五大宫之首",
                            ticket_price=60,
                            booking_tips="提前7天放票",
                            tips="午门进神武门出",
                        ),
                        Attraction(
                            name="景山公园",
                            address="西城区景山西街44号",
                            location=Location(longitude=116.3982, latitude=39.9248),
                            visit_duration=90,
                            description="俯瞰紫禁城全貌最佳点",
                            ticket_price=10,
                            booking_tips="现场刷码入园",
                            tips="傍晚登万春亭看日落",
                        ),
                    ],
                    meals=[
                        Meal(type="breakfast", name="老北京馄饨烧饼", estimated_cost=25),
                        Meal(type="lunch", name="四季民福烤鸭", estimated_cost=120),
                        Meal(type="dinner", name="东来顺涮羊肉", estimated_cost=150),
                    ],
                ),
                DayPlan(
                    date="2026-06-02",
                    day_index=1,
                    description="第2天：颐和园与圆明园",
                    transportation="公共交通",
                    accommodation="舒适型酒店",
                    hotel=Hotel(
                        name="北京王府井希尔顿酒店",
                        address="东城区王府井东街8号",
                        location=Location(longitude=116.4116, latitude=39.9145),
                        estimated_cost=650,
                    ),
                    attractions=[
                        Attraction(
                            name="颐和园",
                            address="海淀区新建宫门路19号",
                            location=Location(longitude=116.2731, latitude=39.9999),
                            visit_duration=180,
                            description="保存最完整的皇家园林",
                            ticket_price=30,
                            booking_tips="公众号提前实名预约",
                            tips="苏州街游船",
                        ),
                        Attraction(
                            name="圆明园遗址公园",
                            address="海淀区清华西路28号",
                            location=Location(longitude=116.2995, latitude=40.0076),
                            visit_duration=120,
                            description="万园之园遗址",
                            ticket_price=25,
                            booking_tips="刷身份证入园",
                            tips="西洋楼大水法必看",
                        ),
                    ],
                    meals=[
                        Meal(type="breakfast", name="酒店自助早点", estimated_cost=40),
                        Meal(type="lunch", name="海淀传统炸酱面", estimated_cost=45),
                        Meal(type="dinner", name="京味私房菜", estimated_cost=140),
                    ],
                ),
            ],
            budget=Budget(
                total_attractions=125,     # 60 + 10 + 30 + 25 = 125
                total_hotels=1300,          # 650 + 650 = 1300
                total_meals=520,            # 25 + 120 + 150 + 40 + 45 + 140 = 520
                total_transportation=100,
                total=2045,                 # 125 + 1300 + 520 + 100 = 2045
            ),
        )

    def test_haversine_distance_calculation(self):
        """测试 Haversine 大圆距离公式的精度与零坐标防御。"""
        # 故宫至景山：实际直线距离约 1 公里左右
        p1 = Location(longitude=116.397128, latitude=39.916527)
        p2 = Location(longitude=116.3982, latitude=39.9248)
        dist = haversine_distance(p1, p2)
        self.assertGreater(dist, 0.5)
        self.assertLess(dist, 2.0)

        # 零坐标防御
        p_zero = Location(longitude=0, latitude=0)
        self.assertEqual(haversine_distance(p1, p_zero), 0.0)

    def test_valid_plan_high_score(self):
        """测试标准优质行程能够获得卓越评分（>= 90分）且全部通过。"""
        report = self.evaluator.evaluate(self.valid_plan)
        self.assertGreaterEqual(report.overall_score, 90.0)
        self.assertIn("EXCELLENT", report.grade)
        self.assertTrue(report.passed)
        self.assertTrue(report.dimensions["completeness"].passed)
        self.assertTrue(report.dimensions["geography"].passed)
        self.assertTrue(report.dimensions["budget"].passed)
        self.assertTrue(report.metrics["budget_arithmetic_valid"])

    def test_completeness_penalties(self):
        """测试计划完整性扣分项：天数不符、缺少三餐、缺少酒店等。"""
        broken_plan = self.valid_plan.model_copy(deep=True)
        broken_plan.end_date = "2026-06-03"  # 预期3天，但实际只有 2 天
        broken_plan.days[0].meals = []  # 缺少早中晚三餐
        broken_plan.days[1].hotel = None  # 缺少酒店

        report = self.evaluator.evaluate(broken_plan)
        self.assertLess(report.dimensions["completeness"].score, 80.0)
        
        issue_messages = [i.message for i in report.issues]
        self.assertTrue(any("行程天数不匹配" in m for m in issue_messages))
        self.assertTrue(any("缺少 breakfast" in m for m in issue_messages))
        self.assertTrue(any("未提供推荐酒店" in m for m in issue_messages))

    def test_geography_large_span_warning(self):
        """测试地理合理性：同日景点距离过远（折返跑/跨城跨区）触发告警扣分。"""
        geo_broken = self.valid_plan.model_copy(deep=True)
        # 将第1天第二个景点设为八达岭长城（距故宫约 60 公里）
        geo_broken.days[0].attractions[1] = Attraction(
            name="八达岭长城",
            address="延庆区G6京藏高速58号出口",
            location=Location(longitude=116.0166, latitude=40.3599),
            visit_duration=240,
            description="万里长城险要关隘",
            ticket_price=40,
        )

        report = self.evaluator.evaluate(geo_broken)
        self.assertLessEqual(report.dimensions["geography"].score, 85.0)
        issue_messages = [i.message for i in report.issues]
        self.assertTrue(any("跨度过大" in m or "折返" in m for m in issue_messages))

    def test_budget_arithmetic_inconsistency(self):
        """测试预算严密性：明细与分项不一致，或四项之和不等于 total 触发严厉扣分。"""
        budget_broken = self.valid_plan.model_copy(deep=True)
        # 算术错误：故意篡改 total_attractions 和 total
        budget_broken.budget.total_attractions = 999
        budget_broken.budget.total = 5000  # 真实应为 125+1300+520+100=2045

        report = self.evaluator.evaluate(budget_broken)
        self.assertLess(report.dimensions["budget"].score, 60.0)
        self.assertFalse(report.dimensions["budget"].passed)
        self.assertFalse(report.metrics["budget_arithmetic_valid"])

        issue_messages = [i.message for i in report.issues]
        self.assertTrue(any("总预算计算错误" in m for m in issue_messages))
        self.assertTrue(any("门票明细合计" in m for m in issue_messages))

    def test_negative_budget_penalty(self):
        """测试出现负数预算时的致命扣分。"""
        neg_plan = self.valid_plan.model_copy(deep=True)
        neg_plan.budget.total_meals = -50

        report = self.evaluator.evaluate(neg_plan)
        self.assertLessEqual(report.dimensions["budget"].score, 70.0)
        issue_messages = [i.message for i in report.issues]
        self.assertTrue(any("负数金额" in m for m in issue_messages))

    def test_observability_safe_traceable_no_crash(self):
        """测试在未配置 LangSmith 密钥时，@safe_traceable 透明透传无报错。"""
        @safe_traceable(name="dummy_chain", run_type="chain")
        def add(a: int, b: int) -> int:
            return a + b

        self.assertEqual(add(10, 20), 30)

        # 验证 feedback 回传在无 Client 时的安全返回 False，不抛异常
        result = record_evaluation_feedback(self.evaluator.evaluate(self.valid_plan), run_id="test_run")
        self.assertIsInstance(result, bool)

    def test_observability_status_service(self):
        """测试系统可观测性状态获取。"""
        status = get_observability_status()
        self.assertIn("tracing_enabled", status)
        self.assertIn("project", status)
        self.assertIn("endpoint", status)

    def test_api_evaluate_endpoint(self):
        """测试 POST /api/trip/evaluate 接口。"""
        req_payload = {
            "trip_plan": self.valid_plan.model_dump(mode="json"),
            "thread_id": "test_thread_eval_01",
        }
        res = self.client.post("/api/trip/evaluate", json=req_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        report = data["data"]
        self.assertGreaterEqual(report["overall_score"], 90.0)
        self.assertIn("completeness", report["dimensions"])
        self.assertIn("geography", report["dimensions"])
        self.assertIn("budget", report["dimensions"])

    def test_api_observability_status_endpoint(self):
        """测试 GET /api/trip/observability/status 接口。"""
        res = self.client.get("/api/trip/observability/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("tracing_enabled", data["data"])


if __name__ == "__main__":
    unittest.main()
