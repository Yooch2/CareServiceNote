import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import CurrentUser, DbSession
from app.models import Recipient
from app.schemas import RecipientIn, RecipientOut

router = APIRouter(prefix="/recipients", tags=["recipients"])


def get_recipient_or_404(db: Session, recipient_id: uuid.UUID) -> Recipient:
    recipient = db.get(Recipient, recipient_id)
    if recipient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "수급자를 찾을 수 없습니다")
    return recipient


@router.get("", response_model=list[RecipientOut])
def list_recipients(db: DbSession, _: CurrentUser) -> Sequence[Recipient]:
    return db.scalars(select(Recipient).order_by(Recipient.created_at, Recipient.id)).all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RecipientOut)
def create_recipient(body: RecipientIn, db: DbSession, _: CurrentUser) -> Recipient:
    recipient = Recipient(name=body.name)
    db.add(recipient)
    db.commit()
    db.refresh(recipient)  # server_default인 created_at 읽어오기
    return recipient


@router.get("/{recipient_id}", response_model=RecipientOut)
def get_recipient(recipient_id: uuid.UUID, db: DbSession, _: CurrentUser) -> Recipient:
    return get_recipient_or_404(db, recipient_id)
