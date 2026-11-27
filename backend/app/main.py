from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import (
    alerts,
    auth,
    corrections,
    guardian,
    handover,
    org,
    photos,
    recipients,
    records,
    search,
    sharing,
)

app = FastAPI(title="CareServiceNote API", version="0.1.0")
app.include_router(auth.router)
app.include_router(recipients.router)
app.include_router(records.router)
app.include_router(handover.router)
app.include_router(search.router)
app.include_router(org.router)
app.include_router(guardian.router)
app.include_router(alerts.router)
app.include_router(sharing.router)
app.include_router(corrections.router)
app.include_router(photos.router)

# multipart 경계·폼 필드에 쓰이는 여유분
_FORM_OVERHEAD = 64 * 1024


_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def same_origin_only(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """브라우저가 다른 출처(같은 사이트의 하위 도메인 포함)에서 보낸 변경 요청을 막는다 (CSRF).

    SameSite=Lax 쿠키와 JSON 본문만으로는 같은 사이트의 다른 하위 도메인에서 보내는 본문 없는 POST나
    multipart 업로드를 막지 못한다. 최신 브라우저는 Sec-Fetch-Site를 보내므로 그것으로 거른다.
    헤더가 없는 요청(브라우저가 아닌 도구)은 쿠키 세션을 가질 일이 없어 그대로 둔다.
    """
    site = request.headers.get("sec-fetch-site")
    if request.method not in _SAFE_METHODS and site not in (None, "same-origin", "none"):
        return JSONResponse(
            {"detail": "다른 사이트에서 보낸 요청은 받지 않습니다"}, status_code=403
        )
    return await call_next(request)


@app.middleware("http")
async def limit_upload_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """음성·사진 업로드는 본문을 읽기 전에 Content-Length로 거른다 (파싱 중 디스크 소모 방지)."""
    path = request.url.path
    is_audio = request.method == "PUT" and path.startswith("/records/")
    is_photo = (
        request.method == "POST" and path.startswith("/records/") and path.endswith("/photos")
    )
    if is_audio or is_photo:
        limit = settings.max_audio_bytes if is_audio else settings.max_photo_bytes
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(
                {"detail": "Content-Length가 필요합니다"},
                status_code=status.HTTP_411_LENGTH_REQUIRED,
            )
        if not length.isdigit() or int(length) > limit + _FORM_OVERHEAD:
            return JSONResponse(
                {"detail": "요청 본문이 너무 큽니다"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
    return await call_next(request)


@app.get("/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "db": "unreachable"}
    return {"status": "ok", "db": "ok"}
