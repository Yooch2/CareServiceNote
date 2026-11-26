class AIError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TransientAIError(AIError):
    """잠시 뒤 다시 시도하면 될 수 있는 오류 (타임아웃, 429, 5xx)."""


class PermanentAIError(AIError):
    """다시 시도해도 같은 결과가 나올 오류 (해석 불가 오디오, 스키마 불일치 반복)."""
