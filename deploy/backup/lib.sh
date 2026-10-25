#!/usr/bin/env bash
# Fonctions partagées : résolution du dépôt, Compose, checksums, secrets.
# shellcheck disable=SC2034
set -euo pipefail

BACKUP_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Git Bash (Windows) réécrit /data → C:/Program Files/Git/data dans docker -v.
export MSYS_NO_PATHCONV=1

log()  { echo "[INFO] $*"; }
ok()   { echo "[OK] $*"; }
warn() { echo "[WARN] $*" >&2; }
err()  { echo "[ERR] $*" >&2; }
die()  { err "$*"; exit 1; }

finflow_dir() {
  if [[ -n "${FINFLOW_DIR:-}" ]]; then
    cd "${FINFLOW_DIR}" && pwd
    return
  fi
  # deploy/backup → racine du dépôt
  cd "${BACKUP_LIB_DIR}/../.." && pwd
}

detect_compose_files() {
  local dir="$1"
  local helper="${BACKUP_LIB_DIR}/../compose-files.sh"

  if [[ -n "${COMPOSE_FILES:-}" ]]; then
    echo "${COMPOSE_FILES}"
    return
  fi
  if [[ -f "$helper" ]]; then
    bash "$helper" "$dir"
    return
  fi
  if [[ -f "$dir/docker-compose.prod.yml" ]]; then
    echo "-f docker-compose.yml -f docker-compose.prod.yml"
    return
  fi
  echo "-f docker-compose.yml"
}

compose() {
  # shellcheck disable=SC2086
  docker compose ${COMPOSE_FILES} "$@"
}

compose_in() {
  local dir="$1"
  shift
  (
    cd "$dir" || exit 1
    # -f relatif : doit être résolu depuis le répertoire de l'instance.
    # shellcheck disable=SC2086
    docker compose --project-directory "$(host_path "$dir")" ${COMPOSE_FILES} "$@"
  )
}

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

dir_bytes() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo 0
    return
  fi
  if command -v du >/dev/null 2>&1; then
    du -sb "$path" 2>/dev/null | awk '{print $1}' || echo 0
  else
    echo 0
  fi
}

count_files() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo 0
    return
  fi
  find "$path" -type f | wc -l | tr -d ' '
}

load_dotenv_value() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || return 0
  local line
  line="$(grep -E "^${key}=" "$file" | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0
  line="${line#${key}=}"
  line="${line%\"}"
  line="${line#\"}"
  line="${line%\'}"
  line="${line#\'}"
  printf '%s' "$line"
}

resolve_passphrase() {
  if [[ -n "${BACKUP_PASSPHRASE:-}" ]]; then
    return 0
  fi
  local file="${BACKUP_PASSPHRASE_FILE:-}"
  if [[ -z "$file" && -f /root/.finflow-backup-pass ]]; then
    file="/root/.finflow-backup-pass"
  fi
  if [[ -n "$file" && -f "$file" ]]; then
    BACKUP_PASSPHRASE="$(tr -d '\r\n' < "$file")"
    export BACKUP_PASSPHRASE
    return 0
  fi
  return 1
}

mktemp_host() {
  # OpenSSL natif Windows ne voit pas /tmp de Git Bash.
  local dir="${1:-}"
  if [[ -z "$dir" ]]; then
    if [[ -n "${LOCALAPPDATA:-}" ]] && command -v cygpath >/dev/null 2>&1; then
      dir="$(cygpath -u "$LOCALAPPDATA")/Temp"
    elif [[ -d /c/Windows/Temp ]]; then
      dir="/c/Windows/Temp"
    else
      dir="${TMPDIR:-/tmp}"
    fi
  fi
  mkdir -p "$dir"
  mktemp "${dir}/ffbk.XXXXXX"
}

encrypt_secrets_file() {
  local src="$1" dest="$2"
  resolve_passphrase || die "BACKUP_PASSPHRASE ou BACKUP_PASSPHRASE_FILE requis pour chiffrer les secrets."
  openssl enc -aes-256-cbc -pbkdf2 -salt \
    -in "$(host_path "$src")" -out "$(host_path "$dest")" \
    -pass env:BACKUP_PASSPHRASE
}

decrypt_secrets_file() {
  local src="$1" dest="$2"
  resolve_passphrase || die "BACKUP_PASSPHRASE ou BACKUP_PASSPHRASE_FILE requis pour lire les secrets."
  openssl enc -d -aes-256-cbc -pbkdf2 \
    -in "$(host_path "$src")" -out "$(host_path "$dest")" \
    -pass env:BACKUP_PASSPHRASE
}

compose_network() {
  local dir="$1"
  local cid
  cid="$(compose_in "$dir" ps -q minio 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    cid="$(compose_in "$dir" ps -q db 2>/dev/null || true)"
  fi
  [[ -n "$cid" ]] || die "Aucun conteneur Compose (minio/db) — stack arrêtée ?"
  docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$cid"
}

host_path() {
  # Docker Desktop sous Git Bash attend un chemin Windows (C:\...).
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}

run_python() {
  local cand venv
  if command -v python3 >/dev/null 2>&1 && python3 -c "import json" >/dev/null 2>&1; then
    python3 "$@"
    return
  fi
  if command -v py >/dev/null 2>&1 && py -3 -c "import json" >/dev/null 2>&1; then
    py -3 "$@"
    return
  fi
  if command -v python >/dev/null 2>&1 && python -c "import json" >/dev/null 2>&1; then
    python "$@"
    return
  fi
  venv="${BACKUP_LIB_DIR}/../../backend/.venv/Scripts/python.exe"
  if [[ -x "$venv" ]]; then
    "$venv" "$@"
    return
  fi
  venv="${BACKUP_LIB_DIR}/../../backend/.venv/bin/python"
  if [[ -x "$venv" ]]; then
    "$venv" "$@"
    return
  fi
  die "python3 est requis pour écrire le manifeste."
}

utc_stamp() {
  date -u +%Y%m%dT%H%M%SZ
}

iso_now() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}
