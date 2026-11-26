from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from app.schemas import Category, RiskTag

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


class TopicMention(BaseModel):
    topic: Topic
    evidence: str


class Classification(BaseModel):
    items: list[DraftItem]
    mentioned_topics: list[TopicMention]


class Transcriber(Protocol):
    def transcribe(self, audio: Path) -> Transcript: ...


class Classifier(Protocol):
    def classify(self, transcript: Transcript) -> Classification: ...
