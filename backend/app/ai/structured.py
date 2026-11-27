from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from app.ai.errors import PermanentAIError


def parse_with_retry[T: BaseModel](request: Callable[[], str], model: type[T]) -> T:
    """응답이 스키마에 맞지 않으면 한 번 더 요청하고, 그래도 안 되면 영구 오류로 본다."""
    for _ in range(2):
        try:
            return model.model_validate_json(request())
        except ValidationError:
            continue
    raise PermanentAIError("invalid_ai_output")
