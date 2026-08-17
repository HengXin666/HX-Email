"""Heuristic discovery of Lagrange.OneBot release URLs (proxy-aware, zero-config).

发现顺序(全程走调用方代理, 不读环境变量, 无需用户配置):
A. GitHub API (best-effort, 限流/404 自动跳过)
B. expanded_assets/nightly (唯一滚动发布通道, 服务端直出 HTML)
C. releases/latest 页面内嵌 JSON
D. releases.atom 订阅源
E. 直连兜底(nightly 当前命名, HEAD 校验存在后返回)
"""

from __future__ import annotations

import platform
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
NIGHTLY_TAG: str = "nightly"
_REQUEST_TIMEOUT: float = 30.0
_ATOM_NS: str = "{http://www.w3.org/2005/Atom}"
# 直连兜底用的已知命名后缀(net9.0 为当前命名, 按时间先后探测, 未来升级也能命中)。
_PINNED_NIGHTLY_SUFFIXES: tuple[str, ...] = (
    "_net9.0_SelfContained",
    "_net8.0_SelfContained",
    "_net10.0_SelfContained",
)


def default_asset_rid() -> str:
    """Map the current platform to a Lagrange.OneBot release asset RID."""
    machine: str = sys.platform
    arch: str = "x64" if sys.maxsize > 2**32 else "x86"
    native: str = platform.machine().lower()
    if machine.startswith("linux"):
        if native in ("aarch64", "arm64"):
            return "linux-arm64"
        if native.startswith("arm"):
            return "linux-arm"
        return f"linux-{arch}"
    if machine.startswith("win"):
        return f"win-{arch}"
    if machine.startswith("darwin"):
        return "osx-arm64" if native in ("aarch64", "arm64") else "osx-x64"
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
    """发现最新 Release 的平台资产: API > nightly 资产页 > 页面/订阅源 > 直连兜底."""
    rid: str = default_asset_rid()
    headers: dict[str, str] = {"User-Agent": GITHUB_USER_AGENT}
    diags: list[str] = []

    api_diag: str
    api_diag, api_url = _api_asset_url(headers, rid, proxy_url)
    if api_url:
        return api_url
    diags.append(f"API {api_diag}")

    # nightly 滚动通道的 expanded_assets 服务端直出 HTML, 不依赖 API/JS 渲染。
    try:
        nightly_url: str = _pick_asset_from_expanded(NIGHTLY_TAG, headers, rid, proxy_url)
        if nightly_url:
            return nightly_url
        diags.append("nightly 资产页无匹配资产")
    except requests.RequestException as error:
        diags.append(f"nightly 资产页失败({error})")

    try:
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
        diags.append("latest 页面无匹配资产")
    except requests.RequestException as error:
        diags.append(f"latest 页面失败({error})")

    try:
        tag = _extract_tag_from_atom(headers, proxy_url)
        if tag:
            asset_url = _pick_asset_from_expanded(tag, headers, rid, proxy_url)
            if asset_url:
                return asset_url
        diags.append("订阅源无匹配资产")
    except requests.RequestException as error:
        diags.append(f"订阅源失败({error})")

    # 最后兜底: nightly 直连地址稳定, HEAD 校验存在后才返回, 不给出失效地址。
    for pinned in _pinned_nightly_urls(rid):
        if _probe_url(pinned, headers, proxy_url):
            return pinned
    diags.append("直连兜底地址不可用")

    raise RuntimeError("GitHub 接口/页面/订阅源均不可用: " + ";".join(diags))


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
        filename.startswith(LAGRANGE_ASSET_PREFIX)
        and rid in filename
        and filename.endswith((".zip", ".tar.gz", ".tgz"))
    )


def _pinned_nightly_urls(rid: str) -> list[str]:
    """Build candidate direct download URLs for the stable nightly channel."""
    ext: str = ".zip" if rid.startswith("win") else ".tar.gz"
    base: str = f"{LAGRANGE_RELEASE_BASE}/{NIGHTLY_TAG}/{LAGRANGE_ASSET_PREFIX}{rid}"
    return [f"{base}{suffix}{ext}" for suffix in _PINNED_NIGHTLY_SUFFIXES]


def _probe_url(url: str, headers: dict[str, str], proxy_url: str) -> bool:
    """Verify a download URL exists (HEAD first, streaming GET as fallback)."""
    proxies: dict[str, str] | None = proxies_for(proxy_url)
    try:
        response: requests.Response = requests.head(
            url,
            headers=headers,
            allow_redirects=True,
            timeout=_REQUEST_TIMEOUT,
            proxies=proxies,
        )
        return response.status_code == 200
    except requests.RequestException:
        pass
    try:
        with requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=_REQUEST_TIMEOUT,
            proxies=proxies,
        ) as response:
            return response.status_code == 200
    except requests.RequestException:
        return False


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
    """Resolve engine URL; 多通道自动发现 + 直连兜底, 全程可走代理, 无需用户配置."""
    proxy_hint: str = "已配置代理" if proxy_url.strip() else "未配置代理(直连)"
    try:
        return discover_latest_asset_url(proxy_url)
    except (requests.RequestException, RuntimeError) as error:
        raise RuntimeError(
            f"无法获取 QQ 引擎最新版本({proxy_hint}): {error}. 请检查网络/代理后重试"
        ) from error
