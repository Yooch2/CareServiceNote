# 2단계 설계: 방문 전 확인 · 후속 확인 · 인계 요약 · 키워드 검색

작성일 2026-11-27

## 1. 목표와 범위

1단계에서 방문 한 번의 기록(녹음 → AI 초안 → 확정)이 만들어졌다. 2단계는 기록과 기록 사이를 잇는다. 기획안의 핵심 목표 "음성 기록 → AI 정리 → 인계 → 다음 방문 확인의 연속성"과 인계 검증 시나리오("담당자가 바뀌어도 이전 기록만으로 방문 전 확인 사항을 찾고, 방문 뒤 확인 결과를 원기록에 연결")를 동작하게 만든다.

포함
- **후속 확인**: 이전 방문의 '다음 확인' 항목을 다음 녹음과 연결한다. AI가 새 녹음에서 답이 되는 구절을 근거와 함께 제안하고, 요양보호사가 검토 화면에서 확인·수정·삭제한다. 확정하면 결과가 원래 항목에 연결되고 '확인 완료'가 된다.
- **방문 전 확인 화면**: 수급자 화면 위쪽에 남은 확인 사항, 기간 내 위험 항목, 최근 확인 결과, 후속 확인 완료율을 보여 준다.
- **인계 요약**: 위의 규칙 묶음에 더해, AI가 기간 내 확정 항목으로 짧은 요약 문장을 쓴다. 문장마다 근거 항목을 달고, 근거가 없거나 존재하지 않는 항목을 가리키는 문장은 서버가 버린다.
- **키워드 검색**: 수급자 화면에서 확정된 항목(내용·근거)과 확정 기록의 전사문을 찾는다. 분류·기간 필터.

제외
- 기관 담당자의 요약 검토·승인, 보호자 공유 → 3단계(권한)·5단계(공유)
- 방문 전 확인 화면에서 녹음 없이 결과를 직접 입력하는 기능 (검토 화면의 직접 입력으로 대신한다)
- 전체 수급자 대상 검색 (권한이 생기는 3단계 이후)

## 2. 결정과 이유

| 결정 | 이유 |
|---|---|
| 후속 확인 결과는 **AI 제안 + 사람 확인** | 녹음에 이미 답이 있는데 다시 손으로 쓰게 하면 기록 부담이 늘어난다. 1단계에서 만든 근거 검증·전부 확인해야 확정 구조를 그대로 쓸 수 있다. |
| 인계 요약은 **규칙 묶음 + AI 문장 요약** | 규칙 묶음(남은 확인 사항, 위험 항목)은 환각이 없고 AI가 실패해도 보인다. AI 문장은 읽기 편하지만 근거 없는 문장이 섞일 수 있어서 서버가 근거를 검증한다. |
| AI 요약은 **버튼을 눌렀을 때 만들고 저장** | 조회할 때마다 호출하면 무료 한도와 지연이 문제다. 저장된 요약보다 새로 확정된 기록이 있으면 "새 기록이 있음"을 표시하고 다시 만들 수 있게 한다. |
| AI 요약은 **API 요청 안에서 동기 호출** | 요약은 수 초 걸리는 단발성 작업이고 녹음처럼 재전송·재시도 흐름이 필요 없다. 워커 큐를 하나 더 만들지 않는다. 로컬 모델은 느릴 수 있어 타임아웃을 둔다. |
| 검색은 **수급자 안에서, 확정 항목 + 확정 기록 전사문** | 인계 상황("이 분 무릎은 언제부터?")에 맞고, 1단계 열람 범위(확정 기록은 로그인 사용자 모두)와 같다. 전체 수급자 검색은 권한이 생긴 뒤에 한다. |
| 검색은 **`pg_trgm` + `ILIKE`** | Postgres 기본 전문 검색은 한국어 형태소를 모른다. 부분 문자열 검색이 인계 용도에 충분하고, 트라이그램 인덱스로 3글자 이상 검색을 빠르게 한다. 2글자 검색은 순차 탐색이지만 수급자 한 명 범위라 문제없다. |
| LLM 호출을 **구조화 출력 하나로 일반화** | 분류와 요약이 같은 어댑터(Ollama, Gemini)를 쓴다. 어댑터에 `generate(system, user, schema)` 하나만 두고 분류·요약은 그 위의 함수로 만든다. 어댑터마다 기능별 메서드를 늘리지 않는다. |

