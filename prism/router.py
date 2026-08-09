"""@ 路由: @name 消息 → agent.chat(消息)。

规则(用户定, 零揣测, 全部报错不静默):
  @name 消息        → name.chat(消息)   (name 必须是已存在 agent)
  @name1 @name2 ..  → 报错(不群发)
  @(裸)             → 报错(不裸写)
  @name(空消息)     → 报错
  name 不存在       → 报错
  其他              → 原样 IPython 执行 Python

注意: 只对【单行 cell】生效。多行 cell 不碰 —— 避免误吞 Python 装饰器
(@decorator / def ...)。多行消息用 agent.chat(\"\"\"...\"\"\")。
"""
from __future__ import annotations
import re


def at_route(name: str, message: str):
    """@name 消息 的执行器: 在 user_ns 找 agent, 调 chat。"""
    from IPython import get_ipython
    ip = get_ipython()
    ns = ip.user_ns if ip is not None else {}
    agent = ns.get(name)
    if agent is None:
        raise NameError(
            f"@{name}: 命名空间里没有 '{name}'。"
            f" 先创建: {name} = Agent('{name}', model=OpenAIModel())"
        )
    if not callable(getattr(agent, "chat", None)):
        raise TypeError(f"@{name}: '{name}' 不是 agent(没有 .chat)。")
    agent.chat(message)


def at_error(msg: str):
    """@ 路由语法错误统一出口。"""
    raise SyntaxError(msg)


def _transform(lines):
    """IPython input_transformers_post: 接收 list[str](行), 返回 list[str]。"""
    src = "".join(lines)
    stripped = src.strip()
    if not stripped.startswith("@"):
        return lines
    # 多行 cell 不路由 —— 可能是 @decorator + def/class, 别误吞
    if "\n" in stripped:
        return lines

    ats = re.findall(r"@(\w+)", stripped)
    if not ats:
        return ['at_error("裸 @ 不允许:必须是 @name 消息(单行)")\n']
    if len(ats) > 1:
        names = ", ".join("@" + n for n in ats)
        return [f'at_error("@ 不允许群发:检测到 {names},一次只准 @ 一个 agent")\n']

    name = ats[0]
    m = re.match(rf"@{re.escape(name)}\s*(.*)", stripped, re.S)
    message = (m.group(1) if m else "").strip()
    if not message:
        return [f'at_error("@{name}:空消息。@ 了就得说事")\n']
    return [f"at_route({name!r}, {message!r})\n"]


def register(ipython):
    """注册 @ 路由 transformer + 执行器到 IPython shell。"""
    ipython.input_transformers_post.append(_transform)
    ipython.user_ns.setdefault("at_route", at_route)
    ipython.user_ns.setdefault("at_error", at_error)
