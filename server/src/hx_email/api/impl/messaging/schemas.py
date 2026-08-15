"""Pydantic request models for the messaging plugin API."""

from pydantic import BaseModel, Field

from hx_email.server.messaging.types import ChatType


class MessagingInstanceCreate(BaseModel):
    kind: str
    name: str = ""
    config: dict[str, str] = Field(default_factory=dict)


class MessagingSendRequest(BaseModel):
    chat_id: str
    chat_type: ChatType = "private"
    text: str


class MessagingGroupActionRequest(BaseModel):
    action: str
    member_id: str = ""
    duration_seconds: int = 0


class MessagingConfigUpdate(BaseModel):
    config: dict[str, str] = Field(default_factory=dict)
