"""변화 알림 규칙. AI가 아니라 서버 규칙이 확정된 값만 보고 알림을 만든다.

- repeated_discomfort: 7일 이내 서로 다른 두 방문에 같은 부위의 불편 (발화자 미확인 항목 제외)
- meal_drop: 식사량이 기록된 두 방문(7일 이내)에서 MEAL_DROP_LEVELS 단계 이상 감소

같은 수급자·같은 사유의 미처리 알림이 있으면 새로 만들지 않고 근거만 합친다.
정정 기능(6단계)이 생기면 정정 뒤에도 evaluate_alerts를 부른다.
"""

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, RecordItem, VisitRecord

WINDOW_DAYS = 7
MEAL_DROP_LEVELS = 2
_ALERT_LOCK = 7_301_003  # advisory lock 번호 (수급자별 두 번째 키)
MEAL_LABEL = ("거의 못 드심", "조금", "절반", "대부분", "다 드심")


def _evidence(record: VisitRecord, text: str, item_id: uuid.UUID | None = None) -> dict[str, Any]:
    return {
        "record_id": str(record.id),
        "item_id": str(item_id) if item_id else None,
        "visited_on": record.visited_on.isoformat(),
        "text": text,
    }


def _raise(
    db: Session, recipient_id: uuid.UUID, kind: str, key: str, evidence: list[dict[str, Any]]
) -> None:
    """미처리 알림이 있으면 근거를 합치고, 없으면 만든다."""
    alert = db.scalar(
        select(Alert)
        .where(
            Alert.recipient_id == recipient_id,
            Alert.kind == kind,
            Alert.key == key,
            Alert.status == "open",
        )
        .with_for_update()
    )
    if alert is None:
        db.add(Alert(recipient_id=recipient_id, kind=kind, key=key, evidence=_dedupe(evidence)))
        return
    merged = _dedupe([*alert.evidence, *evidence])
    if len(merged) != len(alert.evidence):
        alert.evidence = merged  # JSONB는 새 리스트를 넣어야 변경으로 잡힌다


def _dedupe(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 (기록, 항목) 근거는 하나만, 방문일 순"""
    unique = {(e["record_id"], e["item_id"]): e for e in evidence}
    return sorted(unique.values(), key=lambda e: e["visited_on"])


def _nearby(db: Session, record: VisitRecord) -> list[VisitRecord]:
    """같은 수급자의 다른 확정 기록 중 방문일 차이가 WINDOW_DAYS 이내인 것"""
    window = timedelta(days=WINDOW_DAYS)
    return list(
        db.scalars(
            select(VisitRecord).where(
                VisitRecord.recipient_id == record.recipient_id,
                VisitRecord.status == "confirmed",
                VisitRecord.id != record.id,
                VisitRecord.visited_on.between(
                    record.visited_on - window, record.visited_on + window
                ),
            )
        )
    )


def _discomfort_items(record: VisitRecord) -> dict[str, list[RecordItem]]:
    parts: dict[str, list[RecordItem]] = {}
    for item in record.items:
        if item.body_part and not item.speaker_uncertain:
            parts.setdefault(item.body_part, []).append(item)
    return parts


def evaluate_alerts(db: Session, record: VisitRecord) -> None:
    """확정된 기록 하나를 기준으로 규칙을 평가한다 (호출한 쪽이 커밋)."""
    if record.status != "confirmed":
        return
    # 같은 수급자의 기록이 동시에 확정되면 미처리 알림을 두 번 만들 수 있어 수급자별로 잠근다
    db.execute(
        select(func.pg_advisory_xact_lock(_ALERT_LOCK, func.hashtext(str(record.recipient_id))))
    )
    nearby = _nearby(db, record)

    # 사유(kind, key)마다 근거를 모은 뒤 한 번씩만 올린다 (같은 사유가 두 번 생기지 않게)
    found: dict[tuple[str, str], list[dict[str, Any]]] = {}

    mine = _discomfort_items(record)
    for other in nearby:
        theirs = _discomfort_items(other)
        for part in mine.keys() & theirs.keys():
            evidence = found.setdefault(("repeated_discomfort", part), [])
            evidence += [_evidence(other, i.content, i.id) for i in theirs[part]]
    for (_, part), evidence in found.items():
        evidence += [_evidence(record, i.content, i.id) for i in mine[part]]

    if record.meal_level is not None:
        with_meal = sorted(
            [r for r in nearby if r.meal_level is not None] + [record],
            key=lambda r: (r.visited_on, r.created_at),
        )
        at = with_meal.index(record)
        pairs = []
        if at > 0:
            pairs.append((with_meal[at - 1], record))
        if at + 1 < len(with_meal):
            pairs.append((record, with_meal[at + 1]))
        for before, after in pairs:
            assert before.meal_level is not None and after.meal_level is not None
            if before.meal_level - after.meal_level >= MEAL_DROP_LEVELS:
                found.setdefault(("meal_drop", "meal"), []).extend(
                    [
                        _evidence(before, f"식사량: {MEAL_LABEL[before.meal_level]}"),
                        _evidence(after, f"식사량: {MEAL_LABEL[after.meal_level]}"),
                    ]
                )

    for (kind, key), evidence in found.items():
        _raise(db, record.recipient_id, kind, key, evidence)
