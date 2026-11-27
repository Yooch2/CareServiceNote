import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Category = Literal["remark", "observation", "followup"]
RiskTag = Literal["fall", "medication", "pain"]
BodyPart = Literal[
    "head", "neck", "shoulder", "arm", "hand", "chest",
    "abdomen", "back", "hip", "leg", "knee", "foot",
]  # fmt: skip
Mood = Literal["good", "neutral", "low"]
MealLevel = Annotated[int, Field(ge=0, le=4)]

ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]


Role = Literal["manager", "caregiver", "guardian"]
ConsentKind = Literal["health_record", "guardian_share"]
Categories = Annotated[list[Category], Field(min_length=1, max_length=3)]


class SignupIn(BaseModel):
    """센터를 새로 만들거나(center_name) 초대 코드로 가입한다(invite_code). 둘 중 하나만."""

    login_id: str = Field(pattern=r"^[a-z0-9_]{4,20}$")
    password: str = Field(min_length=8, max_length=128)
    display_name: ShortName
    center_name: ShortName | None = None
    invite_code: str | None = Field(default=None, max_length=30)

    @model_validator(mode="after")
    def _one_way(self) -> "SignupIn":
        if (self.center_name is None) == (self.invite_code is None):
            raise ValueError("센터 이름과 초대 코드 중 하나만 입력하세요")
        return self


class LoginIn(BaseModel):
    login_id: str = Field(max_length=20)
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    login_id: str
    display_name: str
    role: Role
    org_name: str


class RecipientIn(BaseModel):
    name: ShortName


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_at: datetime
    consents: list[ConsentKind]  # 지금 유효한 동의 종류
    caregiver_names: list[str]  # 지금 배정된 요양보호사


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
    body_part: BodyPart | None
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
    meal_level: int | None
    mood: Mood | None
    review: "ReviewOut | None"


class ReviewOut(BaseModel):
    """센터 확인 서명"""

    reviewer_name: str
    reviewed_at: datetime


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
    body_part: BodyPart | None = None


class FollowupCheckIn(BaseModel):
    item_id: uuid.UUID
    result: LongText
    evidence: str | None = Field(default=None, max_length=1000)


class ConfirmIn(BaseModel):
    items: list[ConfirmItemIn] = Field(default_factory=list, max_length=50)
    dismissed_draft_indexes: list[int] = Field(default_factory=list)
    followup_checks: list[FollowupCheckIn] = Field(default_factory=list, max_length=20)
    dismissed_followup_items: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    # 오늘 상태 (요양보호사가 확인한 값, 언급이 없으면 null)
    meal_level: MealLevel | None = None
    mood: Mood | None = None

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


# --- 3단계: 센터 관리 ---


class AssignmentIn(BaseModel):
    caregiver_id: uuid.UUID


class AssignmentOut(BaseModel):
    id: uuid.UUID
    caregiver_id: uuid.UUID
    caregiver_name: str
    started_at: datetime
    ended_at: datetime | None
    pending_records: int  # 이 요양보호사가 남긴 확정 전 기록 수 (해제하면 볼 수 없게 됨)


class ConsentIn(BaseModel):
    kind: ConsentKind
    granted_on: date


class ConsentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ConsentKind
    granted_on: date
    created_at: datetime
    withdrawn_at: datetime | None


class GuardianLinkOut(BaseModel):
    id: uuid.UUID
    guardian_id: uuid.UUID
    guardian_name: str
    categories: list[Category]
    active: bool
    guardian_active: bool


class GuardianLinkPatch(BaseModel):
    categories: Categories | None = None
    active: bool | None = None


class RecipientAdminOut(BaseModel):
    assignments: list[AssignmentOut]
    consents: list[ConsentOut]
    guardians: list[GuardianLinkOut]


class MemberOut(BaseModel):
    id: uuid.UUID
    login_id: str
    display_name: str
    role: Role
    active: bool
    recipient_name: str | None  # 보호자일 때 연결된 수급자


class MemberPatch(BaseModel):
    active: bool


class InviteIn(BaseModel):
    role: Literal["caregiver", "guardian"]
    recipient_id: uuid.UUID | None = None
    categories: Categories | None = None

    @model_validator(mode="after")
    def _guardian_target(self) -> "InviteIn":
        guardian = self.role == "guardian"
        if guardian != (self.recipient_id is not None) or guardian != (self.categories is not None):
            raise ValueError("보호자 초대에는 수급자와 열람 범위가 필요합니다")
        return self


class InviteCreatedOut(BaseModel):
    id: uuid.UUID
    code: str  # 이 응답에서만 보여 준다
    expires_at: datetime


class InviteOut(BaseModel):
    id: uuid.UUID
    role: Literal["caregiver", "guardian"]
    recipient_name: str | None
    categories: list[Category] | None
    expires_at: datetime


class ReviewQueueOut(BaseModel):
    record_id: uuid.UUID
    recipient_id: uuid.UUID
    recipient_name: str
    visited_on: date
    caregiver_name: str
    confirmed_at: datetime


# --- 3단계: 보호자 (보여 줄 필드만 적는다) ---


class GuardianItemOut(BaseModel):
    category: Category
    content: str


class GuardianCheckOut(BaseModel):
    followup_content: str
    result: str


class GuardianVisitOut(BaseModel):
    visited_on: date
    items: list[GuardianItemOut]
    checks: list[GuardianCheckOut]


class GuardianHomeOut(BaseModel):
    recipient_name: str
    categories: list[Category]
    records: list[GuardianVisitOut]


# --- 4단계: 알림 · 추이 ---

AlertKind = Literal["repeated_discomfort", "meal_drop", "urgent"]


class AlertEvidenceOut(BaseModel):
    record_id: uuid.UUID
    item_id: uuid.UUID | None
    visited_on: date
    text: str


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recipient_id: uuid.UUID
    kind: AlertKind
    key: str
    status: Literal["open", "resolved"]
    evidence: list[AlertEvidenceOut]
    note: str | None
    created_at: datetime
    updated_at: datetime
    resolution: Literal["acted", "false_alarm"] | None
    resolution_note: str | None
    resolved_at: datetime | None


class OrgAlertOut(AlertOut):
    recipient_name: str
    created_by_name: str | None
    resolved_by_name: str | None


class ConcernIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ResolveIn(BaseModel):
    resolution: Literal["acted", "false_alarm"]
    note: str | None = Field(default=None, max_length=500)


class TrendPointOut(BaseModel):
    record_id: uuid.UUID
    visited_on: date
    meal_level: int | None
    mood: Mood | None
