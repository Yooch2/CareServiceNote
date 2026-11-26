# 1단계 설계: 음성 기록 → AI 초안 → 검토·확정

작성일 2026-11-27

## 1. 목표와 범위

요양보호사가 방문 직후 남긴 음성 기록을 전사하고, AI가 **말씀 / 관찰 / 다음 확인** 초안을 만든 뒤 요양보호사가 검토·확정하는 흐름을 끝까지 동작하게 만든다.

포함
- 회원가입·로그인 (요양보호사)
- 수급자 목록·추가
- 녹음(또는 파일 업로드) → 백그라운드 전사·분류 → 검토·확정
- 검토 화면: 근거 구간 강조·재생, AI 작성 표시, 위험 항목 강조, 빠진 주제 안내, 녹음 전 고지 확인
- 실패 시 직접 작성으로 확정
- 오프라인 녹음 후 재전송 (마지막 작업)

제외 (이후 단계)
- 담당 배정, 기관, 보호자, 역할별 권한, 동의 관리 → 3단계
- 인계 요약, 키워드 검색 → 2단계
- 변화 알림 → 4단계 / 요약 공유·메시지 → 5단계 / 수정 이력·사진·암호화 → 6단계

1단계에서는 로그인한 사용자 누구나 모든 수급자를 볼 수 있다. 기록은 작성자 본인만 수정·확정할 수 있고, 확정 전 기록(전사문·초안·음성)은 작성자만 볼 수 있다. 확정된 기록은 로그인한 사용자 누구나 볼 수 있다 (다른 사람에게는 404).

## 2. AI 처리 방식

`AI_PROVIDER` 환경변수로 선택한다.

| 값 | 전사 | 분류 | 용도 |
|---|---|---|---|
| `fake` | 고정된 가상 전사문 | 고정된 분류 결과 | 테스트, 화면 개발, 오류 흉내 |
| `local` | mlx-whisper | Ollama (JSON 스키마 지정) | 비용 0원 로컬 실행 (macOS) |
| `gemini` | Gemini (음성 입력) | Gemini (`response_schema`) | 배포 데모, 무료 등급 |

- Gemini 무료 등급은 입력 데이터가 서비스 개선에 쓰일 수 있다. 데모는 가상 데이터만 쓰고, 실제 운영이라면 유료 등급으로 바꿔야 한다는 점을 README에 적는다.
- 무료 한도를 넘지 않도록 앱에서 사용자당 하루 기록 수와 서비스 전체 하루 기록 수를 제한한다 (설정값).
- Gemini 전사의 구간 시각은 모델이 추정한 값이라 정확하지 않다. `approximate_times` 플래그로 화면에 표시한다.

## 3. 데이터 모델

모든 외부 노출 ID는 UUID. 상태·분류 값은 Postgres enum 대신 `text + CHECK`로 둔다.

### users
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid PK | |
| login_id | text unique | |
| password_hash | text | argon2 |
| display_name | text | |
| created_at | timestamptz | |

### recipients
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid PK | |
| name | text | URL·로그·에러 메시지에 넣지 않는다 |
| created_at | timestamptz | |

### visit_records
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid PK | 클라이언트가 생성 (재전송 시 중복 방지) |
| recipient_id | uuid FK | |
| caregiver_id | uuid FK → users | |
| visited_on | date | |
| recorded_at | timestamptz | 녹음한 기기 시각 |
| status | text | `queued` `transcribing` `classifying` `draft_ready` `failed` `confirmed` |
| audio_path | text null | 확정 시 파일 삭제 후 null |
| transcript | text null | |
| transcript_segments | jsonb null | `[{start_ms, end_ms, text}]` |
| approximate_times | bool | 구간 시각이 추정값인지 |
| draft | jsonb null | AI 원본. 저장 후 수정하지 않음 |
| error_code | text null | |
| attempts | int | 일시 오류 재시도 횟수 |
| available_at | timestamptz | 다음 처리 가능 시각 (백오프) |
| claimed_at | timestamptz null | 워커가 가져간 시각 |
| created_at | timestamptz | |
| confirmed_at | timestamptz null | |

인덱스: `(status, available_at)` (워커 조회), `(recipient_id, visited_on desc)` (기록 목록), `(caregiver_id, created_at)` (사용량 제한).

### draft JSON
```json
{
  "items": [{
    "category": "remark | observation | followup",
    "content": "...",
    "evidence": "전사문에서 그대로 가져온 구절",
    "evidence_found": true,
    "segment_index": 3,
    "speaker_uncertain": false,
    "risk_tag": "fall | medication | pain | null"
  }],
  "missing_topics": ["meal", "toileting"]
}
```
- `evidence_found`, `segment_index`, `missing_topics`는 서버가 계산한다 (5절).

