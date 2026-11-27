import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.ai.errors import AIError, PermanentAIError
from app.ai.factory import build_ai
from app.ai.postprocess import build_draft
from app.ai.types import Classifier, Segment, Transcriber, Transcript
from app.config import settings
from app.db import SessionLocal
from app.models import VisitRecord

log = logging.getLogger("csn.worker")

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (5, 30)
STALE_AFTER = timedelta(minutes=10)
IDLE_SLEEP_SECONDS = 2.0

SessionFactory = Callable[[], Session]
Clock = Callable[[], datetime]


@dataclass(frozen=True)
class Claim:
    record_id: uuid.UUID
    claimed_at: datetime
    audio_path: str | None
    transcript: Transcript | None


def _stored_transcript(record: VisitRecord) -> Transcript | None:
    if record.transcript is None:
        return None
    segments = [Segment(**s) for s in record.transcript_segments or []]
    return Transcript(record.transcript, segments, record.approximate_times)


def claim_next(session: Session, now: datetime) -> Claim | None:
    """처리할 기록 하나를 잠그고 '처리 중'으로 바꾼 뒤 바로 커밋한다."""
    stmt = (
        select(VisitRecord)
        .where(
            or_(
                and_(VisitRecord.status == "queued", VisitRecord.available_at <= now),
                and_(
                    VisitRecord.status.in_(("transcribing", "classifying")),
                    VisitRecord.claimed_at < now - STALE_AFTER,
                ),
            )
        )
        .order_by(VisitRecord.available_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    record = session.scalar(stmt)
    if record is None:
        session.rollback()
        return None

    if record.status != "queued":
        # 다른 워커가 처리하다 멈춘 작업. 무한 반복을 막기 위해 시도 횟수에 넣는다.
        record.attempts += 1
        if record.attempts >= MAX_ATTEMPTS:
            record.status = "failed"
            record.error_code = "worker_timeout"
            record.claimed_at = None
            session.commit()
            log.info("record %s -> failed (worker_timeout)", record.id)
            return None

    transcript = _stored_transcript(record)
    record.status = "classifying" if transcript else "transcribing"
    record.claimed_at = now
    claim = Claim(record.id, now, record.audio_path, transcript)
    session.commit()
    return claim


def _update_if_owned(session_factory: SessionFactory, claim: Claim, **values: Any) -> bool:
    """내가 가져간 작업이 그대로일 때만 저장한다 (중간에 다른 워커가 회수했으면 버림)."""
    with session_factory() as s:
        updated = s.scalar(
            update(VisitRecord)
            .where(VisitRecord.id == claim.record_id, VisitRecord.claimed_at == claim.claimed_at)
            .values(**values)
            .returning(VisitRecord.id)
        )
        s.commit()
        return updated is not None


def _record_failure(
    session_factory: SessionFactory, claim: Claim, code: str, *, retry: bool, clock: Clock
) -> str:
    with session_factory() as s:
        record = s.get(VisitRecord, claim.record_id, with_for_update=True)
        if record is None or record.claimed_at != claim.claimed_at:
            return "lost"
        record.error_code = code
        record.claimed_at = None
        if retry:
            record.attempts += 1
        if not retry or record.attempts >= MAX_ATTEMPTS:
            record.status = "failed"
        else:
            record.status = "queued"
            record.available_at = clock() + timedelta(seconds=BACKOFF_SECONDS[record.attempts - 1])
        s.commit()
        return record.status


def process(
    claim: Claim,
    session_factory: SessionFactory,
    transcriber: Transcriber,
    classifier: Classifier,
    clock: Clock,
) -> None:
    started = time.monotonic()
    try:
        transcript = claim.transcript
        if transcript is None:
            if claim.audio_path is None:
                raise PermanentAIError("audio_missing")
            transcript = transcriber.transcribe(Path(claim.audio_path))
            if not _update_if_owned(
                session_factory,
                claim,
                status="classifying",
                transcript=transcript.text,
                transcript_segments=[asdict(s) for s in transcript.segments],
                approximate_times=transcript.approximate_times,
            ):
                return
        draft = build_draft(transcript, classifier.classify(transcript))
        if _update_if_owned(
            session_factory,
            claim,
            status="draft_ready",
            draft=draft,
            claimed_at=None,
            error_code=None,
        ):
            elapsed = time.monotonic() - started
            log.info("record %s -> draft_ready (%.1fs)", claim.record_id, elapsed)
    except PermanentAIError as e:
        status = _record_failure(session_factory, claim, e.code, retry=False, clock=clock)
        log.info("record %s -> %s (%s)", claim.record_id, status, e.code)
    except AIError as e:
        status = _record_failure(session_factory, claim, e.code, retry=True, clock=clock)
        log.info("record %s -> %s (%s)", claim.record_id, status, e.code)
    except Exception as e:
        # 메시지에 전사문이 섞일 수 있어 예외 타입 이름만 남긴다
        status = _record_failure(
            session_factory, claim, "unexpected_error", retry=True, clock=clock
        )
        log.warning("record %s -> %s (unexpected %s)", claim.record_id, status, type(e).__name__)


def run_once(
    session_factory: SessionFactory, transcriber: Transcriber, classifier: Classifier, clock: Clock
) -> bool:
    with session_factory() as s:
        claim = claim_next(s, clock())
    if claim is None:
        return False
    process(claim, session_factory, transcriber, classifier, clock)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    transcriber, classifier = build_ai()
    log.info("worker started (provider=%s)", settings.ai_provider)
    # ponytail: 처리 중 Ctrl-C로 끄면 그 작업은 10분 뒤 회수된다.
    # 즉시 반납이 필요해지면 신호 처리를 추가한다.
    while True:
        if not run_once(SessionLocal, transcriber, classifier, lambda: datetime.now(UTC)):
            time.sleep(IDLE_SLEEP_SECONDS)


if __name__ == "__main__":
    main()
