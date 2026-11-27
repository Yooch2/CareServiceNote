from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.routers import auth, guardian, handover, org, recipients, records, search

app = FastAPI(title="CareServiceNote API", version="0.1.0")
app.include_router(auth.router)
app.include_router(recipients.router)
app.include_router(records.router)
app.include_router(handover.router)
app.include_router(search.router)
app.include_router(org.router)
app.include_router(guardian.router)

# multipart 경계·폼 필드에 쓰이는 여유분
_FORM_OVERHEAD = 64 * 1024


@app.middleware("http")
async def limit_upload_size(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """음성 업로드는 본문을 읽기 전에 Content-Length로 거른다 (파싱 중 디스크 소모 방지)."""
    if request.method == "PUT" and request.url.path.startswith("/records/"):
        length = request.headers.get("content-length")
        if length is None:
            return JSONResponse(
                {"detail": "Content-Length가 필요합니다"},
                status_code=status.HTTP_411_LENGTH_REQUIRED,
            )
        if not length.isdigit() or int(length) > settings.max_audio_bytes + _FORM_OVERHEAD:
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
