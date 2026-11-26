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
