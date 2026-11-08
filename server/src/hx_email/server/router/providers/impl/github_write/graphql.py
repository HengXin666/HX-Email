"""GitHub GraphQL as one more outbound call, with the same three outcomes as REST.

Discussions have no REST write API, so ``discussion_create`` and
``discussion_comment_create`` go through ``POST /graphql``. The outbox does not care:
this module turns every answer into either data or a ``SendResult``.

- A query (looking up ids) writes nothing, so a timeout is safe to retry.
- A mutation that timed out may have landed: ``unknown``, exactly like a REST write.
- GraphQL answers 200 even for errors; the ``errors`` list is classified here.

Memory: queries ask only for the ids they need and page lists in small fixed pages,
so no answer grows with the size of a repository.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Protocol

from hx_email.server.router.provider import OutboundPayload, SendResult, SessionRef
from hx_email.server.router.providers.impl.github.github_auth import Clock, TokenIssueError
from hx_email.server.router.providers.impl.github.github_http import (
    GITHUB_API,
    HttpResponse,
    TransportConnectError,
    TransportTimeoutError,
    classify_response,
    failed,
    retryable,
)

GRAPHQL_URL: Final[str] = f"{GITHUB_API}/graphql"
MARKER_TEMPLATE: Final[str] = "<!-- hx-router delivery={delivery_id} -->"
MAX_PAGES: Final[int] = 20
RATE_LIMIT_WAIT_SECONDS: Final[int] = 60
JsonDict = dict[str, object]


class GitHubCaller(Protocol):
    """The part of ``GitHubAppProvider`` the action modules use; avoids an import cycle."""

    clock: Clock

    def call(
        self, instance_id: int, repo: str, method: str, url: str, body: JsonDict | None
    ) -> HttpResponse: ...

    def send(self, session: SessionRef, payload: OutboundPayload) -> SendResult: ...

    def post(
        self,
        instance_id: int,
        repo: str,
        url: str,
        body: JsonDict,
        prefix: str,
        *,
        idempotent: bool = False,
    ) -> SendResult: ...


@dataclass(frozen=True)
class GraphQLReply:
    """``data`` when GitHub answered cleanly, otherwise ``failure`` says what the outbox does."""

    data: JsonDict = field(default_factory=dict)
    failure: SendResult | None = None


def marked(body: str, delivery_id: str) -> str:
    """Body plus the hidden delivery marker, so an ``unknown`` write can be found later."""
    marker: str = MARKER_TEMPLATE.format(delivery_id=delivery_id)
    return f"{body}\n\n{marker}" if body else marker


def dig(data: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def thread_of(address: str, kind: str) -> tuple[str, int] | None:
    """``(owner/name, number)`` of a v1 ``issue`` or ``discussion`` address."""
    parts: list[str] = address.split(":", 3)
    if len(parts) != 4 or parts[0] != "github" or parts[2] != kind:
        return None
    repo, sep, number = parts[3].rpartition("#")
    if not sep or "/" not in repo or not number.isdigit():
        return None
    return repo, int(number)


def repo_of(address: str) -> str | None:
    """``owner/name`` of a v1 ``repo`` address."""
    parts: list[str] = address.split(":", 3)
    if len(parts) != 4 or parts[0] != "github" or parts[2] != "repo" or "/" not in parts[3]:
        return None
    return parts[3]


def error_result(errors: list[object]) -> SendResult:
    """Classify GraphQL ``errors``; only rate limiting is worth a retry."""
    first: object = errors[0]
    kind: str = str(dig(first, "type") or "")
    message: str = str(dig(first, "message") or "GraphQL error")
    if kind == "RATE_LIMITED" or "rate limit" in message.lower():
        return SendResult(
            status="retry",
            retryable=True,
            error_code="rate_limited",
            error_message=message,
            retry_after_seconds=RATE_LIMIT_WAIT_SECONDS,
        )
    if kind == "NOT_FOUND":
        return failed("not_found", message)
    if kind == "FORBIDDEN" or "not accessible by integration" in message.lower():
        return failed("permission_denied", message)
    return failed("unprocessable", message)


def graphql(
    caller: GitHubCaller,
    instance_id: int,
    repo: str,
    query: str,
    variables: Mapping[str, object],
    *,
    mutation: bool,
) -> GraphQLReply:
    body: JsonDict = {"query": query, "variables": dict(variables)}
    try:
        response: HttpResponse = caller.call(instance_id, repo, "POST", GRAPHQL_URL, body)
    except TransportTimeoutError as error:
        if mutation:
            unknown = SendResult(
                status="unknown", error_code="delivery_unknown", error_message=str(error)
            )
            return GraphQLReply(failure=unknown)
        return GraphQLReply(failure=retryable("provider_timeout", str(error)))
    except TransportConnectError as error:
        return GraphQLReply(failure=retryable("provider_offline", str(error)))
    except TokenIssueError as error:
        if error.status >= 500:
            return GraphQLReply(failure=retryable("provider_error", str(error)))
        return GraphQLReply(failure=failed("token_invalid", str(error)))
    if response.status != 200:
        now: int = int(caller.clock().timestamp())
        return GraphQLReply(failure=classify_response(response, now, ""))
    answer: JsonDict = response.as_dict()
    errors: object = answer.get("errors")
    if isinstance(errors, list) and errors:
        return GraphQLReply(failure=error_result(errors))
    data: object = answer.get("data")
    return GraphQLReply(data=data if isinstance(data, dict) else {})


@dataclass(frozen=True)
class Found:
    """The first matching node (or None), the first page's data, or why the lookup failed."""

    node: JsonDict | None = None
    first_page: JsonDict = field(default_factory=dict)
    failure: SendResult | None = None


def find_node(
    caller: GitHubCaller,
    instance_id: int,
    repo: str,
    query: str,
    variables: Mapping[str, object],
    path: tuple[str, ...],
    match: Callable[[JsonDict], bool],
) -> Found:
    """Walk a GraphQL connection page by page and stop at the first match.

    Only the current page is held, and at most ``MAX_PAGES`` pages are read, so a
    repository with many categories or comments costs bounded memory and calls.
    """
    first: JsonDict = {}
    after: str | None = None
    for _page in range(MAX_PAGES):
        reply: GraphQLReply = graphql(
            caller, instance_id, repo, query, {**variables, "after": after}, mutation=False
        )
        if reply.failure is not None:
            return Found(failure=reply.failure)
        first = first or reply.data
        connection: object = dig(reply.data, *path)
        page: object = dig(connection, "nodes")
        for item in page if isinstance(page, list) else []:
            if isinstance(item, dict) and match(item):
                return Found(item, first)
        after = str(dig(connection, "pageInfo", "endCursor") or "") or None
        if dig(connection, "pageInfo", "hasNextPage") is not True or after is None:
            break
    return Found(None, first)
