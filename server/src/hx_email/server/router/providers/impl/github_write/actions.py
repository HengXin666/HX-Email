"""Route one declared GitHub action to the call that performs it.

``GitHubAppProvider.invoke`` hands every ``ActionCall`` here; the gateway already
checked the action name, target kind and params against ``contract/github_actions.py``.

- ``comment_create``: the provider's own comment path, with the delivery marker
- ``reaction_add``: REST reactions, idempotent on GitHub's side, so a timeout retries
- ``review_submit``: REST ``POST /pulls/{n}/reviews`` after a one-field GraphQL check
  that the number is a pull request; not idempotent, a timeout is ``unknown``
- ``discussion_create``, ``discussion_comment_create``: GraphQL, see discussions.py
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from hx_email.server.router.provider import ActionCall, OutboundPayload, SendResult, SessionRef
from hx_email.server.router.providers.impl.github.github_http import GITHUB_API, failed
from hx_email.server.router.providers.impl.github_reactions import (
    REACTION_PREFIX,
    ReactionRequest,
    reaction_request,
)
from hx_email.server.router.providers.impl.github_write.discussions import (
    discussion_comment_create,
    discussion_create,
)
from hx_email.server.router.providers.impl.github_write.graphql import (
    GitHubCaller,
    GraphQLReply,
    JsonDict,
    dig,
    graphql,
    marked,
    thread_of,
)

REVIEW_PREFIX: Final[str] = "rv"
PULL_CHECK_QUERY: Final[str] = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    issueOrPullRequest(number: $number) { __typename }
  }
}
"""
Handler = Callable[[GitHubCaller, str, int, ActionCall], SendResult]


def review_submit(
    caller: GitHubCaller, address: str, instance_id: int, call: ActionCall
) -> SendResult:
    thread: tuple[str, int] | None = thread_of(address, "issue")
    if thread is None:
        return failed("invalid_payload", f"cannot review {address}")
    repo, number = thread
    owner, name = repo.split("/", 1)
    check: GraphQLReply = graphql(
        caller,
        instance_id,
        repo,
        PULL_CHECK_QUERY,
        {"owner": owner, "name": name, "number": number},
        mutation=False,
    )
    if check.failure is not None:
        return check.failure
    if dig(check.data, "repository", "issueOrPullRequest", "__typename") != "PullRequest":
        return failed("invalid_payload", f"#{number} in {repo} is not a pull request")
    body: JsonDict = {
        "event": call.params.get("event", ""),
        "body": marked(call.params.get("body", ""), call.delivery_id),
    }
    url: str = f"{GITHUB_API}/repos/{repo}/pulls/{number}/reviews"
    return caller.post(instance_id, repo, url, body, REVIEW_PREFIX)


def reaction_add(
    caller: GitHubCaller, address: str, instance_id: int, call: ActionCall
) -> SendResult:
    request: ReactionRequest | None = reaction_request(address, call.params)
    if request is None:
        return failed("invalid_payload", f"cannot react on {address}")
    return caller.post(
        instance_id,
        request.repo_full_name,
        request.url,
        request.body,
        REACTION_PREFIX,
        idempotent=True,
    )


HANDLERS: Final[dict[str, Handler]] = {
    "reaction_add": reaction_add,
    "review_submit": review_submit,
    "discussion_create": discussion_create,
    "discussion_comment_create": discussion_comment_create,
}


# 只做平台调用, 幂等, 整形与熔断在 outbox; 不可幂等的写 (review, discussion) 超时进 unknown
# 决策记录: .agents/notes/implemented/feature/2026-11-09-github-outbound-actions.md
def invoke_github(caller: GitHubCaller, session: SessionRef, call: ActionCall) -> SendResult:
    if call.action == "comment_create":
        payload = OutboundPayload(
            call.delivery_id, call.params.get("text", ""), call.params.get("reply_to", ""), ""
        )
        return caller.send(session, payload)
    handler: Handler | None = HANDLERS.get(call.action)
    if handler is None:
        return failed("action_not_supported", f"github has no action {call.action}")
    return handler(caller, session.address, session.instance_id, call)
