#!/usr/bin/env bash
# =========================================================================
# FIN_FLOW — mise à jour d'une instance déjà en production (Ubuntu)
#
# À lancer sur le serveur où FinFlow est installé (typiquement /opt/finflow).
#
# Usage :
#   sudo bash deploy/ubuntu-update.sh
#   sudo bash deploy/ubuntu-update.sh /opt/finflow
#   sudo bash deploy/ubuntu-update.sh --check /opt/finflow
#   # Depuis une installation mise à jour avec un accès GitHub autorisé :
#   sudo bash /opt/finflow/deploy/ubuntu-update.sh
#
# Options (variables d'environnement) :
#   INSTALL_DIR=/opt/finflow   Répertoire d'installation
#   GIT_BRANCH=main            Branche à tirer
#   SKIP_BACKUP=1              Sauter explicitement le snapshot complet (déconseillé)
#   SKIP_GIT=1                 Ne pas faire git pull (images/code déjà présents)
#   REPO_URL=...               Remplacer explicitement l'URL Git origin
#   SKIP_BUILD=0               1 = up -d sans --build (déconseillé)
#
# Le script :
#   1. snapshot chiffré Postgres + MinIO + secrets (sauf SKIP_BACKUP=1 explicite)
#   2. git fetch + pull --ff-only
#   3. docker compose pull + up -d --build
#      (mode IP / IP+TLS via deploy/compose-files.sh)
#   4. migrate + sync_role_packs + bootstrap_all_tenants
#   5. contrôle bloquant health API (frontend local :8080)
# =========================================================================
set -euo pipefail

INSTALL_DIR_DEFAULT="/opt/finflow"

if [[ -t 1 ]]; then
  C_INFO='\033[1;36m'
  C_OK='\033[1;32m'
  C_WARN='\033[1;33m'
  C_ERR='\033[1;31m'
  C_RST='\033[0m'
else
  C_INFO=''
  C_OK=''
  C_WARN=''
  C_ERR=''
  C_RST=''
fi

log()  { echo -e "${C_INFO}[INFO]${C_RST} $*"; }
ok()   { echo -e "${C_OK}[OK]${C_RST} $*"; }
warn() { echo -e "${C_WARN}[WARN]${C_RST} $*"; }
err()  { echo -e "${C_ERR}[ERR]${C_RST} $*" >&2; }
die()  { err "$*"; exit 1; }

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Exécutez en root : sudo bash deploy/ubuntu-update.sh"
  fi
}

require_compose_version() {
  command -v docker >/dev/null 2>&1 || die "Docker Engine est introuvable."
  local version
  version="$(docker compose version --short 2>/dev/null || true)"
  version="${version#v}"
  [[ -n "$version" ]] || die "Docker Compose v2 est requis."
  dpkg --compare-versions "$version" ge 2.24.4 \
    || die "Docker Compose ${version} est trop ancien : FinFlow requiert au minimum 2.24.4 (balise !override)."
  systemctl enable --now docker
}

# Repli si compose-files.sh n'est pas encore tiré (1re update d'une vieille instance).
detect_compose_files_fallback() {
  local dir="$1"
  local mode="" tls=""
  if [[ -f "$dir/.finflow-deploy-mode" ]]; then
    mode="$(tr -d '[:space:]' < "$dir/.finflow-deploy-mode" || true)"
  fi
  if [[ -f "$dir/.finflow-tls-mode" ]]; then
    tls="$(tr -d '[:space:]' < "$dir/.finflow-tls-mode" || true)"
  fi
  if [[ "$mode" == "ip" || -n "$tls" ]]; then
    local files="-f docker-compose.yml -f docker-compose.prod.yml"
    if [[ -f "$dir/docker-compose.ip.yml" ]]; then
      files="${files} -f docker-compose.ip.yml"
    fi
    if [[ "$tls" == "le" || "$tls" == "selfsigned" ]] && [[ -f "$dir/docker-compose.ip-tls.yml" ]]; then
      files="${files} -f docker-compose.ip-tls.yml"
    fi
    echo "$files"
    return
  fi
  if [[ "$mode" == "domain" || "$mode" == "prod" ]]; then
    echo "-f docker-compose.yml -f docker-compose.prod.yml"
    return
  fi
  if [[ -f "$dir/docker-compose.ip.yml" && -f "$dir/.env" ]]; then
    if grep -Eq '^FINFLOW_PUBLIC_IP=' "$dir/.env" 2>/dev/null \
      || grep -Eq '^FRONTEND_BASE_URL=["'"'"']?https?://([0-9]{1,3}\.){3}[0-9]{1,3}' "$dir/.env" 2>/dev/null \
      || grep -Eq '^DJANGO_SECURE_SSL_REDIRECT=["'"'"']?False["'"'"']?' "$dir/.env" 2>/dev/null; then
      echo "-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml"
      return
    fi
  fi
  echo "-f docker-compose.yml -f docker-compose.prod.yml"
}

