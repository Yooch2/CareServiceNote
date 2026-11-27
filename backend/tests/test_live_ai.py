import shutil
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.ai.gemini import GeminiAI
from app.ai.local import LocalTranscriber, OllamaClassifier
from app.ai.postprocess import build_draft
from app.ai.summary import clean_summary, summarize, summarize_for_guardian
from app.ai.types import OpenFollowup
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
    assert draft["state"]["meal_level"] in (2, None)  # 작은 모델은 비울 수 있지만 틀린 값은 안 됨


def test_gemini_pipeline(sample_audio: Path) -> None:
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY가 없습니다")
    ai = GeminiAI(settings.gemini_api_key, settings.gemini_model)
    transcript = ai.transcribe(sample_audio)
    assert "무릎" in transcript.text
    draft = build_draft(transcript, ai.classify(transcript))
    print(draft)
    assert draft["items"]
    assert "knee" in {i["body_part"] for i in draft["items"]}, "무릎 불편 항목에 부위가 있어야 한다"
    assert draft["state"]["meal_level"] == 2, "점심 반 정도 = 2(절반)"


# 두 번째 방문: 지난번 '다음 확인' 사항에 대한 답이 들어 있는 기록
SECOND_VISIT = (
    "지난번에 여쭤보기로 한 산책은 오늘은 집에서 쉬고 싶다고 하셨어요. "
    "무릎은 어제보다 조금 나아졌다고 하셨고, 저녁은 다 드셨습니다."
)
FOLLOWUPS = [
    OpenFollowup("F1", "산책 의향 다시 여쭤보기", date(2026, 11, 20)),
    OpenFollowup("F2", "무릎 상태 다시 확인", date(2026, 11, 20)),
    OpenFollowup("F3", "복약 시간 지키시는지 확인", date(2026, 11, 20)),
]
REFS = {
    f.ref: {"item_id": f.ref.lower(), "content": f.content, "visited_on": "2026-11-20"}
    for f in FOLLOWUPS
}


def _check_followups(draft: dict[str, object]) -> None:
    results = {r["item_id"]: r for r in draft["followup_results"]}  # type: ignore[index, union-attr]
    print(results)
    assert {"f1", "f2"} <= set(results), "산책·무릎 사항의 답을 찾아야 한다"
    assert "f3" not in results, "녹음에 없는 복약 사항은 비워 둬야 한다"
    assert all(r["evidence_found"] for r in results.values())


@pytest.fixture(scope="session")
def second_audio(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if not (shutil.which("say") and shutil.which("afconvert")):
        pytest.skip("macOS say/afconvert가 필요합니다")
    folder = tmp_path_factory.mktemp("audio2")
    aiff, wav = folder / "second.aiff", folder / "second.wav"
    subprocess.run(["say", "-v", "Yuna", "-o", str(aiff), SECOND_VISIT], check=True)
    subprocess.run(
        ["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(wav)], check=True
    )
    return wav


def test_gemini_followups_and_summary(second_audio: Path) -> None:
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY가 없습니다")
    ai = GeminiAI(settings.gemini_api_key, settings.gemini_model)
    transcript = ai.transcribe(second_audio)
    _check_followups(build_draft(transcript, ai.classify(transcript, FOLLOWUPS), REFS))

    lines = [
        "I1. [2026-11-20] [말씀] 오른쪽 무릎이 불편하다",
        "I2. [2026-11-20] [다음 확인] 무릎 상태 다시 확인",
        "I3. [2026-11-27] [확인 결과] 무릎 상태 다시 확인 → 조금 나아졌다고 하심",
        "I4. [2026-11-27] [말씀] 오늘은 집에서 쉬고 싶다",
    ]
    out = summarize(ai, lines)
    print(out)
    cleaned = clean_summary(out, {f"I{i}": i for i in range(1, 5)})
    assert cleaned and len(cleaned) == len(out.sentences), "모든 문장에 실제 근거가 있어야 한다"


def test_local_followups(second_audio: Path) -> None:
    transcript = LocalTranscriber(settings.mlx_whisper_model).transcribe(second_audio)
    classifier = OllamaClassifier(
        settings.ollama_url, settings.ollama_model, settings.ollama_num_ctx
    )
    _check_followups(build_draft(transcript, classifier.classify(transcript, FOLLOWUPS), REFS))


GUARDIAN_LINES = [
    "I1. [말씀] 오른쪽 무릎이 좀 불편하다",
    "I2. [말씀] 날 좋으면 산책 나가고 싶다",
    "I3. [관찰] 점심을 반 정도 드심",
    "I4. [다음 확인] 무릎 상태와 산책 의향 다시 확인",
]


def _check_guardian_summary(llm: Any) -> None:
    refs = {f"I{n}": n for n in range(1, 5)}
    out = summarize_for_guardian(llm, GUARDIAN_LINES)
    print(out)
    cleaned = clean_summary(out, refs, limit=3)
    assert cleaned and len(cleaned) == len(out.sentences[:3]), "모든 문장에 실제 근거가 있어야 한다"
    text = " ".join(t for t, _ in cleaned)
    assert "진단" not in text and "병원" not in text, "목록에 없는 조언을 하지 않아야 한다"


def test_gemini_guardian_summary() -> None:
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY가 없습니다")
    _check_guardian_summary(GeminiAI(settings.gemini_api_key, settings.gemini_model))


def test_local_guardian_summary() -> None:
    _check_guardian_summary(
        OllamaClassifier(settings.ollama_url, settings.ollama_model, settings.ollama_num_ctx)
    )
