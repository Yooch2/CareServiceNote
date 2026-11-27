import pytest
from pydantic import ValidationError

from app.ai.postprocess import build_draft
from app.ai.types import (
    Classification,
    DraftItem,
    FollowupResult,
    Segment,
    TopicMention,
    Transcript,
    VisitState,
)

TRANSCRIPT = Transcript(
    text="오늘 어르신이   무릎이 아프다고 하셨어요.\n점심은 반 정도 드셨습니다.",
    segments=[
        Segment(0, 3000, "오늘 어르신이 무릎이 아프다고 하셨어요."),
        Segment(3000, 6000, "점심은 반 정도 드셨습니다."),
    ],
    approximate_times=False,
)


def _item(evidence: str, category: str = "remark") -> DraftItem:
    return DraftItem.model_validate(
        {
            "category": category,
            "content": "내용",
            "evidence": evidence,
            "speaker_uncertain": False,
            "risk_tag": None,
        }
    )


def test_evidence_matching_ignores_whitespace_and_finds_segment() -> None:
    draft = build_draft(
        TRANSCRIPT,
        Classification(
            items=[_item("어르신이 무릎이 아프다고"), _item("반 정도 드셨")], mentioned_topics=[]
        ),
    )
    first, second = draft["items"]
    assert first["evidence_found"] is True and first["segment_index"] == 0
    assert second["evidence_found"] is True and second["segment_index"] == 1
    assert first["evidence"] == "어르신이 무릎이 아프다고"


def test_unfound_evidence_is_flagged_not_dropped() -> None:
    draft = build_draft(
        TRANSCRIPT, Classification(items=[_item("허리가 아프다"), _item("")], mentioned_topics=[])
    )
    assert [i["evidence_found"] for i in draft["items"]] == [False, False]
    assert [i["segment_index"] for i in draft["items"]] == [None, None]


def test_no_segments_gives_no_index() -> None:
    plain = Transcript(text=TRANSCRIPT.text, segments=[], approximate_times=True)
    draft = build_draft(plain, Classification(items=[_item("반 정도 드셨")], mentioned_topics=[]))
    assert draft["items"][0]["evidence_found"] is True
    assert draft["items"][0]["segment_index"] is None


def test_missing_topics_in_fixed_order() -> None:
    mentions = [
        TopicMention(topic="mood", evidence="무릎이 아프다고"),
        TopicMention(topic="meal", evidence="점심은 반 정도"),
    ]
    draft = build_draft(TRANSCRIPT, Classification(items=[], mentioned_topics=mentions))
    assert draft["missing_topics"] == ["toileting", "sleep"]
    assert draft["items"] == []


def test_topic_without_real_evidence_still_counts_as_missing() -> None:
    mentions = [
        TopicMention(topic="meal", evidence="점심은 반 정도"),
        TopicMention(topic="toileting", evidence="화장실 다녀오셨어요"),
        TopicMention(topic="mood", evidence=""),
    ]
    draft = build_draft(TRANSCRIPT, Classification(items=[], mentioned_topics=mentions))
    assert draft["missing_topics"] == ["toileting", "sleep", "mood"]


def test_duplicate_items_are_merged() -> None:
    items = [_item("반 정도 드셨"), _item("반 정도  드셨"), _item("반 정도 드셨", "observation")]
    draft = build_draft(TRANSCRIPT, Classification(items=items, mentioned_topics=[]))
    assert [i["category"] for i in draft["items"]] == ["remark", "observation"]


def test_followup_results_map_refs_and_drop_unknown_or_duplicate() -> None:
    followups = {
        "F1": {"item_id": "item-1", "content": "무릎 상태 확인", "visited_on": "2026-11-20"},
        "F2": {"item_id": "item-2", "content": "식사량 확인", "visited_on": "2026-11-20"},
    }
    classification = Classification(
        items=[],
        mentioned_topics=[],
        followup_results=[
            FollowupResult(ref=" F1 ", result=" 아직 아프다고 하심 ", evidence="무릎이 아프다고"),
            FollowupResult(ref="F1", result="중복", evidence="무릎이 아프다고"),
            FollowupResult(ref="F9", result="없는 사항", evidence="점심은"),
            FollowupResult(ref="F2", result="반 정도 드심", evidence="저녁은 다 드셨"),
        ],
    )
    draft = build_draft(TRANSCRIPT, classification, followups)
    assert draft["open_followups"] == list(followups.values())
    assert draft["followup_results"] == [
        {
            "item_id": "item-1",
            "result": "아직 아프다고 하심",
            "evidence": "무릎이 아프다고",
            "evidence_found": True,
            "segment_index": 0,
        },
        {
            "item_id": "item-2",
            "result": "반 정도 드심",
            "evidence": "저녁은 다 드셨",
            "evidence_found": False,
            "segment_index": None,
        },
    ]


def test_draft_without_followups_has_empty_lists() -> None:
    draft = build_draft(TRANSCRIPT, Classification(items=[], mentioned_topics=[]))
    assert draft["open_followups"] == [] and draft["followup_results"] == []


def test_evidence_matching_ignores_full_width_punctuation() -> None:
    # 로컬 qwen2.5:7b가 근거를 옮기며 문장부호를 전각(，。)으로 바꿔 쓴 실제 사례
    transcript = Transcript(
        text="무릎은 어제보다 조금 나아졌다고 하셨고, 저녁은 다 드셨습니다.",
        segments=[
            Segment(0, 3000, "무릎은 어제보다 조금 나아졌다고 하셨고, 저녁은 다 드셨습니다.")
        ],
        approximate_times=False,
    )
    draft = build_draft(
        transcript,
        Classification(
            items=[
                _item("무릎은 어제보다 조금 나아졌다고 하셨고，"),
                _item("저녁은 다 드셨습니다。"),
            ],
            mentioned_topics=[],
        ),
    )
    assert [i["evidence_found"] for i in draft["items"]] == [True, True]
    assert [i["segment_index"] for i in draft["items"]] == [0, 0]


def test_state_kept_only_with_evidence_in_transcript() -> None:
    classification = Classification(
        items=[],
        mentioned_topics=[],
        state=VisitState(
            meal_level=2,
            meal_evidence="점심은 반 정도 드셨습니다",
            mood="low",
            mood_evidence="기운이 없어 보이셨어요",  # 전사문에 없음
        ),
    )
    state = build_draft(TRANSCRIPT, classification)["state"]
    assert (state["meal_level"], state["meal_evidence"]) == (2, "점심은 반 정도 드셨습니다")
    assert (state["mood"], state["mood_evidence"]) == (None, None)


def test_body_part_and_meal_level_validated() -> None:
    bad_part = {
        "category": "remark",
        "content": "x",
        "evidence": "x",
        "speaker_uncertain": False,
        "risk_tag": None,
        "body_part": "elbow",
    }
    with pytest.raises(ValidationError):
        DraftItem.model_validate(bad_part)
    with pytest.raises(ValidationError):
        VisitState(meal_level=5)


def test_trailing_punctuation_in_evidence_is_ignored() -> None:
    # 전사문은 '하셨어요.'인데 모델이 끝 부호를 바꿔 옮긴 경우
    classification = Classification(
        items=[_item("무릎이 아프다고 하셨어요。"), _item("점심은 반 정도 드셨습니다,")],
        mentioned_topics=[],
    )
    items = build_draft(TRANSCRIPT, classification)["items"]
    assert [i["evidence_found"] for i in items] == [True, True]
    assert [i["segment_index"] for i in items] == [0, 1]
