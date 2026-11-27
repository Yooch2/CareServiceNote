# 3단계 설계: 센터 · 역할 · 담당 배정 · 동의 · 보호자 열람

작성일 2026-11-27

## 1. 목표와 범위

1·2단계에서는 로그인한 사용자라면 누구나 모든 수급자와 확정 기록을 볼 수 있었다. 실제 방문요양에서는 기록을 보는 사람이 정해져 있다. 같은 센터의 담당 요양보호사와 기관 담당자가 보고, 보호자는 수급자가 동의한 범위만 본다. 기획안의 "동의와 권한" 항목(건강정보 처리 별도 동의, 동의 철회·담당자 변경 시 접근 권한 갱신)과 "권한별 요약"을 동작하게 만든다.

포함
- **센터와 역할**: 사용자는 한 센터에 속하고 역할이 하나다. 역할은 기관 담당자(`manager`), 요양보호사(`caregiver`), 보호자(`guardian`)다.
- **가입**: 센터를 새로 만들면 기관 담당자가 된다. 요양보호사와 보호자는 기관 담당자가 만든 **초대 코드**로 가입한다.
- **담당 배정**: 기관 담당자가 수급자에게 요양보호사를 배정하고 해제한다. 요양보호사는 지금 배정된 수급자만 본다. 해제하면 바로 볼 수 없다.
- **동의 기록**: 기관 담당자가 서면으로 받은 동의(건강정보 처리, 보호자 공유)를 날짜와 함께 기록하고 철회를 기록한다. 건강정보 처리 동의가 없으면 새 녹음과 AI 요약을 막는다. 보호자 공유 동의가 없으면 보호자는 아무것도 볼 수 없다.
- **보호자 여러 명 · 열람 범위**: 수급자 한 명에 보호자를 여러 명 연결하고, 보호자마다 볼 수 있는 분류(말씀/관찰/다음 확인)를 정한다. 보호자는 확정된 항목만 보고 전사문·음성·근거 구절은 보지 않는다.
- **비활성화**: 기관 담당자가 보호자 연결이나 구성원 계정을 비활성화하면 다음 요청부터 바로 막힌다.
- **센터 확인 서명**: 기관 담당자가 확정 기록을 읽고 확인 서명을 남긴다. 서명하지 않은 기록은 "확인 대기"로 모아 본다.

제외
- 열람·정정·내보내기 이력(감사 로그) → 6단계
- 보호자 하루 요약과 담당자 승인 후 공유 → 5단계 (3단계 보호자 화면은 확정 항목을 그대로 보여 준다)
- 보호자 한 계정이 여러 수급자에 연결되는 기능 (초대 코드 하나 = 수급자 하나. 필요해지면 로그인한 상태에서 코드를 추가로 받는 기능을 만든다)
- 서명 취소, 확정 기록 수정 (확정 기록은 1단계부터 수정할 수 없다. 정정은 6단계 수정 이력과 함께)
- 여러 센터에 동시에 속하는 사용자

## 2. 결정과 이유

