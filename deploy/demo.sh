#!/bin/sh
# 비용 없이 공개 데모 열기·닫기: 이 컴퓨터에서 운영 구성을 띄우고 Cloudflare 무료 임시 터널로 연다.
#   ./demo.sh up     띄우고 https://….trycloudflare.com 주소를 출력 (처음엔 1~2분 뒤부터 열림)
#   ./demo.sh url    지금 주소 다시 보기
#   ./demo.sh down   닫기 (데이터 볼륨은 남는다. 완전히 지우려면 down -v)
# 시연할 때만 켜고 끝나면 닫는다. 이 컴퓨터가 켜져 있을 때만 열리고, 띄울 때마다 주소가 바뀐다.
set -eu
cd "$(dirname "$0")"
[ -f .env ] || { echo ".env가 없습니다. DEPLOY.md의 '비용 없이 공개' 순서대로 만들어 주세요"; exit 1; }
dc() { docker compose -f compose.yml -f compose.tunnel.yml "$@"; }
url() { dc logs cloudflared 2>&1 | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1; }

case "${1:-}" in
  up)
    dc up -d --build
    for _ in $(seq 1 30); do u=$(url); [ -n "$u" ] && break; sleep 2; done
    echo "공개 주소: ${u:-아직 없음 (./demo.sh url 로 다시 확인)}"
    echo "주소가 열리기까지 1~2분 걸릴 수 있습니다. 데모 계정: demo / manager / family (비밀번호 demo1234)"
    ;;
  url) url ;;
  down) dc down ;;
  *) echo "사용법: $0 up | url | down"; exit 1 ;;
esac
