"""ext/tools/search_hub.py — 统一搜索工具。

设计: search 是主工具, 搜索源是可装填项(provider)。
内置 Bing web 搜索; 其他搜索源(GitHub API、知乎、B站、小红书等)
通过 register_search_provider 注册, 或直接放 ext/tools/ 下自动加载。

用法(LLM 调用):
  search({"query": "...", "engine": "github"})     # 指定引擎
  search({"query": "...", "engine": "web"})        # 默认 Bing
  search({"query": "...", "engine": "all"})        # 所有引擎并行

用法(代码注册新搜索源):
  from ext.tools.search_hub import register_provider, SearchProvider
  register_provider(SearchProvider(name="xiaohongshu", search_fn=fn, desc="..."))
"""
import re
from html import unescape
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from prism.agent_loop import Tool


# ── 搜索源注册表 ──────────────────────────────────────

class SearchProvider:
    """一个搜索源。name=引擎名, search_fn=query+num->str, desc=描述。"""
    def __init__(self, name: str, search_fn, desc: str = ""):
        self.name = name
        self.search_fn = search_fn
        self.desc = desc


_PROVIDERS: dict[str, SearchProvider] = {}


def register_provider(provider: SearchProvider) -> None:
    """注册一个搜索源。"""
    _PROVIDERS[provider.name] = provider


def list_providers() -> list[str]:
    """列出所有已注册的搜索源。"""
    return sorted(_PROVIDERS.keys())


# ── 内置: Bing web 搜索 ───────────────────────────────

def _bing_search(query: str, num_results: int = 5) -> str:
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

    pattern = r'<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>\s*</h2>'
    matches = re.findall(pattern, html, re.DOTALL)

    snippets_raw = re.findall(
        r'b_lineclamp[0-9]?[^>]*>(.*?)</p>', html, re.DOTALL
    )
    snippets = [
        unescape(re.sub(r"<[^>]+>", "", s)).strip() for s in snippets_raw
    ]

    for i, (link, title_html) in enumerate(matches):
        if len(results) >= num_results:
            break
        link = unescape(link)
        title = unescape(re.sub(r"<[^>]+>", "", title_html)).strip()
        if not title or not link:
            continue
        snip = snippets[i] if i < len(snippets) else ""
        results.append(f"**{title}**\n{link}\n{snip}")

    if not results:
        return "[无结果] 搜索解析失败"
    return "\n\n---\n\n".join(results)


# 注册内置 Bing
register_provider(SearchProvider(
    name="web",
    search_fn=_bing_search,
    desc="Bing 网络搜索。返回标题、链接和摘要。通用信息查找。",
))


# ── 统一 search 工具 ──────────────────────────────────

def _search_execute(args):
    query = args.get("query", "")
    num = args.get("num_results", 5)
    engine = args.get("engine", "web")

    if not query:
        return "[error] query 不能为空"

    # 单引擎
    if engine != "all":
        provider = _PROVIDERS.get(engine)
        if not provider:
            available = ", ".join(list_providers())
            return f"[error] 未知引擎 '{engine}'。可用: {available}"
        try:
            result = provider.search_fn(query, num)
            return f"[{engine}]\n\n{result}"
        except Exception as e:
            return f"[error] {engine}: {type(e).__name__}: {e}"

    # 全引擎并行
    all_results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(p.search_fn, query, num): name
            for name, p in _PROVIDERS.items()
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                all_results.append(f"=== [{name}] ===\n{result}")
            except Exception as e:
                all_results.append(f"=== [{name}] ===\n[error] {type(e).__name__}: {e}")

    return "\n\n".join(all_results)


def _build_description() -> str:
    providers = list_providers()
    engine_list = ", ".join(providers)
    return (
        f"统一搜索工具。可用引擎: {engine_list}。"
        "用 engine 参数指定引擎(默认 web)。engine=all 时并行搜索所有引擎。"
        "不同引擎擅长不同: web=通用搜索, github=GitHub API 精确查询。"
    )


_search_tool = Tool(
    name="search",
    description=_build_description(),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词",
            },
            "engine": {
                "type": "string",
                "description": "搜索引擎。默认 web, 可选: github, all 等。",
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


def _consume_pending_providers():
    """扫描已加载的 ext/tools 模块, 消费 _PENDING_PROVIDERS 延迟队列。"""
    import sys
    for mod_name, mod in list(sys.modules.items()):
        pending = getattr(mod, "_PENDING_PROVIDERS", None)
        if pending and isinstance(pending, list):
            for p in pending:
                register_provider(SearchProvider(**p))
            pending.clear()


def register(registry):
    _consume_pending_providers()
    registry.tool(_search_tool)
