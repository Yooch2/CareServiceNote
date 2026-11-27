from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import pytest
from google.genai import errors

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.fake import FAKE_CLASSIFICATION, FAKE_TRANSCRIPT
from app.ai.gemini import GeminiAI


class FakeModels:
    def __init__(self, replies: list[Any]) -> None:
        self.replies = replies
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(text=reply)


def _ai(replies: list[Any]) -> tuple[GeminiAI, FakeModels]:
    models = FakeModels(replies)
    return GeminiAI("key", "gemini-test", client=SimpleNamespace(models=models)), models


def test_transcribe_marks_times_approximate(tmp_path: Path) -> None:
    audio = tmp_path / "a.webm"
    audio.write_bytes(b"audio")
    reply = (
        '{"text": " 무릎이 아프대요 ", '
        '"segments": [{"start_ms": 0, "end_ms": 900, "text": "무릎이 아프대요"}]}'
    )
    ai, models = _ai([reply])
    transcript = ai.transcribe(audio)
    assert transcript.text == "무릎이 아프대요"
    assert transcript.approximate_times is True
    assert transcript.segments[0].end_ms == 900
    assert models.calls[0]["model"] == "gemini-test"


def test_classify_parses_schema() -> None:
    ai, _ = _ai([FAKE_CLASSIFICATION.model_dump_json()])
    assert ai.classify(FAKE_TRANSCRIPT) == FAKE_CLASSIFICATION


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, TransientAIError),
        (503, TransientAIError),
        (400, PermanentAIError),
        (403, PermanentAIError),
    ],
)
def test_api_errors_are_classified(code: int, expected: type[Exception]) -> None:
    ai, _ = _ai([errors.APIError(code, {"error": {"message": "x", "status": "X"}})])
    with pytest.raises(expected):
        ai.classify(FAKE_TRANSCRIPT)


def test_network_error_is_transient() -> None:
    ai, _ = _ai([httpx2.ConnectError("refused")])
    with pytest.raises(TransientAIError):
        ai.classify(FAKE_TRANSCRIPT)


def test_empty_transcript_is_permanent(tmp_path: Path) -> None:
    audio = tmp_path / "a.wav"
    audio.write_bytes(b"audio")
    ai, _ = _ai(['{"text": "  ", "segments": []}'])
    with pytest.raises(PermanentAIError):
        ai.transcribe(audio)


def test_missing_key_is_permanent() -> None:
    with pytest.raises(PermanentAIError):
        GeminiAI("", "gemini-test")
