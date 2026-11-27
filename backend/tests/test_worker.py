from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app import worker
from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.fake import FakeClassifier, FakeTranscriber
from app.ai.types import Transcript
from app.db import SessionLocal
from app.models import VisitRecord
from tests.helpers import make_confirmed, make_record

# 기록의 available_at은 DB 현재 시각으로 들어가므로, 고정 날짜 대신 실행 시각보다 조금 뒤로 둔다
NOW = datetime.now(UTC).replace(microsecond=0) + timedelta(minutes=1)


def _reload(db: Session, record: VisitRecord) -> VisitRecord:
    db.expire_all()
    fresh = db.get(VisitRecord, record.id)
    assert fresh is not None
    return fresh


def _run(t: FakeTranscriber, c: FakeClassifier, at: datetime = NOW) -> bool:
    return worker.run_once(SessionLocal, t, c, lambda: at)


def test_happy_path_produces_draft(db: Session) -> None:
    record = make_record(db)
    assert _run(FakeTranscriber(), FakeClassifier()) is True
    fresh = _reload(db, record)
    assert fresh.status == "draft_ready"
    assert fresh.transcript and "무릎" in fresh.transcript
    assert fresh.transcript_segments and fresh.transcript_segments[0]["start_ms"] == 0
    assert fresh.draft and len(fresh.draft["items"]) == 4
    assert fresh.draft["missing_topics"] == ["toileting", "sleep", "mood"]
    assert fresh.claimed_at is None
    assert _run(FakeTranscriber(), FakeClassifier()) is False


def test_transient_error_backs_off_then_succeeds(db: Session) -> None:
    record = make_record(db)
    t = FakeTranscriber(failures=[TransientAIError("stt_timeout")])
    _run(t, FakeClassifier())
    fresh = _reload(db, record)
    assert (fresh.status, fresh.attempts, fresh.error_code) == ("queued", 1, "stt_timeout")
    assert fresh.available_at == NOW + timedelta(seconds=5)

    assert _run(t, FakeClassifier(), at=NOW + timedelta(seconds=1)) is False
    assert _run(t, FakeClassifier(), at=NOW + timedelta(seconds=6)) is True
    assert _reload(db, record).status == "draft_ready"
    assert t.calls == 2


def test_three_transient_failures_mark_failed(db: Session) -> None:
    record = make_record(db)
    t = FakeTranscriber(failures=[TransientAIError("x")] * 3)
    for minutes in (0, 1, 2):
        _run(t, FakeClassifier(), at=NOW + timedelta(minutes=minutes))
    fresh = _reload(db, record)
    assert (fresh.status, fresh.attempts) == ("failed", 3)


def test_permanent_error_fails_immediately(db: Session) -> None:
    record = make_record(db)
    _run(FakeTranscriber(failures=[PermanentAIError("audio_unreadable")]), FakeClassifier())
    fresh = _reload(db, record)
    assert (fresh.status, fresh.error_code, fresh.attempts) == ("failed", "audio_unreadable", 0)


def test_unexpected_exception_is_retried(db: Session) -> None:
    record = make_record(db)

    class Boom(FakeTranscriber):
        def transcribe(self, audio: Path) -> Transcript:
            raise RuntimeError("secret transcript text")

    _run(Boom(), FakeClassifier())
    fresh = _reload(db, record)
    assert (fresh.status, fresh.error_code) == ("queued", "unexpected_error")


def test_classify_failure_keeps_transcript_and_resumes(db: Session) -> None:
    record = make_record(db)
    t = FakeTranscriber()
    c = FakeClassifier(failures=[TransientAIError("llm_timeout")])
    _run(t, c)
    fresh = _reload(db, record)
    assert fresh.status == "queued" and fresh.transcript is not None

    _run(t, c, at=NOW + timedelta(minutes=1))
    assert _reload(db, record).status == "draft_ready"
    assert t.calls == 1 and c.calls == 2


def test_missing_audio_without_transcript_fails(db: Session) -> None:
    record = make_record(db, with_audio=False)
    _run(FakeTranscriber(), FakeClassifier())
    assert _reload(db, record).error_code == "audio_missing"


def test_locked_rows_are_skipped(db: Session) -> None:
    make_record(db)
    with SessionLocal() as holder:
        holder.execute(select(VisitRecord).with_for_update())
        with SessionLocal() as s:
            assert worker.claim_next(s, NOW) is None
        holder.rollback()
    with SessionLocal() as s:
        assert worker.claim_next(s, NOW) is not None


def test_stale_claim_is_reclaimed_and_counts_attempt(db: Session) -> None:
    stuck = make_record(db, status="transcribing")
    stuck.claimed_at = NOW - timedelta(minutes=11)
    db.commit()
    with SessionLocal() as s:
        claim = worker.claim_next(s, NOW)
    assert claim is not None and claim.record_id == stuck.id
    fresh = _reload(db, stuck)
    assert (fresh.status, fresh.attempts, fresh.claimed_at) == ("transcribing", 1, NOW)


def test_stale_claim_gives_up_after_max_attempts(db: Session) -> None:
    stuck = make_record(db, status="classifying", transcript="전사문")
    stuck.claimed_at = NOW - timedelta(minutes=11)
    stuck.attempts = 2
    db.commit()
    with SessionLocal() as s:
        assert worker.claim_next(s, NOW) is None
    fresh = _reload(db, stuck)
    assert (fresh.status, fresh.error_code) == ("failed", "worker_timeout")


def test_lost_claim_does_not_overwrite(db: Session) -> None:
    record = make_record(db)
    with SessionLocal() as s:
        claim = worker.claim_next(s, NOW)
    assert claim is not None
    db.execute(
        update(VisitRecord)
        .where(VisitRecord.id == record.id)
        .values(claimed_at=NOW + timedelta(hours=1))
    )
    db.commit()
    worker.process(claim, SessionLocal, FakeTranscriber(), FakeClassifier(), lambda: NOW)
    fresh = _reload(db, record)
    assert fresh.status == "transcribing" and fresh.transcript is None


def test_open_followups_are_sent_and_snapshotted(db: Session) -> None:
    earlier = make_confirmed(
        db, [("followup", "무릎 상태와 산책 의향 다시 확인"), ("remark", "무릎이 불편")]
    )
    other = make_confirmed(db, [("followup", "다른 수급자 확인 사항")])
    record = make_record(db, recipient_id=earlier.recipient_id)
    classifier = FakeClassifier()

    assert _run(FakeTranscriber(), classifier) is True
    fresh = _reload(db, record)
    assert fresh.status == "draft_ready" and fresh.draft is not None
    followup_id = str(earlier.items[0].id)
    assert [f.content for f in classifier.last_followups] == ["무릎 상태와 산책 의향 다시 확인"]
    assert fresh.draft["open_followups"] == [
        {
            "item_id": followup_id,
            "content": "무릎 상태와 산책 의향 다시 확인",
            "visited_on": "2026-11-20",
        }
    ]
    [result] = fresh.draft["followup_results"]
    assert result["item_id"] == followup_id and result["evidence_found"] is True
    assert str(other.items[0].id) not in str(fresh.draft)