detect_compose_files() {
  local dir="$1"
  if [[ -f "$dir/deploy/compose-files.sh" ]]; then
    bash "$dir/deploy/compose-files.sh" "$dir"
    return
  fi
  detect_compose_files_fallback "$dir"
}

compose() {
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES "$@"
}

backup_db() {
  local dir="$1"
  local script="${dir}/deploy/backup/backup.sh"
  [[ -f "$script" ]] || die "Script de snapshot complet absent : $script. Mise à jour interrompue."
  grep -q 'encrypt_snapshot_archive' "$script" \
    || die "Le script de sauvegarde installé est ancien et ne chiffre pas le snapshot complet. Mettez les scripts à jour avant l'update."
  log "Snapshot chiffré pré-update (Postgres + MinIO + secrets)"
  FINFLOW_DIR="$dir" BACKUP_PASSPHRASE_FILE="${BACKUP_PASSPHRASE_FILE:-/root/.finflow-backup-pass}" \
    SKIP_APP_PAUSE="${SKIP_APP_PAUSE:-0}" \
    bash "$script" || die "Le snapshot pré-update a échoué. Aucune mise à jour n'a été appliquée."
  ok "Snapshot pré-update chiffré OK"
}

ensure_mail_env() {
  local dir="$1"
  local env_file="$dir/.env"
  local key_data key source
  [[ -f "$env_file" ]] || return 0

  if ! key_data="$(python3 - "$env_file" <<'PY'
import base64
import hashlib
import re
import sys

values = {}
with open(sys.argv[1], encoding="utf-8") as env_file:
    for line in env_file:
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, value = line.rstrip("\r\n").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\\\"'":
            value = value[1:-1]
        values[name] = value

key = values.get("FIELD_ENCRYPTION_KEY", "").strip()
if key:
    source = "existing"
else:
    secret = values.get("DJANGO_SECRET_KEY", "")
    if not secret:
        raise SystemExit(2)
    # Compatibilité des anciennes instances qui dérivaient Fernet de SECRET_KEY.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest()).decode("ascii")
    source = "derived"

if not re.fullmatch(r"[A-Za-z0-9_-]{43}=", key):
    raise SystemExit(3)
try:
    raw = base64.urlsafe_b64decode(key)
except (ValueError, base64.binascii.Error):
    raise SystemExit(3)
if len(raw) != 32:
    raise SystemExit(3)
print(f"{source}|{key}")
PY
  )"; then
    die "Impossible de valider FIELD_ENCRYPTION_KEY. Vérifiez DJANGO_SECRET_KEY et restaurez la clé de chiffrement d'origine."
  fi
  source="${key_data%%|*}"
  key="${key_data#*|}"
  if [[ "$source" == "derived" ]]; then
    sed -i '/^FIELD_ENCRYPTION_KEY=/d' "$env_file"
    {
      echo
      echo "# Compatibilité migration — clé Fernet dérivée de l'ancienne DJANGO_SECRET_KEY."
      echo "# Ne pas changer cette clé tant que les données chiffrées n'ont pas été migrées."
      printf 'FIELD_ENCRYPTION_KEY="%s"\n' "$key"
    } >> "$env_file"
    warn "FIELD_ENCRYPTION_KEY absente : reprise de la clé historique dérivée de DJANGO_SECRET_KEY pour préserver les secrets déjà chiffrés."
  else
    ok "FIELD_ENCRYPTION_KEY existante validée."
  fi

  if ! grep -Eq '^SMTP_SSL_VERIFY=' "$env_file" 2>/dev/null; then
    echo 'SMTP_SSL_VERIFY="1"' >> "$env_file"
    ok "SMTP_SSL_VERIFY=1 ajouté au .env"
  fi

  if grep -Eq '^EMAIL_BACKEND=.*console' "$env_file" 2>/dev/null; then
    warn "EMAIL_BACKEND=console détecté — passez à smtp.EmailBackend pour un envoi réel (ou SMTP filiale en UI)."
  fi
  chmod 600 "$env_file"
}