| 결정 | 이유 |
|---|---|
| 역할은 **사용자당 하나**, `users.role` 컬럼 | 기획안의 사용자 구분(요양보호사, 기관 담당자, 보호자)이 겹치지 않는다. 역할 테이블과 권한 테이블을 따로 두면 3개 역할에 비해 구조가 크다. |
| 권한 확인은 **`app/access.py` 한 곳** | 수급자 접근 여부를 엔드포인트마다 따로 쓰면 하나만 빠뜨려도 새는 곳이 생긴다. 모든 수급자·기록 엔드포인트가 같은 함수를 거치게 하고, 역할 × 엔드포인트 표 테스트로 빠짐을 잡는다. |
| 볼 수 없는 수급자·기록은 **404** | 403을 주면 다른 센터의 수급자 ID가 존재한다는 사실이 드러난다. 1단계의 "남의 확정 전 기록은 404"와 같은 규칙이다. 역할 자체가 맞지 않는 요청(보호자가 녹음 업로드)은 403. |
| 가입은 **센터 만들기 또는 초대 코드** | 아무나 가입해서 아무 센터에 들어가면 권한 구분이 의미가 없다. 기관 담당자가 비밀번호를 대신 정해 주는 방식은 비밀번호를 남이 알게 된다. 초대 코드는 일회용, 7일 만료, DB에는 해시만 저장한다. |
| 보호자 화면은 **별도 API와 별도 응답 스키마** | 직원용 `RecordOut`에서 필드를 지워서 주면 나중에 필드를 추가할 때 보호자에게 새기 쉽다. 보호자용 스키마에는 보여 줄 필드만 적는다(허용 목록). |
| 동의는 **기관이 받은 사실을 기록** | 실제 동의서는 센터가 서면으로 받는다. 앱이 전자 동의를 받는 척하지 않고, 누가 언제 기록했는지와 철회를 남긴다. 기록은 지우지 않고 철회 시각을 적는다. |
| 동의 철회 시 **기존 확정 기록 열람은 유지, 새 처리만 중단** | 장기요양기관은 급여 제공 기록을 일정 기간 보관해야 한다. 철회 뒤에는 새 녹음, AI 처리(요약), 보호자 공유처럼 새로 처리하는 것을 막는다. 보관 기간과 삭제는 6단계에서 다룬다. |
| 배정 해제 시 **확정 전 기록도 볼 수 없음** | 해제된 요양보호사가 확정 전 초안으로 수급자 정보를 계속 보는 것을 막는다. 접근 철회가 우선이다. 해제 화면에서 확정 전 기록이 남아 있으면 개수를 보여 줘서 먼저 정리하게 한다. |
| 비활성화는 **요청마다 DB 확인** | 세션은 JWT 쿠키라 발급 뒤에는 서버가 회수할 수 없다. 이미 요청마다 사용자를 DB에서 읽고 있으므로 `active`와 연결 상태를 같이 확인하면 바로 막힌다. |
| 센터 확인 서명은 **기록 컬럼 두 개** | 서명은 기록당 한 번이고 취소가 없다. 별도 테이블보다 `reviewed_by`, `reviewed_at`이 단순하다. |

## 3. 데이터 모델

### organizations (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| name | text | 센터 이름 (가상) |
| created_at | timestamptz | |

### users (컬럼 추가)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| org_id | uuid FK organizations, not null | 소속 센터 |
| role | text, CHECK manager/caregiver/guardian | |
| active | bool, 기본 true | false면 로그인과 모든 요청을 막는다 |

### recipients (컬럼 추가)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| org_id | uuid FK organizations, not null, index | |

### assignments (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| recipient_id | uuid FK recipients | |
| caregiver_id | uuid FK users | |
| started_at | timestamptz | |
| ended_at | timestamptz null | 해제 시각. null이면 지금 담당 |
| created_by | uuid FK users | 배정한 기관 담당자 |

- 부분 unique 인덱스 `(recipient_id, caregiver_id) WHERE ended_at IS NULL`: 같은 사람을 두 번 배정하지 않는다.
- 한 수급자에 요양보호사 여러 명을 배정할 수 있다(대체 근무).
- 해제는 행을 지우지 않고 `ended_at`을 채운다. 다시 배정하면 새 행.

### consents (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| recipient_id | uuid FK recipients | |
| kind | text, CHECK health_record/guardian_share | 건강정보 처리 / 보호자 공유 |
| granted_on | date | 서면 동의를 받은 날 |
| recorded_by | uuid FK users | 기록한 기관 담당자 |
| created_at | timestamptz | |
| withdrawn_at | timestamptz null | 철회 기록 시각 |
| withdrawn_by | uuid FK users null | |

- 부분 unique 인덱스 `(recipient_id, kind) WHERE withdrawn_at IS NULL`: 종류마다 유효한 동의는 하나.
- 유효한 동의 = `withdrawn_at IS NULL`인 행이 있음.

### guardian_links (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| recipient_id | uuid FK recipients | |
| guardian_id | uuid FK users, unique | 보호자 계정 하나 = 수급자 하나 |
| categories | text[], CHECK 부분집합 | 열람 범위. 예 `{remark,followup}` |
| active | bool | |
| created_at, updated_at | timestamptz | |

