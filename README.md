# 돌봄수첩 (CareServiceNote)

> 오늘의 기록을 다음 돌봄으로

방문요양 요양보호사가 방문 직후 남긴 짧은 음성 기록을 AI가 **수급자의 말씀 · 관찰 · 다음 확인 사항**으로 정리하고,
요양보호사가 확정한 기록을 다음 방문 전 확인, 담당자 인계, 후속 확인으로 이어 주는 서비스입니다.

## 왜 만들었나

- 장기요양 인정자 123만 5,045명(2025), 재가급여 수급자 중 독거가구 43.6%
- 요양보호사가 바뀌면 수급자의 생활 습관과 요청이 새 담당자에게 잘 전달되지 않고, 보호자는 같은 설명을 반복하게 됨
- 방문요양 평가 기준상 직원 변경 시 인계와 급여 개시 후 14일 이내 상담 기록 확인이 필요함

## 핵심 흐름

1. 방문 후 약 1분 음성 기록
2. STT → LLM이 분류 초안 생성 → 요양보호사가 검토·확정
3. 다음 방문 전 확인 사항과 인계 요약 조회 (요약마다 근거 기록 연결)
4. 방문 중 확인한 결과를 원래 기록에 연결

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| Backend | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS |
| AI | Whisper 계열 STT, LLM 구조화 출력 (로컬 / API 전환) |
| Infra | Docker Compose, GitHub Actions |

## 로컬 실행

```bash
# DB
docker compose up -d --wait

# Backend (http://localhost:8000/docs)
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# Frontend (http://localhost:3100)
cd frontend
pnpm install
pnpm dev
```

## 테스트

```bash
cd backend && uv run pytest
cd frontend && pnpm lint
```

## 개인정보 원칙

이 저장소의 모든 수급자·기록 데이터는 가상으로 만든 것입니다. 실제 건강정보는 사용하지 않습니다.
