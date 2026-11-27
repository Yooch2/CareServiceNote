import json
from datetime import date

import httpx
import pytest

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.fake import FAKE_CLASSIFICATION, FAKE_TRANSCRIPT
from app.ai.local import OllamaClassifier
from app.ai.prompts import CLASSIFY_EXAMPLE_ANSWER, CLASSIFY_EXAMPLE_TRANSCRIPT
from app.ai.types import Classification, OpenFollowup


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
    assert isinstance(messages, list) and FAKE_TRANSCRIPT.text in messages[-1]["content"]
    # 시스템 → 예시(질문·답) → 실제 전사문 순서
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    Classification.model_validate_json(messages[2]["content"])


def test_example_is_valid_and_quotes_its_transcript() -> None:
    example = Classification.model_validate(CLASSIFY_EXAMPLE_ANSWER)
    for item in example.items:
        assert item.evidence in CLASSIFY_EXAMPLE_TRANSCRIPT
    for topic in example.mentioned_topics:
        assert topic.evidence in CLASSIFY_EXAMPLE_TRANSCRIPT


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
    assert "F1. 무릎 상태 다시 확인 (2026-11-20)" in messages[-1]["content"]


def test_runaway_output_fails_fast() -> None:
    """작은 모델이 같은 항목을 반복하다 길이 한도에 닿으면 재시도 없이 바로 실패한다.

    7단계 평가에서 h-handwash 시나리오가 "null" 항목을 끝없이 만들다 2분 시간 초과로 끝났다.
    """
    calls: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={"message": {"content": '{"items": [{"content": "null"'}, "done_reason": "length"},
        )

    with pytest.raises(PermanentAIError) as e:
        _classifier(httpx.MockTransport(handle)).classify(FAKE_TRANSCRIPT)
    assert e.value.code == "llm_output_too_long"
    assert len(calls) == 1
    options = calls[0]["options"]
    assert isinstance(options, dict) and options["num_predict"] == 1024