pull_code() {
  local dir="$1"
  local branch="$2"
  local repo="$3"

  cd "$dir"
  [[ -d .git ]] || die "Pas de dépôt Git dans $dir ; mise à jour impossible."
  log "git fetch / checkout ${branch} / pull --ff-only…"
  if [[ -n "$repo" ]]; then
    if git remote get-url origin >/dev/null 2>&1; then
      git remote set-url origin "$repo"
    else
      git remote add origin "$repo"
    fi
  fi
  git fetch origin "$branch" --prune
  if git show-ref --verify --quiet "refs/heads/$branch"; then
    git checkout "$branch"
  else
    git checkout --track -b "$branch" "origin/$branch"
  fi
  git pull --ff-only origin "$branch"
  ok "Code à jour : $(git rev-parse --short HEAD) ($(git log -1 --pretty=%s))"
}

chmod_deploy_scripts() {
  local dir="$1"
  chmod +x "$dir/deploy/ubuntu-update.sh" \
    "$dir/deploy/ubuntu-install.sh" \
    "$dir/deploy/ubuntu-install-ip.sh" \
    "$dir/deploy/compose-files.sh" \
    2>/dev/null || true
  chmod +x "$dir/deploy/tls-ip/enable-ip-tls.sh" 2>/dev/null || true
  chmod +x "$dir/deploy/backup/"*.sh 2>/dev/null || true
}

rebuild_stack() {
  local dir="$1"
  local with_build="${2:-1}"
  cd "$dir"
  log "Docker Compose pull…"
  compose pull
  if [[ "$with_build" == "1" ]]; then
    log "Build & redémarrage (up -d --build)…"
    compose up -d --build
  else
    log "Redémarrage sans rebuild (up -d)…"
    compose up -d
  fi
  ok "Stack redémarrée."
}

wait_health() {
  log "Attente health API (max ~3 min)…"
  local i
  for i in $(seq 1 36); do
    if curl -fsS http://127.0.0.1:8080/api/v1/health/ >/dev/null 2>&1; then
      ok "API prête : http://127.0.0.1:8080/api/v1/health/"
      return 0
    fi
    sleep 5
  done
  warn "Health check en échec — derniers journaux des services :"
  compose logs --tail=100 backend db minio frontend || true
  return 1
}

post_deploy() {
  local dir="$1"
  cd "$dir"
  log "Migrations…"
  compose exec -T backend python manage.py migrate --noinput
  ok "Migrations appliquées."

  log "Synchronisation packs de rôles…"
  compose exec -T backend python manage.py sync_role_packs
  ok "Packs RBAC synchronisés."

  log "Bootstrap filiales (catalogue, Perfect, circuits ML/Dation/Formalisation)…"
  compose exec -T backend python manage.py bootstrap_all_tenants
  ok "Filiales bootstrapées."
}

