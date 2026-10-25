#!/usr/bin/env bash
# Restauration d'un snapshot FinFlow.
#
#   # Épreuve (stack jetable, ne touche pas la prod) :
#   ./deploy/backup/restore.sh --target drill --snapshot /var/backups/finflow/snapshots/STAMP
#
#   # Sinistre (arrête l'appli, recrée la base, réécrit le bucket) :
#   sudo ./deploy/backup/restore.sh --target live --snapshot ... --confirm=RESTORE
#
#   --restore-secrets   recopie FIELD_ENCRYPTION_KEY / DJANGO_SECRET_KEY dans .env
#   --keep              (drill) ne détruit pas les conteneurs à la fin
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

TARGET=""
SNAP=""
CONFIRM=""
RESTORE_SECRETS=0
KEEP=0

usage() {
  cat <<'EOF'
Usage:
  restore.sh --target drill --snapshot DIR [--keep]
  restore.sh --target live  --snapshot DIR --confirm=RESTORE [--restore-secrets]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="${2:-}"; shift 2 ;;
    --target=*) TARGET="${1#*=}"; shift ;;
    --snapshot) SNAP="${2:-}"; shift 2 ;;
    --snapshot=*) SNAP="${1#*=}"; shift ;;
    --confirm=*) CONFIRM="${1#*=}"; shift ;;
    --restore-secrets) RESTORE_SECRETS=1; shift ;;
    --keep) KEEP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Option inconnue : $1" ;;
  esac
done

[[ "$TARGET" == "live" || "$TARGET" == "drill" ]] || { usage; die "--target live|drill requis"; }
[[ -n "$SNAP" && -d "$SNAP" ]] || { usage; die "--snapshot DIR requis"; }
SNAP="$(cd "$SNAP" && pwd)"
[[ -f "${SNAP}/postgres.dump" ]] || die "postgres.dump introuvable"

bash "${SCRIPT_DIR}/verify.sh" "$SNAP"

PG_USER="finflow"
PG_DB="finflow"
BUCKET="finflow-documents"
if [[ -f "${SNAP}/manifest.json" ]]; then
  _mf="$(host_path "${SNAP}/manifest.json")"
  PG_USER="$(run_python -c "import json,sys; print(json.load(open(sys.argv[1])).get('postgres_user') or 'finflow')" "$_mf")"
  PG_DB="$(run_python -c "import json,sys; print(json.load(open(sys.argv[1])).get('postgres_db') or 'finflow')" "$_mf")"
  BUCKET="$(run_python -c "import json,sys; print(json.load(open(sys.argv[1])).get('bucket') or 'finflow-documents')" "$_mf")"
fi

restore_live() {
  [[ "$CONFIRM" == "RESTORE" ]] || die "Restauration live refusée : passez --confirm=RESTORE"
  local dir
  dir="$(finflow_dir)"
  COMPOSE_FILES="$(detect_compose_files "$dir")"
  export COMPOSE_FILES
  local env_file="${dir}/.env"
  local minio_user minio_pass
  minio_user="$(load_dotenv_value "$env_file" MINIO_ROOT_USER)"
  minio_user="${minio_user:-minioadmin}"
  minio_pass="$(load_dotenv_value "$env_file" MINIO_ROOT_PASSWORD)"
  minio_pass="${minio_pass:-minioadmin}"

  log "Arrêt backend / worker / beat"
  compose_in "$dir" stop backend worker beat || true

  log "Coupure des sessions PostgreSQL puis recréation de ${PG_DB}"
  compose_in "$dir" exec -T db psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
 WHERE datname = '${PG_DB}' AND pid <> pg_backend_pid();
DROP DATABASE IF EXISTS ${PG_DB};
CREATE DATABASE ${PG_DB} OWNER ${PG_USER};
SQL

  log "pg_restore"
  compose_in "$dir" exec -T db \
    pg_restore -U "$PG_USER" -d "$PG_DB" --no-owner --role="$PG_USER" --exit-on-error \
    < "${SNAP}/postgres.dump"

  if [[ -d "${SNAP}/minio" ]]; then
    log "Réécriture du bucket ${BUCKET}"
    local network
    network="$(compose_network "$dir")"
    docker run --rm --network "$network" \
      -e MC_HOST_dst="http://${minio_user}:${minio_pass}@minio:9000" \
      minio/mc:latest mb -p "dst/${BUCKET}" || true
    docker run --rm --network "$network" \
      -e MC_HOST_dst="http://${minio_user}:${minio_pass}@minio:9000" \
      -v "$(host_path "${SNAP}/minio"):/backup:ro" \
      minio/mc:latest mirror --overwrite /backup "dst/${BUCKET}"
  fi

  if [[ "$RESTORE_SECRETS" -eq 1 && -f "${SNAP}/secrets.env.enc" ]]; then
    restore_secrets_into_env "$env_file"
  elif [[ -f "${SNAP}/secrets.env.enc" ]]; then
    compare_secrets_with_env "$env_file"
  fi

  log "Redémarrage de la pile"
  compose_in "$dir" up -d
  sleep 5
  if compose_in "$dir" exec -T backend python manage.py migrate --check >/dev/null 2>&1; then
    ok "migrate --check : schéma aligné"
  else
    warn "migrate --check a échoué — lancez migrate manuellement si le dump est plus ancien que le code"
  fi
  ok "Restauration live terminée. Contrôlez /api/v1/health/"
}

