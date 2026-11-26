import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Recipient, RecordItem, User, VisitRecord


def _record(db: Session, **overrides: object) -> VisitRecord:
    user = User(login_id=f"u{uuid.uuid4().hex[:8]}", password_hash="x", display_name="테스트")
    recipient = Recipient(name="가상수급자")
    db.add_all([user, recipient])
    db.flush()
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "recipient_id": recipient.id,
        "caregiver_id": user.id,
        "visited_on": date(2026, 11, 27),
        "recorded_at": datetime(2026, 11, 27, 1, 0, tzinfo=UTC),
    }
    values.update(overrides)
    record = VisitRecord(**values)
    db.add(record)
    db.flush()
    return record


def test_record_defaults(db: Session) -> None:
    record = _record(db)
    db.commit()
    db.refresh(record)
    assert record.status == "queued"
    assert record.attempts == 0
    assert record.approximate_times is False
    assert record.available_at is not None
    assert record.has_audio is False
    assert record.items == []


def test_status_check_constraint(db: Session) -> None:
    with pytest.raises(IntegrityError):
        _record(db, status="done")


def test_item_constraints_and_order(db: Session) -> None:
    record = _record(db)
    record.items = [
        RecordItem(
            category="followup", content="b", speaker_uncertain=False, origin="human", position=1
        ),
        RecordItem(
            category="remark", content="a", speaker_uncertain=False, origin="ai", position=0
        ),
    ]
    db.commit()
    db.expire_all()
    loaded = db.get(VisitRecord, record.id)
    assert loaded is not None
    assert [i.content for i in loaded.items] == ["a", "b"]

    loaded.items.append(
        RecordItem(
            category="remark", content="c", speaker_uncertain=False, origin="robot", position=2
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