refresh_helpers() {
  local dir="$1"
  mkdir -p "$dir/scripts"

  cat > "$dir/scripts/finflow" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$dir"
if [[ -f "$dir/deploy/compose-files.sh" ]]; then
  exec docker compose \$(bash "$dir/deploy/compose-files.sh" "$dir") "\$@"
fi
exec docker compose -f docker-compose.yml -f docker-compose.prod.yml "\$@"
EOF
  chmod +x "$dir/scripts/finflow"
  ln -sfn "$dir/scripts/finflow" /usr/local/bin/finflow

  if [[ -f "$dir/deploy/ubuntu-update.sh" ]]; then
    ln -sfn "$dir/deploy/ubuntu-update.sh" "$dir/scripts/update.sh"
    ln -sfn "$dir/deploy/ubuntu-update.sh" /usr/local/bin/finflow-update
  fi

  ensure_backup_cron "$dir"
  ok "Helpers rafraîchis : finflow, finflow-update"
}

ensure_backup_cron() {
  local dir="$1"
  [[ -f "$dir/deploy/backup/wire-install.sh" ]] \
    || die "deploy/backup/wire-install.sh manquant — sauvegarde automatique obligatoire."
  bash "$dir/deploy/backup/wire-install.sh" "$dir" \
    || die "Cron de sauvegarde non posé (/var/backups/finflow)."
}

print_summary() {
  local dir="$1"
  local mode="" tls=""
  [[ -f "$dir/.finflow-deploy-mode" ]] && mode="$(tr -d '[:space:]' < "$dir/.finflow-deploy-mode")"
  [[ -f "$dir/.finflow-tls-mode" ]] && tls="$(tr -d '[:space:]' < "$dir/.finflow-tls-mode")"
  cat <<EOF

${C_OK}═══════════════════════════════════════════════════════════${C_RST}
${C_OK} FIN_FLOW — mise à jour terminée${C_RST}
${C_OK}═══════════════════════════════════════════════════════════${C_RST}

  Répertoire : ${dir}
  Mode       : ${mode:-inconnu}${tls:+ + TLS ${tls}}
  Compose    : docker compose ${COMPOSE_FILES}
  Commandes  : finflow ps | finflow logs -f backend
  Prochaine  : sudo finflow-update   (ou sudo bash ${dir}/deploy/ubuntu-update.sh)

  Sauvegardes : cron 02:30 → /var/backups/finflow/snapshots (hors projet)
    sudo FINFLOW_DIR=${dir} ${dir}/deploy/backup/backup.sh

  HTTPS IP interne (auto-signé, sans HSTS) :
    sudo bash ${dir}/deploy/tls-ip/enable-ip-tls.sh ${dir} --self-signed

  Nouveautés typiques après update :
    • migrations DB
    • packs de rôles (dont formalisation)
    • circuits MAIN_LEVEE / DATION / FORMALISATION

EOF
}

run_check() {
  local dir="$1"
  [[ -d "$dir" ]] || die "Répertoire introuvable : $dir"
  [[ -f "$dir/docker-compose.yml" ]] || die "docker-compose.yml manquant dans $dir"
  [[ -f "$dir/docker-compose.prod.yml" ]] || die "docker-compose.prod.yml manquant dans $dir"

  local via="fallback"
  if [[ -f "$dir/deploy/compose-files.sh" ]]; then
    via="compose-files.sh"
  fi
  COMPOSE_FILES="$(detect_compose_files "$dir")"
  local fallback
  fallback="$(detect_compose_files_fallback "$dir")"

  echo "FIN_FLOW — contrôle ubuntu-update (--check)"
  echo "  dir     : $dir"
  echo "  via     : $via"
  echo "  compose : docker compose $COMPOSE_FILES"
  echo "  fallback: docker compose $fallback"

  local f
  for f in docker-compose.yml docker-compose.prod.yml; do
    [[ -f "$dir/$f" ]] || die "Manquant : $f"
  done
  if echo "$COMPOSE_FILES" | grep -q 'docker-compose.ip.yml'; then
    [[ -f "$dir/docker-compose.ip.yml" ]] || die "Mode IP mais docker-compose.ip.yml absent"
  fi
  if echo "$COMPOSE_FILES" | grep -q 'docker-compose.ip-tls.yml'; then
    [[ -f "$dir/docker-compose.ip-tls.yml" ]] || die "Mode IP+TLS mais docker-compose.ip-tls.yml absent"
  fi

  if [[ -f "$dir/deploy/compose-files.sh" ]] && [[ "$COMPOSE_FILES" != "$fallback" ]]; then
    # Le fallback ignore l'heuristique FINFLOW_PUBLIC_IP si mode=domain ; sinon ils doivent coller
    if [[ ! -f "$dir/.finflow-deploy-mode" ]] || [[ "$(tr -d '[:space:]' < "$dir/.finflow-deploy-mode")" != "domain" ]]; then
      warn "compose-files.sh et fallback divergent (OK si heuristique plus riche)."
    fi
  fi

  echo "  backups : /var/backups/finflow/snapshots (hors projet)"
  if [[ -f /etc/cron.d/finflow-backup ]]; then
    echo "  cron    : /etc/cron.d/finflow-backup"
    grep -v '^#' /etc/cron.d/finflow-backup | grep -v '^$' || true
  else
    warn "Cron /etc/cron.d/finflow-backup absent — l'update le posera via wire-install.sh"
  fi
  [[ -f "$dir/deploy/backup/backup.sh" ]] || warn "deploy/backup/backup.sh manquant"
  [[ -f "$dir/deploy/backup/wire-install.sh" ]] || warn "deploy/backup/wire-install.sh manquant"

  ok "Contrôle de résolution Compose : OK"
}

