from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import GroupCreate, TagCreate, UsableEmailOrganization
from hx_email.api.serializers import serialize_workbench_email, serialize_workbench_overview
from hx_email.config import Settings
from hx_email.server.workspace.overview import get_workbench_overview
from hx_email.server.workspace.workbench import (
    create_group,
    create_tag,
    list_workbench_emails,
    organize_usable_email,
)


def register_workspace_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/workbench/overview")
    def get_overview(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        return serialize_workbench_overview(get_workbench_overview(settings, user.id))

    @app.post("/groups", status_code=status.HTTP_201_CREATED)
    def create_user_group(
        payload: GroupCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        group = create_group(settings, user.id, payload.name, payload.color)
        return {"id": group.id, "name": group.name, "color": group.color}

    @app.post("/tags", status_code=status.HTTP_201_CREATED)
    def create_user_tag(
        payload: TagCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        tag = create_tag(settings, user.id, payload.name, payload.color)
        return {"id": tag.id, "name": tag.name, "color": tag.color}

    @app.get("/workbench/usable-emails")
    def get_workbench_usable_emails(
        authorization: Annotated[str | None, Header()] = None,
        kind: str | None = None,
        status: str | None = None,
        group_id: int | None = None,
        tag_id: int | None = None,
        keyword: str | None = None,
        platform_binding: str | None = None,
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
            page=page,
            page_size=page_size,
        )
        return {
            "usable_emails": [serialize_workbench_email(email) for email in result.usable_emails],
            "total": result.total,
            "page": result.page,
            "page_size": result.page_size,
        }

    @app.put("/usable-emails/{usable_email_id}/organize")
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
