#!/usr/bin/env bash
# Nightly Postgres backup. Invoked by cron on the VPS:
#   0 3 * * * /opt/makerbooking/scripts/backup.sh >> /opt/makerbooking/data/backups/backup.log 2>&1
# Keeps the last 7 days of dumps in /opt/makerbooking/data/backups/.

set -euo pipefail

APP_DIR="/opt/makerbooking"
BACKUP_DIR="${APP_DIR}/data/backups"
RETENTION_DAYS=7

mkdir -p "${BACKUP_DIR}"

# Load DB creds from .env (POSTGRES_* vars).
set -a
# shellcheck source=/dev/null
. "${APP_DIR}/.env"
set +a

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
outfile="${BACKUP_DIR}/makerbooking-${timestamp}.sql.gz"

echo "[$(date -u +%FT%TZ)] backup start -> ${outfile}"

cd "${APP_DIR}"
docker compose exec -T db \
  pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
  | gzip -9 > "${outfile}"

# Prune older than RETENTION_DAYS.
find "${BACKUP_DIR}" -maxdepth 1 -name 'makerbooking-*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

size="$(du -h "${outfile}" | cut -f1)"
echo "[$(date -u +%FT%TZ)] backup ok  size=${size}"
