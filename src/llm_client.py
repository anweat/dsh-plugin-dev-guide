"""OpenAI 兼容 LLM 客户端封装。业务代码只依赖此模块，不感知具体模型厂商。"""
from __future__ import annotations

from openai import OpenAI


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.1, timeout: float = 120,
                 max_tokens: int = 4096):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)

    def chat(self, messages: list[dict], json_mode: bool = False,
             max_tokens: int | None = None) -> str:
        """发送对话请求，返回文本内容。"""
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        resp = self.client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
