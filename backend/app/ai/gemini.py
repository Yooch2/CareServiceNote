from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx2
from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.prompts import CLASSIFY_SYSTEM, TRANSCRIBE_PROMPT, classify_user_message
from app.ai.structured import parse_with_retry
from app.ai.types import Classification, OpenFollowup, Segment, Transcript
from app.audio_store import MEDIA_TYPES


class _SegmentOut(BaseModel):
    start_ms: int
    end_ms: int
    text: str


class _TranscriptOut(BaseModel):
    text: str
    segments: list[_SegmentOut]


class GeminiAI:
    """Gemini 하나로 전사와 분류를 모두 처리한다. 구간 시각은 모델 추정값이다."""

    def __init__(self, api_key: str, model: str, client: Any | None = None) -> None:
        if client is None and not api_key:
            raise PermanentAIError("gemini_key_missing")
        self._client = client or genai.Client(api_key=api_key)
        self.model = model

    def _generate(self, contents: Any, schema: type[BaseModel], system: str | None = None) -> str:
        try:
            res = self._client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_schema=schema,
                    temperature=0,
                ),
            )
        except errors.APIError as e:
            code = e.code or 0
            if code == 429 or code >= 500:
                raise TransientAIError(f"gemini_http_{code}") from e
            raise PermanentAIError(f"gemini_http_{code}") from e
        except httpx2.TransportError as e:
            # google-genai는 httpx가 아니라 httpx2로 통신한다
            raise TransientAIError("gemini_unreachable") from e
        return res.text or ""

    def transcribe(self, audio: Path) -> Transcript:
        part = types.Part.from_bytes(
            data=audio.read_bytes(), mime_type=MEDIA_TYPES.get(audio.suffix, "audio/webm")
        )
        out = parse_with_retry(
            lambda: self._generate([part, TRANSCRIBE_PROMPT], _TranscriptOut), _TranscriptOut
        )
        text = out.text.strip()
        if not text:
            raise PermanentAIError("empty_transcript")
        segments = [Segment(s.start_ms, s.end_ms, s.text.strip()) for s in out.segments]
        return Transcript(text, segments, approximate_times=True)

    def classify(
        self, transcript: Transcript, followups: Sequence[OpenFollowup] = ()
    ) -> Classification:
        user = classify_user_message(transcript.text, followups)
        return self.generate(CLASSIFY_SYSTEM, user, Classification)

    def generate[T: BaseModel](self, system: str, user: str, schema: type[T]) -> T:
        return parse_with_retry(lambda: self._generate(user, schema, system), schema)
