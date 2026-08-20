from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

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
from hx_email.server.workspace.impl.recognition import (
    PlatformRule,
    accept_scan_item,
    create_rule,
    delete_rule,
    list_rules,
    scan_historical_messages,
    update_rule,
)
from hx_email.server.workspace.platforms import (
    DuplicatePlatformBindingError,
    DuplicatePlatformNameError,
    InvalidPlatformBindingStatusError,
    create_platform,
    create_platform_binding,
    delete_platform,
    list_platform_bindings,
    list_platforms,
    suggest_platform_candidates,
    update_platform,
    update_platform_binding,
)


class PlatformRuleWrite(BaseModel):
    name: str = ""
    match_field: str = "domain"
    match_type: str = "contains"
    pattern: str = ""
    platform_name: str = ""
    enabled: bool = True


class PlatformScanAcceptRequest(BaseModel):
    platform: str = Field(min_length=1)
    usable_email_ids: list[int] = []


def rule_dict(rule: PlatformRule) -> dict[str, object]:
    return asdict(rule)


def register_platform_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/platforms", status_code=status.HTTP_201_CREATED)
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

    @router.get("/platforms")
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

    @router.put("/platforms/{platform_id}")
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

    @router.delete("/platforms/{platform_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_user_platform(
        platform_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        user = require_user(settings, authorization)
        if not delete_platform(settings, user.id, platform_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Platform not found")

    @router.post("/platform-candidates")
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

    register_platform_rule_routes(router, settings)
    register_platform_scan_routes(router, settings)
    register_platform_binding_routes(router, settings)


def register_platform_rule_routes(router: APIRouter, settings: Settings) -> None:
    @router.get("/platform-rules")
    def get_platform_rules(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {"rules": [rule_dict(rule) for rule in list_rules(settings, user.id)]}

    @router.post("/platform-rules", status_code=status.HTTP_201_CREATED)
    def create_user_platform_rule(
        payload: PlatformRuleWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            rule = create_rule(
                settings,
                user.id,
                name=payload.name,
                match_field=payload.match_field,
                match_type=payload.match_type,
                pattern=payload.pattern,
                platform_name=payload.platform_name,
                enabled=payload.enabled,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return rule_dict(rule)

    @router.put("/platform-rules/{rule_id}")
    def update_user_platform_rule(
        rule_id: int,
        payload: PlatformRuleWrite,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            rule = update_rule(
                settings,
                user.id,
                rule_id,
                name=payload.name,
                match_field=payload.match_field,
                match_type=payload.match_type,
                pattern=payload.pattern,
                platform_name=payload.platform_name,
                enabled=payload.enabled,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if rule is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")
        return rule_dict(rule)

    @router.delete("/platform-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_user_platform_rule(
        rule_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        user = require_user(settings, authorization)
        if not delete_rule(settings, user.id, rule_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")


def register_platform_scan_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/platforms/scan")
    def scan_platforms(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        """一键识别全部历史邮件, 返回按规则/域名聚合的平台候选。"""
        user = require_user(settings, authorization)
        items = [
            {
                **asdict(item),
                "senders": list(item.senders),
                "usable_email_ids": list(item.usable_email_ids),
            }
            for item in scan_historical_messages(settings, user.id)
        ]
        return {"items": items}

    @router.post("/platforms/scan/accept")
    def accept_platform_scan(
        payload: PlatformScanAcceptRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        """把识别出的平台纳入平台目录并创建绑定(用户显式确认)。"""
        user = require_user(settings, authorization)
        try:
            return accept_scan_item(
                settings,
                user.id,
                payload.platform,
                list(payload.usable_email_ids),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error


def register_platform_binding_routes(router: APIRouter, settings: Settings) -> None:
    @router.post(
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

    @router.get("/usable-emails/{usable_email_id}/platform-bindings")
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

    @router.put("/platform-bindings/{binding_id}")
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
