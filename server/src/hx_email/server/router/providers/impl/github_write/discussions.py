"""GitHub Discussions writes: ``discussion_create`` and ``discussion_comment_create``.

Both need GraphQL node ids the router never stores: the repository id and category id
for a new discussion, the discussion id (and optionally the parent comment id) for a
comment. They are looked up on every call, never cached: a category renamed on GitHub
takes effect at once and the process keeps no per-repository state.

A lookup writes nothing, so its failures retry like a connection error. Only the final
mutation can leave the outcome ``unknown``; the body carries the same hidden delivery
marker as REST comments so a later reconcile could find it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from hx_email.server.router.provider import ActionCall, SendResult
from hx_email.server.router.providers.impl.github.github_http import failed
from hx_email.server.router.providers.impl.github_write.graphql import (
    Found,
    GitHubCaller,
    GraphQLReply,
    JsonDict,
    dig,
    find_node,
    graphql,
    marked,
    repo_of,
    thread_of,
)

CATEGORIES_QUERY: Final[str] = """
query($owner: String!, $name: String!, $after: String) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 25, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes { id name slug }
    }
  }
}
"""
CREATE_DISCUSSION: Final[str] = """
mutation($input: CreateDiscussionInput!) {
  createDiscussion(input: $input) { discussion { databaseId number } }
}
"""
DISCUSSION_QUERY: Final[str] = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { discussion(number: $number) { id } }
}
"""
COMMENTS_QUERY: Final[str] = """
query($id: ID!, $after: String) {
  node(id: $id) {
    ... on Discussion {
      comments(first: 50, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes { id databaseId }
      }
    }
  }
}
"""
ADD_COMMENT: Final[str] = """
mutation($input: AddDiscussionCommentInput!) {
  addDiscussionComment(input: $input) { comment { databaseId } }
}
"""


def sent_as(prefix: str, raw_id: object) -> SendResult:
    if raw_id is None or raw_id == "":
        return failed("provider_error", "GitHub answered without the new item's id")
    return SendResult(status="sent", platform_message_id=f"{prefix}:{raw_id}")


def same_category(wanted: str) -> Callable[[JsonDict], bool]:
    folded: str = wanted.strip().casefold()

    def match(node: JsonDict) -> bool:
        names: tuple[str, str] = (str(node.get("name") or ""), str(node.get("slug") or ""))
        return folded in (names[0].casefold(), names[1].casefold())

    return match


def discussion_create(
    caller: GitHubCaller, address: str, instance_id: int, call: ActionCall
) -> SendResult:
    repo: str | None = repo_of(address)
    if repo is None:
        return failed("invalid_payload", f"cannot open a discussion on {address}")
    owner, name = repo.split("/", 1)
    wanted: str = call.params.get("category", "")
    found: Found = find_node(
        caller,
        instance_id,
        repo,
        CATEGORIES_QUERY,
        {"owner": owner, "name": name},
        ("repository", "discussionCategories"),
        same_category(wanted),
    )
    if found.failure is not None:
        return found.failure
    repository_id: object = dig(found.first_page, "repository", "id")
    if not repository_id:
        return failed("not_found", f"{repo} is not visible to the App")
    if found.node is None:
        return failed("invalid_payload", f"{repo} has no discussion category {wanted}")
    reply: GraphQLReply = graphql(
        caller,
        instance_id,
        repo,
        CREATE_DISCUSSION,
        {
            "input": {
                "repositoryId": repository_id,
                "categoryId": found.node.get("id"),
                "title": call.params.get("title", ""),
                "body": marked(call.params.get("body", ""), call.delivery_id),
            }
        },
        mutation=True,
    )
    if reply.failure is not None:
        return reply.failure
    return sent_as("dn", dig(reply.data, "createDiscussion", "discussion", "databaseId"))


def parent_comment(
    caller: GitHubCaller, instance_id: int, repo: str, discussion_id: str, reply_to: str
) -> tuple[str, SendResult | None]:
    """Node id of the parent comment; ``dc:<databaseId>`` is resolved by paging comments."""
    if not reply_to.startswith("dc:"):
        return reply_to, None
    database_id: str = reply_to[3:]
    found: Found = find_node(
        caller,
        instance_id,
        repo,
        COMMENTS_QUERY,
        {"id": discussion_id},
        ("node", "comments"),
        lambda node: str(node.get("databaseId")) == database_id,
    )
    if found.failure is not None:
        return "", found.failure
    if found.node is None:
        return "", failed("invalid_payload", f"no top-level comment {reply_to} in this discussion")
    return str(found.node.get("id") or ""), None


def discussion_comment_create(
    caller: GitHubCaller, address: str, instance_id: int, call: ActionCall
) -> SendResult:
    thread: tuple[str, int] | None = thread_of(address, "discussion")
    if thread is None:
        return failed("invalid_payload", f"cannot comment on {address}")
    repo, number = thread
    owner, name = repo.split("/", 1)
    lookup: GraphQLReply = graphql(
        caller,
        instance_id,
        repo,
        DISCUSSION_QUERY,
        {"owner": owner, "name": name, "number": number},
        mutation=False,
    )
    if lookup.failure is not None:
        return lookup.failure
    discussion_id: object = dig(lookup.data, "repository", "discussion", "id")
    if not discussion_id:
        return failed("not_found", f"discussion #{number} in {repo} is gone")
    request: JsonDict = {
        "discussionId": discussion_id,
        "body": marked(call.params.get("body", ""), call.delivery_id),
    }
    reply_to: str = call.params.get("reply_to", "")
    if reply_to:
        parent, problem = parent_comment(caller, instance_id, repo, str(discussion_id), reply_to)
        if problem is not None:
            return problem
        request["replyToId"] = parent
    reply: GraphQLReply = graphql(
        caller, instance_id, repo, ADD_COMMENT, {"input": request}, mutation=True
    )
    if reply.failure is not None:
        return reply.failure
    return sent_as("dc", dig(reply.data, "addDiscussionComment", "comment", "databaseId"))
