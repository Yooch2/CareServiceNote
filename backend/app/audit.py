import uuid

from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def audit(
    db: Session,
    user: User,
    action: str,
    recipient_id: uuid.UUID,
    record_id: uuid.UUID | None = None,
    *,
    commit: bool = True,
) -> None:
    """누가·언제·무엇을 했는지만 남긴다 (검색어·기록 내용은 남기지 않는다)."""
    db.add(
        AuditEvent(actor_id=user.id, recipient_id=recipient_id, record_id=record_id, action=action)
    )
    if commit:
        db.commit()
