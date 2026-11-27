"""음성·사진 파일을 암호화해 저장한다 (Fernet: AES-128-CBC + HMAC).

디스크에는 암호문만 남고, 처리하거나 내려줄 때만 메모리에서 복호화한다.
키는 STORAGE_KEY 환경변수. 키를 잃으면 저장된 파일을 읽을 수 없다.
"""

import contextlib
import os
import re
import tempfile
import uuid
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Response

from app.config import settings

SUFFIX = ".enc"
_NO_KEY = "STORAGE_KEY가 없습니다. python -m app.storage 로 만들어 .env에 넣어 주세요"


class StorageKeyMissing(RuntimeError):
    pass


@cache
def _fernet(key: str) -> Fernet:
    return Fernet(key.encode())


def _cipher() -> Fernet:
    if not settings.storage_key:
        raise StorageKeyMissing(
            "STORAGE_KEY가 없습니다. python -m app.storage 로 만들어 .env에 넣어 주세요"
        )
    return _fernet(settings.storage_key)


def write(folder: Path, stem: str, data: bytes) -> Path:
    """암호화해 저장하고 경로를 돌려준다. 파일 이름은 매번 새로 만든다."""
    folder.mkdir(parents=True, exist_ok=True)
    path = (folder / f"{stem}-{uuid.uuid4().hex}{SUFFIX}").resolve()
    token = _cipher().encrypt(data)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(token)
    return path


def read(path: Path) -> bytes:
    data = path.read_bytes()
    if path.suffix != SUFFIX:
        # ponytail: 암호화 도입(6단계) 전에 저장된 개발용 파일.
        # 운영 데이터가 생기면 일괄 암호화한 뒤 이 분기를 지운다.
        return data
    try:
        return _cipher().decrypt(data)
    except InvalidToken as e:
        raise ValueError("파일을 복호화하지 못했습니다 (키가 다르거나 손상됨)") from e


@contextlib.contextmanager
def plain_copy(path: Path, suffix: str) -> Iterator[Path]:
    """경로가 필요한 처리(로컬 STT)를 위해 잠깐 복호화한 임시 파일. 끝나면 지운다."""
    fd, name = tempfile.mkstemp(suffix=suffix)  # 0600
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(read(path))
        yield Path(name)
    finally:
        Path(name).unlink(missing_ok=True)


def ranged_response(data: bytes, media_type: str, range_header: str | None) -> Response:
    """복호화한 바이트를 내려준다. 브라우저 오디오가 구간으로 이동할 수 있게 Range를 지원한다."""
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    total = len(data)
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", (range_header or "").strip())
    if not match or not any(match.groups()):
        return Response(data, media_type=media_type, headers=headers)
    first, last = match.groups()
    if first:
        start, end = int(first), int(last) if last else total - 1
    else:  # bytes=-500 → 마지막 500바이트
        start, end = max(total - int(last), 0), total - 1
    end = min(end, total - 1)
    if start > end:
        return Response(status_code=416, headers={**headers, "Content-Range": f"bytes */{total}"})
    headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return Response(data[start : end + 1], status_code=206, media_type=media_type, headers=headers)


def delete(path: str | None) -> None:
    if path:
        Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    print(Fernet.generate_key().decode())