restore_secrets_into_env() {
  local env_file="$1"
  local tmp
  tmp="$(mktemp_host "$SNAP")"
  decrypt_secrets_file "${SNAP}/secrets.env.enc" "$tmp"
  run_python - "$env_file" "$tmp" <<'PY'
import pathlib, re, sys
env_path, secrets_path = map(pathlib.Path, sys.argv[1:])
text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
updates = {}
for line in secrets_path.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        updates[k.strip()] = v
for key, value in updates.items():
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    if pattern.search(text):
        text = pattern.sub(f"{key}={value}", text, count=1)
    else:
        text = text.rstrip() + f"\n{key}={value}\n"
env_path.write_text(text, encoding="utf-8")
print("secrets written:", ", ".join(updates))
PY
  rm -f "$tmp"
  ok "Secrets recopiés dans ${env_file}"
}

compare_secrets_with_env() {
  local env_file="$1"
  local tmp
  tmp="$(mktemp_host "$SNAP")"
  decrypt_secrets_file "${SNAP}/secrets.env.enc" "$tmp" || { rm -f "$tmp"; return 0; }
  run_python - "$env_file" "$tmp" <<'PY'
import pathlib, sys
env_path, secrets_path = map(pathlib.Path, sys.argv[1:])
current = {}
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            current[k.strip()] = v
snap = {}
for line in secrets_path.read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, _, v = line.partition("=")
        snap[k.strip()] = v
mismatch = [k for k in snap if current.get(k) != snap[k]]
if mismatch:
    print("WARN clés différentes de .env : " + ", ".join(mismatch), file=sys.stderr)
    print("Relancez avec --restore-secrets si le dump doit être relu avec ces clés.", file=sys.stderr)
    sys.exit(2)
print("secrets .env alignés avec le snapshot")
PY
  local rc=$?
  rm -f "$tmp"
  if [[ $rc -eq 2 ]]; then
    warn "FIELD_ENCRYPTION_KEY / DJANGO_SECRET_KEY du .env ≠ snapshot"
  fi
}

restore_drill() {
  local net="finflow-backup-drill"
  local db="finflow-drill-db"
  local minio="finflow-drill-minio"

  cleanup_drill() {
    docker rm -f finflow-drill-db finflow-drill-minio >/dev/null 2>&1 || true
    docker network rm finflow-backup-drill >/dev/null 2>&1 || true
  }
  if [[ "$KEEP" -ne 1 ]]; then
    trap cleanup_drill EXIT
  fi

  docker rm -f "$db" "$minio" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  docker network create "$net" >/dev/null

  log "Drill : PostgreSQL 16 + MinIO jetables"
  docker run -d --name "$db" --network "$net" \
    -e POSTGRES_USER=finflow -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=finflow \
    postgres:16-alpine >/dev/null
  docker run -d --name "$minio" --network "$net" \
    -e MINIO_ROOT_USER=drill -e MINIO_ROOT_PASSWORD=drilldrill \
    minio/minio:latest server /data --console-address ":9001" >/dev/null

  local i
  for i in $(seq 1 30); do
    if docker exec "$db" pg_isready -U finflow >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  docker exec "$db" pg_isready -U finflow >/dev/null

  log "pg_restore → ${db}"
  docker run --rm --network "$net" \
    -v "$(host_path "$SNAP"):/snap:ro" \
    -e PGPASSWORD=drill \
    postgres:16-alpine \
    pg_restore -h "$db" -U finflow -d finflow --no-owner --exit-on-error /snap/postgres.dump

  local tables
  tables="$(docker exec -e PGPASSWORD=drill "$db" \
    psql -U finflow -d finflow -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")"
  local min_tables="${FINFLOW_DRILL_MIN_TABLES:-10}"
  [[ "${tables// /}" -ge "$min_tables" ]] || die "Restore drill : trop peu de tables (${tables}, minimum ${min_tables})"
  ok "Base drill : ${tables// /} tables publiques"

  if [[ -d "${SNAP}/minio" ]] && [[ "$(count_files "${SNAP}/minio")" -gt 0 ]]; then
    docker run --rm --network "$net" \
      -e MC_HOST_dst="http://drill:drilldrill@${minio}:9000" \
      minio/mc:latest mb -p "dst/${BUCKET}" || true
    docker run --rm --network "$net" \
      -e MC_HOST_dst="http://drill:drilldrill@${minio}:9000" \
      -v "$(host_path "${SNAP}/minio"):/backup:ro" \
      minio/mc:latest mirror --overwrite /backup "dst/${BUCKET}"
    local objects
    objects="$(
      docker run --rm --network "$net" \
        -e MC_HOST_dst="http://drill:drilldrill@${minio}:9000" \
        minio/mc:latest ls --recursive "dst/${BUCKET}" | wc -l | tr -d ' '
    )"
    ok "Bucket drill : ${objects} objets"
  else
    warn "Pas d'objets MinIO dans le snapshot"
  fi

  if [[ -f "${SNAP}/secrets.env.enc" ]] && resolve_passphrase; then
    local tmp
    tmp="$(mktemp_host "$SNAP")"
    decrypt_secrets_file "${SNAP}/secrets.env.enc" "$tmp"
    grep -q '^FIELD_ENCRYPTION_KEY=' "$tmp" || die "Secrets drill : clé absente"
    rm -f "$tmp"
    ok "Secrets du snapshot déchiffrables"
  fi

  ok "Épreuve drill réussie (snapshot restaurable)"
}

if [[ "$TARGET" == "live" ]]; then
  restore_live
else
  restore_drill
fi
