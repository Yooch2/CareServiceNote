"""보관 기간이 지난 파일·전사문을 지운다.

워커가 한 시간마다 실행한다 (직접 실행: python -m app.retention).
- 확정되지 않은 기록(초안·실패·처리 중)이 AUDIO_RETENTION_DAYS보다 오래되면
  음성·사진·전사문·초안 삭제
- 확정 기록은 확정 후 TRANSCRIPT_RETENTION_DAYS가 지나면 전사문·구간·초안 삭제
  (확정 항목과 근거 구절은 공식 기록이라 남긴다)
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app import storage
from app.config import settings
from app.db import SessionLocal
from app.models import AuthFailure, RecordPhoto, VisitRecord

log = logging.getLogger("csn.retention")


@dataclass(frozen=True)
class PurgeResult:
    audio: int
    photos: int
    transcripts: int


def purge(db: Session, now: datetime) -> PurgeResult:
    audio_cutoff = now - timedelta(days=settings.audio_retention_days)
    stale = VisitRecord.status != "confirmed", VisitRecord.created_at < audio_cutoff

    audio_rows = db.execute(
        select(VisitRecord.id, VisitRecord.audio_path).where(
            *stale, VisitRecord.audio_path.is_not(None)
        )
    ).all()
    photo_rows = db.execute(
        select(RecordPhoto.id, RecordPhoto.path)
        .join(VisitRecord, RecordPhoto.record_id == VisitRecord.id)
        .where(*stale, RecordPhoto.path.is_not(None))
    ).all()
    if audio_rows:
        db.execute(
            update(VisitRecord)
            .where(VisitRecord.id.in_([r.id for r in audio_rows]))
            .values(audio_path=None)
        )
    # 확정되지 않은 채 남은 기록(초안 방치·동의 철회·처리 실패)의 전사문·초안도 지운다
    stale_texts = db.scalars(
        update(VisitRecord)
        .where(
            *stale,
            or_(
                VisitRecord.transcript.is_not(None),
                VisitRecord.transcript_segments.is_not(None),
                VisitRecord.draft.is_not(None),
            ),
        )
        .values(transcript=None, transcript_segments=None, draft=None)
        .returning(VisitRecord.id)
    ).all()
    if photo_rows:
        db.execute(
            update(RecordPhoto)
            .where(RecordPhoto.id.in_([r.id for r in photo_rows]))
            .values(path=None)
        )

    transcript_cutoff = now - timedelta(days=settings.transcript_retention_days)
    transcripts = db.scalars(
        update(VisitRecord)
        .where(
            VisitRecord.status == "confirmed",
            VisitRecord.confirmed_at < transcript_cutoff,
            or_(
                VisitRecord.transcript.is_not(None),
                VisitRecord.transcript_segments.is_not(None),
                VisitRecord.draft.is_not(None),
            ),
        )
        .values(transcript=None, transcript_segments=None, draft=None)
        .returning(VisitRecord.id)
    ).all()
    # 시도 횟수 제한용 실패 기록은 하루, 아는 기기(로그인 성공) 기록은 30일 지나면 지운다
    db.execute(
        delete(AuthFailure).where(
            AuthFailure.kind != "login_ok", AuthFailure.created_at < now - timedelta(days=1)
        )
    )
    db.execute(
        delete(AuthFailure).where(
            AuthFailure.kind == "login_ok", AuthFailure.created_at < now - timedelta(days=30)
        )
    )
    db.commit()
    # DB에서 경로를 지운 뒤 파일을 지운다 (반대 순서면 실패 시 없는 파일을 가리키게 된다)
    for _, path in [*audio_rows, *photo_rows]:
        storage.delete(path)
    result = PurgeResult(len(audio_rows), len(photo_rows), len(transcripts) + len(stale_texts))
    if any((result.audio, result.photos, result.transcripts)):
        log.info("retention purge: %s", result)
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    with SessionLocal() as s:
        print(purge(s, datetime.now(UTC)))
