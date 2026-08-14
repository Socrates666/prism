"""ext/tools/github_search.py — GitHub 搜索源。

用 GitHub Search API 精确查询仓库。
作为 search 工具的 engine=github, 不独立暴露为 Tool。

加载顺序: github_search(g) 先于 search_hub(s) 加载。
通过 _PENDING_PROVIDERS 延迟注册, search_hub 加载时自动消费。
"""
import json
import urllib.request
import urllib.parse
import os

# ── 延迟注册队列(全局, search_hub 加载时消费) ──────────
_PENDING_PROVIDERS: list = []

# 外发域名白名单(SSRF 防护): query 来自 LLM, 域名钉死
_ALLOWED_HOSTS = {"api.github.com"}


def _assert_allowed_url(url: str) -> None:
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    if parts.scheme != "https" or (parts.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise ValueError(f"[blocked] 非白名单请求目标: {parts.scheme}://{parts.hostname}")


def _github_search(query: str, num_results: int = 5) -> str:
    """GitHub API 搜索仓库。query 直接传给 GitHub Search API。"""
    api_url = (
        "https://api.github.com/search/repositories?q="
        + urllib.parse.quote(query)
        + f"&sort=stars&order=desc&per_page={min(num_results, 30)}"
    )
    _assert_allowed_url(api_url)

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Prism-Agent",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())

    repos = data.get("items", [])
    if not repos:
        return "[无结果]"

    lines = []
    for repo in repos[:num_results]:
        name = repo["full_name"]
        stars = repo["stargazers_count"]
        desc = (repo["description"] or "(无描述)")[:120]
        lang = repo.get("language") or "?"
        url = repo["html_url"]
        topics = ", ".join(repo.get("topics", [])[:5])
        lines.append(
            f"**{name}** ⭐{stars:,} [{lang}]\n"
            f"{desc}\n"
            f"{url}"
            + (f"\nTopics: {topics}" if topics else "")
        )

    return "\n\n---\n\n".join(lines)


# 注册到延迟队列
_PENDING_PROVIDERS.append({
    "name": "github",
    "search_fn": _github_search,
    "desc": "GitHub API 搜索仓库。精确查询, 按 stars 排序。适合找开源项目。",
})


def register(registry):
    """被 load_ext 调用。不注册 Tool, 只标记延迟 provider。

    search_hub 的 register() 会扫描所有已加载模块的 _PENDING_PROVIDERS。
    """
    # 如果 search_hub 已经加载(不太可能, 但防御), 直接注册
    import sys
    hub = sys.modules.get("ext.tools.search_hub")
    if hub and hasattr(hub, "register_provider"):
        for p in _PENDING_PROVIDERS:
            hub.register_provider(hub.SearchProvider(**p))
        _PENDING_PROVIDERS.clear()
