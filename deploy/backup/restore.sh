#!/usr/bin/env bash
# Restauration d'un snapshot FinFlow.
#
#   # Épreuve (stack jetable, ne touche pas la prod) :
#   ./deploy/backup/restore.sh --target drill --snapshot /var/backups/finflow/snapshots/STAMP.tar.gz.gpg
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
RESTORE_LIVE_ACTIVE=0
RESTORE_LIVE_DONE=0
RESTORE_DESTRUCTIVE=0
RESTORE_LIVE_DIR=""
RESTORE_SAFETY_ARCHIVE=""

usage() {
  cat <<'EOF'
Usage:
  restore.sh --target drill --snapshot DIR|ARCHIVE.gpg [--keep]
  restore.sh --target live  --snapshot DIR|ARCHIVE.gpg --confirm=RESTORE [--restore-secrets]
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
[[ -n "$SNAP" ]] || { usage; die "--snapshot DIR|ARCHIVE.gpg requis"; }
SNAP_WORK=""
cleanup_snapshot_temp() {
  [[ -z "$SNAP_WORK" ]] || rm -rf "$SNAP_WORK"
}
trap cleanup_snapshot_temp EXIT
if [[ -f "$SNAP" ]]; then
  SNAP_ARCHIVE="$(cd "$(dirname "$SNAP")" && pwd)/$(basename "$SNAP")"
  SNAP_WORK="$(mktemp -d "${TMPDIR:-/tmp}/finflow-restore.XXXXXX")"
  chmod 700 "$SNAP_WORK"
  decrypt_snapshot_archive "$SNAP_ARCHIVE" "$SNAP_WORK" \
    || die "Archive illisible, phrase de passe incorrecte ou GPG indisponible."
  SNAP="$(find "$SNAP_WORK" -mindepth 1 -maxdepth 1 -type d -print -quit)"
  [[ -n "$SNAP" ]] || die "Aucun dossier de snapshot dans l'archive."
elif [[ -d "$SNAP" ]]; then
  SNAP="$(cd "$SNAP" && pwd)"
else
  usage
  die "--snapshot doit désigner un dossier ou une archive chiffrée."
fi
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

[[ "$PG_USER" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "postgres_user invalide dans le snapshot"
[[ "$PG_DB" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "postgres_db invalide dans le snapshot"
[[ "$BUCKET" =~ ^[A-Za-z0-9._-]+$ ]] || die "bucket invalide dans le snapshot"

restore_live_exit() {
  local rc=$?
  if [[ "$RESTORE_LIVE_ACTIVE" == "1" && "$RESTORE_LIVE_DONE" != "1" ]]; then
    if [[ "$RESTORE_DESTRUCTIVE" == "1" ]]; then
      warn "Restauration interrompue après remplacement de données (code ${rc}). Services applicatifs laissés arrêtés pour éviter d'exposer un état partiel. Le snapshot de sécurité doit être restauré ou vérifié avant remise en service."
      [[ -z "$RESTORE_SAFETY_ARCHIVE" ]] || warn "Snapshot de sécurité : $RESTORE_SAFETY_ARCHIVE"
      warn "Après correction, restaurez-le avec : sudo $RESTORE_LIVE_DIR/scripts/restore.sh --target live --snapshot '$RESTORE_SAFETY_ARCHIVE' --confirm=RESTORE"
      compose_in "$RESTORE_LIVE_DIR" stop backend worker beat frontend >/dev/null 2>&1 || true
    else
      warn "Restauration interrompue avant remplacement de données (code ${rc}) ; redémarrage des services applicatifs."
      compose_in "$RESTORE_LIVE_DIR" up -d backend worker beat frontend || \
        warn "Redémarrage automatique incomplet ; utilisez finflow up -d après correction."
    fi
  fi
  cleanup_snapshot_temp
}

restore_live() {
  [[ "$CONFIRM" == "RESTORE" ]] || die "Restauration live refusée : passez --confirm=RESTORE"
  local dir
  dir="$(finflow_dir)"
  RESTORE_LIVE_ACTIVE=1
  RESTORE_LIVE_DIR="$dir"
  trap restore_live_exit EXIT
  COMPOSE_FILES="$(detect_compose_files "$dir")"
  export COMPOSE_FILES
  local env_file="${dir}/.env"
  local minio_user minio_pass
  minio_user="$(load_dotenv_value "$env_file" MINIO_ROOT_USER)"
  minio_user="${minio_user:-minioadmin}"
  minio_pass="$(load_dotenv_value "$env_file" MINIO_ROOT_PASSWORD)"
  minio_pass="${minio_pass:-minioadmin}"
  local minio_client_image safety_archive
  minio_client_image="${MINIO_CLIENT_IMAGE:-$(load_dotenv_value "$env_file" MINIO_CLIENT_IMAGE)}"
  minio_client_image="${minio_client_image:-cgr.dev/chainguard/minio-client:latest}"

  log "Snapshot de sécurité avant restauration live"
  safety_archive="$(FINFLOW_DIR="$dir" bash "$dir/deploy/backup/backup.sh" | tail -n 1)" \
    || die "Snapshot de sécurité pré-restauration échoué ; aucune donnée n'a été remplacée."
  [[ -f "$safety_archive" ]] || die "Archive de sécurité introuvable : ${safety_archive:-inconnue}"
  RESTORE_SAFETY_ARCHIVE="$safety_archive"
  bash "$dir/deploy/backup/verify.sh" "$safety_archive" \
    || die "Snapshot de sécurité non vérifiable ; aucune donnée n'a été remplacée."
  ok "Snapshot de sécurité conservé : $safety_archive"

  log "Arrêt backend / worker / beat / frontend"
  compose_in "$dir" stop backend worker beat frontend \
    || die "Impossible d'arrêter les services applicatifs ; la base n'a pas été remplacée."

  log "Coupure des sessions PostgreSQL puis recréation de ${PG_DB}"
  RESTORE_DESTRUCTIVE=1
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
      "$minio_client_image" mb -p "dst/${BUCKET}" || true
    docker run --rm --network "$network" \
      -e MC_HOST_dst="http://${minio_user}:${minio_pass}@minio:9000" \
      --user 0:0 \
      -v "$(host_path "${SNAP}/minio"):/backup:ro" \
      "$minio_client_image" mirror --overwrite --remove /backup "dst/${BUCKET}"
  fi

  if [[ "$RESTORE_SECRETS" -eq 1 && -f "${SNAP}/secrets.env.enc" ]]; then
    restore_secrets_into_env "$env_file"
  elif [[ -f "${SNAP}/secrets.env.enc" ]]; then
    compare_secrets_with_env "$env_file"
  fi

  # pg_dump n'embarque pas les mots de passe globaux des rôles. Aligner celui
  # du rôle restauré sur le .env avant de relancer l'application.
  local pg_password role_sql
  pg_password="$(load_dotenv_value "$env_file" POSTGRES_PASSWORD)"
  [[ -n "$pg_password" ]] || die "POSTGRES_PASSWORD absent du .env après restauration."
  role_sql="$(mktemp_host "$SNAP")"
  chmod 600 "$role_sql"
  FINFLOW_PG_ROLE="$PG_USER" FINFLOW_PG_PASSWORD="$pg_password" run_python - "$role_sql" <<'PY'
import os, pathlib
role = os.environ["FINFLOW_PG_ROLE"]
password = os.environ["FINFLOW_PG_PASSWORD"]
path = pathlib.Path(os.sys.argv[1])
escaped = password.replace("'", "''")
path.write_text('ALTER ROLE "{}" PASSWORD \'{}\';\n'.format(role, escaped), encoding="utf-8")
os.chmod(path, 0o600)
PY
  compose_in "$dir" exec -T db psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 < "$role_sql" \
    || die "Impossible d'aligner le mot de passe PostgreSQL du rôle restauré."
  rm -f "$role_sql"

  log "Redémarrage de la pile"
  compose_in "$dir" up -d
  local i
  for i in $(seq 1 36); do
    if curl -fsS http://127.0.0.1:8080/api/v1/health/ >/dev/null 2>&1; then
      break
    fi
    sleep 5
  done
  curl -fsS http://127.0.0.1:8080/api/v1/health/ >/dev/null \
    || die "La restauration a terminé, mais le contrôle de santé API échoue. Vérifiez les journaux."
  if compose_in "$dir" exec -T backend python manage.py migrate --check >/dev/null 2>&1; then
    ok "migrate --check : schéma aligné"
  else
    warn "migrate --check a échoué — lancez migrate manuellement si le dump est plus ancien que le code"
  fi
  RESTORE_LIVE_DONE=1
  ok "Restauration live terminée ; API disponible sur /api/v1/health/"
}

restore_secrets_into_env() (
  local env_file="$1"
  local tmp
  tmp="$(mktemp_host "$SNAP")"
  trap 'rm -f "$tmp"' EXIT
  decrypt_secrets_file "${SNAP}/secrets.env.enc" "$tmp"
  local format="legacy-keys"
  if [[ -f "${SNAP}/manifest.json" ]]; then
    format="$(run_python - "$(host_path "${SNAP}/manifest.json")" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    print(json.load(fh).get("secrets_format") or "legacy-keys")
PY
)"
  fi
  run_python - "$env_file" "$tmp" "$format" <<'PY'
import os, pathlib, re, sys, tempfile
env_path, secrets_path = map(pathlib.Path, sys.argv[1:3])
format_name = sys.argv[3]
snapshot_text = secrets_path.read_text(encoding="utf-8")
if format_name == "dotenv-full-v1":
    values = {
        line.split("=", 1)[0].strip()
        for line in snapshot_text.splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    required = {"DJANGO_SECRET_KEY", "FIELD_ENCRYPTION_KEY", "POSTGRES_PASSWORD", "MINIO_ROOT_PASSWORD"}
    missing = sorted(required - values)
    if missing:
        raise SystemExit("configuration complète invalide, champs absents : " + ", ".join(missing))
    env_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".finflow-env-restore-", dir=env_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(snapshot_text)
        os.chmod(temporary, 0o600)
        os.replace(temporary, env_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("configuration .env complète restaurée (mode 0600)")
else:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    updates = {}
    for line in snapshot_text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            updates[k.strip()] = v
    for key, value in updates.items():
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
        if pattern.search(text):
            text = pattern.sub(lambda _match: f"{key}={value}", text, count=1)
        else:
            text = text.rstrip() + f"\n{key}={value}\n"
    env_path.write_text(text, encoding="utf-8")
    os.chmod(env_path, 0o600)
    print("secrets historiques fusionnés :", ", ".join(updates))
PY
  ok "Secrets recopiés dans ${env_file}"
)

compare_secrets_with_env() {
  local env_file="$1"
  local tmp
  tmp="$(mktemp_host "$SNAP")"
  decrypt_secrets_file "${SNAP}/secrets.env.enc" "$tmp" || { rm -f "$tmp"; return 0; }
  local rc
  if run_python - "$env_file" "$tmp" <<'PY'
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
    print("WARN paramètres différents de .env : " + ", ".join(mismatch), file=sys.stderr)
    print("Relancez avec --restore-secrets si la configuration complète du snapshot doit être restaurée.", file=sys.stderr)
    sys.exit(2)
print("secrets .env alignés avec le snapshot")
PY
  then
    rc=0
  else
    rc=$?
  fi
  rm -f "$tmp"
  if [[ $rc -eq 2 ]]; then
    warn "Configuration .env différente du snapshot"
  fi
}

restore_drill() {
  local net="finflow-backup-drill"
  local db="finflow-drill-db"
  local minio="finflow-drill-minio"
  local instance_dir postgres_image minio_image minio_client_image
  instance_dir="$(finflow_dir)"
  postgres_image="${POSTGRES_IMAGE:-$(load_dotenv_value "$instance_dir/.env" POSTGRES_IMAGE)}"
  postgres_image="${postgres_image:-postgres:16-alpine}"
  minio_image="${MINIO_IMAGE:-$(load_dotenv_value "$instance_dir/.env" MINIO_IMAGE)}"
  minio_image="${minio_image:-cgr.dev/chainguard/minio:latest}"
  minio_client_image="${MINIO_CLIENT_IMAGE:-$(load_dotenv_value "$instance_dir/.env" MINIO_CLIENT_IMAGE)}"
  minio_client_image="${minio_client_image:-cgr.dev/chainguard/minio-client:latest}"

  cleanup_drill() {
    docker rm -f finflow-drill-db finflow-drill-minio >/dev/null 2>&1 || true
    docker network rm finflow-backup-drill >/dev/null 2>&1 || true
  }
  if [[ "$KEEP" -ne 1 ]]; then
    trap 'cleanup_drill; cleanup_snapshot_temp' EXIT
  fi

  docker rm -f "$db" "$minio" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
  docker network create "$net" >/dev/null

  log "Drill : PostgreSQL 16 + MinIO jetables"
  docker run -d --name "$db" --network "$net" \
    -e POSTGRES_USER=finflow -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=finflow \
    "$postgres_image" >/dev/null
  docker run -d --name "$minio" --network "$net" \
    -e MINIO_ROOT_USER=drill -e MINIO_ROOT_PASSWORD=drilldrill \
    --user 0:0 \
    "$minio_image" server /data --console-address ":9001" >/dev/null

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
    "$postgres_image" \
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
      "$minio_client_image" mb -p "dst/${BUCKET}" || true
    docker run --rm --network "$net" \
      -e MC_HOST_dst="http://drill:drilldrill@${minio}:9000" \
      --user 0:0 \
      -v "$(host_path "${SNAP}/minio"):/backup:ro" \
      "$minio_client_image" mirror --overwrite --remove /backup "dst/${BUCKET}"
    local objects
    objects="$(
      docker run --rm --network "$net" \
        -e MC_HOST_dst="http://drill:drilldrill@${minio}:9000" \
        "$minio_client_image" ls --recursive "dst/${BUCKET}" | wc -l | tr -d ' '
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
