from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    PlatformBindingCreate,
    PlatformBindingUpdate,
    PlatformCandidateRequest,
    PlatformWrite,
)
from hx_email.api.serializers import (
    serialize_platform,
    serialize_platform_binding,
    serialize_platform_candidate,
)
from hx_email.config import Settings
from hx_email.server.workspace.platforms import (
    DuplicatePlatformBindingError,
    DuplicatePlatformNameError,
    InvalidPlatformBindingStatusError,
    create_platform,
    create_platform_binding,
    list_platform_bindings,
    list_platforms,
    suggest_platform_candidates,
    update_platform,
    update_platform_binding,
)


def register_platform_routes(app: FastAPI, settings: Settings) -> None:
    @app.post("/platforms", status_code=status.HTTP_201_CREATED)
    def create_user_platform(
        payload: PlatformWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            platform = create_platform(settings, user.id, payload.name)
        except DuplicatePlatformNameError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        return serialize_platform(platform)

    @app.get("/platforms")
    def get_platforms(
        authorization: Annotated[str | None, Header()] = None,
        q: str | None = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {
            "platforms": [
                serialize_platform(platform) for platform in list_platforms(settings, user.id, q)
            ]
        }

    @app.put("/platforms/{platform_id}")
    def update_user_platform(
        platform_id: int,
        payload: PlatformWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            platform = update_platform(settings, user.id, platform_id, payload.name)
        except DuplicatePlatformNameError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if platform is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")
        return serialize_platform(platform)

    @app.post("/platform-candidates")
    def get_platform_candidates(
        payload: PlatformCandidateRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        require_user(settings, authorization)
        return {
            "platform_candidates": [
                serialize_platform_candidate(candidate)
                for candidate in suggest_platform_candidates(
                    payload.sender, payload.subject, payload.body
                )
            ]
        }

    register_platform_binding_routes(app, settings)


def register_platform_binding_routes(app: FastAPI, settings: Settings) -> None:
    @app.post(
        "/usable-emails/{usable_email_id}/platform-bindings", status_code=status.HTTP_201_CREATED
    )
    def create_user_platform_binding(
        usable_email_id: int,
        payload: PlatformBindingCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            binding = create_platform_binding(
                settings,
                user.id,
                usable_email_id,
                payload.platform_id,
                payload.status,
                payload.notes,
            )
        except DuplicatePlatformBindingError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        except InvalidPlatformBindingStatusError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if binding is None:
            detail = "Usable email or platform not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        return serialize_platform_binding(binding)

    @app.get("/usable-emails/{usable_email_id}/platform-bindings")
    def get_user_platform_bindings(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        bindings = list_platform_bindings(settings, user.id, usable_email_id)
        if bindings is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return {"platform_bindings": [serialize_platform_binding(binding) for binding in bindings]}

    @app.put("/platform-bindings/{binding_id}")
    def update_user_platform_binding(
        binding_id: int,
        payload: PlatformBindingUpdate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            binding = update_platform_binding(
                settings,
                user.id,
                binding_id,
                payload.status,
                payload.notes,
            )
        except InvalidPlatformBindingStatusError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if binding is None:
            detail = "Platform binding not found"
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
        return serialize_platform_binding(binding)
