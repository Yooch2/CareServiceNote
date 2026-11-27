import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import FollowupCheck, Recipient, RecordItem, VisitRecord
from tests.helpers import make_confirmed, make_user, new_org


def _record(db: Session, **overrides: object) -> VisitRecord:
    org = new_org(db)
    user = make_user(db, org.id)
    recipient = Recipient(name="가상수급자", org_id=org.id)
    db.add(recipient)
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


def test_followup_item_is_checked_once_and_cascades(db: Session) -> None:
    first = make_confirmed(db, [("followup", "무릎 상태 다시 확인")])
    second = make_confirmed(db, [("remark", "괜찮다")], recipient_id=first.recipient_id)
    item = first.items[0]
    db.add(
        FollowupCheck(followup_item_id=item.id, record_id=second.id, result="괜찮다", origin="ai")
    )
    db.commit()
    db.expire_all()
    assert item.check is not None and item.check.result == "괜찮다"
    assert item.check.record.visited_on == second.visited_on

    dup = FollowupCheck(followup_item_id=item.id, record_id=second.id, result="중복", origin="ai")
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.delete(db.get(VisitRecord, second.id))
    db.commit()
    assert db.query(FollowupCheck).count() == 0