## 3. 데이터 모델

### followup_checks (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| followup_item_id | uuid FK record_items, **unique** | 확인한 '다음 확인' 항목. 한 항목은 한 번만 확인 완료 |
| record_id | uuid FK visit_records (cascade) | 확인 결과를 남긴 방문 기록 |
| result | text | 확인 결과 ("오늘은 집에서 쉬고 싶다고 하심") |
| evidence | text null | 새 녹음의 근거 구절 |
| origin | text CHECK (ai, ai_edited, human) | 서버가 계산 |
| created_at | timestamptz | |

- **남은 확인 사항(open followup)** = 수급자의 확정 기록에 있는 `category='followup'` 항목 중 `followup_checks`가 없는 것. 작성자와 관계없이 수급자 기준이다(인계 목적).
- 같은 항목을 두 기록이 동시에 확인하면 unique 제약으로 하나만 성공하고 나머지는 409.

### handover_summaries (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| recipient_id | uuid FK | |
| days | int CHECK (7, 14, 30) | 요약 기간 |
| sentences | jsonb | `[{"text": "...", "item_ids": ["uuid", ...]}]` |
| covered_until | timestamptz null | 요약에 들어간 확정 기록 중 가장 늦은 `confirmed_at` |
| created_by | uuid FK users | |
| created_at | timestamptz | |

- 조회는 (recipient_id, days)의 가장 최근 행. 오래된 행은 남겨 둔다(요약 이력, 6단계 감사와 연결 가능).
- `stale` = 기간 안에 `confirmed_at > covered_until`인 확정 기록이 있음.

### 검색 인덱스
- `CREATE EXTENSION IF NOT EXISTS pg_trgm`
- `record_items.content`, `visit_records.transcript`에 `gin_trgm_ops` GIN 인덱스

### draft JSON 확장
```json
{
  "items": [...],
  "missing_topics": [...],
  "open_followups": [
    {"item_id": "uuid", "content": "무릎 상태와 산책 의향 다시 확인", "visited_on": "2026-11-20"}
  ],
  "followup_results": [
    {"item_id": "uuid", "result": "무릎은 아직 불편하다고 하심", "evidence": "...",
     "evidence_found": true, "segment_index": 0}
  ]
}
```
- `open_followups`: 분류 시점에 워커가 넣는 스냅샷 (최근 것부터 최대 10개). 검토 화면이 이 목록을 보여 준다.
- `followup_results`: LLM이 낸 결과 중 `open_followups`에 있는 항목만, 항목당 하나. 근거 검증은 일반 항목과 같은 함수로 한다.
- 1단계에서 만들어진 draft에는 두 키가 없으므로 화면·서버 모두 없으면 빈 목록으로 본다.

## 4. AI

### 어댑터 일반화
```python
class StructuredLLM(Protocol):
    def generate(self, system: str, user: str, schema: type[T]) -> T: ...
```
- `OllamaLLM`, `GeminiAI.generate`가 구현하고, 내부에서 `parse_with_retry`(스키마 불일치 시 1회 재요청)를 쓴다.
- `classify(llm, transcript, open_followups) -> Classification`과 `summarize(llm, items) -> SummaryOut`은 `app/ai/` 아래 순수 함수.
- 가짜 어댑터 `FakeLLM`은 스키마 타입에 따라 고정 응답을 돌려준다. 분류 응답은 열린 확인 사항이 있으면 첫 번째 항목에 대한 결과를 하나 낸다.

