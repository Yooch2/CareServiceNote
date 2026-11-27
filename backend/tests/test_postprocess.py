from app.ai.postprocess import build_draft
from app.ai.types import Classification, DraftItem, Segment, TopicMention, Transcript

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
