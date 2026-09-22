# -*- coding: utf-8 -*-
"""通义千问 / OpenAI 兼容 Embedding 服务。"""

import os
from typing import List
from openai import OpenAI

from ..config import get_settings


class EmbeddingService:
    def __init__(self):
        settings = get_settings()
        self.api_key = (
            os.getenv("EMBEDDING_API_KEY")
            or settings.embedding_api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or settings.openai_api_key
        )
        if not self.api_key:
            raise ValueError("未配置 EMBEDDING_API_KEY 或 LLM_API_KEY，请在 backend/.env 配置")

        self.base_url = (
            os.getenv("EMBEDDING_BASE_URL")
            or settings.embedding_base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or settings.openai_base_url
        )

        self.model = (
            os.getenv("EMBEDDING_MODEL_ID")
            or settings.embedding_model
            or "text-embedding-v3"
        )

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def get_embedding(self, text: str) -> List[float]:
        """获取单条文本的向量表示。"""
        clean_text = text.replace("\n", " ").strip()
        if not clean_text:
            clean_text = " "
        response = self.client.embeddings.create(
            model=self.model,
            input=clean_text,
        )
        return response.data[0].embedding

    def get_embeddings_batch(self, texts: List[str], batch_size: int = 8) -> List[List[float]]:
        """批量获取文本向量，自动切分为不超过 batch_size (默认8条) 的小批次请求，防止百炼 400 报错。"""
        clean_texts = [t.replace("\n", " ").strip() or " " for t in texts]
        if not clean_texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(clean_texts), batch_size):
            chunk = clean_texts[i : i + batch_size]
            response = self.client.embeddings.create(
                model=self.model,
                input=chunk,
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([item.embedding for item in sorted_data])

        return all_embeddings



_embedding_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_instance
    if _embedding_instance is None:
        _embedding_instance = EmbeddingService()
    return _embedding_instance
