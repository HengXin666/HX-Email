"""GitHub 写动作的 provider 单元测试: review_submit, discussion_create, discussion_comment_create.

HTTP 与 GraphQL 都走 FakeTransport, 不碰网络.
"""

from __future__ import annotations

from hx_email.server.router.provider import ActionCall, SessionRef
from hx_email.server.router.providers.github import GitHubAppProvider
from hx_email.server.router.providers.impl.github.github_http import (
    HttpResponse,
    TransportTimeoutError,
)

from tests.test_router_github_actions import CONFIG, FakeTransport, gql, ref

REPO = SessionRef("github:7:repo:hx/HX-Email", "github", 7, "repo", "hx/HX-Email", "")
DISCUSSION = SessionRef(
    "github:7:discussion:hx/HX-Email#5", "github", 7, "discussion", "hx/HX-Email#5", ""
)
PULL = gql({"repository": {"issueOrPullRequest": {"__typename": "PullRequest"}}})
ISSUE = gql({"repository": {"issueOrPullRequest": {"__typename": "Issue"}}})
CREATE = {"title": "发布计划", "body": "大家看看", "category": "ideas"}


def provider_with(transport: FakeTransport) -> GitHubAppProvider:
    return GitHubAppProvider(lambda _iid: CONFIG, transport)


def categories(page: int) -> HttpResponse:
    if page == 1:
        nodes = [{"id": "DIC_1", "name": "General", "slug": "general"}]
        info = {"hasNextPage": True, "endCursor": "c1"}
    else:
        nodes = [{"id": "DIC_2", "name": "Ideas", "slug": "ideas"}]
        info = {"hasNextPage": False, "endCursor": "c2"}
    connection = {"pageInfo": info, "nodes": nodes}
    return gql({"repository": {"id": "R_1", "discussionCategories": connection}})


def test_review_submit_posts_review_after_pull_check() -> None:
    transport = FakeTransport()
    transport.add_gql("issueOrPullRequest", PULL)
    transport.add("POST", "/pulls/42/reviews", HttpResponse(200, {}, {"id": 801}))
    result = provider_with(transport).invoke(
        ref(42), ActionCall("d_r1", "review_submit", {"event": "APPROVE"})
    )
    assert result.status == "sent" and result.platform_message_id == "rv:801"
    assert transport.posted("/pulls/42/reviews") == [
        {"event": "APPROVE", "body": "<!-- hx-router delivery=d_r1 -->"}
    ]
    assert transport.gql_variables("issueOrPullRequest") == [
        {"owner": "hx", "name": "HX-Email", "number": 42}
    ]


def test_review_submit_refuses_plain_issue_and_times_out_unknown() -> None:
    transport = FakeTransport()
    transport.add_gql("issueOrPullRequest", ISSUE)
    plain = provider_with(transport).invoke(
        ref(42), ActionCall("d_r2", "review_submit", {"event": "COMMENT", "body": "x"})
    )
    assert plain.status == "failed" and plain.error_code == "invalid_payload"
    assert transport.posted("/reviews") == []
    transport.add_gql("issueOrPullRequest", PULL)
    transport.add("POST", "/pulls/42/reviews", TransportTimeoutError("slow"))
    slow = provider_with(transport).invoke(
        ref(42), ActionCall("d_r3", "review_submit", {"event": "REQUEST_CHANGES", "body": "改"})
    )
    assert slow.status == "unknown" and slow.error_code == "delivery_unknown"
    assert transport.posted("/pulls/42/reviews")[-1] == {
        "event": "REQUEST_CHANGES",
        "body": "改\n\n<!-- hx-router delivery=d_r3 -->",
    }


