import base64
import binascii
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class StatusUpdate(BaseModel):
    status: Literal["active", "completed", "withdrawn", "expired"]


class WhatsAppInbound(BaseModel):
    chat_name: str = Field(max_length=200)
    sender: str = Field(max_length=100)
    message: str = Field(max_length=10_000)
    urls: list[HttpUrl] = Field(max_length=10)
    quoted_message: str | None = Field(default=None, max_length=10_000)


class WhatsAppMediaAttachment(BaseModel):
    mime_type: Literal["image/jpeg", "image/png", "image/webp", "application/pdf"]
    data: str = Field(min_length=1, max_length=2_800_000)
    filename: str | None = Field(default=None, max_length=200)

    @field_validator("data")
    @classmethod
    def validate_media_data(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Media must be valid base64 data") from exc
        if not decoded or len(decoded) > 2 * 1024 * 1024:
            raise ValueError("Media must be between 1 byte and 2 MiB")
        return value


class WhatsAppChannelPost(BaseModel):
    channel_name: str = Field(min_length=1, max_length=200)
    channel_id: str = Field(min_length=1, max_length=200)
    message_id: str = Field(min_length=1, max_length=300)
    post_url: HttpUrl
    message: str = Field(max_length=10_000)
    urls: list[HttpUrl] = Field(default_factory=list, max_length=10)
    media: list[WhatsAppMediaAttachment] = Field(default_factory=list, max_length=3)
    notify_group: bool = False


class ScrapedOpportunity(BaseModel):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    organization: str | None = Field(default=None, max_length=200)
    summary: str = Field(min_length=1, max_length=5000)
    category: str = Field(default="job", max_length=100)
    location: str | None = Field(default=None, max_length=200)
    deadline: datetime | None = None
    matched_recipient: Literal["Feli", "Brandon"] | None = None
    match_reason: str | None = Field(default=None, max_length=500)
    source: str = Field(default="job scraper", max_length=100)


class ManagedSiteCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    url: HttpUrl
