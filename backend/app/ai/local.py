from pathlib import Path
from typing import Any

import httpx

from app.ai.errors import PermanentAIError, TransientAIError
from app.ai.prompts import CLASSIFY_SYSTEM, classify_user_message
from app.ai.structured import parse_with_retry
from app.ai.types import Classification, Segment, Transcript


class LocalTranscriber:
    def __init__(self, model: str) -> None:
        self.model = model

    def transcribe(self, audio: Path) -> Transcript:
        try:
            import mlx_whisper  # pyright: ignore[reportMissingImports]
        except ImportError as e:
            raise PermanentAIError("local_stt_unavailable") from e
        try:
            result: dict[str, Any] = mlx_whisper.transcribe(
                str(audio), path_or_hf_repo=self.model, language="ko"
            )
        except Exception as e:
            # ffmpeg 디코딩 실패 등. 같은 파일로 다시 해도 결과가 같다고 본다.
            raise PermanentAIError("audio_unreadable") from e
        text = str(result.get("text", "")).strip()
        if not text:
            raise PermanentAIError("empty_transcript")
        segments = [
            Segment(int(s["start"] * 1000), int(s["end"] * 1000), str(s["text"]).strip())
            for s in result.get("segments", [])
        ]
        return Transcript(text, segments, approximate_times=False)


class OllamaClassifier:
    def __init__(
        self, url: str, model: str, num_ctx: int, client: httpx.Client | None = None
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self._client = client or httpx.Client(timeout=120)

    def classify(self, transcript: Transcript) -> Classification:
        return parse_with_retry(lambda: self._request(transcript.text), Classification)

    def _request(self, text: str) -> str:
        try:
            res = self._client.post(
                f"{self.url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "format": Classification.model_json_schema(),
                    "options": {"num_ctx": self.num_ctx, "temperature": 0},
                    "messages": [
                        {"role": "system", "content": CLASSIFY_SYSTEM},
                        {"role": "user", "content": classify_user_message(text)},
                    ],
                },
            )
        except httpx.TransportError as e:
            raise TransientAIError("llm_unreachable") from e
        if res.status_code == 429 or res.status_code >= 500:
            raise TransientAIError(f"llm_http_{res.status_code}")
        if res.status_code >= 400:
            raise PermanentAIError(f"llm_http_{res.status_code}")
        return str(res.json()["message"]["content"])
