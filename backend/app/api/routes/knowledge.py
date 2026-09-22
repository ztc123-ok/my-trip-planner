# -*- coding: utf-8 -*-
"""旅行知识库 RAG 检索与元数据接口。"""

import glob
import os
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ...services.knowledge_service import get_knowledge_service

router = APIRouter(prefix="/knowledge", tags=["旅行知识库"])


class KnowledgeSearchResponse(BaseModel):
    success: bool = True
    city: str
    query: str
    count: int
    data: List[Dict[str, Any]]


class CityGuideSummary(BaseModel):
    city: str
    filename: str
    size_bytes: int


class KnowledgeCitiesResponse(BaseModel):
    success: bool = True
    total_cities: int
    cities: List[CityGuideSummary]


@router.get(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="语义检索城市深度攻略与避坑贴士",
)
async def search_knowledge(
    city: str = Query(..., description="目标城市，如：北京、西安、成都"),
    query: str = Query(..., description="检索问题或关键词，如：故宫放票时间、兵马俑避坑"),
    top_k: int = Query(3, ge=1, le=10, description="返回条数"),
    section_type: Optional[str] = Query(None, description="可选特定小节过滤"),
):
    ks = get_knowledge_service()
    hits = ks.search_knowledge(city=city, query=query, top_k=top_k, section_type=section_type)
    return KnowledgeSearchResponse(
        success=True,
        city=city,
        query=query,
        count=len(hits),
        data=hits,
    )


@router.get(
    "/cities",
    response_model=KnowledgeCitiesResponse,
    summary="获取已收录攻略的城市列表",
)
async def get_indexed_cities():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # backend/data/knowledge_base/attractions
    base_dir = os.path.abspath(os.path.join(current_dir, "..", "..", "..", "data", "knowledge_base", "attractions"))
    cities = []
    if os.path.exists(base_dir):
        for f in glob.glob(os.path.join(base_dir, "*.md")):
            name = os.path.splitext(os.path.basename(f))[0]
            size = os.path.getsize(f)
            # 尝试读取文件 frontmatter 中的中文城市名
            city_name = name
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    for line in fp:
                        if line.startswith("city:"):
                            city_name = line.split("city:")[1].strip().strip('"').strip("'")
                            break
            except Exception:
                pass
            cities.append(CityGuideSummary(city=city_name, filename=os.path.basename(f), size_bytes=size))

    return KnowledgeCitiesResponse(
        success=True,
        total_cities=len(cities),
        cities=cities,
    )
