import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from app.ai.types import TOPICS, Classification, Transcript

# NFKC가 바꾸지 않는 CJK 문장부호 (로컬 모델이 근거를 옮기며 바꿔 쓰는 경우가 있음)
_CJK_PUNCT = str.maketrans({"。": ".", "、": ",", "「": '"', "」": '"'})


def _norm(text: str) -> str:
    """근거 대조용 정규화: 전각 문장부호(，。！？)를 반각으로, 공백을 하나로."""
    text = unicodedata.normalize("NFKC", text).translate(_CJK_PUNCT)
    return re.sub(r"\s+", " ", text).strip()


def _norm_quote(text: str) -> str:
    """근거 구절용: 끝 문장부호는 무시한다 (전사문의 '하셨고,'를 '하셨고。'로 옮기는 경우)"""
    return _norm(text).rstrip(".,!?~ ")


def build_draft(
    transcript: Transcript,
    classification: Classification,
    followups: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """LLM 결과에 서버가 확인한 값(근거 존재 여부, 구간 위치, 빠진 주제)을 붙인다.

    followups는 분류에 넘긴 이전 확인 사항 {참조 번호: {item_id, content, visited_on}}.
    """
    followups = followups or {}
    full = _norm(transcript.text)
    joined = ""
    starts: list[int] = []
    for seg in transcript.segments:
        if joined:
            joined += " "
        starts.append(len(joined))
        joined += _norm(seg.text)

    def locate(raw_evidence: str) -> dict[str, Any]:
        evidence = _norm_quote(raw_evidence)
        segment_index: int | None = None
        if evidence and starts:
            pos = joined.find(evidence)
            if pos >= 0:
                segment_index = max(i for i, start in enumerate(starts) if start <= pos)
        return {
            "evidence_found": bool(evidence) and evidence in full,
            "segment_index": segment_index,
        }

    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in classification.items:
        evidence = _norm(item.evidence)
        key = (item.category, _norm(item.content), evidence)
        if key in seen:  # 작은 모델이 같은 항목을 두 번 내는 경우
            continue
        seen.add(key)
        items.append({**item.model_dump(), **locate(item.evidence)})

    # 분류에 넘긴 확인 사항에 대한 결과만, 사항마다 하나씩
    followup_results: list[dict[str, Any]] = []
    answered: set[str] = set()
    for fr in classification.followup_results:
        ref = fr.ref.strip()
        if ref not in followups or ref in answered or not fr.result.strip():
            continue
        answered.add(ref)
        followup_results.append(
            {
                "item_id": followups[ref]["item_id"],
                "result": fr.result.strip(),
                "evidence": fr.evidence,
                **locate(fr.evidence),
            }
        )

    # 근거 구절이 전사문에 실제로 있는 주제만 '언급됨'으로 본다
    mentioned = {
        m.topic
        for m in classification.mentioned_topics
        if _norm_quote(m.evidence) and _norm_quote(m.evidence) in full
    }
    # 근거가 전사문에 없는 상태 값은 버린다
    state = classification.state
    meal_found = (
        state.meal_level is not None and locate(state.meal_evidence or "")["evidence_found"]
    )
    mood_found = state.mood is not None and locate(state.mood_evidence or "")["evidence_found"]
    state_out: dict[str, Any] = {
        "meal_level": state.meal_level if meal_found else None,
        "meal_evidence": state.meal_evidence if meal_found else None,
        "mood": state.mood if mood_found else None,
        "mood_evidence": state.mood_evidence if mood_found else None,
    }
    return {
        "state": state_out,
        "items": items,
        "missing_topics": [t for t in TOPICS if t not in mentioned],
        "open_followups": list(followups.values()),
        "followup_results": followup_results,
    }
