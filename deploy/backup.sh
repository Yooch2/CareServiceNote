#!/bin/sh
# DB와 암호화된 음성·사진을 백업한다. 매일 cron으로 돌리고 결과를 서버 밖에 보관한다.
#   0 4 * * * cd /srv/careservicenote/deploy && ./backup.sh >> backup.log 2>&1
# STORAGE_KEY는 이 백업에 들어가지 않는다(파일과 키를 같은 곳에 두지 않으려고). 따로 보관할 것.
set -eu
cd "$(dirname "$0")"
out="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
docker compose exec -T db pg_dump -U csn -d csn --format=custom > "$out/db.dump"
docker compose exec -T api tar -C /data -czf - media > "$out/media.tar.gz"
# 14일보다 오래된 백업은 지운다
find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
echo "backup ok: $out"
