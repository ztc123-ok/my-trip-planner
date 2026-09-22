# -*- coding: utf-8 -*-
"""LangSmith 可观测性与追踪服务 (Observability & Tracing Service).

职责:
1. 初始化与管理 LangSmith 链路追踪环境;
2. 提供零侵入/优雅降级的 @safe_traceable 装饰器;
3. 将结构化评估结果 (EvaluationReport) 作为 Run Feedback 回传至 LangSmith 平台;
4. 输出当前可观测性状态诊断.
"""

import os
import functools
from typing import Callable, Any, Optional, Dict

from ..config import get_settings
from ..models.schemas import EvaluationReport


def is_tracing_enabled() -> bool:
    """判断当前环境是否已启用 LangSmith Tracing。"""
    settings = get_settings()
    tracing_v2 = (
        str(os.getenv("LANGCHAIN_TRACING_V2", "")).lower() in ("true", "1")
        or settings.langchain_tracing_v2
    )
    api_key = os.getenv("LANGCHAIN_API_KEY") or settings.langchain_api_key
    return bool(tracing_v2 and api_key)


def get_langsmith_client():
    """获取 LangSmith Client 实例，若未配置或库缺失则安全返回 None。"""
    if not is_tracing_enabled():
        return None
    try:
        from langsmith import Client
        api_key = os.getenv("LANGCHAIN_API_KEY") or get_settings().langchain_api_key
        endpoint = os.getenv("LANGCHAIN_ENDPOINT") or get_settings().langchain_endpoint
        return Client(api_key=api_key, api_url=endpoint)
    except Exception as exc:
        print(f"⚠️ 初始化 LangSmith Client 失败 (降级为无操作): {exc}")
        return None


def safe_traceable(name: Optional[str] = None, run_type: str = "chain", **kwargs) -> Callable:
    """包装 LangSmith @traceable 装饰器。

    若环境中已启用 LangSmith，则上报执行 Run 与跨度追踪；
    若未启用或 langsmith 库异常，则作为透明代理零开销直接调用原函数。
    """
    def decorator(fn: Callable) -> Callable:
        if not is_tracing_enabled():
            return fn
        try:
            from langsmith.run_helpers import traceable
            trace_opts = {"run_type": run_type, **kwargs}
            if name:
                trace_opts["name"] = name
            return traceable(**trace_opts)(fn)
        except Exception:
            return fn

    return decorator


def record_evaluation_feedback(
    report: EvaluationReport,
    run_id: Optional[str] = None,
    thread_id: Optional[str] = None,
) -> bool:
    """将旅行规划的结构化评估得分与诊断作为 Feedback 回传至 LangSmith 平台。

    支持对特定 run_id 回传综合质量分及分维度指标；
    若 LangSmith 未开启或网络不可达，静默捕获并返回 False，绝不阻断业务主流程。
    """
    client = get_langsmith_client()
    if not client:
        return False

    # 若未提供精确 run_id，尝试通过 thread_id 或最近 run 检索
    target_run_id = run_id
    if not target_run_id and thread_id:
        try:
            project_name = os.getenv("LANGCHAIN_PROJECT") or get_settings().langchain_project
            runs = list(client.list_runs(
                project_name=project_name,
                filter=f'eq(metadata.thread_id, "{thread_id}")',
                limit=1,
            ))
            if runs:
                target_run_id = str(runs[0].id)
        except Exception:
            pass

    if not target_run_id:
        # 无关联 Run ID，跳过 Feedback 记录
        return False

    try:
        # 1. 综合质量反馈
        client.create_feedback(
            run_id=target_run_id,
            key="plan_quality_score",
            score=round(report.overall_score / 100.0, 3),
            value=report.grade,
            comment=f"综合评分: {report.overall_score} ({report.grade}) | 合格: {report.passed}",
        )

        # 2. 三大核心维度指标反馈
        for dim_key, dim_val in report.dimensions.items():
            client.create_feedback(
                run_id=target_run_id,
                key=f"{dim_key}_score",
                score=round(dim_val.score / 100.0, 3),
                value=f"{dim_val.score}分",
                comment=f"权重: {dim_val.weight}, 及格: {dim_val.passed}",
            )
        print(f"📊 [LangSmith] 成功将旅行计划评估指标上报至 Run: {target_run_id}")
        return True
    except Exception as exc:
        print(f"⚠️ [LangSmith] 回传评估 Feedback 出现异常 (已优雅降级): {exc}")
        return False


def get_observability_status() -> Dict[str, Any]:
    """返回当前系统的可观测性状态汇总。"""
    settings = get_settings()
    enabled = is_tracing_enabled()
    project = os.getenv("LANGCHAIN_PROJECT") or settings.langchain_project
    endpoint = os.getenv("LANGCHAIN_ENDPOINT") or settings.langchain_endpoint
    has_key = bool(os.getenv("LANGCHAIN_API_KEY") or settings.langchain_api_key)

    return {
        "tracing_enabled": enabled,
        "has_api_key": has_key,
        "project": project,
        "endpoint": endpoint,
        "client_ready": enabled,
    }
