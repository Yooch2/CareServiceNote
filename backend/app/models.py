import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

RECORD_STATUSES = ("queued", "transcribing", "classifying", "draft_ready", "failed", "confirmed")
CATEGORIES = ("remark", "observation", "followup")
RISK_TAGS = ("fall", "medication", "pain")
ORIGINS = ("ai", "ai_edited", "human")
ROLES = ("manager", "caregiver", "guardian")
CONSENT_KINDS = ("health_record", "guardian_share")
BODY_PARTS = (
    "head", "neck", "shoulder", "arm", "hand", "chest",
    "abdomen", "back", "hip", "leg", "knee", "foot",
)  # fmt: skip
MOODS = ("good", "neutral", "low")
ALERT_KINDS = ("repeated_discomfort", "meal_drop", "urgent")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


_CATEGORY_SUBSET = "categories <@ ARRAY['remark', 'observation', 'followup']::text[]"


class Organization(Base):
    """방문요양센터. 사용자와 수급자는 한 센터에 속한다."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_one_of("role", ROLES), name="ck_users_role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    login_id: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    org: Mapped[Organization] = relationship(lazy="joined", viewonly=True)

    @property
    def org_name(self) -> str:
        return self.org.name


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    active_consents: Mapped[list["Consent"]] = relationship(
        primaryjoin="and_(Consent.recipient_id == Recipient.id, Consent.withdrawn_at.is_(None))",
        lazy="selectin",
        viewonly=True,
    )
    active_assignments: Mapped[list["Assignment"]] = relationship(
        primaryjoin="and_(Assignment.recipient_id == Recipient.id, Assignment.ended_at.is_(None))",
        order_by="Assignment.started_at",
        lazy="selectin",
        viewonly=True,
    )

    @property
    def consents(self) -> list[str]:
        return sorted(c.kind for c in self.active_consents)

    @property
    def caregiver_names(self) -> list[str]:
        return [a.caregiver.display_name for a in self.active_assignments]


class Assignment(Base):
    """담당 배정. 해제하면 행을 지우지 않고 ended_at을 채운다."""

    __tablename__ = "assignments"
    __table_args__ = (
        Index(
            "uq_assignments_active",
            "recipient_id",
            "caregiver_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"), index=True)
    caregiver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    caregiver: Mapped[User] = relationship(
        foreign_keys=[caregiver_id], lazy="joined", viewonly=True
    )


class Consent(Base):
    """센터가 서면으로 받은 동의를 기록한다. 철회해도 지우지 않고 withdrawn_at을 채운다."""

    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint(_one_of("kind", CONSENT_KINDS), name="ck_consents_kind"),
        Index(
            "uq_consents_active",
            "recipient_id",
            "kind",
            unique=True,
            postgresql_where=text("withdrawn_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    granted_on: Mapped[date] = mapped_column(Date)
    recorded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class GuardianLink(Base):
    """보호자 계정과 수급자 연결. categories = 볼 수 있는 분류 (열람 범위)."""

    __tablename__ = "guardian_links"
    __table_args__ = (
        CheckConstraint(
            f"cardinality(categories) > 0 AND {_CATEGORY_SUBSET}",
            name="ck_guardian_links_categories",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"), index=True)
    guardian_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    categories: Mapped[list[str]] = mapped_column(ARRAY(Text))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    guardian: Mapped[User] = relationship(lazy="joined", viewonly=True)


class Invite(Base):
    """일회용 초대 코드. 원문은 만들 때 한 번만 보여 주고 해시만 저장한다."""

    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint("role IN ('caregiver', 'guardian')", name="ck_invites_role"),
        CheckConstraint(
            "role <> 'guardian' OR (recipient_id IS NOT NULL AND categories IS NOT NULL)",
            name="ck_invites_guardian_target",
        ),
        CheckConstraint(
            f"categories IS NULL OR (cardinality(categories) > 0 AND {_CATEGORY_SUBSET})",
            name="ck_invites_categories",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    role: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recipients.id"))
    categories: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    code_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisitRecord(Base):
    __tablename__ = "visit_records"
    __table_args__ = (
        CheckConstraint(_one_of("status", RECORD_STATUSES), name="ck_visit_records_status"),
        CheckConstraint("meal_level BETWEEN 0 AND 4", name="ck_visit_records_meal_level"),
        CheckConstraint(f"mood IS NULL OR {_one_of('mood', MOODS)}", name="ck_visit_records_mood"),
        Index("ix_visit_records_queue", "status", "available_at"),
        Index("ix_visit_records_recipient", "recipient_id", "visited_on"),
        Index("ix_visit_records_caregiver_created", "caregiver_id", "created_at"),
        # 키워드 검색 (pg_trgm, 한국어 부분 문자열)
        Index(
            "ix_visit_records_transcript_trgm",
            "transcript",
            postgresql_using="gin",
            postgresql_ops={"transcript": "gin_trgm_ops"},
        ),
    )

    # 클라이언트가 만든 UUID. 재전송 시 중복 저장을 막는 키로 쓴다.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    caregiver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    visited_on: Mapped[date] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="queued")
    audio_path: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[str | None] = mapped_column(Text)
    transcript_segments: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    approximate_times: Mapped[bool] = mapped_column(Boolean, default=False)
    draft: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 오늘 상태: 0 거의 못 드심 ~ 4 다 드심 / good·neutral·low (확정 때 요양보호사가 확인한 값)
    meal_level: Mapped[int | None] = mapped_column(SmallInteger)
    mood: Mapped[str | None] = mapped_column(Text)
    # 센터 확인 서명 (기관 담당자)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    reviewer: Mapped[User | None] = relationship(
        foreign_keys=[reviewed_by], lazy="selectin", viewonly=True
    )

    items: Mapped[list["RecordItem"]] = relationship(
        order_by="RecordItem.position", cascade="all, delete-orphan", lazy="selectin"
    )
    # 이 방문에서 확인한 이전 확인 사항의 결과
    followup_checks: Mapped[list["FollowupCheck"]] = relationship(
        order_by="FollowupCheck.created_at",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="FollowupCheck.record_id",
    )

    @property
    def has_audio(self) -> bool:
        return self.audio_path is not None

    @property
    def review(self) -> dict[str, Any] | None:
        if self.reviewer is None or self.reviewed_at is None:
            return None
        return {"reviewer_name": self.reviewer.display_name, "reviewed_at": self.reviewed_at}


class RecordItem(Base):
    __tablename__ = "record_items"
    __table_args__ = (
        CheckConstraint(_one_of("category", CATEGORIES), name="ck_record_items_category"),
        CheckConstraint(
            f"risk_tag IS NULL OR {_one_of('risk_tag', RISK_TAGS)}", name="ck_record_items_risk_tag"
        ),
        CheckConstraint(_one_of("origin", ORIGINS), name="ck_record_items_origin"),
        CheckConstraint(
            f"body_part IS NULL OR {_one_of('body_part', BODY_PARTS)}",
            name="ck_record_items_body_part",
        ),
        Index(
            "ix_record_items_content_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visit_records.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    speaker_uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_tag: Mapped[str | None] = mapped_column(Text)
    body_part: Mapped[str | None] = mapped_column(Text)  # 불편·통증을 말한 부위 (좌우 구분 없음)
    origin: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer)

    # '다음 확인' 항목이 이후 방문에서 확인됐으면 그 결과
    check: Mapped["FollowupCheck | None"] = relationship(
        foreign_keys="FollowupCheck.followup_item_id", lazy="selectin", viewonly=True
    )
    record: Mapped["VisitRecord"] = relationship(lazy="select", viewonly=True)

    @property
    def record_visited_on(self) -> date:
        return self.record.visited_on


class FollowupCheck(Base):
    """이전 방문의 '다음 확인' 항목을 이후 방문에서 확인한 결과. 한 항목은 한 번만 확인된다."""

    __tablename__ = "followup_checks"
    __table_args__ = (
        CheckConstraint(_one_of("origin", ORIGINS), name="ck_followup_checks_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    followup_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("record_items.id", ondelete="CASCADE"), unique=True
    )
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visit_records.id", ondelete="CASCADE"), index=True
    )
    result: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str | None] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    record: Mapped[VisitRecord] = relationship(
        foreign_keys=[record_id], lazy="joined", viewonly=True
    )
    followup_item: Mapped[RecordItem] = relationship(
        foreign_keys=[followup_item_id], lazy="joined", viewonly=True
    )

    @property
    def visited_on(self) -> date:
        return self.record.visited_on

    @property
    def followup_content(self) -> str:
        return self.followup_item.content

    @property
    def followup_record_id(self) -> uuid.UUID:
        return self.followup_item.record_id

    @property
    def followup_visited_on(self) -> date:
        # ponytail: 항목에는 방문일이 없어 기록을 한 번 더 읽는다. 목록이 커지면 조인으로 바꾼다.
        return self.followup_item.record_visited_on


class HandoverSummary(Base):
    """AI 인계 요약. 문장마다 근거 항목 id를 단다. 다시 만들면 새 행을 쌓는다."""

    __tablename__ = "handover_summaries"
    __table_args__ = (
        CheckConstraint("days IN (7, 14, 30)", name="ck_handover_summaries_days"),
        Index("ix_handover_summaries_lookup", "recipient_id", "days", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    days: Mapped[int] = mapped_column(Integer)
    sentences: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    covered_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AiUsage(Base):
    """API 요청 안에서 부르는 AI 호출 기록 (하루 한도용). 실패한 시도도 센다."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_kind_created", "kind", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Alert(Base):
    """변화 알림(규칙)과 긴급 우려(요양보호사 제출). 같은 사유의 미처리 알림은 하나로 합친다."""

    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(_one_of("kind", ALERT_KINDS), name="ck_alerts_kind"),
        CheckConstraint("status IN ('open', 'resolved')", name="ck_alerts_status"),
        CheckConstraint(
            "resolution IS NULL OR resolution IN ('acted', 'false_alarm')",
            name="ck_alerts_resolution",
        ),
        Index(
            "uq_alerts_open",
            "recipient_id",
            "kind",
            "key",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_alerts_recipient_status", "recipient_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    kind: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")
    # [{record_id, item_id, visited_on, text}]
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 처리 결과를 보호자에게 알릴 때 담당자가 따로 쓴 안내문 (알림 원문은 보내지 않는다)
    guardian_message: Mapped[str | None] = mapped_column(Text)
    shared_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuardianSummary(Base):
    """보호자 하루 요약. 방문당 하나, 기관 담당자가 승인해야 보호자에게 보인다.

    sentences: [{text, item_ids, edited}]. 보호자별 열람 범위는 문장의 근거 항목으로 거른다.
    """

    __tablename__ = "guardian_summaries"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'approved')", name="ck_guardian_summaries_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visit_records.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(Text, default="draft")
    sentences: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VisitSession(Base):
    """방문 시작·종료 시각 (위치는 수집하지 않는다). 요양보호사당 열린 방문은 하나."""

    __tablename__ = "visit_sessions"
    __table_args__ = (
        Index(
            "uq_visit_sessions_open",
            "caregiver_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
        Index("ix_visit_sessions_recipient_started", "recipient_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    caregiver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    caregiver: Mapped[User] = relationship(lazy="joined", viewonly=True)


class Message(Base):
    """수급자별 업무 메시지 (기관 담당자 ↔ 담당 요양보호사). 보호자는 볼 수 없다."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_recipient_created", "recipient_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recipients.id"))
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    author: Mapped[User] = relationship(lazy="joined", viewonly=True)
