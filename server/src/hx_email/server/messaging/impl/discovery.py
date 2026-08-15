"""Heuristic discovery of Lagrange.OneBot release URLs (proxy-aware).

发现顺序 (全程可走调用方传入的代理, 不读环境变量):
A. GitHub 官方 API (JSON, 最可靠; 代理出口一般不限流)
B. releases/latest 页面内嵌 JSON (tag_name + browser_download_url)
C. 拿到 tag 后经 releases/expanded_assets 拉资产列表
D. 页面解析失败时退到 releases.atom 订阅源取最新 tag
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import requests

LAGRANGE_REPO: str = "LagrangeDev/Lagrange.Core"
LAGRANGE_RELEASE_BASE: str = f"https://github.com/{LAGRANGE_REPO}/releases/download"
LAGRANGE_ASSET_PREFIX: str = "Lagrange.OneBot_"
LAGRANGE_API_URL: str = f"https://api.github.com/repos/{LAGRANGE_REPO}/releases/latest"
LATEST_RELEASE_URL: str = f"https://github.com/{LAGRANGE_REPO}/releases/latest"
EXPANDED_ASSETS_URL: str = f"https://github.com/{LAGRANGE_REPO}/releases/expanded_assets/{{tag}}"
RELEASES_ATOM_URL: str = f"https://github.com/{LAGRANGE_REPO}/releases.atom"
GITHUB_USER_AGENT: str = "Mozilla/5.0 (compatible; HX-Email engine installer)"
ENGINE_URL_CACHE_NAME: str = "engine-url.txt"
_REQUEST_TIMEOUT: float = 30.0
_ATOM_NS: str = "{http://www.w3.org/2005/Atom}"


def default_asset_rid() -> str:
    """Map the current platform to a Lagrange.OneBot release asset RID."""
    machine: str = sys.platform
    arch: str = "x64" if sys.maxsize > 2**32 else "x86"
    if machine.startswith("linux"):
        return f"linux-{arch}"
    if machine.startswith("win"):
        return f"win-{arch}"
    if machine.startswith("darwin"):
        return "osx-x64" if arch == "x64" else "osx-arm64"
    return f"linux-{arch}"


def read_cached_url(path: Path) -> str:
    """Read a previously resolved engine URL from disk."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def write_cached_url(path: Path, url: str) -> None:
    """Persist a successfully resolved engine URL for later starts."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(url, encoding="utf-8")
    except OSError:
        pass


def proxies_for(proxy_url: str) -> dict[str, str] | None:
    """Build a requests proxies dict from a proxy URL (or None when empty)."""
    value: str = proxy_url.strip()
    if not value:
        return None
    return {"http": value, "https": value}


def discover_latest_asset_url(proxy_url: str = "") -> str:
    """发现最新 Release 的平台资产: API > 页面内嵌 JSON > expanded_assets > Atom."""
    rid: str = default_asset_rid()
    headers: dict[str, str] = {"User-Agent": GITHUB_USER_AGENT}
    api_diag: str
    api_diag, api_url = _api_asset_url(headers, rid, proxy_url)
    if api_url:
        return api_url
    page_diag: str = ""
    page: requests.Response = requests.get(
        LATEST_RELEASE_URL,
        headers=headers,
        allow_redirects=True,
        timeout=_REQUEST_TIMEOUT,
        proxies=proxies_for(proxy_url),
    )
    page.raise_for_status()
    page_html: str = page.text
    tag: str = _extract_tag(page_html)
    asset_url: str = _pick_asset_url_from_text(page_html, rid)
    if asset_url:
        return asset_url
    if tag:
        asset_url = _pick_asset_from_expanded(tag, headers, rid, proxy_url)
        if asset_url:
            return asset_url
    tag = tag or _extract_tag_from_atom(headers, proxy_url)
    if tag:
        asset_url = _pick_asset_from_expanded(tag, headers, rid, proxy_url)
        if asset_url:
            return asset_url
    page_diag = "页面/订阅源均无匹配资产"
    raise RuntimeError(f"GitHub 接口与页面均不可用({api_diag}; {page_diag})")


def _api_asset_url(
    headers: dict[str, str],
    rid: str,
    proxy_url: str,
) -> tuple[str, str]:
    """Try the GitHub API (most reliable); returns (diagnostic, url)."""
    try:
        response: requests.Response = requests.get(
            LAGRANGE_API_URL,
            headers={**headers, "Accept": "application/vnd.github+json"},
            timeout=_REQUEST_TIMEOUT,
            proxies=proxies_for(proxy_url),
        )
    except requests.RequestException as error:
        return f"API 请求失败({error})", ""
    if response.status_code == 403:
        return "API 限流(403)", ""
    if response.status_code != 200:
        return f"API HTTP {response.status_code}", ""
    try:
        payload: Any = response.json()
    except ValueError:
        return "API 响应非 JSON", ""
    if not isinstance(payload, dict):
        return "API 响应格式无效", ""
    assets: Any = payload.get("assets", [])
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            url: str = str(asset.get("browser_download_url", ""))
            if url and _asset_matches(url, rid):
                return "ok", url
    return "API 无匹配资产", ""


def _extract_tag(page_html: str) -> str:
    """Extract the latest release tag from page embedded JSON or links."""
    match = re.search(r'"tag_name"\s*:\s*"([^"]+)"', page_html)
    if match:
        return str(match.group(1))
    match = re.search(r"/releases/tag/([^\"'/?]+)", page_html)
    return str(match.group(1)) if match else ""


def _pick_asset_url_from_text(text: str, rid: str) -> str:
    """Pick the platform asset URL from embedded JSON or hrefs in HTML."""
    for raw_url in re.findall(r'"browser_download_url"\s*:\s*"(https://[^"]+)"', text):
        candidate: str = str(raw_url)
        if _asset_matches(candidate, rid):
            return candidate
    for href in re.findall(r'href="([^"]+)"', text):
        if href.startswith(f"/{LAGRANGE_REPO}/releases/download/"):
            candidate = f"https://github.com{href}"
            if _asset_matches(candidate, rid):
                return candidate
    return ""


def _asset_matches(url: str, rid: str) -> bool:
    filename: str = url.rsplit("/", 1)[-1]
    return (
        filename.startswith(LAGRANGE_ASSET_PREFIX) and rid in filename and filename.endswith(".zip")
    )


def _pick_asset_from_expanded(
    tag: str,
    headers: dict[str, str],
    rid: str,
    proxy_url: str = "",
) -> str:
    response: requests.Response = requests.get(
        EXPANDED_ASSETS_URL.format(tag=tag),
        headers=headers,
        timeout=_REQUEST_TIMEOUT,
        proxies=proxies_for(proxy_url),
    )
    response.raise_for_status()
    return _pick_asset_url_from_text(response.text, rid)


def _extract_tag_from_atom(headers: dict[str, str], proxy_url: str = "") -> str:
    """Extract the latest tag from the GitHub releases Atom feed."""
    response: requests.Response = requests.get(
        RELEASES_ATOM_URL,
        headers=headers,
        timeout=_REQUEST_TIMEOUT,
        proxies=proxies_for(proxy_url),
    )
    response.raise_for_status()
    try:
        root: ET.Element = ET.fromstring(response.text)
    except ET.ParseError:
        return ""
    for entry in root.iter(f"{_ATOM_NS}entry"):
        link = entry.find(f"{_ATOM_NS}link")
        if link is None:
            continue
        href: str = str(link.get("href", ""))
        match = re.search(r"/releases/tag/([^/]+)/?$", href)
        if match:
            return str(match.group(1))
    return ""


def resolve_default_download_url(proxy_url: str = "") -> str:
    """Resolve engine URL; API 优先, 页面/订阅源兜底, 全程可走代理."""
    proxy_hint: str = "已配置代理" if proxy_url.strip() else "未配置代理(直连)"
    try:
        return discover_latest_asset_url(proxy_url)
    except (requests.RequestException, RuntimeError) as error:
        raise RuntimeError(
            f"无法获取 QQ 引擎最新版本({proxy_hint}): {error}. 请检查网络/代理后重试"
        ) from error
