from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_user
from hx_email.api.impl.workspace.proxy import ProxyTestRequest, test_proxy_connect
from hx_email.api.schemas import GroupCreate, TagCreate, UsableEmailOrganization
from hx_email.api.serializers import serialize_workbench_email, serialize_workbench_overview
from hx_email.config import Settings
from hx_email.server.mail.imap.impl.address_guard import validate_proxy_endpoint
from hx_email.server.workspace.groups import (
    create_group,
    create_tag,
    delete_group,
    delete_groups,
    export_group_accounts_text,
    list_groups,
    list_tags,
    reorder_groups,
    update_group,
)
from hx_email.server.workspace.overview import get_workbench_overview
from hx_email.server.workspace.workbench import (
    list_workbench_emails,
    organize_usable_email,
)


class _GroupIdsRequest(BaseModel):
    group_ids: list[int]


def register_workspace_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/workbench/overview")
    def get_overview(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return serialize_workbench_overview(get_workbench_overview(settings, user.id))

    @router.post("/groups", status_code=status.HTTP_201_CREATED)
    def create_user_group(
        payload: GroupCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if payload.proxy_url.strip():
            try:
                validate_proxy_endpoint(payload.proxy_url)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
        group = create_group(
            settings,
            user.id,
            payload.name,
            payload.color,
            payload.proxy_url,
            payload.notify_enabled,
            payload.polling_enabled,
        )
        return {
            "id": group.id,
            "name": group.name,
            "color": group.color,
            "proxy_url": group.proxy_url,
            "notify_enabled": group.notify_enabled,
            "polling_enabled": group.polling_enabled,
        }

    @router.get("/groups")
    def get_user_groups(
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, object]]:
        user = require_user(settings, authorization)
        return [
            {
                "id": group.id,
                "name": group.name,
                "color": group.color,
                "proxy_url": group.proxy_url,
                "notify_enabled": group.notify_enabled,
                "polling_enabled": group.polling_enabled,
            }
            for group in list_groups(settings, user.id)
        ]

    @router.put("/groups/{group_id}")
    def update_user_group(
        group_id: int,
        payload: GroupCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        if payload.proxy_url.strip():
            try:
                validate_proxy_endpoint(payload.proxy_url)
            except ValueError as error:
                raise HTTPException(status_code=400, detail=str(error)) from error
        group = update_group(
            settings,
            user.id,
            group_id,
            payload.name,
            payload.color,
            payload.proxy_url,
            payload.notify_enabled,
            payload.polling_enabled,
        )
        if group is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        return {
            "id": group.id,
            "name": group.name,
            "color": group.color,
            "proxy_url": group.proxy_url,
            "notify_enabled": group.notify_enabled,
            "polling_enabled": group.polling_enabled,
        }

    @router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_user_group(
        group_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        user = require_user(settings, authorization)
        if not delete_group(settings, user.id, group_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    @router.post("/groups/reorder")
    def reorder_user_groups(
        payload: _GroupIdsRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Persist a new display order for the current user's groups."""
        user = require_user(settings, authorization)
        if not reorder_groups(settings, user.id, payload.group_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="group_ids must contain exactly the user's own group ids",
            )
        return {"success": True}

    @router.post("/groups/batch-delete")
    def delete_user_groups(
        payload: _GroupIdsRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Delete several groups at once (associated emails keep their data)."""
        user = require_user(settings, authorization)
        deleted = delete_groups(settings, user.id, payload.group_ids)
        return {"deleted": deleted}

    @router.get("/groups/{group_id}/export")
    def export_group(
        group_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> Response:
        user = require_user(settings, authorization)
        text = export_group_accounts_text(settings, user.id, group_id)
        if text is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
        headers: dict[str, str] = {
            "Content-Disposition": 'attachment; filename="group-accounts.txt"',
        }
        return Response(text, media_type="text/plain; charset=utf-8", headers=headers)

    @router.post("/groups/proxy-test")
    def test_group_proxy(
        payload: ProxyTestRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """Test whether a proxy URL is reachable via HTTP CONNECT."""
        require_user(settings, authorization)
        return test_proxy_connect(payload.proxy_url.strip())

    @router.post("/tags", status_code=status.HTTP_201_CREATED)
    def create_user_tag(
        payload: TagCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        tag = create_tag(settings, user.id, payload.name, payload.color)
        return {"id": tag.id, "name": tag.name, "color": tag.color}

    @router.get("/tags")
    def get_user_tags(
        authorization: Annotated[str | None, Header()] = None,
    ) -> list[dict[str, object]]:
        user = require_user(settings, authorization)
        return [
            {"id": tag.id, "name": tag.name, "color": tag.color}
            for tag in list_tags(settings, user.id)
        ]

    @router.get("/workbench/usable-emails")
    def get_workbench_usable_emails(
        authorization: Annotated[str | None, Header()] = None,
        kind: str | None = None,
        status: str | None = None,
        group_id: int | None = None,
        tag_id: int | None = None,
        keyword: str | None = None,
        platform_binding: str | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        result = list_workbench_emails(
            settings,
            user.id,
            kind=kind,
            status=status,
            group_id=group_id,
            tag_id=tag_id,
            keyword=keyword,
            platform_binding=platform_binding,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            page_size=page_size,
        )
        return {
            "usable_emails": [serialize_workbench_email(email) for email in result.usable_emails],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }

    @router.put("/usable-emails/{usable_email_id}/organize")
    def organize_email(
        usable_email_id: int,
        payload: UsableEmailOrganization,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        usable_email = organize_usable_email(
            settings,
            user.id,
            usable_email_id,
            payload.label,
            payload.group_id,
            payload.tag_ids,
        )
        if usable_email is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return serialize_workbench_email(usable_email)
