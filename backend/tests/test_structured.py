import pytest
from pydantic import BaseModel

from app.ai.errors import PermanentAIError
from app.ai.structured import parse_with_retry


class Out(BaseModel):
    value: int


def test_returns_first_valid() -> None:
    assert parse_with_retry(lambda: '{"value": 1}', Out).value == 1


def test_retries_once_then_succeeds() -> None:
    replies = iter(["not json", '{"value": 2}'])
    assert parse_with_retry(lambda: next(replies), Out).value == 2


def test_gives_up_after_second_failure() -> None:
    calls: list[int] = []

    def bad() -> str:
        calls.append(1)
        return '{"value": "x"}'

    with pytest.raises(PermanentAIError) as err:
        parse_with_retry(bad, Out)
    assert err.value.code == "invalid_ai_output"
    assert len(calls) == 2
