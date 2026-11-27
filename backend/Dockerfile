# API와 워커가 같은 이미지를 쓴다 (명령만 다름)
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.10 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# 의존성 층을 먼저 만들어 코드만 바뀌면 다시 설치하지 않게 한다 (dev·local 그룹 제외)
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .

RUN useradd --system --uid 10001 app && mkdir -p /data/media && chown app /data/media
USER app
ENV PATH="/app/.venv/bin:$PATH" AUDIO_DIR=/data/media PYTHONUNBUFFERED=1
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
