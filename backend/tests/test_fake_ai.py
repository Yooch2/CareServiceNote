from pathlib import Path

import pytest

from app.ai.errors import TransientAIError
from app.ai.factory import build_ai
from app.ai.fake import FAKE_CLASSIFICATION, FAKE_TRANSCRIPT, FakeClassifier, FakeTranscriber
from app.ai.postprocess import build_draft


def test_fake_data_is_self_consistent() -> None:
    draft = build_draft(FAKE_TRANSCRIPT, FAKE_CLASSIFICATION)
    assert all(item["evidence_found"] for item in draft["items"])
    assert [item["segment_index"] for item in draft["items"]] == [0, 1, 2, 3]
    assert draft["missing_topics"] == ["toileting", "sleep", "mood"]


def test_fake_failures_are_consumed_in_order() -> None:
    transcriber = FakeTranscriber(failures=[TransientAIError("timeout")])
    with pytest.raises(TransientAIError):
        transcriber.transcribe(Path("x.webm"))
    assert transcriber.transcribe(Path("x.webm")) == FAKE_TRANSCRIPT
    assert transcriber.calls == 2

    classifier = FakeClassifier()
    assert classifier.classify(FAKE_TRANSCRIPT) == FAKE_CLASSIFICATION


def test_factory_returns_fake_in_tests() -> None:
    transcriber, classifier = build_ai()
    assert isinstance(transcriber, FakeTranscriber)
    assert isinstance(classifier, FakeClassifier)