### record_items (확정 시 생성)
| 컬럼 | 타입 | 비고 |
|---|---|---|
| id | uuid PK | |
| record_id | uuid FK | |
| category | text | `remark` `observation` `followup` |
| content | text | |
| evidence | text null | |
| speaker_uncertain | bool | |
| risk_tag | text null | `fall` `medication` `pain` |
| origin | text | `ai` `ai_edited` `human` |
| position | int | |

### 상태 전이
```
queued → transcribing → classifying → draft_ready → confirmed
              │               │
              └──→ failed ←───┘   (일시 오류 3회 또는 영구 오류)
failed ──(직접 작성)──→ confirmed
```

## 4. API

Next.js `rewrites`로 `/api/*`를 FastAPI로 넘겨 같은 출처로 동작한다 (CORS 설정 없음).

### 인증
- `POST /auth/signup` — 아이디, 비밀번호(8자 이상), 표시 이름
- `POST /auth/login` — PyJWT(HS256, 12시간) 토큰을 httpOnly + SameSite=Lax 쿠키로 발급
- `POST /auth/logout`, `GET /auth/me`
- refresh 토큰 없음. 만료 시 다시 로그인.

### 수급자·기록
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/recipients` | 목록 |
| POST | `/recipients` | 추가 |
| GET | `/recipients/{id}` | 상세 |
| GET | `/recipients/{id}/records` | 기록 목록 (날짜·상태) |
| PUT | `/records/{id}` | multipart: audio, recipient_id, visited_on, recorded_at |
| GET | `/records/{id}` | 상태, 전사문, 구간, 초안, 확정 항목 |
| GET | `/records/{id}/audio` | 작성자 본인, 확정 전까지만 |
| POST | `/records/{id}/confirm` | 확정 |

`PUT /records/{id}`
- 새 id → 201, 상태 `queued`
- 같은 사용자가 같은 id로 다시 보냄 → 200, 기존 기록 반환 (파일 다시 저장하지 않음)
- 다른 사용자의 id → 409
- 10MB 초과 → 413, 허용 형식(webm, ogg, mp4, m4a, wav) 외 → 415
- 하루 사용량 초과 → 429

`POST /records/{id}/confirm`
```json
{
  "items": [{"draft_index": 0, "category": "...", "content": "...", "evidence": "...",
             "speaker_uncertain": false, "risk_tag": null}],
  "dismissed_draft_indexes": [2]
}
```
- 상태가 `draft_ready` 또는 `failed`가 아니면 409
- 초안의 모든 index가 `items[].draft_index` 또는 `dismissed_draft_indexes` 중 한 곳에 정확히 한 번 나와야 한다. 아니면 422
- `origin`은 서버가 계산: draft_index가 있고 내용·분류가 초안과 같으면 `ai`, 다르면 `ai_edited`, draft_index가 없으면 `human`
- 성공 시 record_items 생성, 상태 `confirmed`, 오디오 파일 삭제

에러 응답에는 수급자 이름이나 전사문을 넣지 않는다.

## 5. 워커

`python -m app.worker`, API와 별도 프로세스.

1. 작업 하나를 가져온다
   - `status='queued' AND available_at <= now()`
   - 또는 `status IN ('transcribing','classifying') AND claimed_at < now() - 10분` (멈춘 작업 회수)
   - `FOR UPDATE SKIP LOCKED LIMIT 1`
2. 상태와 `claimed_at`을 바꾸고 바로 커밋
3. 전사문이 없으면 전사 → 저장 → `classifying`
4. 분류 → 후처리 → draft 저장 → `draft_ready`
5. 가져올 작업이 없으면 2초 대기

오류 처리
- 일시 오류(타임아웃, 429, 5xx): `attempts += 1`, `available_at = now() + 백오프(1회 실패 5초, 2회 실패 30초)`, 상태를 `queued`로 되돌림. 3회 실패하면 `failed`
- 영구 오류(오디오 해석 불가, 분류 결과 스키마가 재요청 1회 후에도 맞지 않음): 바로 `failed`, `error_code` 기록
- 로그에는 기록 id, 상태, 소요 시간만 남긴다

### 어댑터 인터페이스
```python
class Transcriber(Protocol):
    def transcribe(self, audio: Path) -> Transcript: ...   # text, segments, approximate_times

class Classifier(Protocol):
    def classify(self, transcript: Transcript) -> Classification: ...  # items, mentioned_topics
