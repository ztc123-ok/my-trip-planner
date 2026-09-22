# -*- coding: utf-8 -*-
"""旅行规划结构化评估引擎 (Structured Evaluation Engine).

实现三维度严密量化评估:
1. 计划完整性 (Completeness): 天数对齐、景点饱和度、早中晚三餐完备度、酒店与知识库贴士覆盖;
2. 地理合理性 (Geographical Rationality): Haversine 空间大圆距离、同日折返跑跨度告警、酒店就近度、动线里程;
3. 预算严密性 (Budget Consistency): 门票/餐饮/住宿明细与各分项预算的一致性、总预算四项数学求和绝对一致性。
"""

import math
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional

from ..models.schemas import (
    TripPlan,
    DayPlan,
    Location,
    EvaluationReport,
    DimensionScore,
    EvaluationIssue,
)
from .observability_service import safe_traceable


def haversine_distance(loc1: Location | dict, loc2: Location | dict) -> float:
    """计算两经纬度坐标之间的大圆球面物理距离（公里 km）。"""
    if isinstance(loc1, Location):
        lon1, lat1 = loc1.longitude, loc1.latitude
    else:
        lon1, lat1 = float(loc1.get("longitude", 0)), float(loc1.get("latitude", 0))

    if isinstance(loc2, Location):
        lon2, lat2 = loc2.longitude, loc2.latitude
    else:
        lon2, lat2 = float(loc2.get("longitude", 0)), float(loc2.get("latitude", 0))

    # 异常或零坐标防御
    if (lon1 == 0 and lat1 == 0) or (lon2 == 0 and lat2 == 0):
        return 0.0

    r = 6371.0  # 地球半径（公里）
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2.0) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2.0) ** 2
    )
    c = 2.0 * math.asin(math.sqrt(max(0.0, min(1.0, a))))
    return r * c


