"""ModelBackend — LLM 接入(可插拔).

核心 Agent 不绑死任何 provider。
  chat()        非流式(兼容)
  chat_stream() 流式 + function calling(agent_loop 用这个)
"""
from __future__ import annotations
import os


class ModelBackend:
    """LLM 接入接口。可插拔: OpenAIModel / ClaudeModel / LocalModel ..."""

    def chat(self, messages: list[dict], **kw) -> str:
        raise NotImplementedError

    def chat_stream(self, messages: list[dict], tools: list | None = None):
        """流式 function calling。yield:
        {"type":"delta","text":str}              流式文本片段
        {"type":"done","tool_calls":[...]}       最终累积的 tool_calls
        """
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
        resp = self.client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages, tools=None):
        kwargs: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        stream = self.client.chat.completions.create(**kwargs)
        # openai 流式 tool_calls 是分片的(index + arguments 累积), 这里拼回完整
        tc_acc: dict[int, dict] = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield {"type": "delta", "text": delta.content}
            tcs = getattr(delta, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    idx = tc.index if tc.index is not None else 0
                    slot = tc_acc.setdefault(idx, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["function"]["arguments"] += tc.function.arguments
        yield {"type": "done", "tool_calls": [tc_acc[i] for i in sorted(tc_acc)]}
