"""ModelBackend — LLM 接入(可插拔).

核心 Agent 不绑死任何 provider, 只依赖 ModelBackend.chat().
"""
from __future__ import annotations
import os


class ModelBackend:
    """LLM 接入接口。可插拔: OpenAIModel / ClaudeModel / LocalModel ..."""

    def chat(self, messages: list[dict], **kw) -> str:
        raise NotImplementedError


class OpenAIModel(ModelBackend):
    """OpenAI 兼容接口(OpenAI / DeepSeek / GLM / 任意兼容 provider).

    配置走环境变量:
      PRISM_MODEL       模型名(默认 gpt-4o-mini)
      OPENAI_BASE_URL   兼容 endpoint
      OPENAI_API_KEY    密钥
    """

    def __init__(self, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
        )
        self.model = model or os.getenv("PRISM_MODEL", "gpt-4o-mini")

    def chat(self, messages, **kw) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages,
        )
        return resp.choices[0].message.content or ""
