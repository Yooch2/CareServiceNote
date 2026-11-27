from app.ai.fake import FakeClassifier
from app.ai.summary import SummaryOut, SummarySentence, clean_summary, summarize


def test_clean_summary_drops_unknown_refs_and_unsupported_sentences() -> None:
    out = SummaryOut(
        sentences=[
            SummarySentence(text=" 무릎 불편이 반복됨 ", refs=["I1", "I9", "I1"]),
            SummarySentence(text="근거 없는 문장", refs=["I9"]),
            SummarySentence(text="참조 없음", refs=[]),
            SummarySentence(text="  ", refs=["I2"]),
        ]
    )
    assert clean_summary(out, {"I1": "a", "I2": "b"}) == [("무릎 불편이 반복됨", ["a"])]


def test_clean_summary_keeps_at_most_five_sentences() -> None:
    out = SummaryOut(sentences=[SummarySentence(text=f"문장{i}", refs=["I1"]) for i in range(8)])
    assert len(clean_summary(out, {"I1": 1})) == 5


def test_summarize_sends_numbered_lines() -> None:
    out = summarize(FakeClassifier(), ["I1. [2026-11-20] [말씀] 무릎이 불편하다"])
    assert out.sentences == [SummarySentence(text="무릎이 불편하다", refs=["I1"])]


def test_reference_markers_removed_from_text() -> None:
    out = SummaryOut(
        sentences=[
            SummarySentence(text="무릎이 불편하다고 하셨습니다. (I1)", refs=["I1"]),
            SummarySentence(text="산책을 원하셨어요 [I2, I3]", refs=["I2"]),
        ]
    )
    cleaned = clean_summary(out, {"I1": 1, "I2": 2})
    assert [t for t, _ in cleaned] == ["무릎이 불편하다고 하셨습니다.", "산책을 원하셨어요"]
