"""Pydantic response models for envelopes and cursor pages (spec 3.1 and 5.4)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from hx_email.server.router.envelope import Envelope


class SenderModel(BaseModel):
    id: str
    name: str = ""
    is_self: bool = False


class AttachmentModel(BaseModel):
    kind: str
    url: str = ""
    name: str = ""
    size: int = 0


class EnvelopeModel(BaseModel):
    id: str
    cursor: str
    platform: str
    instance_id: int
    session: str
    session_type: str
    direction: str
    sender: SenderModel
    text: str
    reply_to: str = ""
    platform_message_id: str
    attachments: list[AttachmentModel] = Field(default_factory=list)
    occurred_at: str
    received_at: str
    raw: dict[str, object] | None = None
    raw_ref: str = ""

    @classmethod
    def from_envelope(cls, envelope: Envelope, include_raw: bool = False) -> EnvelopeModel:
        return cls.model_validate(envelope.to_dict(include_raw=include_raw))


class MessagesPageModel(BaseModel):
    messages: list[EnvelopeModel]
    next_cursor: str
    has_more: bool
    gap: bool = False


class RouterErrorBody(BaseModel):
    code: str
    message: str
    retryable: bool


class RouterErrorResponse(BaseModel):
    error: RouterErrorBody
