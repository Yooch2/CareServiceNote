import json
from datetime import date

import httpx
import pytest

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.fake import FAKE_CLASSIFICATION, FAKE_TRANSCRIPT
from app.ai.local import OllamaClassifier
from app.ai.types import OpenFollowup


def _classifier(transport: httpx.MockTransport) -> OllamaClassifier:
    return OllamaClassifier(
        "http://ollama", "qwen2.5:7b", 8192, client=httpx.Client(transport=transport)
    )


def test_sends_schema_and_parses_reply() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        reply = {"message": {"content": FAKE_CLASSIFICATION.model_dump_json()}}
        return httpx.Response(200, json=reply)

    result = _classifier(httpx.MockTransport(handle)).classify(FAKE_TRANSCRIPT)
    assert result == FAKE_CLASSIFICATION
    assert seen["model"] == "qwen2.5:7b"
    assert seen["stream"] is False
    assert isinstance(seen["format"], dict) and "properties" in seen["format"]
    messages = seen["messages"]
    assert isinstance(messages, list) and FAKE_TRANSCRIPT.text in messages[1]["content"]


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503), TransientAIError),
        (httpx.Response(429), TransientAIError),
        (httpx.Response(404, json={"error": "model not found"}), PermanentAIError),
    ],
)
def test_http_errors_are_classified(response: httpx.Response, error: type[Exception]) -> None:
    with pytest.raises(error):
        _classifier(httpx.MockTransport(lambda _: response)).classify(FAKE_TRANSCRIPT)


def test_connection_error_is_transient() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(TransientAIError):
        _classifier(httpx.MockTransport(handle)).classify(FAKE_TRANSCRIPT)


def test_invalid_json_twice_is_permanent() -> None:
    reply = httpx.Response(200, json={"message": {"content": '{"items": 3}'}})
    with pytest.raises(PermanentAIError):
        _classifier(httpx.MockTransport(lambda _: reply)).classify(FAKE_TRANSCRIPT)


def test_previous_followups_are_sent_without_ids() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": FAKE_CLASSIFICATION.model_dump_json()}}
        )

    followups = [OpenFollowup("F1", "무릎 상태 다시 확인", date(2026, 11, 20))]
    _classifier(httpx.MockTransport(handle)).classify(FAKE_TRANSCRIPT, followups)
    messages = seen["messages"]
    assert isinstance(messages, list)
    assert "F1. 무릎 상태 다시 확인 (2026-11-20)" in messages[1]["content"]
