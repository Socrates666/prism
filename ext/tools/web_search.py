"""ext/tools/web_search.py — Bing 网络搜索工具。

热插拔人格插件(原则 12)。registry 启动时 load_ext 自动加载。
"""
import requests
import re
from html import unescape

from prism.agent_loop import Tool


def _do_search(query: str, num_results: int = 5) -> str:
    """Bing 搜索, 返回标题+链接+摘要。"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    url = (
        "https://www.bing.com/search?q="
        + requests.utils.quote(query)
        + f"&count={num_results}"
    )
    resp = requests.get(url, timeout=15, headers=headers)
    if resp.status_code != 200:
        return f"[error] HTTP {resp.status_code}"

    html = resp.text
    results = []

    # 标题+链接
    pattern = r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>'
    matches = re.findall(pattern, html, re.DOTALL)

    # 摘要
    snippets_raw = re.findall(
        r'b_lineclamp[0-9]?[^>]*>(.*?)</p>', html, re.DOTALL
    )
    snippets = [
        unescape(re.sub(r'<[^>]+>', "", s)).strip() for s in snippets_raw
    ]

    for i, (link, title_html) in enumerate(matches):
        if len(results) >= num_results:
            break
        link = unescape(link)
        title = unescape(re.sub(r'<[^>]+>', "", title_html)).strip()
        if not title or not link:
            continue
        snip = snippets[i] if i < len(snippets) else ""
        results.append(f"**{title}**\n{link}\n{snip}")

    if not results:
        return "[无结果] 搜索解析失败"
    return "\n\n---\n\n".join(results)


def _search_execute(args):
    query = args.get("query", "")
    num = args.get("num_results", 5)
    try:
        return _do_search(query, num)
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"


_search_tool = Tool(
    name="web_search",
    description=(
        "网络搜索(Bing)。返回标题、链接和摘要。"
        "用于查找最新信息、文档、API 用法等。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "num_results": {
                "type": "integer",
                "description": "返回结果数量, 默认 5",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    execute=_search_execute,
)


def register(registry):
    registry.tool(_search_tool)
