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
      PRISM_TIMEOUT     请求超时秒(默认 600=10分钟, 兼兜底网络挂起; 带思考+大代码单轮常超 60s)
    """

    def __init__(self, model: str | None = None,
                 base_url: str | None = None, api_key: str | None = None,
                 timeout: float | None = None, thinking_level: str | None = None):
        from openai import OpenAI
        self.client = OpenAI(
            base_url=base_url or os.getenv("OPENAI_BASE_URL"),
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            timeout=timeout if timeout is not None else float(os.getenv("PRISM_TIMEOUT", "600")),
        )
        self.model = model or os.getenv("PRISM_MODEL", "gpt-4o-mini")
        self.thinking_level = thinking_level    # off→关思考(enable_thinking=False); None/其他→endpoint 默认

    def _thinking_extra_body(self):
        """对齐 pi thinkingLevel + 防 reasoning 发散。

        off → 关思考(智谱 enable_thinking=False)。
        其他 → 限制思考 max_tokens(GLM-5.2 对大任务 reasoning 易失控发散,
               实测整个塔防 prompt 123s 吐 1 万 reasoning chunk 不停、零输出)。
        """
        lvl = getattr(self, "thinking_level", None)
        if lvl == "off":
            return {"enable_thinking": False}
        max_tokens = {"minimal": 300, "low": 600, "medium": 1500,
                      "high": 4000, "xhigh": 8000, "max": 16000}.get(lvl, 1500)
        return {"thinking": {"type": "enabled", "max_tokens": max_tokens}}

    def chat(self, messages, **kw) -> str:
        resp = self.client.chat.completions.create(model=self.model, messages=messages)
        return resp.choices[0].message.content or ""

    def chat_stream(self, messages, tools=None):
        """流式 function calling。纯流式, 不 fallback。

        producer 线程跑 stream 请求; 出错通过队列传 err, 主循环 raise。
        网络挂起由 client.timeout 兜底(producer 抛 → err → raise, agent_loop retry/error 接管)
        ——不退化为非流式: 非流式会丢 reasoning_content(思考显示) + 大任务要等完整生成很慢。
        """
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

        tc_acc: dict[int, dict] = {}
        while True:
            kind, payload = q.get()   # 阻塞: producer 会 put chunk/end/err(client timeout 兜底)
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
