import re
from typing import Any

from app.ai.types import TOPICS, Classification, Transcript


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def build_draft(transcript: Transcript, classification: Classification) -> dict[str, Any]:
    """LLM 결과에 서버가 확인한 값(근거 존재 여부, 구간 위치, 빠진 주제)을 붙인다."""
    full = _norm(transcript.text)
    joined = ""
    starts: list[int] = []
    for seg in transcript.segments:
        if joined:
            joined += " "
        starts.append(len(joined))
        joined += _norm(seg.text)

    items: list[dict[str, Any]] = []
    for item in classification.items:
        evidence = _norm(item.evidence)
        segment_index: int | None = None
        if evidence and starts:
            pos = joined.find(evidence)
            if pos >= 0:
                segment_index = max(i for i, start in enumerate(starts) if start <= pos)
        items.append(
            {
                **item.model_dump(),
                "evidence_found": bool(evidence) and evidence in full,
                "segment_index": segment_index,
            }
        )

    mentioned = set(classification.mentioned_topics)
    return {"items": items, "missing_topics": [t for t in TOPICS if t not in mentioned]}
