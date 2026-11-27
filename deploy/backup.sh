#!/bin/sh
# DB와 암호화된 음성·사진을 백업한다. 매일 cron으로 돌리고 결과를 서버 밖에 보관한다.
#   0 4 * * * cd /srv/careservicenote/deploy && ./backup.sh >> backup.log 2>&1
# STORAGE_KEY는 이 백업에 들어가지 않는다(파일과 키를 같은 곳에 두지 않으려고). 따로 보관할 것.
# 음성·사진은 이미 암호화돼 있지만 db.dump는 평문이다. 서버 밖으로 옮길 때는 암호화한다
#   (예: age -r <공개키> db.dump > db.dump.age, DEPLOY.md 참고)
set -eu
umask 077  # 백업 파일은 소유자만 읽고 쓴다
cd "$(dirname "$0")"
out="backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$out"
chmod 700 backups "$out"
docker compose exec -T db pg_dump -U csn -d csn --format=custom > "$out/db.dump"
docker compose exec -T api tar -C /data -czf - media > "$out/media.tar.gz"
# 14일보다 오래된 백업은 지운다
find backups -mindepth 1 -maxdepth 1 -type d -mtime +14 -exec rm -rf {} +
echo "backup ok: $out"
