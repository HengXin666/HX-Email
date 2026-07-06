from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from hx_email.api.dependencies import require_user
from hx_email.config import Settings
from hx_email.server.mail.send_mail import send_debug_email


class SendDebugEmailRequest(BaseModel):
    recipient: str = ""
    subject: str = ""
    body: str = ""


def register_send_email_routes(router: APIRouter, settings: Settings) -> None:
    @router.post("/usable-emails/{usable_email_id}/send-debug-email")
    def send_debug_email_route(
        usable_email_id: int,
        payload: SendDebugEmailRequest,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        user = require_user(settings, authorization)
        result = send_debug_email(
            settings,
            user.id,
            usable_email_id,
            recipient=payload.recipient,
            subject=payload.subject,
            body=payload.body,
        )
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Usable email not found"
            )
        return result.to_dict()