def test_discussion_create_pages_categories_and_matches_slug() -> None:
    transport = FakeTransport()
    transport.add_gql("discussionCategories", categories(1), categories(2))
    created = {"createDiscussion": {"discussion": {"databaseId": 31, "number": 9}}}
    transport.add_gql("createDiscussion", gql(created))
    result = provider_with(transport).invoke(REPO, ActionCall("d_c1", "discussion_create", CREATE))
    assert result.status == "sent" and result.platform_message_id == "dn:31"
    pages = transport.gql_variables("discussionCategories")
    assert [page["after"] for page in pages if isinstance(page, dict)] == [None, "c1"]
    assert transport.gql_variables("createDiscussion") == [
        {
            "input": {
                "repositoryId": "R_1",
                "categoryId": "DIC_2",
                "title": "发布计划",
                "body": "大家看看\n\n<!-- hx-router delivery=d_c1 -->",
            }
        }
    ]


def test_discussion_create_unknown_category_lookup_retry_and_mutation_unknown() -> None:
    transport = FakeTransport()
    transport.add_gql("discussionCategories", categories(2))
    missing = provider_with(transport).invoke(
        REPO, ActionCall("d_c2", "discussion_create", {**CREATE, "category": "Q&A"})
    )
    assert missing.status == "failed" and missing.error_code == "invalid_payload"
    assert transport.gql_variables("createDiscussion") == []
    transport.add_gql("discussionCategories", TransportTimeoutError("slow lookup"))
    lookup = provider_with(transport).invoke(REPO, ActionCall("d_c3", "discussion_create", CREATE))
    assert lookup.status == "retry" and lookup.error_code == "provider_timeout"
    transport.add_gql("discussionCategories", categories(2))
    transport.add_gql("createDiscussion", TransportTimeoutError("slow write"))
    write = provider_with(transport).invoke(REPO, ActionCall("d_c4", "discussion_create", CREATE))
    assert write.status == "unknown" and write.error_code == "delivery_unknown"


def test_discussion_comment_resolves_parent_and_classifies_errors() -> None:
    transport = FakeTransport()
    transport.add_gql("discussion(number", gql({"repository": {"discussion": {"id": "D_9"}}}))
    comments = {
        "pageInfo": {"hasNextPage": False, "endCursor": "x"},
        "nodes": [{"id": "DC_a", "databaseId": 11}, {"id": "DC_b", "databaseId": 12}],
    }
    transport.add_gql("comments(first", gql({"node": {"comments": comments}}))
    added = {"addDiscussionComment": {"comment": {"databaseId": 500}}}
    transport.add_gql("addDiscussionComment", gql(added))
    provider = provider_with(transport)
    reply = provider.invoke(
        DISCUSSION,
        ActionCall("d_k1", "discussion_comment_create", {"body": "同意", "reply_to": "dc:12"}),
    )
    assert reply.status == "sent" and reply.platform_message_id == "dc:500"
    by_node = provider.invoke(
        DISCUSSION,
        ActionCall("d_k2", "discussion_comment_create", {"body": "+1", "reply_to": "DC_a"}),
    )
    assert by_node.status == "sent"
    inputs = [
        v["input"] for v in transport.gql_variables("addDiscussionComment") if isinstance(v, dict)
    ]
    assert inputs == [
        {
            "discussionId": "D_9",
            "body": "同意\n\n<!-- hx-router delivery=d_k1 -->",
            "replyToId": "DC_b",
        },
        {
            "discussionId": "D_9",
            "body": "+1\n\n<!-- hx-router delivery=d_k2 -->",
            "replyToId": "DC_a",
        },
    ]
    stray = provider.invoke(
        DISCUSSION,
        ActionCall("d_k3", "discussion_comment_create", {"body": "x", "reply_to": "dc:99"}),
    )
    assert stray.status == "failed" and stray.error_code == "invalid_payload"
    denied = {
        "errors": [{"type": "FORBIDDEN", "message": "Resource not accessible by integration"}]
    }
    transport.add_gql("addDiscussionComment", HttpResponse(200, {}, denied))
    refused = provider.invoke(
        DISCUSSION, ActionCall("d_k4", "discussion_comment_create", {"body": "x"})
    )
    assert refused.status == "failed" and refused.error_code == "permission_denied"
    transport.add_gql("discussion(number", gql({"repository": {"discussion": None}}))
    gone = provider.invoke(
        DISCUSSION, ActionCall("d_k5", "discussion_comment_create", {"body": "x"})
    )
    assert gone.status == "failed" and gone.error_code == "not_found"
