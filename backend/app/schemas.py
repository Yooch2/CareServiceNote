import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Category = Literal["remark", "observation", "followup"]
RiskTag = Literal["fall", "medication", "pain"]

ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


class SignupIn(BaseModel):
    login_id: str = Field(pattern=r"^[a-z0-9_]{4,20}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: ShortName


class LoginIn(BaseModel):
    login_id: str = Field(max_length=20)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    login_id: str
    display_name: str


class RecipientIn(BaseModel):
    name: ShortName


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime


class RecordItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: Category
    content: str
    evidence: str | None
    speaker_uncertain: bool
    risk_tag: RiskTag | None
    origin: Literal["ai", "ai_edited", "human"]
    position: int


class RecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_id: uuid.UUID
    visited_on: date
    recorded_at: datetime
    status: str
    error_code: str | None
    transcript: str | None
    transcript_segments: list[dict[str, Any]] | None
    approximate_times: bool
    draft: dict[str, Any] | None
    items: list[RecordItemOut]
    has_audio: bool
    created_at: datetime
    confirmed_at: datetime | None


class RecordSummaryOut(BaseModel):
    id: uuid.UUID
    visited_on: date
    status: str
    is_mine: bool
    created_at: datetime


LongText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class ConfirmItemIn(BaseModel):
    draft_index: int | None = Field(default=None, ge=0)
    category: Category
    content: LongText
    evidence: str | None = Field(default=None, max_length=1000)
    speaker_uncertain: bool = False
    risk_tag: RiskTag | None = None


class ConfirmIn(BaseModel):
    items: list[ConfirmItemIn] = Field(min_length=1, max_length=50)
    dismissed_draft_indexes: list[int] = Field(default_factory=list)
