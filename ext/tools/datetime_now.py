"""ext/tools/datetime_now.py — 当前日期时间工具(我的 patch)。

热插拔人格插件(原则 12)。配合 web_search: agent 经常需要知道"现在"
(回答"今天"/"本周"等问题)。registry 启动时 load_ext 自动加载。
"""
from datetime import datetime

from prism.agent_loop import Tool


def _execute(args):
    now = datetime.now()
    fmt = args.get("format", "%Y-%m-%d %H:%M:%S")
    try:
        return now.strftime(fmt)
    except Exception as e:
        return f"[error] 格式无效: {type(e).__name__}: {e}"


_tool = Tool(
    name="datetime_now",
    description=(
        "当前日期时间。format 是 strftime 格式(默认 %%Y-%%m-%%d %%H:%%M:%%S)。"
        "用于回答'今天星期几''现在几点'等需要实时时间的问题。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "strftime 格式, 如 %Y-%m-%d / %A(星期) / %H:%M",
            },
        },
    },
    execute=_execute,
)


def register(registry):
    registry.tool(_tool)
