"""ModelBackend — LLM 接入(可插拔).

核心 Agent 不绑死任何 provider。
  chat()        非流式(兼容)
  chat_stream() 流式 + function calling(agent_loop 用这个)

chat_stream 策略: 先试流式(SSE), 首事件 5s 超时则 fallback 非流式 ——
兼容不支持/挂起 SSE 的 endpoint(如某些网关), 对支持的 endpoint 仍保留流式体验。
"""
from __future__ import annotations
import os
import queue as _q
import threading as _th


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
      PRISM_TIMEOUT     请求超时秒(默认 60)
      PRISM_STREAM_FIRST_TIMEOUT  流式首事件超时秒(默认 5); 超时则 fallback 非流式
    """

    def __init__(self, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None,
                 timeout: float | None = None, thinking_level: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            timeout=timeout if timeout is not None else float(os.getenv("PRISM_TIMEOUT", "60")),
        )
        self.model = model or os.getenv("PRISM_MODEL", "gpt-4o-mini")
        self._first_timeout = float(os.getenv("PRISM_STREAM_FIRST_TIMEOUT", "5"))
        self.thinking_level = thinking_level    # off→关思考(enable_thinking=False); None/其他→endpoint 默认

    def _thinking_extra_body(self):
        """对齐 pi thinkingLevel: off → 关思考(智谱 enable_thinking=False, 快且简洁)。"""
        if getattr(self, "thinking_level", None) == "off":
            return {"enable_thinking": False}
        return None

    def chat(self, messages, **kw) -> str:
        resp = self.client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or ""

    def _non_stream(self, messages, tools):
        """非流式 fallback: 完整 content 作为单个 delta。"""
        try:
            kwargs: dict = {"model": self.model, "messages": messages, "stream": False}
            if tools:
                kwargs["tools"] = tools
            eb = self._thinking_extra_body()
            if eb:
                kwargs["extra_body"] = eb
            resp = self.client.chat.completions.create(**kwargs)
        except Exception:
            yield {"type": "done", "tool_calls": []}
            return
        msg = resp.choices[0].message
        if msg.content:
            yield {"type": "delta", "text": msg.content}
        tcs = []
        raw = getattr(msg, "tool_calls", None)
        if raw:
            for tc in raw:
                tcs.append({"id": tc.id, "type": "function",
                            "function": {"name": tc.function.name,
                                         "arguments": tc.function.arguments or ""}})
        yield {"type": "done", "tool_calls": tcs}

    def chat_stream(self, messages, tools=None):
        """流式 function calling。首事件超时 → fallback 非流式(兼容挂起的 SSE endpoint)。"""
        q: _q.Queue = _q.Queue()

        def producer():
            try:
                kwargs: dict = {"model": self.model, "messages": messages, "stream": True}
                if tools:
                    kwargs["tools"] = tools
                eb = self._thinking_extra_body()
                if eb:
                    kwargs["extra_body"] = eb
                stream = self.client.chat.completions.create(**kwargs)
                for chunk in stream:
                    q.put(("c", chunk))
                q.put(("end", None))
            except Exception as e:
                q.put(("err", e))

        t = _th.Thread(target=producer, daemon=True)
        t.start()

        # 首事件超时: 5s 内无任何 chunk/end/err → 流式挂起, fallback 非流式
        try:
            first = q.get(timeout=self._first_timeout)
        except _q.Empty:
            yield from self._non_stream(messages, tools)
            return

        tc_acc: dict[int, dict] = {}
        pending = [first]
        while True:
            if pending:
                kind, payload = pending.pop(0)
            else:
                try:
                    kind, payload = q.get(timeout=60.0)
                except _q.Empty:
                    break  # 流式中断(60s 无后续), 结束
            if kind == "end":
                break
            if kind == "err":
                raise payload
            # kind == "c": chunk
            chunk = payload
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield {"type": "delta", "text": delta.content}
            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield {"type": "reasoning", "text": reasoning}
            tcs = getattr(delta, "tool_calls", None)
            if tcs:
                for tc in tcs:
                    idx = tc.index if tc.index is not None else 0
                    slot = tc_acc.setdefault(idx, {"id": None, "type": "function",
                                                   "function": {"name": "", "arguments": ""}})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["function"]["name"] += tc.function.name
                        if tc.function.arguments:
                            slot["function"]["arguments"] += tc.function.arguments
        yield {"type": "done", "tool_calls": [tc_acc[i] for i in sorted(tc_acc)]}
