import uuid
from pathlib import Path
from typing import BinaryIO

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
    """기록마다 고유 파일명으로 저장한다. 같은 id 동시 업로드에서 서로의 파일을 덮어쓰지 않게."""
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    path = (settings.audio_dir / f"{record_id}-{uuid.uuid4().hex}{ext}").resolve()
    written = 0
    try:
        with path.open("wb") as out:
            while chunk := src.read(_CHUNK):
                written += len(chunk)
                if written > settings.max_audio_bytes:
                    raise AudioTooLarge
                out.write(chunk)
        if written == 0:
            raise AudioEmpty
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def delete(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)
