#!/usr/bin/env bash
# Épreuve isolée : dump → verify → restore drill, sans toucher une instance FinFlow.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
export MSYS_NO_PATHCONV=1

command -v docker >/dev/null || die "docker est requis"

if [[ -n "${LOCALAPPDATA:-}" ]]; then
  _tmp="$(cygpath -u "$LOCALAPPDATA" 2>/dev/null || echo "$LOCALAPPDATA")/Temp"
elif [[ -d /c/Windows/Temp ]]; then
  _tmp="/c/Windows/Temp"
else
  _tmp="${TMPDIR:-/tmp}"
fi
mkdir -p "$_tmp"
WORKDIR="$(mktemp -d "${_tmp}/finflow-backup-selftest.XXXXXX")"
cleanup() {
  if [[ -n "${WORKDIR:-}" ]]; then
    local host
    host="$(host_path "$WORKDIR" 2>/dev/null || echo "$WORKDIR")"
    docker compose --project-directory "$host" down -v >/dev/null 2>&1 || true
    rm -rf "$WORKDIR"
  fi
}
trap cleanup EXIT

log "Atelier selftest : ${WORKDIR}"

cat > "${WORKDIR}/docker-compose.yml" <<'YAML'
name: ffbackupselftest
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: finflow
      POSTGRES_PASSWORD: selftest
      POSTGRES_DB: finflow
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U finflow"]
      interval: 2s
      timeout: 3s
      retries: 30
  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
YAML

cat > "${WORKDIR}/.env" <<'ENV'
POSTGRES_USER=finflow
POSTGRES_DB=finflow
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
AWS_STORAGE_BUCKET_NAME=finflow-documents
FIELD_ENCRYPTION_KEY=selftest-fernet-key-not-for-prod
DJANGO_SECRET_KEY=selftest-django-secret
ENV

WORKDIR_HOST="$(host_path "$WORKDIR")"
docker compose --project-directory "$WORKDIR_HOST" -f "$WORKDIR_HOST/docker-compose.yml" up -d
for _ in $(seq 1 40); do
  if docker compose --project-directory "$WORKDIR_HOST" exec -T db pg_isready -U finflow >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker compose --project-directory "$WORKDIR_HOST" exec -T db \
  psql -U finflow -d finflow -v ON_ERROR_STOP=1 \
  -c "CREATE TABLE restore_marker (id int PRIMARY KEY, label text);" \
  -c "INSERT INTO restore_marker VALUES (7, 'finflow-backup-selftest');"

NETWORK="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' \
  "$(docker compose --project-directory "$WORKDIR_HOST" ps -q minio)")"
docker run --rm --network "$NETWORK" \
  -e MC_HOST_src="http://minioadmin:minioadmin@minio:9000" \
  minio/mc:latest mb -p src/finflow-documents
printf 'ged-selftest' > "${WORKDIR}/selftest.txt"
docker run --rm --network "$NETWORK" \
  -e MC_HOST_src="http://minioadmin:minioadmin@minio:9000" \
  -v "$(host_path "${WORKDIR}/selftest.txt"):/data/selftest.txt:ro" \
  minio/mc:latest cp /data/selftest.txt src/finflow-documents/selftest.txt

export FINFLOW_DIR="$WORKDIR"
export COMPOSE_FILES="-f docker-compose.yml"
export BACKUP_ROOT="${WORKDIR}/backups"
export BACKUP_PASSPHRASE="selftest-passphrase"
export SKIP_APP_PAUSE=1
export FINFLOW_DRILL_MIN_TABLES=1

SNAP="$(bash "${SCRIPT_DIR}/backup.sh" | tail -n 1)"
[[ -d "$SNAP" ]] || die "backup.sh n'a pas renvoyé un dossier snapshot"
bash "${SCRIPT_DIR}/verify.sh" "$SNAP"

bash "${SCRIPT_DIR}/restore.sh" --target drill --snapshot "$SNAP" --keep
# restore.sh --keep laisse finflow-drill-db : on y lit le marqueur
MARKER="$(docker exec -e PGPASSWORD=drill finflow-drill-db \
  psql -U finflow -d finflow -tAc "SELECT label FROM restore_marker WHERE id=7")"
docker rm -f finflow-drill-db finflow-drill-minio >/dev/null 2>&1 || true
docker network rm finflow-backup-drill >/dev/null 2>&1 || true

[[ "${MARKER// /}" == "finflow-backup-selftest" ]] || die "Marqueur restauré incorrect : [${MARKER}]"
ok "Selftest : dump → verify → restore drill, marqueur et GED OK"
