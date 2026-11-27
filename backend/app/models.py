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
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

RECORD_STATUSES = ("queued", "transcribing", "classifying", "draft_ready", "failed", "confirmed")
CATEGORIES = ("remark", "observation", "followup")
RISK_TAGS = ("fall", "medication", "pain")
ORIGINS = ("ai", "ai_edited", "human")


def _one_of(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login_id: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Recipient(Base):
    __tablename__ = "recipients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VisitRecord(Base):
    __tablename__ = "visit_records"
    __table_args__ = (
        CheckConstraint(_one_of("status", RECORD_STATUSES), name="ck_visit_records_status"),
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


class RecordItem(Base):
    __tablename__ = "record_items"
    __table_args__ = (
        CheckConstraint(_one_of("category", CATEGORIES), name="ck_record_items_category"),
        CheckConstraint(
            f"risk_tag IS NULL OR {_one_of('risk_tag', RISK_TAGS)}", name="ck_record_items_risk_tag"
        ),
        CheckConstraint(_one_of("origin", ORIGINS), name="ck_record_items_origin"),
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
