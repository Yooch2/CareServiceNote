# 배포 안내

서버 한 대(리눅스, 메모리 2GB 이상, Docker와 Docker Compose)에 DB·API·워커·화면·Caddy를 함께 띄웁니다.
클라우드 회사나 요금제에 묶이지 않도록 일반 VM이면 어디서든 같은 방법으로 올라갑니다.

```
인터넷 ─ 443 ─ Caddy (자동 HTTPS)
                ├─ /api/* ─→ api (FastAPI)  ─┐
                └─ 그 외   ─→ web (Next.js)   │
                                worker ───────┼─→ db (Postgres, 밖으로 안 열림)
                                              └─→ media 볼륨 (암호화된 음성·사진)
```

## 처음 올리기

1. 도메인의 A 레코드(IPv6면 AAAA)가 서버 IP를 가리키게 한다. 방화벽은 80·443만 연다.
2. 코드를 받고 설정 파일을 만든다.
   ```bash
   git clone https://github.com/Yooch2/CareServiceNote.git /srv/careservicenote
   cd /srv/careservicenote/deploy
   cp .env.example .env && chmod 600 .env
   ```
3. `.env`를 채운다.
   - `DOMAIN`, `POSTGRES_PASSWORD`(`openssl rand -base64 24`), `JWT_SECRET`(`openssl rand -base64 48`)
   - `STORAGE_KEY`: `openssl rand -base64 32 | tr '+/' '-_'` 로 만든다(32바이트 URL-safe base64 = Fernet 키). **서버 밖(비밀번호 관리자 등)에도 따로 보관한다.** 잃으면 저장된 음성·사진을 읽을 수 없다.
   - `GEMINI_API_KEY`: Google AI Studio 무료 등급 키. 무료 등급은 입력이 서비스 개선에 쓰일 수 있으므로 **가상 데이터만** 넣는다.
4. 띄운다.
   ```bash
   docker compose up -d --build
   docker compose ps          # migrate는 Exited (0), 나머지는 running/healthy
   ```
   `SEED_DEMO=true`면 데모 센터와 계정(`manager`, `demo`, `demo2`, `family` / `demo1234`)이 만들어진다.

`ENV=production`에서는 API가 시작할 때 설정을 확인한다. `COOKIE_SECURE`가 꺼져 있거나, `JWT_SECRET`이 짧거나 예시값이거나, `STORAGE_KEY`가 없거나, AI 설정이 비어 있으면 **시작하지 않고** 무엇이 틀렸는지 로그에 남긴다(`docker compose logs api`).

## 업데이트

```bash
cd /srv/careservicenote && git pull
cd deploy && docker compose up -d --build   # migrate가 먼저 마이그레이션을 돌린다
```

## 백업과 복구

```bash
./backup.sh          # backups/<시각>/db.dump, media.tar.gz (14일 보관, 소유자만 읽기)
# cron 예: 0 4 * * * cd /srv/careservicenote/deploy && ./backup.sh >> backup.log 2>&1
```

- 음성·사진(`media.tar.gz`)은 이미 암호화돼 있지만 `db.dump`는 평문이다. 서버 밖으로 옮길 때는 암호화한다. 예: `age -r <공개키> db.dump > db.dump.age`
- `STORAGE_KEY`는 백업에 넣지 않는다. 파일과 키를 같은 곳에 두지 않기 위해서다.

복구:
```bash
docker compose up -d db
docker compose exec -T db pg_restore -U csn -d csn --clean --if-exists < backups/<시각>/db.dump
docker compose run --rm --no-deps -T api sh -c "tar -C /data -xzf -" < backups/<시각>/media.tar.gz
docker compose up -d
```

## 운영에서 켜지는 것

| 항목 | 내용 |
|---|---|
| HTTPS | Caddy가 인증서를 자동으로 받고 갱신한다. HSTS, `nosniff`, `Referrer-Policy`, 마이크·카메라만 같은 출처에 허용 |
| 쿠키 | `Secure; HttpOnly; SameSite=Lax` |
| 업로드 | Caddy가 12MB를 넘는 요청을 막고, `/api`는 화면 서버를 거치지 않고 API로 바로 간다 |
| 시도 횟수 제한 | 로그인: (아이디+IP)별 15분 5번, IP별 15분 30번, 아이디별 한 시간 30번(넘으면 그 아이디로 로그인에 성공한 적 있는 '아는 IP'만 통과). 초대 코드: IP별 한 시간 10번, 전체 실패가 많으면 경고 로그. API는 Caddy를 거쳐서만 닿으므로 Caddy가 넣는 `X-Forwarded-For`를 클라이언트 IP로 쓴다(`TRUST_PROXY`). IPv6는 /64로 묶는다 |
| AI 사용 한도 | 사용자별·서비스 전체 하루 기록·요약 수 (`DAILY_*`) |
| 보관 기간 | 워커가 한 시간마다 확정되지 않은 기록의 음성·사진(30일), 확정 기록의 전사문(180일), 하루 지난 로그인 실패 기록을 지운다 |
| 포트 | 80·443(Caddy)만 연다. DB와 API는 Docker 네트워크 안에만 있다 |

## 로컬에서 운영 구성 확인하기

```bash
cd deploy
cp .env.example .env   # DOMAIN=localhost, HTTP_PORT=8080, HTTPS_PORT=8443 와 비밀값 채우기
docker compose up -d --build
open https://localhost:8443   # Caddy 자체 인증서라 브라우저 경고가 뜬다
docker compose down -v        # 확인이 끝나면 볼륨까지 지운다
```
