#!/usr/bin/env bash
# Snapshot chiffré d'instance FinFlow : Postgres (custom) + MinIO + secrets.
#
#   sudo FINFLOW_DIR=/opt/finflow ./deploy/backup/backup.sh
#   BACKUP_PASSPHRASE_FILE=/root/.finflow-backup-pass ./deploy/backup/backup.sh
#
# Variables :
#   FINFLOW_DIR            Racine de l'instance (défaut : racine du dépôt)
#   BACKUP_ROOT            /var/backups/finflow
#   BACKUP_PASSPHRASE      Phrase de chiffrement du snapshot complet
#   BACKUP_PASSPHRASE_FILE Fichier contenant la phrase (recommandé)
#   BACKUP_OFFSITE_DIR     Copie rsync du snapshot (optionnel)
#   SKIP_APP_PAUSE=1       Ne pas arrêter worker/beat
#   SKIP_MINIO=1           Dump SQL + secrets seulement
#   SKIP_SECRETS=1         Ne pas empaqueter .env (déconseillé)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

DIR="$(finflow_dir)"
COMPOSE_FILES="$(detect_compose_files "$DIR")"
export COMPOSE_FILES
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/finflow}"
# Jamais écrire les dumps dans le dépôt applicatif.
case "${BACKUP_ROOT}" in
  "${DIR}"|"${DIR}"/*)
    die "BACKUP_ROOT=${BACKUP_ROOT} est dans l'instance ${DIR}. Utilisez /var/backups/finflow."
    ;;
esac
STAMP="$(utc_stamp)"
SNAP="${BACKUP_ROOT}/snapshots/${STAMP}"
ENV_FILE="${DIR}/.env"
PG_USER="${POSTGRES_USER:-}"
PG_DB="${POSTGRES_DB:-}"
BUCKET="${AWS_STORAGE_BUCKET_NAME:-}"

if [[ -z "$PG_USER" ]]; then
  PG_USER="$(load_dotenv_value "$ENV_FILE" POSTGRES_USER)"
  PG_USER="${PG_USER:-finflow}"
fi
if [[ -z "$PG_DB" ]]; then
  PG_DB="$(load_dotenv_value "$ENV_FILE" POSTGRES_DB)"
  PG_DB="${PG_DB:-finflow}"
fi
if [[ -z "$BUCKET" ]]; then
  BUCKET="$(load_dotenv_value "$ENV_FILE" AWS_STORAGE_BUCKET_NAME)"
  BUCKET="${BUCKET:-finflow-documents}"
fi
MINIO_USER="$(load_dotenv_value "$ENV_FILE" MINIO_ROOT_USER)"
MINIO_USER="${MINIO_USER:-minioadmin}"
MINIO_PASS="$(load_dotenv_value "$ENV_FILE" MINIO_ROOT_PASSWORD)"
MINIO_PASS="${MINIO_PASS:-minioadmin}"

STOPPED=()
SNAP_CREATED=0
cleanup_backup() {
  local svc
  # Ne jamais laisser un dump ou miroir en clair après un échec de snapshot.
  if [[ "$SNAP_CREATED" == "1" ]]; then
    case "$SNAP" in
      "${BACKUP_ROOT}/snapshots/"*) rm -rf -- "$SNAP" ;;
    esac
  fi
  for svc in "${STOPPED[@]+"${STOPPED[@]}"}"; do
    compose_in "$DIR" start "$svc" >/dev/null 2>&1 || warn "Impossible de relancer ${svc}"
  done
}
trap cleanup_backup EXIT

mkdir -p "${BACKUP_ROOT}/snapshots"
mkdir "$SNAP" || die "Un snapshot existe déjà pour ${STAMP}; réessayez dans une seconde."
SNAP_CREATED=1
chmod 700 "$SNAP" 2>/dev/null || true
log "Snapshot ${STAMP} → ${SNAP}"
log "Instance  ${DIR}"
log "Compose   docker compose ${COMPOSE_FILES}"

if [[ "${SKIP_APP_PAUSE:-0}" != "1" ]]; then
  for svc in worker beat; do
    if compose_in "$DIR" ps --status running --services 2>/dev/null | grep -qx "$svc"; then
      log "Pause ${svc}"
      compose_in "$DIR" stop "$svc"
      STOPPED+=("$svc")
    fi
  done
fi

log "Dump PostgreSQL (${PG_USER}/${PG_DB}, format custom)"
compose_in "$DIR" exec -T db \
  pg_dump -U "$PG_USER" -d "$PG_DB" -Fc -Z 6 \
  > "${SNAP}/postgres.dump"
[[ -s "${SNAP}/postgres.dump" ]] || die "postgres.dump vide"

if [[ "${SKIP_MINIO:-0}" != "1" ]]; then
  log "Miroir MinIO bucket ${BUCKET}"
  mkdir -p "${SNAP}/minio"
  NETWORK="$(compose_network "$DIR")"
  docker run --rm \
    --network "$NETWORK" \
    -e MC_HOST_src="http://${MINIO_USER}:${MINIO_PASS}@minio:9000" \
    --user 0:0 \
    -v "$(host_path "${SNAP}/minio"):/backup" \
    cgr.dev/chainguard/minio-client:latest \
    mirror --overwrite "src/${BUCKET}" /backup
else
  warn "MinIO ignoré (SKIP_MINIO=1)"
fi

SECRETS_INCLUDED=0
if [[ "${SKIP_SECRETS:-0}" != "1" && -f "$ENV_FILE" ]]; then
  TMP_SECRETS="$(mktemp_host "$SNAP")"
  {
    echo "# FinFlow secrets snapshot ${STAMP}"
    grep -E '^(FIELD_ENCRYPTION_KEY|DJANGO_SECRET_KEY)=' "$ENV_FILE" || true
  } > "$TMP_SECRETS"
  if grep -q '=' "$TMP_SECRETS"; then
    encrypt_secrets_file "$TMP_SECRETS" "${SNAP}/secrets.env.enc"
    SECRETS_INCLUDED=1
  else
    warn "Aucune clé FIELD_ENCRYPTION_KEY / DJANGO_SECRET_KEY dans .env"
  fi
  rm -f "$TMP_SECRETS"
else
  warn "Secrets non empaquetés (SKIP_SECRETS=1 ou .env absent)"
fi

GIT_SHA=""
if [[ -d "${DIR}/.git" ]]; then
  GIT_SHA="$(git -C "$DIR" rev-parse HEAD 2>/dev/null || true)"
fi

MIGRATIONS=""
if compose_in "$DIR" ps --status running --services 2>/dev/null | grep -qx backend; then
  MIGRATIONS="$(
    compose_in "$DIR" exec -T backend \
      python manage.py showmigrations --plan 2>/dev/null \
      | grep -c '\[X\]' || true
  )"
fi

PG_SHA="$(sha256_file "${SNAP}/postgres.dump")"
PG_BYTES="$(wc -c < "${SNAP}/postgres.dump" | tr -d ' ')"
MINIO_BYTES="$(dir_bytes "${SNAP}/minio")"
MINIO_FILES="$(count_files "${SNAP}/minio")"
SEC_SHA=""
SEC_BYTES=0
if [[ -f "${SNAP}/secrets.env.enc" ]]; then
  SEC_SHA="$(sha256_file "${SNAP}/secrets.env.enc")"
  SEC_BYTES="$(wc -c < "${SNAP}/secrets.env.enc" | tr -d ' ')"
fi

run_python - "$(host_path "$SNAP")" "$STAMP" "$GIT_SHA" "$MIGRATIONS" "$PG_SHA" "$PG_BYTES" \
  "$MINIO_BYTES" "$MINIO_FILES" "$SEC_SHA" "$SEC_BYTES" "$SECRETS_INCLUDED" \
  "$PG_USER" "$PG_DB" "$BUCKET" "$DIR" <<'PY'
import json, os, socket, sys
snap, stamp, git_sha, migrations, pg_sha, pg_bytes, minio_bytes, minio_files, sec_sha, sec_bytes, secrets_included, pg_user, pg_db, bucket, inst = sys.argv[1:]
manifest = {
    "created_at": stamp if "T" in stamp else stamp,
    "created_at_iso": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "hostname": socket.gethostname(),
    "instance_dir": inst,
    "git_sha": git_sha or None,
    "applied_migrations": int(migrations or 0) or None,
    "postgres_user": pg_user,
    "postgres_db": pg_db,
    "bucket": bucket,
    "secrets_included": secrets_included == "1",
    "files": {
        "postgres.dump": {"sha256": pg_sha, "bytes": int(pg_bytes)},
        "minio": {"bytes": int(minio_bytes or 0), "objects": int(minio_files or 0)},
    },
}
if sec_sha:
    manifest["files"]["secrets.env.enc"] = {"sha256": sec_sha, "bytes": int(sec_bytes)}
path = os.path.join(snap, "manifest.json")
with open(path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)
    fh.write("\n")
print(path)
PY

chmod 600 "${SNAP}/manifest.json" "${SNAP}/postgres.dump" 2>/dev/null || true
[[ -f "${SNAP}/secrets.env.enc" ]] && chmod 600 "${SNAP}/secrets.env.enc"

ARCHIVE="${SNAP}.tar.gz.gpg"
log "Chiffrement du snapshot complet"
encrypt_snapshot_archive "$SNAP" "$ARCHIVE" \
  || die "Impossible de chiffrer le snapshot (GPG et phrase de passe requis)."
rm -rf "$SNAP"
SNAP_CREATED=0

# Rétention : 14 j snapshots, 8 sem. hebdo, 12 mois
prune_entries() {
  local path="$1" days="$2"
  [[ -d "$path" ]] || return 0
  find "$path" -mindepth 1 -maxdepth 1 -mtime "+${days}" -exec rm -rf {} +
}

DOW="$(date +%u)"   # 7 = dimanche selon locale... use %w 0=Sunday
DOW="$(date +%w)"
DOM="$(date +%d)"

if [[ "$DOW" == "0" ]]; then
  mkdir -p "${BACKUP_ROOT}/weekly"
  cp -a "$ARCHIVE" "${BACKUP_ROOT}/weekly/${STAMP}.tar.gz.gpg"
fi
if [[ "$DOM" == "01" ]]; then
  mkdir -p "${BACKUP_ROOT}/monthly"
  cp -a "$ARCHIVE" "${BACKUP_ROOT}/monthly/${STAMP}.tar.gz.gpg"
fi

prune_entries "${BACKUP_ROOT}/snapshots" 14
prune_entries "${BACKUP_ROOT}/weekly" 56
prune_entries "${BACKUP_ROOT}/monthly" 366

if [[ -n "${BACKUP_OFFSITE_DIR:-}" ]]; then
  mkdir -p "${BACKUP_OFFSITE_DIR}"
  log "Copie hors site → ${BACKUP_OFFSITE_DIR}"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$ARCHIVE" "${BACKUP_OFFSITE_DIR}/"
  else
    cp -a "$ARCHIVE" "${BACKUP_OFFSITE_DIR}/"
  fi
fi

ok "Snapshot chiffré prêt : ${ARCHIVE}"
echo "$ARCHIVE"