### invites (새 테이블)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | uuid PK | |
| org_id | uuid FK organizations | |
| role | text, CHECK caregiver/guardian | |
| recipient_id | uuid FK recipients null | 보호자 초대일 때 필수 |
| categories | text[] null | 보호자 초대일 때 열람 범위 |
| code_hash | text unique | SHA-256(코드). 원문은 만들 때 한 번만 보여 준다 |
| expires_at | timestamptz | 만든 시각 + 7일 |
| used_at | timestamptz null | |
| used_by | uuid FK users null | |
| created_by | uuid FK users | |

- CHECK: `role = 'guardian'`이면 `recipient_id`, `categories` 둘 다 있어야 한다.
- 코드는 헷갈리는 글자(0/O, 1/I/L)를 뺀 대문자·숫자 10자, `secrets.choice`로 만든다(약 50비트). 해시는 솔트 없는 SHA-256로 충분하다. 코드 자체가 무작위이고 7일 뒤 만료된다.
- 가입 시 `SELECT ... FOR UPDATE`로 잡고 `used_at`을 채워 같은 코드로 두 명이 가입하지 못하게 한다.

### visit_records (컬럼 추가)
| 컬럼 | 타입 | 설명 |
|---|---|---|
| reviewed_by | uuid FK users null | 센터 확인 서명한 기관 담당자 |
| reviewed_at | timestamptz null | |

### 기존 데이터 마이그레이션
개발 DB에 1·2단계 데이터가 있다. 마이그레이션은 "기존 데이터 센터"를 하나 만들고 모든 사용자를 그 센터의 요양보호사로, 모든 수급자를 그 센터로 옮긴 뒤 모든 사용자 × 수급자에 배정을 만든다. 1·2단계에서 보이던 것이 그대로 보인다. 건강정보 처리 동의도 기존 수급자마다 하나 만든다(`granted_on` = 마이그레이션 날짜). 그렇지 않으면 기존 사용자가 녹음을 못 한다. 모두 가상 데이터라 가능한 처리이고, 운영 데이터라면 동의를 자동으로 만들면 안 된다는 점을 마이그레이션 주석에 적는다.

## 4. 접근 규칙

`app/access.py`에 둔다.

| | 기관 담당자 | 요양보호사 | 보호자 |
|---|---|---|---|
| 수급자 목록 | 같은 센터 전부 | 지금 배정된 수급자 | 보호자 API로 연결된 수급자 하나 |
| 확정 기록·방문 전 확인·검색 | 같은 센터 전부 | 배정된 수급자 | 없음 (보호자 API만) |
| 확정 전 기록 | 볼 수 없음 | 내가 쓴 것 + 지금 배정 중 | 없음 |
| 음성 | 볼 수 없음 | 내가 쓴 것 + 지금 배정 중 | 없음 |
| 녹음 업로드 | 403 | 배정 + 건강정보 동의 | 403 |
| AI 요약 만들기 | 건강정보 동의 | 배정 + 건강정보 동의 | 403 |
| 수급자 추가·배정·동의·초대·보호자 관리·서명 | 가능 | 403 | 403 |
| 보호자 API | 403 | 403 | 활성 연결 + 공유 동의 + 열람 범위 |

- `active = false`인 사용자는 로그인 401, 기존 쿠키 요청도 401.
- 함수: `recipient_for_staff(db, user, recipient_id) -> Recipient` (없거나 범위 밖이면 404), `staff_recipients(db, user) -> Select`, `require_role(*roles)` 의존성, `guardian_link_for(db, user) -> GuardianLink` (비활성·동의 없음이면 403과 이유).
- 보호자 403 이유는 화면에 그대로 보여 준다: "보호자 연결이 해제되었습니다", "수급자의 공유 동의가 없어 볼 수 없습니다". 보호자는 자기 수급자가 있다는 것을 이미 알기 때문에 404로 숨길 필요가 없다.

## 5. API

