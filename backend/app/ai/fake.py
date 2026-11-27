import re
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel

from app.ai.errors import AIError
from app.ai.summary import SummaryOut, SummarySentence
from app.ai.types import (
    Classification,
    DraftItem,
    FollowupResult,
    OpenFollowup,
    Segment,
    TopicMention,
    Transcript,
)

FAKE_TRANSCRIPT = Transcript(
    text=(
        "오늘 어르신이 오른쪽 무릎이 좀 불편하다고 하셨어요. "
        "그래도 날 좋으면 산책 나가고 싶다고 하셨고요. "
        "점심은 반 정도 드셨습니다. "
        "다음 방문 때 무릎 상태랑 산책 의향 다시 여쭤봐야 할 것 같아요."
    ),
    segments=[
        Segment(0, 4200, "오늘 어르신이 오른쪽 무릎이 좀 불편하다고 하셨어요."),
        Segment(4200, 8600, "그래도 날 좋으면 산책 나가고 싶다고 하셨고요."),
        Segment(8600, 11000, "점심은 반 정도 드셨습니다."),
        Segment(11000, 16500, "다음 방문 때 무릎 상태랑 산책 의향 다시 여쭤봐야 할 것 같아요."),
    ],
    approximate_times=False,
)

FAKE_CLASSIFICATION = Classification(
    items=[
        DraftItem(
            category="remark",
            content="오른쪽 무릎이 좀 불편하다",
            evidence="오른쪽 무릎이 좀 불편하다고 하셨어요",
            speaker_uncertain=False,
            risk_tag="pain",
        ),
        DraftItem(
            category="remark",
            content="날 좋으면 산책 나가고 싶다",
            evidence="날 좋으면 산책 나가고 싶다고 하셨고요",
            speaker_uncertain=False,
            risk_tag=None,
        ),
        DraftItem(
            category="observation",
            content="점심을 반 정도 드심",
            evidence="점심은 반 정도 드셨습니다",
            speaker_uncertain=False,
            risk_tag=None,
        ),
        DraftItem(
            category="followup",
            content="무릎 상태와 산책 의향 다시 확인",
            evidence="다음 방문 때 무릎 상태랑 산책 의향 다시 여쭤봐야",
            speaker_uncertain=False,
            risk_tag=None,
        ),
    ],
    mentioned_topics=[TopicMention(topic="meal", evidence="점심은 반 정도 드셨습니다")],
)


class FakeTranscriber:
    """고정된 가상 전사문을 돌려준다. failures에 넣은 오류를 앞에서부터 한 번씩 먼저 던진다."""

    def __init__(self, failures: Sequence[AIError] = ()) -> None:
        self.failures = list(failures)
        self.calls = 0

    def transcribe(self, audio: Path) -> Transcript:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return FAKE_TRANSCRIPT


FAKE_FOLLOWUP_RESULT = "무릎은 아직 불편하다고 하심"
FAKE_FOLLOWUP_EVIDENCE = "오른쪽 무릎이 좀 불편하다고 하셨어요"


class FakeClassifier:
    """분류와 요약을 흉내 낸다. 이전 확인 사항이 있으면 첫 번째 사항에 대한 결과를 하나 낸다."""

    def __init__(self, failures: Sequence[AIError] = ()) -> None:
        self.failures = list(failures)
        self.calls = 0
        self.last_followups: list[OpenFollowup] = []

    def classify(
        self, transcript: Transcript, followups: Sequence[OpenFollowup] = ()
    ) -> Classification:
        self.calls += 1
        self.last_followups = list(followups)
        if self.failures:
            raise self.failures.pop(0)
        if not followups:
            return FAKE_CLASSIFICATION
        result = FollowupResult(
            ref=followups[0].ref, result=FAKE_FOLLOWUP_RESULT, evidence=FAKE_FOLLOWUP_EVIDENCE
        )
        return FAKE_CLASSIFICATION.model_copy(update={"followup_results": [result]})

    def generate[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        if schema is SummaryOut:
            # 입력 앞의 두 항목을 그대로 한 문장씩 옮긴다
            lines = re.findall(r"^(I\d+)\. \[[^\]]*\] \[[^\]]*\] (.+)$", user, re.M)
            sentences = [SummarySentence(text=text, refs=[ref]) for ref, text in lines[:2]]
            return schema.model_validate(SummaryOut(sentences=sentences).model_dump())
        if schema is Classification:
            return schema.model_validate(FAKE_CLASSIFICATION.model_dump())
        raise NotImplementedError(schema.__name__)
