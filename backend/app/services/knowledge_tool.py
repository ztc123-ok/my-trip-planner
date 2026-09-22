# -*- coding: utf-8 -*-
"""旅行知识库 LangChain 适配工具（供 ReAct Agent 与 LLM 自主工具调用）。"""

import json
import logging
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool, BaseTool

from .knowledge_service import KnowledgeService, get_knowledge_service

logger = logging.getLogger(__name__)


def create_knowledge_langchain_tool(knowledge_service: Optional[KnowledgeService] = None) -> BaseTool:
    """创建并返回供 LangChain / LangGraph ReAct 绑定的知识库检索工具。"""
    ks = knowledge_service or get_knowledge_service()

    @tool
    def search_travel_knowledge(query: str, city: str, section_type: Optional[str] = None) -> str:
        """检索指定城市的官方深度攻略、门票预约与放票规则、闭馆时间、最佳机位与避坑防骗贴士。
        
        适用场景：
        1. 当用户询问某个景点怎么预约、提前几天抢票、周几闭馆（如“故宫周一开门吗”、“兵马俑门票怎么买”）；
        2. 当用户询问景点的游览路线、拍照机位、耗时建议；
        3. 当用户询问避坑防骗指南、交通防黑车野导游；
        4. 在替换或新增核心景点时，获取该景点的权威贴士与注意事项。

        Args:
            query: 检索关键词或具体问题（如 "故宫 门票预约 放票时间"、"兵马俑 避坑防黑车"、"大熊猫和花 几点排队"）
            city: 目标城市（如 "北京"、"西安"、"成都"、"南京" 等，用于强过滤）
            section_type: 可选特定维度过滤（如 "基础信息与预约规则"、"游览路线与打卡机位"、"避坑与实用贴士"）
        """
        try:
            hits = ks.search_knowledge(city=city, query=query, top_k=3, section_type=section_type)
            if not hits:
                return json.dumps({
                    "status": "empty",
                    "city": city,
                    "query": query,
                    "message": f"知识库中暂未收录针对 {city} '{query}' 的深度切片，建议参考通用常识或常规路线规划。"
                }, ensure_ascii=False)

            results = []
            for h in hits:
                results.append({
                    "spot_name": h.get("spot_name"),
                    "section_type": h.get("section_type"),
                    "score": round(float(h.get("score", 0.0)), 4),
                    "content": h.get("content"),
                })
            return json.dumps({
                "status": "success",
                "city": city,
                "query": query,
                "count": len(results),
                "knowledge_items": results
            }, ensure_ascii=False)

        except Exception as exc:
            logger.warning("search_travel_knowledge 执行异常: %s", exc)
            return json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False)

    return search_travel_knowledge