### 인증
- `POST /auth/signup`: `center_name` 또는 `invite_code` 중 하나 필수(둘 다·둘 다 없음은 422).
  - `center_name`: 센터를 만들고 `manager`로 가입.
  - `invite_code`: 코드 확인(없음·만료·사용됨은 모두 같은 메시지 "초대 코드가 올바르지 않습니다", 400) → 초대의 센터·역할로 가입. 보호자면 `guardian_links` 생성.
- `POST /auth/login`: 비활성 사용자는 같은 401 메시지.
- `GET /auth/me`: `role`, `org_name` 추가.

### 센터 관리 (manager)
- `GET /org/members`: 구성원 목록(역할, 활성, 보호자면 연결된 수급자·열람 범위).
- `PATCH /org/members/{user_id}`: `{active}`. 자기 자신은 비활성화할 수 없다(409).
- `POST /org/invites`: `{role, recipient_id?, categories?}` → `{code, expires_at}`. 코드 원문은 이 응답에만 있다.
- `GET /org/invites`: 아직 쓰지 않은 유효한 초대 목록(코드 없이 역할·대상·만료).
- `DELETE /org/invites/{id}`: 초대 취소.
- `GET /org/reviews`: 서명 안 된 확정 기록(수급자 이름, 방문일, 작성자, 확정 시각).

### 수급자 관리 (manager)
- `POST /recipients`: manager만, 같은 센터로 생성.
- `GET /recipients/{id}/admin`: 배정(현재·지난), 동의(현재·철회 이력), 보호자 연결, 배정 해제 시 남는 확정 전 기록 수.
- `POST /recipients/{id}/assignments` `{caregiver_id}`: 같은 센터의 활성 요양보호사만(아니면 422). 이미 배정 중이면 409.
- `DELETE /recipients/{id}/assignments/{assignment_id}`: `ended_at` 채움.
- `POST /recipients/{id}/consents` `{kind, granted_on}`: 이미 유효하면 409. `granted_on`은 미래 날짜 불가.
- `POST /recipients/{id}/consents/{consent_id}/withdraw`.
- `PATCH /org/guardian-links/{id}` `{categories?, active?}`: 같은 센터만. categories는 1개 이상.

### 기존 API 변경
- `GET /recipients`, `GET /recipients/{id}`, `/records`, `/handover`, `/handover/summary`, `/search`: 모두 `recipient_for_staff`를 거친다. 보호자는 403.
- `GET /recipients` 응답에 `consents: {health_record: bool, guardian_share: bool}` 추가(녹음 버튼 상태용).
- `PUT /records/{id}`: caregiver + 배정 + 건강정보 동의(없으면 409 "건강정보 처리 동의가 없어 기록할 수 없습니다"). 같은 id 재전송(1단계 중복 방지)은 그대로 기존 기록을 돌려준다.
- `GET /records/{id}`: 수급자 접근 확인 후, 확정 전이면 작성자만. 응답에 `review: {reviewer_name, reviewed_at} | null` 추가.
- `GET /records/{id}/audio`: 작성자 + 지금 배정 중.
- `POST /records/{id}/confirm`: 작성자 + 지금 배정 중 + 건강정보 동의(없으면 409).
- 워커: 기록을 가져갈 때 건강정보 동의를 확인하고, 업로드 뒤 철회됐으면 AI로 보내지 않고 `failed`(`consent_withdrawn`)로 둔다.
- `POST /records/{id}/review` (manager): 확정 기록만(기관 담당자는 확정 전 기록을 볼 수 없으므로 404), 이미 서명했으면 409.

### 보호자 (guardian)
- `GET /guardian/home`: `{recipient_name, categories, records: [{visited_on, items: [{category, content}], checks: [{followup_content, result}]}]}`.
  - 확정 기록만, 최근 30일, 방문일 내림차순.
  - `items`는 열람 범위 분류만. `checks`는 `followup`이 범위에 있을 때만.
  - 근거 구절, 전사문, 음성, 위험 표시, 요양보호사 이름, 기록 id는 넣지 않는다.
  - 열람 범위 항목이 하나도 없는 방문은 뺀다.

## 6. 화면

