# -*- coding: utf-8 -*-
"""旅行知识库服务：基于 Qdrant 与通义千问 Embedding。"""

import glob
import os
import uuid

# 确保本地 127.0.0.1 请求不被 Windows 代理软件劫持
if "127.0.0.1" not in os.environ.get("NO_PROXY", ""):
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    os.environ["no_proxy"] = "localhost,127.0.0.1"

from typing import Any, Dict, List, Optional
import frontmatter
from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from ..config import get_settings
from .embedding_service import get_embedding_service


class KnowledgeService:
    def __init__(self):
        settings = get_settings()
        # 确保本地请求不被系统代理劫持
        no_proxy = os.getenv("NO_PROXY", "")
        if "127.0.0.1" not in no_proxy:
            os.environ["NO_PROXY"] = "localhost,127.0.0.1" if not no_proxy else f"{no_proxy},localhost,127.0.0.1"
            os.environ["no_proxy"] = os.environ["NO_PROXY"]

        self.host = os.getenv("QDRANT_HOST") or settings.qdrant_host or "127.0.0.1"
        self.port = int(os.getenv("QDRANT_PORT") or settings.qdrant_port or 6333)
        self.collection_name = (
            os.getenv("QDRANT_COLLECTION") or settings.qdrant_collection_name
        )
        self.embedding_service = get_embedding_service()
        self.client = QdrantClient(url=f"http://{self.host}:{self.port}", timeout=10)
        self._ensure_collection()


    def _ensure_collection(self):
        """确保 Qdrant Collection 存在，若不存在则根据 Embedding 输出动态探测维度并创建。"""
        try:
            if not self.client.collection_exists(self.collection_name):
                # 动态探测维度（如 text-embedding-v3 通常是 1024 维）
                probe_vec = self.embedding_service.get_embedding("ping")
                dim = len(probe_vec)
                print(
                    f"💡 [KnowledgeService] 探测到 Embedding 维度为 {dim}，正在创建集合: {self.collection_name}"
                )
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )
                # 为 city 字段创建索引，优化 Payload 过滤性能
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="city",
                    field_schema="keyword",
                )
                print(f"✅ [KnowledgeService] 集合 {self.collection_name} 创建成功")
        except Exception as e:
            print(f"⚠️ [KnowledgeService] 连接 Qdrant 或初始化集合失败: {e}")

    def ingest_markdown_file(self, file_path: str) -> int:
        """解析单个 Markdown 攻略文件，按 ## 景点 和 ### 维度切分并写入 Qdrant。"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            post = frontmatter.load(f)

        city = post.metadata.get("city", "")
        category = post.metadata.get("category", "attraction_guide")
        source_file = os.path.basename(file_path)

        # 简单的层级解析（不强制依赖额外分块库，纯原生高稳定性）
        lines = post.content.split("\n")
        current_spot = ""
        current_section = ""
        section_lines = []

        chunks: List[Dict[str, Any]] = []

        def flush_chunk():
            nonlocal section_lines
            content_str = "\n".join(section_lines).strip()
            if current_spot and current_section and content_str:
                chunk_id = f"{city}_{current_spot}_{current_section}".replace(" ", "_")
                enhanced_content = f"【{city}·{current_spot} - {current_section}】\n{content_str}"
                chunks.append(
                    {
                        "id": chunk_id,
                        "content": enhanced_content,
                        "city": city,
                        "spot_name": current_spot,
                        "section_type": current_section,
                        "category": category,
                        "source_file": source_file,
                    }
                )
            section_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## ") and not stripped.startswith("### "):
                flush_chunk()
                current_spot = stripped.replace("## ", "").strip()
                current_section = ""
            elif stripped.startswith("### "):
                flush_chunk()
                current_section = stripped.replace("### ", "").strip()
            else:
                if current_spot and current_section:
                    section_lines.append(line)

        flush_chunk()

        if not chunks:
            return 0

        # 批量向量化
        texts = [c["content"] for c in chunks]
        vectors = self.embedding_service.get_embeddings_batch(texts)

        # 构造 Qdrant Points
        points = []
        for c, vec in zip(chunks, vectors):
            point = PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, c["id"])),
                vector=vec,
                payload={
                    "city": c["city"],
                    "spot_name": c["spot_name"],
                    "section_type": c["section_type"],
                    "category": c["category"],
                    "content": c["content"],
                    "source_file": c["source_file"],
                },
            )
            points.append(point)

        self.client.upsert(collection_name=self.collection_name, points=points)
        return len(points)

    def ingest_all_attractions(self, kb_dir: str) -> Dict[str, int]:
        """批量导入知识库目录下所有的景点 markdown 文件。"""
        results = {}
        for file_path in glob.glob(os.path.join(kb_dir, "*.md")):
            name = os.path.basename(file_path)
            try:
                cnt = self.ingest_markdown_file(file_path)
                results[name] = cnt
            except Exception as e:
                results[name] = f"Error: {e}"
        return results

    def search_knowledge(
        self,
        city: str,
        query: str,
        top_k: int = 3,
        section_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """基于城市（必须）和语义检索相关攻略切片。

        Args:
            city: 城市名称（如 "深圳"、"北京"），作为 Payload 强过滤项
            query: 检索关键词或用户偏好描述
            top_k: 返回条数
            section_type: 可选，如 "避坑与实用贴士" 或 "基础信息与预约规则"
        """
        try:
            query_vec = self.embedding_service.get_embedding(f"{city} {query}")

            conditions = [FieldCondition(key="city", match=MatchValue(value=city))]
            if section_type:
                conditions.append(
                    FieldCondition(
                        key="section_type", match=MatchValue(value=section_type)
                    )
                )

            filter_condition = Filter(must=conditions)

            # Qdrant Client 1.19+ 使用 query_points
            query_res = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vec,
                query_filter=filter_condition,
                limit=top_k,
            )

            hits = []
            for hit in getattr(query_res, "points", []):
                hits.append(
                    {
                        "score": hit.score,
                        "spot_name": hit.payload.get("spot_name") if hit.payload else "",
                        "section_type": hit.payload.get("section_type") if hit.payload else "",
                        "content": hit.payload.get("content") if hit.payload else "",
                    }
                )
            return hits

        except Exception as e:
            print(f"⚠️ [KnowledgeService] 检索异常: {e}")
            return []


_knowledge_instance: KnowledgeService | None = None


def get_knowledge_service() -> KnowledgeService:
    global _knowledge_instance
    if _knowledge_instance is None:
        _knowledge_instance = KnowledgeService()
    return _knowledge_instance
