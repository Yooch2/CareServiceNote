"""7단계: 평가셋·지표. 알림 규칙 시나리오는 CI에서 전부 맞아야 한다."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.fake import FakeClassifier
from app.evaluation.__main__ import classify
from app.evaluation.alerts_eval import run_alert_scenarios
from app.evaluation.dataset import SCENARIOS
from app.evaluation.metrics import cer, score, summary_table
from app.models import Alert, VisitRecord

BY_ID = {s.id: s for s in SCENARIOS}


def _item(category: str, content: str, **kw: Any) -> dict[str, Any]:
    return {"category": category, "content": content, "evidence_found": True, **kw}


def test_alert_rule_scenarios_all_match(db: Session) -> None:
    results = run_alert_scenarios(db)
    assert [r.scenario.id for r in results if not r.ok] == []
    # 평가는 DB에 아무것도 남기지 않는다
    assert db.scalar(select(func.count()).select_from(VisitRecord)) == 0
    assert db.scalar(select(func.count()).select_from(Alert)) == 0


def test_perfect_answer_scores_full() -> None:
    draft = {
        "items": [
            _item("remark", "오른쪽 무릎이 불편하다", body_part="knee", risk_tag="pain"),
            _item("remark", "날 좋으면 산책하고 싶다"),
            _item("observation", "점심을 반 정도 드심"),
            _item("followup", "무릎 상태 다시 확인"),
        ],
        "state": {"meal_level": 2, "mood": None},
        "followup_results": [],
    }
    table = summary_table(score(BY_ID["basic-knee-walk"], draft))
    assert table["항목 재현율"] == table["항목 정밀도"] == 1.0
    assert table["부위 정확도"] == table["위험 표시 재현율"] == table["식사량 정확도"] == 1.0


def test_hard_negatives_are_counted() -> None:
    draft = {
        "items": [
            _item("observation", "무릎 담요를 덮어 드림", body_part="knee"),  # 부위 오탐
            _item("remark", "따뜻하다고 하심"),
            _item("remark", "로또 이야기"),  # 정답에도 허용 목록에도 없음
        ],
        "state": {"meal_level": 4, "mood": "good"},
        "followup_results": [],
    }
    c = score(BY_ID["blanket-not-pain"], draft)
    assert (c.part_false, c.false_items, c.hit, c.expected) == (1, 1, 2, 2)

    wrong_followup = {
        "items": [],
        "state": {"meal_level": None, "mood": "good"},
        "followup_results": [{"item_id": "F1"}],  # 답이 없는 사항에 답
    }
    c = score(BY_ID["followup-none"], wrong_followup)
    assert c.followup_false == 1 and c.hit == 0

    invented_meal = {"items": [], "state": {"meal_level": 2}, "followup_results": []}
    assert score(BY_ID["back-pain-hand"], invented_meal).meal_false == 1


def test_runner_classifies_with_masking() -> None:
    draft, _ = classify(FakeClassifier(), BY_ID["contact-masked"])
    assert "items" in draft  # fake는 고정 결과지만 실행 경로(마스킹 → 분류 → 후처리)는 같다


def test_cer() -> None:
    assert cer("무릎이 불편하다", "무릎이 불편하다.") == 0
    assert cer("무릎이 불편하다", "무릎이 불편하다고") == 1 / 7
    assert cer("가나다", "") == 1
