#!/usr/bin/env bash
# Runs on the VPS. Invoked over SSH by .github/workflows/deploy.yml and rollback.yml.
#
# Usage:
#   ./deploy.sh <image_tag>
#
# Steps:
#   1. docker pull the requested tag
#   2. record currently-running tag for auto-rollback
#   3. one-shot `flask db upgrade` (abort if it fails — old containers keep serving)
#   4. docker compose up -d app scheduler (recreates with new image)
#   5. poll /healthz for up to 30s — on failure, re-deploy previous tag
#   6. prune old images, keeping last 10

set -euo pipefail

APP_DIR="/opt/makerbooking"
COMPOSE="docker compose"
HEALTH_URL="http://127.0.0.1:8000/healthz"
KEEP_IMAGES=10

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <image_tag>" >&2
  exit 2
fi

NEW_TAG="$1"

cd "${APP_DIR}"

# .env supplies GHCR_OWNER, DB creds, app secrets.
set -a
# shellcheck source=/dev/null
. "${APP_DIR}/.env"
set +a

if [[ -z "${GHCR_OWNER:-}" ]]; then
  echo "GHCR_OWNER must be set in /opt/makerbooking/.env" >&2
  exit 2
fi

IMAGE="ghcr.io/${GHCR_OWNER}/makerbooking:${NEW_TAG}"

log() { echo "[$(date -u +%FT%TZ)] $*"; }

# Track the running tag in a state file so rollback always knows the previous good one.
STATE_FILE="${APP_DIR}/.current_tag"
PREVIOUS_TAG=""
if [[ -f "${STATE_FILE}" ]]; then
  PREVIOUS_TAG="$(cat "${STATE_FILE}")"
fi

log "deploy start  new=${NEW_TAG}  previous=${PREVIOUS_TAG:-<none>}"

export IMAGE_TAG="${NEW_TAG}"

log "pulling ${IMAGE}"
docker pull "${IMAGE}"

log "running migrations"
if ! ${COMPOSE} run --rm app flask db upgrade; then
  log "MIGRATION FAILED — aborting; old containers still running"
  exit 1
fi

log "starting app + scheduler + caddy at ${NEW_TAG}"
${COMPOSE} up -d app scheduler caddy

log "waiting for /healthz (up to 30s)"
ok=0
for i in $(seq 1 30); do
  if curl -fsS --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    ok=1
    log "healthz ok after ${i}s"
    break
  fi
  sleep 1
done

if [[ "${ok}" -ne 1 ]]; then
  log "HEALTH CHECK FAILED — rolling back"
  if [[ -n "${PREVIOUS_TAG}" && "${PREVIOUS_TAG}" != "${NEW_TAG}" ]]; then
    export IMAGE_TAG="${PREVIOUS_TAG}"
    ${COMPOSE} up -d app scheduler caddy
    log "rolled back to ${PREVIOUS_TAG}"
  else
    log "no previous tag recorded — manual intervention required"
  fi
  exit 1
fi

# Record the new tag only after a successful deploy.
echo "${NEW_TAG}" > "${STATE_FILE}"

log "pruning old images (keeping last ${KEEP_IMAGES})"
docker images "ghcr.io/${GHCR_OWNER}/makerbooking" \
  --format '{{.ID}} {{.CreatedAt}} {{.Tag}}' \
  | sort -k2 -r \
  | awk -v keep="${KEEP_IMAGES}" 'NR>keep { print $1 }' \
  | xargs -r docker rmi -f 2>/dev/null || true

log "deploy ok    running=${NEW_TAG}"