```

### 후처리 (공통 함수 하나)
- 근거 대조: 공백을 정규화한 뒤 전사문에 근거 구절이 그대로 있는지 확인해 `evidence_found` 설정. 항목을 지우지는 않는다
- `segment_index`: 근거 구절이 시작되는 구간
- `missing_topics`: 고정 목록(`meal`, `toileting`, `sleep`, `mood`)에서 LLM이 고른 `mentioned_topics`를 뺀 값

### 프롬프트 규칙
- 녹음에 없는 내용은 만들지 않는다. 해당 분류에 내용이 없으면 비워 둔다
- 낙상·투약·통증 같은 위험 항목은 판정하지 않고 `risk_tag`와 근거만 남긴다
- 누가 한 말인지 불분명하면 `speaker_uncertain: true`
- 수급자 말씀은 원래 말투를 유지한다

## 6. 화면

모바일 우선. URL에는 UUID만 쓴다.

| 경로 | 내용 |
|---|---|
| `/signup`, `/login` | 가입·로그인. 실제 개인정보·건강정보 입력 금지 안내 |
| `/` | 수급자 목록, 추가 |
| `/recipients/[id]` | 기록 목록, 기록하기 버튼 |
| `/recipients/[id]/record` | 녹음 전 고지 확인 체크 → 녹음/정지/다시 녹음 또는 파일 업로드 → 클라이언트 UUID로 PUT |
| `/records/[id]` | 상태별 화면 |

`/records/[id]`
- 처리 중: 1.5초 간격 폴링, "전사 중 / 분류 중" 표시
- 검토(`draft_ready`)
  - 전사문을 구간 단위로 표시, 구간을 누르면 그 시점부터 재생
  - 말씀 / 관찰 / 다음 확인 카드. 카드마다 AI 표시, 근거 구절, 확인·수정·삭제
  - 근거를 누르면 전사문 구간 강조 + 재생
  - `evidence_found: false`면 경고, `risk_tag`가 있으면 강조 표시
  - "언급 없음: 식사·배변" 안내
  - 직접 항목 추가 가능. AI 항목을 모두 처리해야 확정 버튼 활성화 (남은 개수 표시)
- 실패: 사유 표시, 전사문이 있으면 함께 보여 주고 직접 작성해 확정
- 확정: 읽기 전용

### 오프라인 녹음
- 업로드가 실패하면 음성, 메타데이터, UUID를 IndexedDB에 저장
- "업로드 대기 N건" 표시, `online` 이벤트나 앱 재시작 시 재전송 (같은 UUID라 중복 없음)
- 대기 데이터는 사용자별로 저장하고, 로그아웃 시 삭제

## 7. 테스트

백엔드 (pytest, 별도 테스트 DB `csn_test`, 테스트가 끝날 때마다 테이블 비우기. 워커 테스트가 실제 커밋과 행 잠금을 써야 해서 롤백 방식 대신 사용)
- 단위: 근거 대조, segment_index, missing_topics, 확정 검증, origin 계산
- API: 가입·로그인·쿠키, PUT 멱등성(201/200/409), 업로드 제한(413/415/429), 확정 검증(422/409), 남의 기록 접근 차단
- 워커: 동시 작업 가져오기(SKIP LOCKED), 재시도·백오프, 3회 실패, 분류부터 재개, 멈춘 작업 회수 (fake 어댑터로 오류 흉내)
- 실제 어댑터(local, gemini)는 `@pytest.mark.live`로 표시하고 수동 실행만

프론트
- `pnpm lint && pnpm build`
- Playwright E2E: 가입 → 수급자 추가 → 파일 업로드(fake) → 검토 → 확정
- 오프라인 재전송 시나리오
- E2E를 CI에 붙이는 건 7단계

## 8. 진행 순서

- PR①: 백엔드 (모델·마이그레이션, 인증, 수급자·기록 API, 워커, 어댑터 3종, 시드 스크립트)
- PR②: 화면 + 오프라인 녹음

## 참고한 제품

추가 기능은 공개 자료 기준으로 비교한 제품에서 가져왔다.

| 기능 | 참고 |
|---|---|
| 항목별 근거 구간 연결·재생 | Abridge (Linked Evidence), Birdie |
| AI 작성 표시, 사람이 확인하면 해제 | Microsoft Dragon Copilot |
| 녹음에 없는 내용은 비워 두기, 위험 항목은 판정하지 않기 | Dragon Copilot, Birdie |
| 빠진 항목 안내 | MatrixCare Voice |
| 녹음 전 고지 안내 | Heidi Health |
| 오프라인 기록 후 동기화 | Nourish, Birdie, Access Care Planning |