### 가입 `/signup`
- "센터 만들기"와 "초대 코드로 가입" 두 탭. 초대 코드 탭은 코드 입력 칸이 추가된다.
- 로그인 화면 데모 안내에 역할별 데모 계정을 적는다.

### 홈 `/`
- 기관 담당자: 상단에 "센터 관리" 링크와 "확인 대기 n건". 수급자 목록 각 줄에 담당자 수, 동의 상태 배지.
- 요양보호사: 배정된 수급자 목록(지금과 같음). 배정이 없으면 "기관 담당자에게 배정을 요청하세요".
- 보호자: `/family`로 보낸다.

### 센터 관리 `/center` (manager)
- 확인 대기 기록 목록 → 기록 화면으로.
- 구성원: 요양보호사·보호자 목록, 비활성화/다시 활성화.
- 초대: 요양보호사 초대 만들기, 유효한 초대 목록과 취소. 만든 코드는 한 번만 크게 보여 준다.

### 수급자 관리 `/recipients/[id]/manage` (manager)
- 담당 요양보호사: 지금 담당, 배정 추가(같은 센터 요양보호사 선택), 해제(확정 전 기록이 있으면 경고 문구).
- 동의: 종류별 상태, 받은 날 입력 후 기록, 철회.
- 보호자: 연결 목록, 열람 범위 체크박스, 연결 해제/다시 연결, 보호자 초대 만들기(열람 범위 선택).

### 수급자 화면·기록 화면
- 건강정보 동의가 없으면 "오늘 방문 기록하기"와 "요약 만들기" 대신 안내 문구.
- 기록 화면: 센터 확인 서명 표시. 기관 담당자에게는 "확인 서명" 버튼.

### 보호자 `/family`
- 수급자 이름, 열람 범위 안내("말씀, 다음 확인 사항을 볼 수 있습니다"), 방문일별 항목 카드.
- 403이면 이유 문구와 로그아웃 버튼.

## 7. 테스트

- **접근 표 테스트**: 역할 4종(같은 센터 manager, 배정된 caregiver, 배정 안 된 caregiver, 다른 센터 manager) + guardian × 엔드포인트 전부 → 기대 상태 코드. 새 엔드포인트를 추가하면 표에 줄을 추가해야 하도록 라우터의 경로 목록과 표의 경로 목록을 비교하는 테스트를 둔다.
- 초대: 만료·사용됨·없는 코드 같은 메시지, 동시 사용 시 한 명만 성공, DB에 원문 없음.
- 배정 해제 직후 확정 전 기록·음성·확정 404.
- 동의: 철회 후 업로드 409·요약 409, 열람은 유지, 보호자 403.
- 보호자: 열람 범위 밖 분류·근거·전사문이 응답에 없음(응답 JSON 문자열 검사), 연결 비활성화·계정 비활성화 즉시 차단.
- 서명: 두 번 409, 요양보호사 403, 확정 전 기록 404(접근 표).
- 마이그레이션: 개발 DB(기존 사용자 16명)에서 upgrade → 기존 데이터 센터·배정·동의 생성 확인, downgrade·upgrade 왕복, `alembic check`. (자동 테스트는 세션 단위로 최신 스키마를 쓰므로 수동 확인)
- E2E: (1) 센터 만들기 → 수급자 추가·동의 기록 → 요양보호사 초대 → 요양보호사 가입·배정 → 녹음·확정 → 기관 담당자 확인 서명. (2) 보호자 초대 → 보호자 가입 → 열람 범위만 보임 → 연결 해제 → 차단. 기존 E2E는 시드 계정이나 헬퍼로 센터·배정을 만든 뒤 시작하게 바꾼다.

## 8. 시드

가상 센터 "햇살방문요양센터(가상)".
- `manager` / `demo1234`: 기관 담당자
- `demo` / `demo1234`: 요양보호사 (가상 수급자 3명 배정)
- `demo2` / `demo1234`: 요양보호사 (배정 없음, 담당 교체 시연용)
- `family` / `demo1234`: 김순자(가상)의 보호자, 열람 범위 말씀·다음 확인
- 동의: 세 수급자 모두 건강정보 처리, 김순자(가상)만 보호자 공유
