# -*- coding: utf-8 -*-
"""OpenAI-compatible model client used by LangGraph nodes and ReAct tools."""

import os
from threading import Lock
from typing import Optional

from langchain_openai import ChatOpenAI
from openai import OpenAI

from ..config import get_settings


class ChatLLM:
    def __init__(self):
        settings = get_settings()
        self.api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
        if not self.api_key:
            raise ValueError("请在 backend/.env 配置 LLM_API_KEY 或 OPENAI_API_KEY")
        self.model = os.getenv("LLM_MODEL_ID") or os.getenv("OPENAI_MODEL") or settings.openai_model
        self.base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or settings.openai_base_url
        self.timeout = float(os.getenv("LLM_TIMEOUT") or 60)
        self.provider = "qwen" if self.model.lower().startswith("qwen") else "openai"
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=self.timeout)

    def generate(self, system_prompt: str, user_prompt: str, **options) -> str:
        if self.provider == "qwen" and self.model.startswith("qwen3."):
            options.setdefault("extra_body", {"enable_thinking": False})
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **options,
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("模型未返回文本内容")
        return content

    def get_chat_model(self, temperature: float = 0.2, **kwargs) -> ChatOpenAI:
        """返回已配置的 LangChain ChatOpenAI 实例，支持 bind_tools 与 ReAct。"""
        model_kwargs = kwargs.pop("model_kwargs", {})
        extra_body = kwargs.pop("extra_body", {})
        if self.provider == "qwen" and self.model.startswith("qwen3."):
            extra_body.setdefault("enable_thinking", False)

        chat_kwargs = {
            "model": self.model,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "temperature": temperature,
            **kwargs,
        }
        if extra_body:
            chat_kwargs["extra_body"] = extra_body
        if model_kwargs:
            chat_kwargs["model_kwargs"] = model_kwargs

        return ChatOpenAI(**chat_kwargs)


_llm_instance: ChatLLM | None = None
_llm_lock = Lock()


def get_llm() -> ChatLLM:
    global _llm_instance
    with _llm_lock:
        if _llm_instance is None:
            _llm_instance = ChatLLM()
        return _llm_instance


def reset_llm() -> None:
    global _llm_instance
    with _llm_lock:
        _llm_instance = None


def get_chat_model(temperature: float = 0.2, **kwargs) -> ChatOpenAI:
    """获取单例或配置好的 LangChain ChatOpenAI 实例。"""
    llm = get_llm()
    return llm.get_chat_model(temperature=temperature, **kwargs)
