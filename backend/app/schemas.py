import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

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


class CheckOut(BaseModel):
    """'다음 확인' 항목이 이후 방문에서 확인된 결과"""

    model_config = ConfigDict(from_attributes=True)

    result: str
    origin: Literal["ai", "ai_edited", "human"]
    record_id: uuid.UUID
    visited_on: date


class FollowupCheckOut(BaseModel):
    """이 방문에서 확인한 이전 확인 사항"""

    model_config = ConfigDict(from_attributes=True)

    followup_item_id: uuid.UUID
    followup_content: str
    followup_record_id: uuid.UUID
    followup_visited_on: date
    result: str
    evidence: str | None
    origin: Literal["ai", "ai_edited", "human"]


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
    check: CheckOut | None


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
    followup_checks: list[FollowupCheckOut]
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


class FollowupCheckIn(BaseModel):
    item_id: uuid.UUID
    result: LongText
    evidence: str | None = Field(default=None, max_length=1000)


class ConfirmIn(BaseModel):
    items: list[ConfirmItemIn] = Field(default_factory=list, max_length=50)
    dismissed_draft_indexes: list[int] = Field(default_factory=list)
    followup_checks: list[FollowupCheckIn] = Field(default_factory=list, max_length=20)
    dismissed_followup_items: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _not_empty(self) -> "ConfirmIn":
        if not self.items and not self.followup_checks:
            raise ValueError("남길 항목이나 확인 결과가 하나 이상 있어야 합니다")
        return self


Days = Literal[7, 14, 30]


class OpenFollowupOut(BaseModel):
    item_id: uuid.UUID
    content: str
    evidence: str | None
    record_id: uuid.UUID
    visited_on: date


class RiskItemOut(BaseModel):
    item_id: uuid.UUID
    category: Category
    content: str
    risk_tag: RiskTag
    record_id: uuid.UUID
    visited_on: date


class RecentCheckOut(BaseModel):
    followup_item_id: uuid.UUID
    followup_content: str
    result: str
    origin: Literal["ai", "ai_edited", "human"]
    record_id: uuid.UUID
    visited_on: date


class CompletionOut(BaseModel):
    due: int
    checked: int


class SummaryRefOut(BaseModel):
    item_id: uuid.UUID
    record_id: uuid.UUID
    visited_on: date


class SummarySentenceOut(BaseModel):
    text: str
    items: list[SummaryRefOut]


class SummaryOutApi(BaseModel):
    sentences: list[SummarySentenceOut]
    created_at: datetime
    stale: bool


class HandoverOut(BaseModel):
    days: int
    last_visit_on: date | None
    open_followups: list[OpenFollowupOut]
    risk_items: list[RiskItemOut]
    recent_checks: list[RecentCheckOut]
    completion: CompletionOut
    summary: SummaryOutApi | None


class SearchHitOut(BaseModel):
    record_id: uuid.UUID
    visited_on: date
    kind: Literal["item", "check", "transcript"]
    category: Category | None
    text: str
    item_id: uuid.UUID | None
