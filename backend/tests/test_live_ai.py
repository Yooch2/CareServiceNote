import shutil
import subprocess
from pathlib import Path

import pytest

from app.ai.gemini import GeminiAI
from app.ai.local import LocalTranscriber, OllamaClassifier
from app.ai.postprocess import build_draft
from app.config import settings

pytestmark = pytest.mark.live

SCRIPT = (
    "오늘 어르신이 오른쪽 무릎이 좀 불편하다고 하셨어요. "
    "점심은 반 정도 드셨고, 다음 방문 때 산책 의향을 다시 여쭤봐야겠어요."
)


@pytest.fixture(scope="session")
def sample_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """macOS 음성 합성(say)으로 가상 기록 음성을 만든다. 실제 녹음은 쓰지 않는다."""
    if not (shutil.which("say") and shutil.which("afconvert")):
        pytest.skip("macOS say/afconvert가 필요합니다")
    folder = tmp_path_factory.mktemp("audio")
    aiff, wav = folder / "sample.aiff", folder / "sample.wav"
    subprocess.run(["say", "-v", "Yuna", "-o", str(aiff), SCRIPT], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True
    )
    return wav


def test_local_pipeline(sample_audio: Path) -> None:
    transcript = LocalTranscriber(settings.mlx_whisper_model).transcribe(sample_audio)
    assert "무릎" in transcript.text
    assert transcript.segments

    classification = OllamaClassifier(
        settings.ollama_url, settings.ollama_model, settings.ollama_num_ctx
    ).classify(transcript)
    draft = build_draft(transcript, classification)
    print(draft)
    assert draft["items"]
    assert "meal" not in draft["missing_topics"]


def test_gemini_pipeline(sample_audio: Path) -> None:
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY가 없습니다")
    ai = GeminiAI(settings.gemini_api_key, settings.gemini_model)
    transcript = ai.transcribe(sample_audio)
    assert "무릎" in transcript.text
    draft = build_draft(transcript, ai.classify(transcript))
    print(draft)
    assert draft["items"]
