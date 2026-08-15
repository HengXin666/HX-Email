"""Heuristic discovery of Lagrange.OneBot release URLs without GitHub API.

解析 GitHub releases 页面获取最新版本与其资产, 不调用 api.github.com
(未认证限流), 实现「默认自动选最新、最兼容」的引擎安装路径。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

LAGRANGE_REPO: str = "LagrangeDev/Lagrange.Core"
LAGRANGE_RELEASE_BASE: str = f"https://github.com/{LAGRANGE_REPO}/releases/download"
LAGRANGE_ASSET_PREFIX: str = "Lagrange.OneBot_"
LATEST_RELEASE_URL: str = f"https://github.com/{LAGRANGE_REPO}/releases/latest"
EXPANDED_ASSETS_URL: str = f"https://github.com/{LAGRANGE_REPO}/releases/expanded_assets/{{tag}}"
LAGRANGE_PINNED_VERSION: str = "0.18.0"
ENGINE_DOWNLOAD_URL_ENV: str = "HX_EMAIL_QQ_ENGINE_URL"
LAGRANGE_VERSION_ENV: str = "HX_EMAIL_QQ_ENGINE_VERSION"
GITHUB_USER_AGENT: str = "Mozilla/5.0 (compatible; HX-Email engine installer)"
ENGINE_URL_CACHE_NAME: str = "engine-url.txt"
_REQUEST_TIMEOUT: float = 30.0


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


def pinned_url_for(version: str) -> str:
    """Build a direct release download URL for a pinned version."""
    rid: str = default_asset_rid()
    return f"{LAGRANGE_RELEASE_BASE}/{version}/{LAGRANGE_ASSET_PREFIX}{version}_{rid}.zip"


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


def discover_latest_asset_url() -> str:
    """启发式发现最新 Release 的平台资产 (解析页面, 不走 GitHub API)."""
    rid: str = default_asset_rid()
    headers: dict[str, str] = {"User-Agent": GITHUB_USER_AGENT}
    latest: requests.Response = requests.get(
        LATEST_RELEASE_URL,
        headers=headers,
        allow_redirects=True,
        timeout=_REQUEST_TIMEOUT,
    )
    latest.raise_for_status()
    final_url: str = str(latest.url).rstrip("/")
    tag: str = final_url.rsplit("/", 1)[-1]
    if not tag or tag == "releases":
        raise RuntimeError("无法解析 GitHub 最新版本号")
    assets: requests.Response = requests.get(
        EXPANDED_ASSETS_URL.format(tag=tag),
        headers=headers,
        timeout=_REQUEST_TIMEOUT,
    )
    assets.raise_for_status()
    for href in re.findall(r'href="([^"]+)"', assets.text):
        if not href.startswith(f"/{LAGRANGE_REPO}/releases/download/"):
            continue
        filename: str = href.rsplit("/", 1)[-1]
        if (
            filename.startswith(LAGRANGE_ASSET_PREFIX)
            and rid in filename
            and filename.endswith(".zip")
        ):
            return f"{LAGRANGE_RELEASE_BASE}/{tag}/{filename}"
    raise RuntimeError(f"未在最新 Release ({tag}) 中找到适配平台 ({rid}) 的资产")


def resolve_default_download_url() -> str:
    """Resolve engine URL: 环境变量 URL > 环境变量版本 > 最新启发式发现."""
    configured: str = os.environ.get(ENGINE_DOWNLOAD_URL_ENV, "").strip()
    if configured:
        return configured
    version: str = os.environ.get(LAGRANGE_VERSION_ENV, "").strip()
    if version:
        return pinned_url_for(version)
    try:
        return discover_latest_asset_url()
    except (requests.RequestException, RuntimeError) as error:
        raise RuntimeError(
            f"自动发现 QQ 引擎最新版本失败: {error}. 可设置 {ENGINE_DOWNLOAD_URL_ENV} 指定下载地址"
        ) from error
