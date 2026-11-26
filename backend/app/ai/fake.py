from collections.abc import Sequence
from pathlib import Path

from app.ai.errors import AIError
from app.ai.types import Classification, DraftItem, Segment, TopicMention, Transcript

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


class FakeClassifier:
    def __init__(self, failures: Sequence[AIError] = ()) -> None:
        self.failures = list(failures)
        self.calls = 0

    def classify(self, transcript: Transcript) -> Classification:
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return FAKE_CLASSIFICATION
