"""QQ 空间网页 CGI 的最小客户端: 取 cookie, 读说说列表, 发评论.

登录态来自同一实例的 NapCat: ``get_cookies`` 指定空间域名即可拿到带 ``p_skey`` 的 cookie,
不另外扫码, 也不保存密码. cookie 只在内存里缓存 30 分钟, 登录态失效时立即丢弃重取.
接口地址与参数取自公开的社区资料, 腾讯没有文档, 字段需复核 (docs/providers/qq-zone.md 7).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

import requests

from hx_email.server.router.provider import SendResult, SendStatus
from hx_email.server.router.providers.impl.qq_types import OneBotCaller, OneBotCallResult
from hx_email.server.router.providers.impl.qzone.qzone_contract import (
    COMMENTS_PER_POST,
    COOKIE_DOMAIN,
    POSTS_PER_POLL,
    REQUEST_TIMEOUT_SECONDS,
    QzoneError,
    classify,
    decode_body,
    g_tk,
    parse_cookies,
    uin_of,
)
from hx_email.server.router.providers.impl.qzone.qzone_events import (
    JsonDict,
    Target,
    as_dict,
    as_list,
)

LIST_URL: Final[str] = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6"
)
COMMENT_URL: Final[str] = (
    "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds"
)
COOKIE_TTL_SECONDS: Final[float] = 1800.0
USER_AGENT: Final[str] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class HttpResponse(Protocol):
    status_code: int
    text: str


class HttpClient(Protocol):
    def get(self, url: str, **kwargs: object) -> HttpResponse: ...

    def post(self, url: str, **kwargs: object) -> HttpResponse: ...


@dataclass(frozen=True)
class Credentials:
    cookie: str
    token: int
    uin: str
    fetched_at: float


def failure(status: SendStatus, code: str, message: str) -> QzoneError:
    """超时是 unknown (评论可能已经发出, 不重发), 连不上与 5xx 可重试, 其余失败."""
    result = SendResult(status, retryable=status == "retry", error_code=code, error_message=message)
    return QzoneError(message, result)


class QzoneClient:
    """一个 QQ 账号的空间访问; 线程安全由调用方保证 (分发与轮询各自串行)."""

    def __init__(
        self,
        caller: OneBotCaller,
        http: HttpClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.caller: OneBotCaller = caller
        self.http: HttpClient = http or requests.Session()  # type: ignore[assignment]
        self.clock: Callable[[], float] = clock
        self.cached: Credentials | None = None

    def credentials(self) -> Credentials:
        now: float = self.clock()
        if self.cached is not None and now - self.cached.fetched_at < COOKIE_TTL_SECONDS:
            return self.cached
        result: OneBotCallResult = self.caller.call_action("get_cookies", {"domain": COOKIE_DOMAIN})
        if result.transport != "ok":
            raise failure("retry", "provider_unreachable", f"get_cookies: {result.transport}")
        cookie: str = str(as_dict(result.data).get("cookies") or "")
        jar: dict[str, str] = parse_cookies(cookie)
        if result.retcode != 0 or not jar.get("p_skey") or not uin_of(jar):
            raise failure("failed", "provider_auth", "NapCat returned no Qzone p_skey cookie")
        self.cached = Credentials(cookie, g_tk(jar["p_skey"]), uin_of(jar), now)
        return self.cached

    def call(self, method: str, url: str, **kwargs: object) -> dict[str, object]:
        creds: Credentials = self.credentials()
        headers: dict[str, str] = {
            "Cookie": creds.cookie,
            "User-Agent": USER_AGENT,
            "Referer": f"https://user.qzone.qq.com/{creds.uin}",
        }
        try:
            send = self.http.get if method == "GET" else self.http.post
            response: HttpResponse = send(
                url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs
            )
        except requests.Timeout as error:
            raise failure("unknown", "delivery_unknown", f"qzone timeout: {error}") from error
        except requests.RequestException as error:
            raise failure("retry", "provider_unreachable", str(error)) from error
        if response.status_code >= 500:
            raise failure("retry", "provider_unavailable", f"qzone http {response.status_code}")
        try:
            body: dict[str, object] = decode_body(response.text)
        except ValueError as error:
            raise failure("failed", "provider_error", str(error)) from error
        verdict: SendResult | None = classify(body)
        if verdict is not None:
            if verdict.error_code == "provider_auth":
                self.cached = None
            raise QzoneError(verdict.error_message, verdict)
        return body

    def list_posts(self, owner: str) -> list[JsonDict]:
        """``owner`` 空间最新的几条说说, 带最新评论与二级回复."""
        creds: Credentials = self.credentials()
        params: dict[str, object] = {
            "uin": owner,
            "hostUin": owner,
            "ftype": 0,
            "sort": 0,
            "pos": 0,
            "num": POSTS_PER_POLL,
            "replynum": COMMENTS_PER_POST,
            "need_private_comment": 1,
            "format": "json",
            "g_tk": creds.token,
        }
        body: dict[str, object] = self.call("GET", LIST_URL, params=params)
        return as_list(body.get("msglist"))

    def comment(self, target: Target, text: str) -> str:
        """发一级评论, 或在 ``target.comment_tid`` 下回复; 返回新评论的平台 id."""
        creds: Credentials = self.credentials()
        form: dict[str, object] = {
            "topicId": f"{target.owner}_{target.tid}__1",
            "feedsType": 100,
            "inCharset": "utf-8",
            "outCharset": "utf-8",
            "plat": "qzone",
            "source": "ic",
            "hostUin": target.owner,
            "uin": creds.uin,
            "platformid": 50,
            "format": "json",
            "ref": "feeds",
            "content": text,
            "richval": "",
            "richtype": "",
            "private": 0,
            "paramstr": 2 if target.comment_tid else 1,
            "qzreferrer": f"https://user.qzone.qq.com/{creds.uin}",
        }
        if target.comment_tid:
            form["commentId"] = target.comment_tid
            form["commentUin"] = target.comment_uin
        body: dict[str, object] = self.call(
            "POST", COMMENT_URL, params={"g_tk": creds.token}, data=form
        )
        new_id: str = str(as_dict(body.get("data")).get("commentid") or body.get("commentid") or "")
        if target.comment_tid:
            return f"qzr:{target.tid}:{target.comment_tid}:{new_id or 'new'}:{creds.uin}"
        return f"qzc:{target.tid}:{new_id or 'new'}:{creds.uin}"
