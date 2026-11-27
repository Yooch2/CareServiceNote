import uuid
from pathlib import Path
from typing import BinaryIO

from app import storage
from app.config import settings

_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/wave": ".wav",
    "audio/x-wav": ".wav",
}
MEDIA_TYPES = {".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".wav": "audio/wav"}
_CHUNK = 1024 * 1024


class AudioTooLarge(Exception):
    pass


class AudioEmpty(Exception):
    pass


def extension_for(content_type: str | None) -> str | None:
    if not content_type:
        return None
    return _EXTENSIONS.get(content_type.split(";")[0].strip().lower())


def save(record_id: uuid.UUID, src: BinaryIO, ext: str) -> Path:
    """크기를 확인하며 읽고 암호화해 저장한다.

    파일 이름에 원래 확장자를 남겨 형식을 알 수 있게 한다.
    """
    data = bytearray()
    while chunk := src.read(_CHUNK):
        data += chunk
        if len(data) > settings.max_audio_bytes:
            raise AudioTooLarge
    if not data:
        raise AudioEmpty
    return storage.write(settings.audio_dir, f"{record_id}{ext}", bytes(data))


def original_suffix(path: Path) -> str:
    """'<id>.webm-<랜덤>.enc' → '.webm' (암호화 전 파일은 그대로 확장자)"""
    if path.suffix != storage.SUFFIX:
        return path.suffix
    return "." + path.name.split(".")[1].split("-")[0]


def media_type(path: Path) -> str:
    return MEDIA_TYPES.get(original_suffix(path), "application/octet-stream")


delete = storage.delete
