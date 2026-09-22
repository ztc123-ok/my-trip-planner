# -*- coding: utf-8 -*-
"""Phase 6: 离线行程评估 Benchmark 评测脚本 (Offline Evaluation Benchmark Runner).

用于批量评测典型行程用例并输出多维评估分析报表。
"""

import sys
import os
from pathlib import Path

# 添加 backend 到 sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.models.schemas import (
    TripPlan,
    DayPlan,
    Attraction,
    Meal,
    Hotel,
    Budget,
    WeatherInfo,
    Location,
)
from app.services.eval_service import evaluate_plan


def get_benchmark_dataset():
    """构造基准测试集"""
    # Case 1: 完美行程（北京2日游）
    c1 = TripPlan(
        city="北京",
        start_date="2026-06-01",
        end_date="2026-06-02",
        overall_suggestions="游玩愉快",
        knowledge_highlights=["【故宫预约】提前7天20:00放票"],
        weather_info=[
            WeatherInfo(date="2026-06-01", day_weather="晴", night_weather="多云", day_temp=28, night_temp=18),
            WeatherInfo(date="2026-06-02", day_weather="多云", night_weather="晴", day_temp=29, night_temp=19),
        ],
        days=[
            DayPlan(
                date="2026-06-01",
                day_index=0,
                description="第1天：紫禁城与景山",
                transportation="公共交通",
                accommodation="舒适型酒店",
                hotel=Hotel(name="王府井希尔顿酒店", address="东城区王府井", location=Location(longitude=116.4116, latitude=39.9145), estimated_cost=600),
                attractions=[
                    Attraction(name="故宫博物院", address="景山前街4号", location=Location(longitude=116.3971, latitude=39.9165), visit_duration=180, description="世界五大宫之首", ticket_price=60, booking_tips="提前7天抢票", tips="由午门进"),
                    Attraction(name="景山公园", address="景山西街44号", location=Location(longitude=116.3982, latitude=39.9248), visit_duration=90, description="俯瞰紫禁城", ticket_price=10, booking_tips="现场刷码", tips="看日落"),
                ],
                meals=[
                    Meal(type="breakfast", name="老北京烧饼", estimated_cost=20),
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
                hotel=Hotel(name="王府井希尔顿酒店", address="东城区王府井", location=Location(longitude=116.4116, latitude=39.9145), estimated_cost=600),
                attractions=[
                    Attraction(name="颐和园", address="新建宫门路19号", location=Location(longitude=116.2731, latitude=39.9999), visit_duration=180, description="皇家园林", ticket_price=30, booking_tips="实名预约", tips="游船"),
                    Attraction(name="圆明园", address="清华西路28号", location=Location(longitude=116.2995, latitude=40.0076), visit_duration=120, description="万园之园", ticket_price=25, booking_tips="刷身份证", tips="大水法"),
                ],
                meals=[
                    Meal(type="breakfast", name="酒店早点", estimated_cost=30),
                    Meal(type="lunch", name="老北京炸酱面", estimated_cost=40),
                    Meal(type="dinner", name="京味私房菜", estimated_cost=140),
                ],
            ),
        ],
        budget=Budget(
            total_attractions=125,
            total_hotels=1200,
            total_meals=500,
            total_transportation=100,
            total=1925,
        ),
    )

    # Case 2: 动线远距离折返跑用例（延庆八达岭与市区混排）
    c2 = c1.model_copy(deep=True)
    c2.days[0].attractions[1] = Attraction(
        name="八达岭长城",
        address="延庆区",
        location=Location(longitude=116.0166, latitude=40.3599),
        visit_duration=240,
        description="万里长城著名关隘",
        ticket_price=40,
    )
    c2.budget.total_attractions = 155
    c2.budget.total = 1955

    # Case 3: 预算不一致算术错误用例
    c3 = c1.model_copy(deep=True)
    c3.budget.total_attractions = 888  # 与实际明细严重不符
    c3.budget.total = 9999              # 总和计算错误

    # Case 4: 缺少早晚餐与推荐酒店的不完整用例
    c4 = c1.model_copy(deep=True)
    c4.days[0].meals = [Meal(type="lunch", name="快餐", estimated_cost=30)]  # 缺少早晚两餐
    c4.days[1].hotel = None                                                  # 缺少酒店

    return [
        ("优质标准行程 (高质量基准)", c1),
        ("动线折返瑕疵行程 (跨度超长)", c2),
        ("预算算术矛盾行程 (校验漏洞)", c3),
        ("要素缺失不完整行程 (要素不齐)", c4),
    ]


def run_benchmark():
    print("=" * 80)
    print("🎯 开始执行旅行智能体结构化质量评估 Benchmark")
    print("=" * 80)

    dataset = get_benchmark_dataset()
    results = []

    for name, plan in dataset:
        report = evaluate_plan(plan)
        results.append((name, report))

    # 输出表格
    print("\n| 用例名称 | 综合得分 | 评级 | 完整性(35%) | 地理动线(35%) | 预算严密(30%) | 动线里程 | 算术合规 | 合格判定 |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name, rep in results:
        comp = rep.dimensions["completeness"].score
        geo = rep.dimensions["geography"].score
        bud = rep.dimensions["budget"].score
        km = rep.metrics.get("total_route_distance_km", 0.0)
        arith = "✅ 正常" if rep.metrics.get("budget_arithmetic_valid") else "❌ 错误"
        passed = "✅ 通过" if rep.passed else "❌ 未达标"
        print(f"| {name} | {rep.overall_score:.1f} | {rep.grade.split(' ')[0]} | {comp:.1f} | {geo:.1f} | {bud:.1f} | {km:.1f}km | {arith} | {passed} |")

    print("\n" + "=" * 80)
    print("📋 各用例典型扣分与优化建议诊断:")
    for name, rep in results:
        print(f"\n【{name}】综合得分: {rep.overall_score:.1f}")
        if rep.issues:
            print("  - 扣分原因明细:")
            for issue in rep.issues:
                prefix = "❌ 错误" if issue.severity == "error" else "⚠️ 警告"
                print(f"    {prefix}: [{issue.dimension}] {issue.message}")
        if rep.suggestions:
            print("  - 智能优化建议:")
            for sugg in rep.suggestions:
                print(f"    💡 {sugg}")

    print("\n" + "=" * 80)
    print("✅ Benchmark 批量评测完成！")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