class TripPlanEvaluator:
    """旅行规划综合质量评估器。"""

    WEIGHT_COMPLETENESS = 0.35
    WEIGHT_GEOGRAPHY = 0.35
    WEIGHT_BUDGET = 0.30

    @safe_traceable(name="TripPlanEvaluator.evaluate", run_type="evaluator")
    def evaluate(self, plan: TripPlan) -> EvaluationReport:
        """对旅行规划执行全方位多维度评估并返回结构化报告。"""
        issues: List[EvaluationIssue] = []
        suggestions: List[str] = []

        # 1. 评估计划完整性
        comp_score, comp_details, comp_issues, comp_suggs = self._eval_completeness(plan)
        issues.extend(comp_issues)
        suggestions.extend(comp_suggs)

        # 2. 评估地理与动线合理性
        geo_score, geo_details, geo_issues, geo_suggs = self._eval_geography(plan)
        issues.extend(geo_issues)
        suggestions.extend(geo_suggs)

        # 3. 评估预算一致性与合理性
        bud_score, bud_details, bud_issues, bud_suggs = self._eval_budget(plan)
        issues.extend(bud_issues)
        suggestions.extend(bud_suggs)

        # 综合加权得分
        overall_score = round(
            comp_score * self.WEIGHT_COMPLETENESS
            + geo_score * self.WEIGHT_GEOGRAPHY
            + bud_score * self.WEIGHT_BUDGET,
            1,
        )
        overall_score = max(0.0, min(100.0, overall_score))

        # 评级划分
        if overall_score >= 90.0:
            grade = "卓越 (EXCELLENT)"
        elif overall_score >= 75.0:
            grade = "良好 (GOOD)"
        elif overall_score >= 60.0:
            grade = "及格 (ACCEPTABLE)"
        else:
            grade = "待改进 (NEEDS_IMPROVEMENT)"

        # 是否合格判定（无严重阻断性错误且单项不低于40分）
        critical_errors = [i for i in issues if i.severity == "error"]
        passed = (
            overall_score >= 60.0
            and comp_score >= 40.0
            and geo_score >= 40.0
            and bud_score >= 40.0
            and len(critical_errors) <= 1
        )

        # 汇总各维度结果
        dimensions = {
            "completeness": DimensionScore(
                dimension="completeness",
                dimension_name="计划完整性",
                score=comp_score,
                weight=self.WEIGHT_COMPLETENESS,
                passed=comp_score >= 60.0,
                details=comp_details,
            ),
            "geography": DimensionScore(
                dimension="geography",
                dimension_name="地理合理性",
                score=geo_score,
                weight=self.WEIGHT_GEOGRAPHY,
                passed=geo_score >= 60.0,
                details=geo_details,
            ),
            "budget": DimensionScore(
                dimension="budget",
                dimension_name="预算一致性",
                score=bud_score,
                weight=self.WEIGHT_BUDGET,
                passed=bud_score >= 60.0,
                details=bud_details,
            ),
        }

        # 计算预期天数
        try:
            from datetime import date
            s_d = date.fromisoformat(plan.start_date)
            e_d = date.fromisoformat(plan.end_date)
            expected_days = (e_d - s_d).days + 1
        except Exception:
            expected_days = getattr(plan, "travel_days", len(plan.days))

        # 量化指标汇总
        metrics = {
            "total_days": len(plan.days),
            "expected_days": expected_days,
            "total_attractions": sum(len(d.attractions) for d in plan.days),
            "avg_attractions_per_day": round(
                sum(len(d.attractions) for d in plan.days) / max(1, len(plan.days)), 1
            ),
            "total_route_distance_km": geo_details.get("total_route_distance_km", 0.0),
            "max_single_leg_km": geo_details.get("max_single_leg_km", 0.0),
            "budget_total": plan.budget.total if plan.budget else 0,
            "budget_arithmetic_valid": bud_details.get("arithmetic_valid", False),
            "critical_errors_count": len(critical_errors),
        }

        # 去重且精简建议
        unique_suggestions = []
        for s in suggestions:
            if s and s not in unique_suggestions:
                unique_suggestions.append(s)

        return EvaluationReport(
            overall_score=overall_score,
            grade=grade,
            passed=passed,
            dimensions=dimensions,
            metrics=metrics,
            issues=issues,
            suggestions=unique_suggestions[:6],  # 突出最有价值的前6条建议
            created_at=datetime.now().isoformat(),
        )

    # ---------------- 维度 1: 计划完整性 ----------------

    def _eval_completeness(
        self, plan: TripPlan
    ) -> Tuple[float, Dict[str, Any], List[EvaluationIssue], List[str]]:
        score = 100.0
        issues: List[EvaluationIssue] = []
        suggs: List[str] = []

        total_days = len(plan.days)
        try:
            from datetime import date
            s_d = date.fromisoformat(plan.start_date)
            e_d = date.fromisoformat(plan.end_date)
            expected_days = (e_d - s_d).days + 1
        except Exception:
            expected_days = getattr(plan, "travel_days", total_days)

        # 1.1 天数一致性
        if total_days != expected_days:
            diff = abs(total_days - expected_days)
            penalty = min(25.0, diff * 15.0)
            score -= penalty
            issues.append(
                EvaluationIssue(
                    dimension="completeness",
                    severity="error",
                    message=f"行程天数不匹配：预期 {expected_days} 天，实际生成 {total_days} 天",
                    suggestion="建议补充或修整各天行程结构，确保与请求出行周期严格对应",
                )
            )

        # 1.2 每日景点、餐饮、酒店完备度检查
        days_with_few_attractions = 0
        days_with_too_many_attractions = 0
        days_missing_hotel = 0
        days_missing_meals = 0
        total_meals_count = 0

        for day in plan.days:
            attr_count = len(day.attractions)
            if attr_count == 0:
                score -= 20.0
                issues.append(
                    EvaluationIssue(
                        dimension="completeness",
                        severity="error",
                        day_index=day.day_index,
                        message=f"第 {day.day_index + 1} 天未安排任何景点",
                        suggestion=f"建议为第 {day.day_index + 1} 天增加 2-3 个代表性景点或文化街区",
                    )
                )
            elif attr_count == 1:
                days_with_few_attractions += 1
                score -= 4.0
                issues.append(
                    EvaluationIssue(
                        dimension="completeness",
                        severity="warning",
                        day_index=day.day_index,
                        message=f"第 {day.day_index + 1} 天仅安排了 1 个景点，行程可能略显单薄",
                        suggestion=f"可为第 {day.day_index + 1} 天适当补充 1 个顺路小众景点或公园",
                    )
                )
            elif attr_count >= 4:
                days_with_too_many_attractions += 1
                score -= 3.0
                issues.append(
                    EvaluationIssue(
                        dimension="completeness",
                        severity="info",
                        day_index=day.day_index,
                        message=f"第 {day.day_index + 1} 天安排了 {attr_count} 个景点，游览节奏可能较紧凑",
                        suggestion="建议留意游玩时间，避免因景点过多造成走马观花或体力透支",
                    )
                )

            # 餐饮检查：应包含早中晚三餐
            meal_types = {m.type.lower() for m in day.meals}
            for m_type in ("breakfast", "lunch", "dinner"):
                if m_type not in meal_types:
                    days_missing_meals += 1
                    score -= 3.0
                    issues.append(
                        EvaluationIssue(
                            dimension="completeness",
                            severity="warning",
                            day_index=day.day_index,
                            message=f"第 {day.day_index + 1} 天缺少 {m_type}（三餐未齐备）",
                            suggestion=f"建议补齐第 {day.day_index + 1} 天的 {m_type} 推荐",
                        )
                    )
            total_meals_count += len(day.meals)

            # 酒店检查：多日游应每晚提供推荐住宿
            if total_days > 1:
                if not day.hotel or not day.hotel.name:
                    days_missing_hotel += 1
                    score -= 6.0
                    issues.append(
                        EvaluationIssue(
                            dimension="completeness",
                            severity="error",
                            day_index=day.day_index,
                            message=f"第 {day.day_index + 1} 天未提供推荐酒店信息",
                            suggestion="建议推荐当晚靠近景点的特色酒店或便捷住宿",
                        )
                    )

        # 1.3 天气信息覆盖检查
        if not plan.weather_info:
            score -= 5.0
            issues.append(
                EvaluationIssue(
                    dimension="completeness",
                    severity="info",
                    message="未获取到可靠天气预报数据",
                    suggestion="建议临近出发时刷新天气信息以便适时调整衣物与雨具",
                )
            )

        # 1.4 知识库贴士覆盖检查
        has_knowledge = bool(plan.knowledge_highlights)
        has_booking_tips = any(
            bool(a.booking_tips) for day in plan.days for a in day.attractions
        )
        if not (has_knowledge or has_booking_tips):
            score -= 4.0
            issues.append(
                EvaluationIssue(
                    dimension="completeness",
                    severity="info",
                    message="行程缺少权威知识库攻略或预约放票避坑贴士",
                    suggestion="建议结合目的地文旅官方攻略，为核心景点补充预约提前期与避坑动线",
                )
            )
        else:
            suggs.append("已成功整合知识库深度攻略，包含了预约抢票与避坑指南，游玩体验更可靠")

        score = max(0.0, min(100.0, round(score, 1)))
        details = {
            "days_count": total_days,
            "days_with_few_attractions": days_with_few_attractions,
            "days_missing_hotel": days_missing_hotel,
            "days_missing_meals": days_missing_meals,
            "has_weather": bool(plan.weather_info),
            "has_knowledge": has_knowledge or has_booking_tips,
        }
        return score, details, issues, suggs

    # ---------------- 维度 2: 地理与动线合理性 ----------------

    def _eval_geography(
        self, plan: TripPlan
    ) -> Tuple[float, Dict[str, Any], List[EvaluationIssue], List[str]]:
        score = 100.0
        issues: List[EvaluationIssue] = []
        suggs: List[str] = []

        total_route_distance_km = 0.0
        max_single_leg_km = 0.0
        invalid_coords_count = 0
        long_distance_legs = 0

        for day in plan.days:
            # 校验坐标合规性
            coords = []
            for attr in day.attractions:
                if (
                    not attr.location
                    or attr.location.longitude == 0
                    or attr.location.latitude == 0
                    or not (-180 <= attr.location.longitude <= 180)
                    or not (-90 <= attr.location.latitude <= 90)
                ):
                    invalid_coords_count += 1
                    score -= 8.0
                    issues.append(
                        EvaluationIssue(
                            dimension="geography",
                            severity="error",
                            day_index=day.day_index,
                            message=f"景点【{attr.name}】经纬度坐标异常或缺失",
                            suggestion="通过高德地理编码接口校准真实空间坐标，以便地图准确定位",
                        )
                    )
                else:
                    coords.append((attr.name, attr.location))

            # 计算同日相邻景点间的物理动线跨度
            for i in range(len(coords) - 1):
                name1, loc1 = coords[i]
                name2, loc2 = coords[i + 1]
                dist = haversine_distance(loc1, loc2)
                total_route_distance_km += dist
                if dist > max_single_leg_km:
                    max_single_leg_km = dist

                if dist > 35.0:
                    long_distance_legs += 1
                    score -= 15.0
                    issues.append(
                        EvaluationIssue(
                            dimension="geography",
                            severity="error",
                            day_index=day.day_index,
                            message=f"第 {day.day_index + 1} 天【{name1}】至【{name2}】跨度过大（约 {dist:.1f} 公里），存在严重折返或远距离奔波",
                            suggestion=f"建议将【{name1}】与【{name2}】拆分至不同天，或调整同日景点游览次序",
                        )
                    )
                elif dist > 20.0:
                    long_distance_legs += 1
                    score -= 10.0
                    issues.append(
                        EvaluationIssue(
                            dimension="geography",
                            severity="warning",
                            day_index=day.day_index,
                            message=f"第 {day.day_index + 1} 天【{name1}】至【{name2}】跨度较远（约 {dist:.1f} 公里）",
                            suggestion="建议合理规划游览路线或选用快速交通接驳",
                        )
                    )
                elif dist > 12.0:
                    score -= 4.0
                    issues.append(
                        EvaluationIssue(
                            dimension="geography",
                            severity="info",
                            day_index=day.day_index,
                            message=f"第 {day.day_index + 1} 天【{name1}】至【{name2}】距离适中（约 {dist:.1f} 公里）",
                            suggestion="建议优先选乘地铁或打车，预留充足路途交通时间",
                        )
                    )

            # 酒店与景点就近度检查
            if day.hotel and day.hotel.location and coords:
                h_loc = day.hotel.location
                if h_loc.longitude != 0 and h_loc.latitude != 0:
                    # 与当日首个景点与末尾景点的距离
                    first_dist = haversine_distance(h_loc, coords[0][1])
                    last_dist = haversine_distance(h_loc, coords[-1][1])
                    if first_dist > 25.0 and last_dist > 25.0:
                        score -= 5.0
                        issues.append(
                            EvaluationIssue(
                                dimension="geography",
                                severity="warning",
                                day_index=day.day_index,
                                message=f"第 {day.day_index + 1} 天推荐酒店【{day.hotel.name}】距离游览景点均偏远（>{first_dist:.1f}km）",
                                suggestion="建议选择靠近核心景点圈或地铁枢纽的酒店，减少早晚通勤耗时",
                            )
                        )

        if max_single_leg_km <= 10.0 and total_route_distance_km > 0:
            suggs.append(
                f"动线设计极佳：单日景点间最大跨度仅 {max_single_leg_km:.1f} 公里，动线集中顺畅，游览舒适度高"
            )
        elif max_single_leg_km > 20.0:
            suggs.append("部分景点相距较远，建议注意交通接驳，或在地图视图中微调游览顺序")

        score = max(0.0, min(100.0, round(score, 1)))
        details = {
            "total_route_distance_km": round(total_route_distance_km, 1),
            "max_single_leg_km": round(max_single_leg_km, 1),
            "invalid_coords_count": invalid_coords_count,
            "long_distance_legs": long_distance_legs,
        }
        return score, details, issues, suggs

    # ---------------- 维度 3: 预算严密性与合理性 ----------------

    def _eval_budget(
        self, plan: TripPlan
    ) -> Tuple[float, Dict[str, Any], List[EvaluationIssue], List[str]]:
        score = 100.0
        issues: List[EvaluationIssue] = []
        suggs: List[str] = []

        budget = plan.budget
        if not budget:
            score -= 40.0
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="error",
                    message="行程未提供任何预算汇总信息 (budget 为空)",
                    suggestion="建议补充门票、住宿、餐饮及交通预估预算",
                )
            )
            return round(score, 1), {"arithmetic_valid": False, "missing_budget": True}, issues, suggs

        # 3.1 严格算术一致性检查
        calc_attr_cost = sum(
            a.ticket_price for day in plan.days for a in day.attractions
        )
        calc_meal_cost = sum(
            m.estimated_cost for day in plan.days for m in day.meals
        )
        calc_hotel_cost = sum(
            day.hotel.estimated_cost
            for day in plan.days
            if day.hotel and day.hotel.estimated_cost
        )

        # 门票一致性
        diff_attr = abs(calc_attr_cost - budget.total_attractions)
        if diff_attr > 0:
            penalty = min(20.0, (diff_attr / max(1, budget.total_attractions)) * 30.0)
            score -= penalty
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="warning",
                    message=f"门票明细合计 ({calc_attr_cost}元) 与预算总览 total_attractions ({budget.total_attractions}元) 存在差额 {diff_attr}元",
                    suggestion="建议校准行程内各景点 ticket_price 之和与预算汇总保持完全一致",
                )
            )

        # 餐饮一致性
        diff_meal = abs(calc_meal_cost - budget.total_meals)
        if diff_meal > 0:
            penalty = min(20.0, (diff_meal / max(1, budget.total_meals)) * 30.0)
            score -= penalty
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="warning",
                    message=f"餐饮明细合计 ({calc_meal_cost}元) 与预算总览 total_meals ({budget.total_meals}元) 存在差额 {diff_meal}元",
                    suggestion="建议校准每日三餐预估费用之和与预算汇总保持一致",
                )
            )

        # 酒店一致性
        diff_hotel = abs(calc_hotel_cost - budget.total_hotels)
        if diff_hotel > 0:
            penalty = min(20.0, (diff_hotel / max(1, budget.total_hotels)) * 30.0)
            score -= penalty
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="warning",
                    message=f"住宿明细合计 ({calc_hotel_cost}元) 与预算总览 total_hotels ({budget.total_hotels}元) 存在差额 {diff_hotel}元",
                    suggestion="建议核对每日酒店房费之和与预算汇总的住宿费用",
                )
            )

        # 四项总和与 total 的算术严密校验
        expected_total = (
            budget.total_attractions
            + budget.total_hotels
            + budget.total_meals
            + budget.total_transportation
        )
        arithmetic_valid = expected_total == budget.total
        if not arithmetic_valid:
            score -= 25.0
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="error",
                    message=f"总预算计算错误：门票+住宿+餐饮+交通 = {expected_total}元，但标记的 total 为 {budget.total}元",
                    suggestion="必须保证 budget.total 等于四项细项之和，杜绝算术不一致",
                )
            )

        # 3.2 负数与异常值防范
        has_negative = (
            budget.total < 0
            or budget.total_attractions < 0
            or budget.total_hotels < 0
            or budget.total_meals < 0
            or budget.total_transportation < 0
            or any(a.ticket_price < 0 for day in plan.days for a in day.attractions)
            or any(m.estimated_cost < 0 for day in plan.days for m in day.meals)
        )
        if has_negative:
            score -= 30.0
            issues.append(
                EvaluationIssue(
                    dimension="budget",
                    severity="error",
                    message="预算明细中出现了负数金额，属于严重数据异常",
                    suggestion="确保所有门票、房费、餐费均为 >= 0 的正整数",
                )
            )

        if arithmetic_valid and diff_attr == 0 and diff_meal == 0 and diff_hotel == 0:
            suggs.append("预算严密性达到 100%：门票、餐饮、酒店各项明细与总计严格吻合，算术逻辑严谨")

        score = max(0.0, min(100.0, round(score, 1)))
        details = {
            "arithmetic_valid": arithmetic_valid,
            "calculated_total": expected_total,
            "reported_total": budget.total,
            "diff_attractions": diff_attr,
            "diff_meals": diff_meal,
            "diff_hotels": diff_hotel,
            "has_negative": has_negative,
        }
        return score, details, issues, suggs


# 全局单例
_evaluator_instance: Optional[TripPlanEvaluator] = None


def get_evaluator() -> TripPlanEvaluator:
    """获取评估器单例实例。"""
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = TripPlanEvaluator()
    return _evaluator_instance


def evaluate_plan(plan: TripPlan) -> EvaluationReport:
    """快捷评估函数。"""
    return get_evaluator().evaluate(plan)
