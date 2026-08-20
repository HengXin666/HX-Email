"""Platform recognition rule routes (CRUD + JSON 导入/导出分享)。

规则: 一个平台可配多个匹配模式(patterns), 支持 from/domain/subject/body x
contains/exact/regex; 导出为纯数据 JSON 便于用户间分享, 导入按策略去重。
"""

from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.workspace.impl.rules_store import (
    PlatformRule,
    create_rule,
    delete_rule,
    export_rules,
    import_rules,
    list_rules,
    update_rule,
)


class PlatformRuleWrite(BaseModel):
    name: str = ""
    match_field: str = "domain"
    match_type: str = "contains"
    pattern: str = ""  # 兼容单模式导入
    patterns: list[str] = []
    platform_name: str = ""
    enabled: bool = True


class PlatformRuleImportRequest(BaseModel):
    rules: list[dict[str, Any]] = []
    strategy: str = "skip"


def rule_dict(rule: PlatformRule) -> dict[str, object]:
    return asdict(rule)


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
        patterns = payload.patterns or ([payload.pattern] if payload.pattern else [])
        try:
            rule = create_rule(
                settings,
                user.id,
                name=payload.name,
                match_field=payload.match_field,
                match_type=payload.match_type,
                patterns=patterns,
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
        patterns = payload.patterns or ([payload.pattern] if payload.pattern else [])
        try:
            rule = update_rule(
                settings,
                user.id,
                rule_id,
                name=payload.name,
                match_field=payload.match_field,
                match_type=payload.match_type,
                patterns=patterns,
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

    @router.get("/platform-rules/export")
    def export_user_platform_rules(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {"rules": export_rules(settings, user.id)}

    @router.post("/platform-rules/import")
    def import_user_platform_rules(
        payload: PlatformRuleImportRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, int]:
        user = require_user(settings, authorization)
        if payload.strategy not in ("skip", "replace"):
            raise HTTPException(status_code=422, detail="strategy 仅支持 skip/replace")
        try:
            return import_rules(settings, user.id, payload.rules, payload.strategy)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