main() {
  local check=0
  local dir=""
  local arg
  local -a cleaned=()
  for arg in "$@"; do
    cleaned+=("${arg%$'\r'}")
  done
  set -- "${cleaned[@]}"

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --check) check=1; shift ;;
      -h|--help)
        sed -n '2,28p' "$0"
        exit 0
        ;;
      *)
        dir="$1"
        shift
        ;;
    esac
  done
  dir="${dir:-${INSTALL_DIR:-$INSTALL_DIR_DEFAULT}}"

  if [[ "$check" -eq 1 ]]; then
    run_check "$dir"
    return 0
  fi

  need_root

  local branch="${GIT_BRANCH:-main}"
  local repo="${REPO_URL:-}"
  local skip_backup="${SKIP_BACKUP:-0}"
  local skip_git="${SKIP_GIT:-0}"
  local skip_build="${SKIP_BUILD:-0}"
  local with_build=1
  [[ "$skip_build" == "1" ]] && with_build=0

  echo
  echo "FIN_FLOW — mise à jour production"
  echo "Guide : documentation/13-guide-deploiement-ubuntu.md"
  echo

  [[ -d "$dir" ]] || die "Répertoire introuvable : $dir"
  [[ -f "$dir/docker-compose.yml" ]] || die "docker-compose.yml manquant dans $dir"
  [[ -f "$dir/docker-compose.prod.yml" ]] || die "docker-compose.prod.yml manquant dans $dir"
  [[ -f "$dir/.env" ]] || die "Fichier .env manquant dans $dir — ne pas écraser les secrets."
  if [[ "$skip_git" != "1" ]]; then
    [[ -d "$dir/.git" ]] || die "Pas de dépôt Git dans $dir ; précisez SKIP_GIT=1 ou restaurez le dépôt."
  fi

  require_compose_version
  COMPOSE_FILES="$(detect_compose_files "$dir")"
  log "Install dir : $dir"
  log "Compose     : docker compose $COMPOSE_FILES"
  log "Branche     : $branch"
  ensure_mail_env "$dir"

  if [[ "$skip_backup" != "1" ]]; then
    ensure_backup_cron "$dir"
    backup_db "$dir"
  else
    warn "SKIP_BACKUP=1 — pas de dump DB."
  fi

  if [[ "$skip_git" != "1" ]]; then
    pull_code "$dir" "$branch" "$repo"
  else
    warn "SKIP_GIT=1 — pas de git pull."
  fi

  chmod_deploy_scripts "$dir"
  COMPOSE_FILES="$(detect_compose_files "$dir")"
  log "Compose (après pull) : docker compose $COMPOSE_FILES"
  ensure_backup_cron "$dir"

  rebuild_stack "$dir" "$with_build"
  wait_health
  post_deploy "$dir"
  refresh_helpers "$dir"
  wait_health
  print_summary "$dir"
}

main "$@"
