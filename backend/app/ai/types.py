from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from app.schemas import BodyPart, Category, MealLevel, Mood, RiskTag

Topic = Literal["meal", "toileting", "sleep", "mood"]
TOPICS: tuple[Topic, ...] = ("meal", "toileting", "sleep", "mood")


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: list[Segment]
    approximate_times: bool


class DraftItem(BaseModel):
    category: Category
    content: str
    evidence: str
    speaker_uncertain: bool
    risk_tag: RiskTag | None
    body_part: BodyPart | None = None


class VisitState(BaseModel):
    """오늘 상태: 식사량(0 거의 못 드심 ~ 4 다 드심)과 기분. 언급이 없으면 null."""

    meal_level: MealLevel | None = None
    meal_evidence: str | None = None
    mood: Mood | None = None
    mood_evidence: str | None = None


class TopicMention(BaseModel):
    topic: Topic
    evidence: str


class FollowupResult(BaseModel):
    """이전 방문의 확인 사항(ref: F1, F2 ...)에 대해 이번 녹음에서 찾은 답"""

    ref: str
    result: str
    evidence: str


class Classification(BaseModel):
    items: list[DraftItem]
    mentioned_topics: list[TopicMention]
    followup_results: list[FollowupResult] = []
    state: VisitState = VisitState()


@dataclass(frozen=True)
class OpenFollowup:
    """LLM에 넘기는 이전 확인 사항. 이름·UUID 없이 참조 번호와 내용만."""

    ref: str
    content: str
    visited_on: date


class Transcriber(Protocol):
    def transcribe(self, audio: Path) -> Transcript: ...


class Classifier(Protocol):
    def classify(
        self, transcript: Transcript, followups: Sequence[OpenFollowup] = ()
    ) -> Classification: ...


class StructuredLLM(Protocol):
    """시스템·사용자 메시지를 보내 스키마에 맞는 응답을 받는다 (형식이 틀리면 한 번 재요청)."""

    def generate[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T: ...
