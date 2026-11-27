# ruff: noqa: E501  (가상 기록 데이터라 줄이 길다)
"""데모용 가상 방문 이력 (김순자(가상), 최근 2주). 실제 인물·기록이 아니다.

데모를 열자마자 방문 전 확인·변화 알림·추이·후속 확인·보호자 화면에 볼거리가 있도록,
AI를 부르지 않고 '확정된 기록'을 직접 만든다. 이야기:
  13일 전  오른쪽 무릎이 시큰거린다 → 다음에 무릎 다시 확인
  10일 전  무릎은 비슷하다(확인 결과), 손녀가 다음 달에 온다 → 손녀 방문 날짜 확인
   6일 전  계단 내려갈 때 무릎이 아프다 → 7일 안 두 번째 무릎 불편 = 변화 알림
   3일 전  기운이 없다, 점심 조금(식사량 감소 알림), 손녀 방문 날짜 확인 결과
그리고 보호자 하루 요약 승인, 긴급 우려와 센터 안내, 센터 확인 서명 일부.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.models import (
    Alert,
    FollowupCheck,
    GuardianSummary,
    Recipient,
    RecordItem,
    User,
    VisitRecord,
)

# (며칠 전, 식사량, 기분, 항목[(분류, 내용, 근거, 부위, 위험)], 이전 확인 결과[(이전 방문 며칠 전, 결과)], 서명)
_VISITS = [
    (
        13,
        3,
        "neutral",
        [
            (
                "remark",
                "오른쪽 무릎이 시큰거린다고 하심",
                "오른쪽 무릎이 좀 시큰거린다고 하셨어요",
                "knee",
                "pain",
            ),
            ("observation", "점심은 대부분 드심", "점심은 대부분 드셨고요", None, None),
            ("followup", "무릎 상태 다시 확인", "다음에 무릎 상태 다시 여쭤볼게요", None, None),
        ],
        [],
        True,
    ),
    (
        10,
        4,
        "good",
        [
            (
                "remark",
                "손녀가 다음 달에 온다며 기뻐하심",
                "손녀가 다음 달에 온다고 기뻐하셨어요",
                None,
                None,
            ),
            ("observation", "점심을 다 드심", "점심은 다 드셨습니다", None, None),
            (
                "followup",
                "손녀 방문 날짜 확인",
                "손녀 오는 날짜를 다음에 여쭤봐야겠어요",
                None,
                None,
            ),
        ],
        [(13, "무릎은 지난번과 비슷하다고 하심")],
        True,
    ),
    (
        6,
        3,
        "neutral",
        [
            (
                "remark",
                "계단 내려갈 때 무릎이 아프다고 하심",
                "계단 내려갈 때 무릎이 아프다고 하셨어요",
                "knee",
                "pain",
            ),
            (
                "observation",
                "걸을 때 난간을 잡으심",
                "걸으실 때 난간을 꼭 잡으셨어요",
                None,
                "fall",
            ),
        ],
        [],
        False,
    ),
    (
        3,
        1,
        "low",
        [
            ("remark", "요즘 기운이 없다고 하심", "요즘 기운이 없다고 하셨어요", None, None),
            ("observation", "점심을 조금만 드심", "점심은 조금밖에 못 드셨어요", None, None),
            ("followup", "식사량 다시 확인", "다음에도 식사 잘 하시는지 볼게요", None, None),
        ],
        [(10, "손녀는 다음 달 15일에 온다고 하심")],
        False,
    ),
]


def seed_history(
    session: Session, recipient: Recipient, caregiver: User, manager: User, guardian: User
) -> None:
    """수급자에게 확정 기록이 하나도 없을 때만 만든다 (여러 번 실행해도 같음)."""
    exists = session.scalar(
        select(VisitRecord.id).where(VisitRecord.recipient_id == recipient.id).limit(1)
    )
    if exists is not None:
        return
    today = date.today()
    by_day: dict[int, VisitRecord] = {}
    for days_ago, meal, mood, items, checks, reviewed in _VISITS:
        visited = today - timedelta(days=days_ago)
        at = datetime.combine(visited, datetime.min.time(), UTC) + timedelta(hours=5)
        record = VisitRecord(
            id=uuid.uuid4(),
            recipient_id=recipient.id,
            caregiver_id=caregiver.id,
            visited_on=visited,
            recorded_at=at,
            status="confirmed",
            confirmed_at=at + timedelta(minutes=10),
            meal_level=meal,
            mood=mood,
            transcript=" ".join(evidence for _, _, evidence, _, _ in items),
            reviewed_by=manager.id if reviewed else None,
            reviewed_at=at + timedelta(hours=3) if reviewed else None,
            items=[
                RecordItem(
                    category=category,
                    content=content,
                    evidence=evidence,
                    body_part=part,
                    risk_tag=risk,
                    origin="ai",
                    position=n,
                )
                for n, (category, content, evidence, part, risk) in enumerate(items)
            ],
        )
        session.add(record)
        session.flush()
        for earlier, result in checks:
            target = next(i for i in by_day[earlier].items if i.category == "followup")
            session.add(
                FollowupCheck(
                    followup_item_id=target.id, record_id=record.id, result=result, origin="ai"
                )
            )
        session.flush()
        evaluate_alerts(session, record)  # 무릎 반복·식사량 감소 알림이 규칙으로 생긴다
        session.flush()
        by_day[days_ago] = record

    # 3일 전 방문의 보호자 하루 요약 (승인됨)
    latest = by_day[3]
    remark, observation = latest.items[0], latest.items[1]
    session.add(
        GuardianSummary(
            record_id=latest.id,
            status="approved",
            sentences=[
                {
                    "text": "어르신께서 요즘 기운이 없다고 말씀하셨습니다.",
                    "item_ids": [str(remark.id)],
                    "edited": False,
                },
                {
                    "text": "점심은 조금만 드셨습니다.",
                    "item_ids": [str(observation.id)],
                    "edited": False,
                },
            ],
            created_by=manager.id,
            approved_by=manager.id,
            approved_at=datetime.now(UTC),
        )
    )
    # 처리된 긴급 우려와 보호자 안내
    resolved_at = datetime.now(UTC) - timedelta(days=2)
    session.add(
        Alert(
            recipient_id=recipient.id,
            kind="urgent",
            key=str(uuid.uuid4()),
            evidence=[],
            note="밤에 무릎 통증으로 잠을 설치셨다고 함",
            created_by=caregiver.id,
            status="resolved",
            resolution="acted",
            resolution_note="보호자와 통화, 정형외과 진료 예약",
            resolved_by=manager.id,
            resolved_at=resolved_at,
            guardian_message="무릎 통증 때문에 이번 주 금요일 정형외과 진료를 예약해 두었습니다.",
            shared_at=resolved_at,
            shared_with=[guardian.id],
        )
    )