### 분류 프롬프트 확장
- 사용자 메시지에 `이전 방문에서 확인하기로 한 사항` 목록을 `F1. 내용 (날짜)` 형식으로 붙인다. 이름·UUID는 보내지 않는다.
- 규칙 추가: "전사문에 이전 확인 사항에 대한 답이 있으면 followup_results에 ref(F번호), result(확인 결과), evidence(전사문 구절 그대로)를 넣는다. 답이 없으면 넣지 않는다."
- 서버는 ref를 실제 item_id로 바꾸고, 없는 ref·중복 ref는 버린다.

### 인계 요약 프롬프트
- 입력: 기간 안 확정 항목(최대 60개, 최근 순)을 `I1. [날짜] [분류] 내용` 형식으로. 확인 결과도 `I7. [날짜] [확인 결과] 무릎 상태 → 아직 불편` 형식으로 포함.
- 출력: `sentences: [{text, refs: ["I1","I3"]}]`, 최대 5문장.
- 규칙: 주어진 항목에 없는 내용 금지, 진단·조언 금지, 문장마다 근거 ref 필수.
- 서버: 존재하지 않는 ref 제거, ref가 하나도 남지 않은 문장 버림. 모두 버려지면 `summary_empty`.

## 5. API

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/recipients/{id}/handover?days=14` | 방문 전 확인 묶음 + 저장된 AI 요약 |
| POST | `/recipients/{id}/handover/summary?days=14` | AI 요약 생성 (동기) |
| GET | `/recipients/{id}/search?q=&category=&days=` | 키워드 검색 |
| POST | `/records/{id}/confirm` | (확장) 후속 확인 결과 포함 |
| GET | `/records/{id}` | (확장) 항목별 확인 결과 |

`days`는 7, 14, 30만 허용 (기본 14). 기획안의 "용도별 조회 기간"과 공단 평가 매뉴얼의 "14일 이내 상담 기록 확인"을 참고했다.

### GET /recipients/{id}/handover
```json
{
  "days": 14,
  "last_visit_on": "2026-11-27",
  "open_followups": [{"item_id", "content", "evidence", "record_id", "visited_on"}],
  "risk_items": [{"item_id", "content", "risk_tag", "category", "record_id", "visited_on"}],
  "recent_checks": [{"followup_item_id", "followup_content", "result", "origin", "record_id", "visited_on"}],
  "completion": {"due": 4, "checked": 3},
  "summary": {"sentences": [{"text", "items": [{"item_id", "record_id", "visited_on"}]}],
              "created_at", "stale": false} | null
}
```
- 남은 확인 사항은 기간과 관계없이 전부(오래 남은 것일수록 중요), 위험 항목·확인 결과·완료율은 기간 안.
- 완료율: 기간 안 확정 기록에서 생긴 followup 항목 수(due) 중 확인된 수(checked). 기획안 품질 지표 "후속 확인 완료율 = 예정 항목 중 결과를 기록한 비율".

### POST /recipients/{id}/handover/summary
- 기간 안 확정 항목이 없으면 422 "요약할 확정 기록이 없습니다".
- 사용자당 하루 요약 생성 수 제한(`daily_summaries_per_user`, 기본 20). 초과 429.
- AI 일시 오류 → 503 "AI 요약을 잠시 만들 수 없습니다", 영구 오류·빈 요약 → 502 "AI 요약을 만들지 못했습니다". 규칙 묶음은 그대로 쓸 수 있다.
- 성공 시 `handover_summaries`에 저장하고 GET과 같은 `summary` 형식으로 돌려준다.

### GET /recipients/{id}/search
- `q`는 앞뒤 공백 제거 후 2~50자. `%`, `_`, `\`는 이스케이프.
- 대상: 확정 기록의 `record_items.content`, `record_items.evidence`, `visit_records.transcript`, `followup_checks.result`.
- 결과 최대 50개, 방문일 최근 순: `[{record_id, visited_on, kind: "item"|"check"|"transcript", category, text, item_id}]`. 전사문은 일치 위치 앞뒤 40자만 잘라서(`text`) 보낸다.
- `category` 필터는 항목에만 적용, `days` 없으면 전체 기간.

### POST /records/{id}/confirm 확장
```json
{
  "items": [...],
  "dismissed_draft_indexes": [...],
  "followup_checks": [{"item_id": "uuid", "result": "...", "evidence": "..." }],
  "dismissed_followup_items": ["uuid"]
}
```
- `followup_results`(AI 제안)에 있는 item_id는 `followup_checks` 또는 `dismissed_followup_items` 중 한 곳에 정확히 한 번 나와야 한다(1단계의 "AI 항목은 전부 처리" 규칙과 같다). 아니면 422.
- `followup_checks`의 item_id는 이 수급자의 **현재** 남은 확인 사항이어야 한다. 이미 확인됐으면 409 "이미 다른 기록에서 확인된 항목입니다", 다른 수급자 항목이거나 followup이 아니면 422.
- origin: AI 제안과 결과가 같으면 `ai`, 다르면 `ai_edited`, 제안이 없으면 `human`.
- 실패한 기록(초안 없음)도 `followup_checks`를 직접 넣을 수 있다.

### GET /records/{id} 확장
- `items[]`에 `check: {result, origin, record_id, visited_on} | null` (followup 항목만)
- `followup_checks[]`: 이 기록에서 확인한 결과 `{followup_item_id, followup_content, followup_visited_on, followup_record_id, result, evidence, origin}`

## 6. 화면

### 수급자 화면 `/recipients/[id]` → "방문 전 확인"
1. 이름, 마지막 방문일, `오늘 방문 기록하기`
2. 기간 선택(7·14·30일)
3. **남은 확인 사항**: 항목, 원래 방문일, 근거. 누르면 원래 기록으로
4. **AI 인계 요약**: 문장마다 근거 날짜 칩(누르면 해당 기록). 없으면 `요약 만들기`, 오래됐으면 "새로 확정된 기록이 있습니다 · 다시 만들기". 실패 시 사유 + 규칙 묶음은 그대로
5. **주의 항목**(위험 태그), **최근 확인 결과**, **후속 확인 완료율** (예: 4건 중 3건)
6. **기록 검색**: 입력창 + 분류 필터, 결과는 날짜·종류·일치 부분 강조, 누르면 기록으로
7. 지난 기록 목록 (1단계)

### 검토 화면 확장
- 카드 위에 **이전 확인 사항** 섹션. 각 항목:
  - 이전 내용과 날짜
  - AI 제안이 있으면: 결과 + 근거(누르면 구간 재생) + 확인/수정/삭제 → 남은 개수에 포함
  - 제안이 없으면: "이번 녹음에서 답을 찾지 못했습니다" + 직접 입력(선택)
- 확정 요청에 `followup_checks`, `dismissed_followup_items` 포함

### 확정 화면·이전 기록
- 확정 기록에 "확인한 이전 사항" 섹션 (결과, 원래 항목 날짜 링크)
- 이전 기록의 '다음 확인' 항목에 "확인 완료 · 날짜 · 결과" 표시, 아직이면 "확인 전"

## 7. 테스트

백엔드
- 단위: 분류 결과 후처리(ref → item_id, 없는 ref·중복 버림, 근거 검증), 요약 후처리(ref 검증·빈 문장 버림), 확정 검증(제안 전부 처리, origin 계산), 검색 이스케이프·스니펫
- API: handover 묶음(기간·남은 확인 사항·완료율), 요약 생성(저장·stale·429·503·422), 검색(범위·필터·확정 전 기록 제외·다른 수급자 제외), 확정 확장(409 중복 확인, 422 누락), 레코드 응답의 check 필드
- 워커: 분류 시 열린 확인 사항 스냅샷이 draft에 들어감
- 실제 어댑터(live): 두 번째 녹음에서 이전 확인 사항 결과가 근거와 함께 나오는지

프론트
- 단위: 검토 상태에 후속 확인 카드 추가 (남은 개수, 확정 본문)
- E2E: 첫 방문 확정 → 두 번째 방문 업로드 → 이전 확인 사항 AI 제안 확인 → 확정 → 방문 전 확인 화면에 완료율·확인 결과, AI 요약 만들기(근거 칩), 검색 '무릎'

## 8. 진행

PR 하나(백엔드 + 화면).
