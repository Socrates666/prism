"""ext/tools/search_providers_template.py — 搜索源模板(参考)。

复制此文件, 改名为如 zhihu_search.py / bilibili_search.py / xhs_search.py,
实现 _xxx_search 函数即可自动注册为 search 工具的引擎。

模式: 不注册 Tool, 只往 _PENDING_PROVIDERS 加 provider dict。
search_hub 加载时会自动消费。

=== 已知平台 API 参考 ===

知乎:
  - 非官方: https://www.zhihu.com/api/v4/search/q (需 cookie)
  - 或用 web 搜索: site:zhihu.com

B站:
  - 非官方: https://api.bilibili.com/x/web-interface/search/type?search_type=video
  - 参数: keyword, page, page_size

小红书:
  - 无公开 API, 建议用 web 搜索: site:xiaohongshu.com

通用模式:
  1. 有 API → 直接调 API, 解析 JSON
  2. 无 API → 用 Bing site: 搜索, 复用 _bing_search
"""
import urllib.request
import urllib.parse
import json

# ── 延迟注册队列 ──────────────────────────────────────
_PENDING_PROVIDERS: list = []

# 外发域名白名单(SSRF 防护): query 来自 LLM, 域名钉死。新增平台时把 API 域名加进来。
_ALLOWED_HOSTS = {"api.bilibili.com"}


def _assert_allowed_url(url: str) -> None:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise ValueError(f"[blocked] 非白名单请求目标: {parts.scheme}://{parts.hostname}")


# === 示例: B站搜索 (非官方 API) ===
def _bilibili_search(query: str, num_results: int = 5) -> str:
    """B站视频搜索。用非官方 API, 可能不稳定。"""
    api_url = (
        "https://api.bilibili.com/x/web-interface/search/type"
        f"?search_type=video&keyword={urllib.parse.quote(query)}"
        f"&page_size={num_results}&page=1"
    )
    _assert_allowed_url(api_url)
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    items = data.get("data", {}).get("result", [])
    if not items:
        return "[无结果]"

    lines = []
    for item in items[:num_results]:
        title = item.get("title", "").replace("<em class=\"keyword\">", "").replace("</em>", "")
        bvid = item.get("bvid", "")
        play = item.get("play", 0)
        up = item.get("author", "?")
        desc = item.get("description", "")[:100]
        url = f"https://www.bilibili.com/video/{bvid}" if bvid else ""
        lines.append(
            f"**{title}** ▶{play:,} UP:{up}\n"
            f"{desc}\n{url}"
        )

    return "\n\n---\n\n".join(lines)


# === 示例: 知乎搜索 (用 Bing site: 间接搜索) ===
def _zhihu_search(query: str, num_results: int = 5) -> str:
    """知乎内容搜索。用 Bing site:zhihu.com 间接搜索。"""
    from ext.tools.search_hub import _bing_search
    return _bing_search(f"site:zhihu.com {query}", num_results)


# 注册到延迟队列(取消注释即可启用)
# _PENDING_PROVIDERS.append({
#     "name": "bilibili",
#     "search_fn": _bilibili_search,
#     "desc": "B站视频搜索。用非官方 API。",
# })
# _PENDING_PROVIDERS.append({
#     "name": "zhihu",
#     "search_fn": _zhihu_search,
#     "desc": "知乎内容搜索(通过 Bing site: 间接)。",
# })


def register(registry):
    """被 load_ext 调用。只标记延迟 provider, 不注册 Tool。"""
    import sys
    hub = sys.modules.get("ext.tools.search_hub")
    if hub and hasattr(hub, "register_provider"):
        for p in _PENDING_PROVIDERS:
            hub.register_provider(hub.SearchProvider(**p))
        _PENDING_PROVIDERS.clear()
