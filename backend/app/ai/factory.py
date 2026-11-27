from app.ai.fake import FakeClassifier, FakeTranscriber
from app.ai.types import Classifier, StructuredLLM, Transcriber
from app.config import settings


def build_ai() -> tuple[Transcriber, Classifier]:
    match settings.ai_provider:
        case "fake":
            return FakeTranscriber(), FakeClassifier()
        case "local":
            # mlx-whisper는 macOS 전용 선택 의존성이라 필요할 때만 import
            from app.ai.local import LocalTranscriber, OllamaClassifier

            return (
                LocalTranscriber(settings.mlx_whisper_model),
                OllamaClassifier(
                    settings.ollama_url, settings.ollama_model, settings.ollama_num_ctx
                ),
            )
        case "gemini":
            from app.ai.gemini import GeminiAI

            gemini = GeminiAI(settings.gemini_api_key, settings.gemini_model)
            return gemini, gemini


def build_llm() -> StructuredLLM:
    """API 프로세스에서 쓰는 구조화 생성 모델 (인계 요약)"""
    match settings.ai_provider:
        case "fake":
            return FakeClassifier()
        case "local":
            from app.ai.local import OllamaClassifier

            return OllamaClassifier(
                settings.ollama_url, settings.ollama_model, settings.ollama_num_ctx
            )
        case "gemini":
            from app.ai.gemini import GeminiAI

            return GeminiAI(settings.gemini_api_key, settings.gemini_model)
