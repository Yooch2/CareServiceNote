"""알림 규칙 평가: 시나리오마다 가상 기록을 만들어 규칙을 돌리고, 끝나면 되돌린다(rollback)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts import evaluate_alerts
from app.evaluation.dataset import ALERT_SCENARIOS, AlertScenario
from app.models import Alert, Organization, Recipient, RecordItem, User, VisitRecord

D0 = date(2026, 11, 1)


@dataclass(frozen=True)
class AlertResult:
    scenario: AlertScenario
    got: frozenset[tuple[str, str]]

    @property
    def ok(self) -> bool:
        return self.got == self.scenario.expected


def _run_one(db: Session, scenario: AlertScenario) -> frozenset[tuple[str, str]]:
    org = Organization(name="평가용 가상센터")
    db.add(org)
    db.flush()
    user = User(
        org_id=org.id, role="caregiver", login_id=f"eval{uuid.uuid4().hex[:8]}",
        password_hash="x", display_name="평가",
    )  # fmt: skip
    recipient = Recipient(org_id=org.id, name="평가용 가상수급자")
    db.add_all([user, recipient])
    db.flush()
    for n, visit in enumerate(scenario.visits):
        parts = [(p, False) for p in visit.parts] + [(p, True) for p in visit.uncertain_parts]
        record = VisitRecord(
            id=uuid.uuid4(),
            recipient_id=recipient.id,
            caregiver_id=user.id,
            visited_on=D0 + timedelta(days=visit.day),
            recorded_at=datetime.now(UTC),
            status="confirmed",
            confirmed_at=datetime.now(UTC) + timedelta(seconds=n),
            meal_level=visit.meal_level,
            items=[
                RecordItem(
                    category="remark",
                    content=f"{part} 불편",
                    origin="ai",
                    position=i,
                    body_part=part,
                    speaker_uncertain=uncertain,
                )  # fmt: skip
                for i, (part, uncertain) in enumerate(parts)
            ],
        )
        db.add(record)
        db.flush()
        evaluate_alerts(db, record)
        db.flush()
    rows = db.execute(
        select(Alert.kind, Alert.key).where(
            Alert.recipient_id == recipient.id, Alert.status == "open"
        )
    ).all()
    return frozenset((kind, key) for kind, key in rows)


def run_alert_scenarios(db: Session) -> list[AlertResult]:
    """DB에 아무것도 남기지 않는다 (시나리오마다 rollback)."""
    results = []
    for scenario in ALERT_SCENARIOS:
        try:
            results.append(AlertResult(scenario, _run_one(db, scenario)))
        finally:
            db.rollback()
    return results
