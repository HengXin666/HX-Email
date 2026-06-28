from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status

from hx_email.api.dependencies import require_user
from hx_email.api.schemas import (
    MailPoolClaimRequest,
    MailPoolCompleteRequest,
    MailPoolEntryCreate,
)
from hx_email.api.serializers import serialize_mail_pool_entry
from hx_email.config import Settings
from hx_email.server.mail.mail_pool import (
    DuplicateMailPoolEntryError,
    add_mail_pool_entry,
    claim_mail_pool_entry,
    complete_mail_pool_entry,
    cooldown_mail_pool_entry,
    list_mail_pool_entries,
    release_mail_pool_entry,
    remove_mail_pool_entry,
)


def register_mail_pool_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/mail-pool/entries", status_code=status.HTTP_201_CREATED)
    def create_mail_pool_entry(
        payload: MailPoolEntryCreate,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        try:
            entry = add_mail_pool_entry(settings, user.id, payload.usable_email_id)
        except DuplicateMailPoolEntryError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return serialize_mail_pool_entry(entry)

    @router.get("/mail-pool/entries")
    def get_mail_pool_entries(
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, list[dict[str, object]]]:
        user = require_user(settings, authorization)
        return {
            "entries": [
                serialize_mail_pool_entry(entry)
                for entry in list_mail_pool_entries(settings, user.id)
            ]
        }

    @router.delete("/mail-pool/entries/{usable_email_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_mail_pool_entry(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> None:
        user = require_user(settings, authorization)
        removed = remove_mail_pool_entry(settings, user.id, usable_email_id)
        if not removed:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mail pool entry not found",
            )

    @router.post("/mail-pool/claim")
    def claim_mail_pool(
        payload: MailPoolClaimRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        entry = claim_mail_pool_entry(settings, user.id, payload.project_key, payload.claim_key)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No usable email available",
            )
        return serialize_mail_pool_entry(entry)

    @router.post("/mail-pool/entries/{usable_email_id}/release")
    def release_mail_pool(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        entry = release_mail_pool_entry(settings, user.id, usable_email_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mail pool entry not found",
            )
        return serialize_mail_pool_entry(entry)

    @router.post("/mail-pool/entries/{usable_email_id}/complete")
    def complete_mail_pool(
        usable_email_id: int,
        payload: MailPoolCompleteRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        entry = complete_mail_pool_entry(settings, user.id, usable_email_id, payload.project_key)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mail pool entry not found",
            )
        return serialize_mail_pool_entry(entry)

    @router.post("/mail-pool/entries/{usable_email_id}/cooldown")
    def cooldown_mail_pool(
        usable_email_id: int,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        entry = cooldown_mail_pool_entry(settings, user.id, usable_email_id)
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Mail pool entry not found",
            )
        return serialize_mail_pool_entry(entry)
