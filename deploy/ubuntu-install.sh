#!/usr/bin/env bash
# =========================================================================
# FIN_FLOW — déploiement interactif Ubuntu (22.04 / 24.04 / 26.04 LTS)
#
# Usage (depuis une machine Ubuntu, avec sudo) :
#   # Cloner d'abord FinFlow2.0 avec un accès GitHub autorisé, puis :
#   sudo bash deploy/ubuntu-install.sh
#
# Le script demande les noms DNS internes, les paramètres de secrets et le CIDR
# LAN, installe Docker/Nginx et démarre Compose en accès réseau local.
#
# Variante sans domaine (accès par IP, HTTP ou HTTPS) :
#   sudo bash deploy/ubuntu-install-ip.sh
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow
#
# Mise à jour d'une instance déjà déployée :
#   sudo bash deploy/ubuntu-update.sh
# =========================================================================
set -euo pipefail

REPO_URL_DEFAULT="${REPO_URL:-https://github.com/Bouma-J/FinFlow2.0.git}"
INSTALL_DIR_DEFAULT="${INSTALL_DIR_DEFAULT:-/opt/finflow}"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml"
DEPLOY_MODE="domain"
LAN_CIDR=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR=""

# Couleurs (si TTY)
if [[ -t 1 ]]; then
  C_INFO='\033[1;36m'
  C_OK='\033[1;32m'
  C_WARN='\033[1;33m'
  C_ERR='\033[1;31m'
  C_RST='\033[0m'
else
  C_INFO='' C_OK='' C_WARN='' C_ERR='' C_RST=''
fi

log()  { echo -e "${C_INFO}[INFO]${C_RST} $*"; }
ok()   { echo -e "${C_OK}[OK]${C_RST} $*"; }
warn() { echo -e "${C_WARN}[WARN]${C_RST} $*"; }
err()  { echo -e "${C_ERR}[ERR]${C_RST} $*" >&2; }
die()  { err "$*"; exit 1; }

installation_exit_notice() {
  local rc=$?
  if [[ "$rc" -ne 0 && -n "${INSTALL_DIR:-}" && -f "$INSTALL_DIR/.env" && -f "$INSTALL_DIR/.finflow-install-state" ]]; then
    echo "[WARN] Installation interrompue ; secrets conservés. Reprise : sudo bash $INSTALL_DIR/deploy/ubuntu-install.sh --resume $INSTALL_DIR" >&2
    echo "[INFO] Si une image ne peut pas être téléchargée, ajustez MINIO_IMAGE / MINIO_CLIENT_IMAGE dans $INSTALL_DIR/.env avant la reprise." >&2
  fi
}
trap installation_exit_notice EXIT

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Exécutez ce script en root : sudo bash deploy/ubuntu-install.sh"
  fi
}

prompt() {
  # prompt "Label" "default" → écrit dans REPLY
  local label="$1"
  local def="${2:-}"
  if [[ -n "$def" ]]; then
    read -r -p "$label [$def] : " REPLY || true
    REPLY="${REPLY:-$def}"
  else
    read -r -p "$label : " REPLY || true
  fi
}

prompt_secret() {
  local label="$1"
  local def="${2:-}"
  if [[ -n "$def" ]]; then
    read -r -s -p "$label [généré si vide] : " REPLY || true
    echo
    REPLY="${REPLY:-$def}"
  else
    read -r -s -p "$label : " REPLY || true
    echo
  fi
}

ask_yes_no() {
  local label="$1"
  local def="${2:-y}"
  local hint="y/N"
  [[ "$def" == "y" || "$def" == "Y" ]] && hint="Y/n"
  read -r -p "$label [$hint] : " REPLY || true
  REPLY="${REPLY:-$def}"
  [[ "$REPLY" =~ ^[yYoO] ]]
}

rand_secret() {
  openssl rand -base64 48 | tr -d '\n'
}

rand_fernet_key() {
  # Clé Fernet (32 octets, base64 url-safe) pour chiffrement SMTP / secrets au repos
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
}

validate_fernet_key() {
  printf '%s' "$1" | python3 -c '
import base64, re, sys
key = sys.stdin.read()
if not re.fullmatch(r"[A-Za-z0-9_-]{43}=", key):
    raise SystemExit(1)
try:
    raw = base64.urlsafe_b64decode(key)
except (ValueError, base64.binascii.Error):
    raise SystemExit(1)
raise SystemExit(0 if len(raw) == 32 else 1)
'
}

rand_password() {
  # Hex URL-safe pour .env, URLs PostgreSQL et MC_HOST MinIO.
  openssl rand -hex 18
  echo
}

escape_env() {
  # Les valeurs Compose single-quoted sont littérales, notamment les $ des mots de passe SMTP.
  printf '%s' "$1" | sed "s/'/\\\\'/g"
}
valid_image_ref() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._:/@-]*$ ]]; }

valid_hostname() {
  python3 - "$1" <<'PY' >/dev/null 2>&1
import re, sys
name = sys.argv[1].rstrip(".")
label = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
raise SystemExit(0 if len(name) <= 253 and re.fullmatch(label + r"(?:\." + label + r")+", name) else 1)
PY
}

env_line() {
  # env_line KEY value → KEY="escaped"
  local key="$1"
  local val="$2"
  printf "%s='%s'\n" "$key" "$(escape_env "$val")"
}

detect_ubuntu() {
  if [[ ! -f /etc/os-release ]]; then
    die "OS non détecté (/etc/os-release manquant)."
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "Ce script cible Ubuntu (détecté: ${ID:-inconnu})."
  case "${VERSION_ID:-}" in
    22.04|24.04|26.04) ok "Ubuntu ${VERSION_ID} LTS détecté." ;;
    *) warn "Ubuntu ${VERSION_ID:-?} — cibles LTS prévues : 22.04, 24.04 et 26.04." ;;
  esac
}

install_base_packages() {
  log "Mise à jour APT et paquets de base…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get upgrade -y
  local -a packages=(
    ca-certificates curl wget gnupg lsb-release \
    apt-transport-https software-properties-common \
    unzip jq htop net-tools openssl ufw fail2ban \
    dnsutils rsync openssh-server \
    nginx
  )
  [[ -n "${FINFLOW_LOCAL_SOURCE_DIR:-}" ]] || packages+=(git)
  apt-get install -y "${packages[@]}"
  ok "Paquets système installés."
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    local compose_version
    compose_version="$(docker compose version --short 2>/dev/null)"
    compose_version="${compose_version#v}"
    if dpkg --compare-versions "$compose_version" ge 2.24.4; then
      systemctl enable --now docker
      ok "Docker déjà installé : $(docker --version), Compose ${compose_version}"
      return
    fi
    warn "Docker Compose ${compose_version} est trop ancien ; installation de la version requise (≥ 2.24.4)."
  fi
  log "Installation Docker Engine + Compose plugin…"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  # shellcheck disable=SC1091
  . /etc/os-release
  local ubuntu_codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
  [[ -n "$ubuntu_codename" ]] || die "Nom de version Ubuntu introuvable pour le dépôt Docker."
  rm -f /etc/apt/sources.list.d/docker.list
  cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${ubuntu_codename}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  local compose_version
  compose_version="$(docker compose version --short 2>/dev/null)"
  compose_version="${compose_version#v}"
  dpkg --compare-versions "$compose_version" ge 2.24.4 \
    || die "Docker Compose ${compose_version:-inconnu} ne prend pas en charge !override (2.24.4 requis)."
  systemctl enable --now docker
  ok "Docker installé."
}

configure_ufw() {
  log "Restriction UFW au réseau local ${LAN_CIDR}…"
  bash "$INSTALL_DIR/deploy/lan-firewall.sh" apply "$LAN_CIDR" "22 80 443" \
    "$INSTALL_DIR/deploy/lan-firewall.sh"
}

write_install_state() {
  printf 'LAN_CIDR=%s\nTLS_MODE=\n' "$LAN_CIDR" > "$INSTALL_DIR/.finflow-install-state"
  chmod 600 "$INSTALL_DIR/.finflow-install-state"
}

resume_install() {
  local dir="${1:-$INSTALL_DIR_DEFAULT}" state_key state_value
  [[ -f "$dir/.env" && -f "$dir/.finflow-install-state" ]] \
    || die "Aucun état d'installation reprenable dans $dir."
  [[ -f "$dir/deploy/lan-firewall.sh" ]] \
    || die "Script LAN absent dans $dir ; actualisez le dépôt avant la reprise."
  INSTALL_DIR="$dir"
  LAN_CIDR="$(cat "$dir/.finflow-lan-cidr" 2>/dev/null || true)"
  if [[ -z "$LAN_CIDR" ]]; then
    while IFS='=' read -r state_key state_value; do
      [[ "$state_key" == "LAN_CIDR" ]] && LAN_CIDR="$state_value"
    done < "$dir/.finflow-install-state"
  fi
  LAN_CIDR="$(bash "$dir/deploy/lan-firewall.sh" validate-cidr "$LAN_CIDR")" \
    || die "CIDR LAN invalide dans l'état de reprise."
  readarray -t domains < <(python3 - "$dir/.env" <<'PY'
import sys
values = {}
for line in open(sys.argv[1], encoding="utf-8"):
    if "=" not in line or line.lstrip().startswith("#"):
        continue
    key, value = line.rstrip("\r\n").split("=", 1)
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    values[key] = value
app = values.get("FRONTEND_BASE_URL", "")
if "://" in app:
    app = app.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
mini = values.get("AWS_S3_CUSTOM_DOMAIN", "").split(":", 1)[0]
print(app)
print(mini)
PY
)
  APP_DOMAIN="${domains[0]:-}"
  MINIO_DOMAIN="${domains[1]:-}"
  valid_hostname "$APP_DOMAIN" || die "Domaine applicatif invalide dans $dir/.env"
  valid_hostname "$MINIO_DOMAIN" || die "Domaine MinIO invalide dans $dir/.env"

  log "Reprise de l'installation domaine dans $dir"
  install_docker
  systemctl enable --now nginx
  systemctl enable --now fail2ban 2>/dev/null || true
  write_helpers "$dir"
  configure_ufw
  write_nginx_http_only "$APP_DOMAIN" "$MINIO_DOMAIN"
  start_stack "$dir"
  post_deploy_commands "$dir"
  rm -f "$dir/.finflow-install-state"
  print_summary
}

prepare_install_dir() {
  local dir="$1"
  local repo="$2"
  local branch="$3"

  [[ ! -e "$dir/.env" ]] || die "Un .env existe déjà dans $dir. L'installateur refuse d'écraser les secrets ; utilisez ubuntu-update.sh."
  mkdir -p "$dir"
  if [[ -n "${FINFLOW_LOCAL_SOURCE_DIR:-}" ]]; then
    local source_dir="$(cd "$FINFLOW_LOCAL_SOURCE_DIR" && pwd)"
    [[ -f "$source_dir/docker-compose.yml" && -f "$source_dir/docker-compose.prod.yml" ]] \
      || die "Archive locale incomplète : docker-compose.yml ou docker-compose.prod.yml manquant."
    [[ -z "$(ls -A "$dir" 2>/dev/null || true)" ]] \
      || die "Le répertoire $dir n'est pas vide ; choisissez un répertoire neuf ou reprenez l'installation interrompue."
    cp -a "$source_dir/." "$dir/"
    log "Code copié depuis l'archive locale vers $dir (sans Git)."
  elif [[ -f "$dir/docker-compose.yml" && -f "$dir/docker-compose.prod.yml" ]]; then
    [[ -d "$dir/.git" ]] || die "Le projet présent dans $dir n'est pas un dépôt Git."
    log "Projet déjà présent dans $dir — synchronisation stricte de $branch…"
    if git -C "$dir" remote get-url origin >/dev/null 2>&1; then
      git -C "$dir" remote set-url origin "$repo"
    else
      git -C "$dir" remote add origin "$repo"
    fi
    git -C "$dir" fetch origin "$branch" --prune
    if git -C "$dir" show-ref --verify --quiet "refs/heads/$branch"; then
      git -C "$dir" checkout "$branch"
    else
      git -C "$dir" checkout --track -b "$branch" "origin/$branch"
    fi
    git -C "$dir" pull --ff-only origin "$branch"
  else
    if [[ -n "$(ls -A "$dir" 2>/dev/null || true)" ]]; then
      die "Le répertoire $dir n'est pas vide et ne contient pas FinFlow."
    fi
    log "Clone de $repo → $dir (branche $branch)…"
    git clone --branch "$branch" "$repo" "$dir"
  fi

  # Si le script est lancé depuis une copie locale (dev), synchroniser optionnel
  SCRIPT_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd 2>/dev/null || true)"
  if [[ -n "${SCRIPT_SRC}" && -f "${SCRIPT_SRC}/docker-compose.prod.yml" \
        && "${SCRIPT_SRC}" != "$dir" && "${USE_LOCAL_COPY:-0}" == "1" ]]; then
    log "Copie locale demandée depuis ${SCRIPT_SRC}…"
    rsync -a --exclude '.git' --exclude '.env' --exclude 'node_modules' --exclude '.venv' \
      "${SCRIPT_SRC}/" "$dir/"
  fi

  ok "Code prêt dans $dir"
}

write_env_file() {
  local dir="$1"
  local env_file="$dir/.env"
  [[ ! -e "$env_file" ]] || die "Refus d'écraser le fichier de secrets existant : $env_file"

  {
    echo "# Généré par deploy/ubuntu-install.sh — $(date -Iseconds)"
    echo "# Ne pas committer ce fichier."
    echo
    env_line DJANGO_SECRET_KEY "$DJANGO_SECRET_KEY"
    echo 'DJANGO_DEBUG="False"'
    env_line DJANGO_ALLOWED_HOSTS "${APP_DOMAIN},localhost,127.0.0.1,backend"
    echo 'DJANGO_SECURE_SSL_REDIRECT="False"'
    env_line DJANGO_CORS_ALLOWED_ORIGINS "http://${APP_DOMAIN}"
    env_line FRONTEND_BASE_URL "http://${APP_DOMAIN}"
    env_line POSTGRES_IMAGE "${POSTGRES_IMAGE:-postgres:16-alpine}"
    env_line REDIS_IMAGE "${REDIS_IMAGE:-redis:7-alpine}"
    env_line MINIO_IMAGE "$MINIO_IMAGE"
    env_line MINIO_CLIENT_IMAGE "$MINIO_CLIENT_IMAGE"
    env_line PYTHON_BASE_IMAGE "${PYTHON_BASE_IMAGE:-python:3.12-slim}"
    env_line NODE_BUILD_IMAGE "${NODE_BUILD_IMAGE:-node:24-alpine}"
    env_line NGINX_RUNTIME_IMAGE "${NGINX_RUNTIME_IMAGE:-nginx:1.30-alpine}"
    echo 'SEED_DEMO="0"'
    echo 'SMTP_SSL_VERIFY="1"'
    env_line FIELD_ENCRYPTION_KEY "$FIELD_ENCRYPTION_KEY"
    echo
    env_line POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
    echo
    env_line MINIO_ROOT_USER "$MINIO_ROOT_USER"
    env_line MINIO_ROOT_PASSWORD "$MINIO_ROOT_PASSWORD"
    env_line AWS_S3_CUSTOM_DOMAIN "$MINIO_DOMAIN"
    echo 'AWS_S3_URL_PROTOCOL="http:"'
    echo 'AWS_STORAGE_BUCKET_NAME="finflow-documents"'
    echo
    # Pile e-mail : backend SMTP + worker Celery (alertes async) via Compose
    env_line EMAIL_BACKEND "$EMAIL_BACKEND"
    env_line EMAIL_HOST "$EMAIL_HOST"
    env_line EMAIL_PORT "$EMAIL_PORT"
    env_line EMAIL_USE_TLS "$EMAIL_USE_TLS"
    env_line EMAIL_USE_SSL "$EMAIL_USE_SSL"
    env_line EMAIL_HOST_USER "$EMAIL_HOST_USER"
    env_line EMAIL_HOST_PASSWORD "$EMAIL_HOST_PASSWORD"
    env_line DEFAULT_FROM_EMAIL "$DEFAULT_FROM_EMAIL"
  } > "$env_file"

  chmod 600 "$env_file"
  ok "Fichier .env écrit (${env_file})."
}

write_nginx_http_only() {
  local app_domain="$1"
  local minio_domain="$2"

  cat > /etc/nginx/sites-available/finflow <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${app_domain};

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
        client_max_body_size 25m;
    }
}
EOF

  cat > /etc/nginx/sites-available/finflow-minio <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${minio_domain};

    ignore_invalid_headers off;
    proxy_buffering off;
    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_connect_timeout 300;
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
EOF

  ln -sf /etc/nginx/sites-available/finflow /etc/nginx/sites-enabled/finflow
  ln -sf /etc/nginx/sites-available/finflow-minio /etc/nginx/sites-enabled/finflow-minio
  rm -f /etc/nginx/sites-enabled/default
  mkdir -p /var/www/html
  nginx -t
  systemctl enable nginx
  systemctl reload nginx
  ok "Nginx (HTTP) configuré pour ${app_domain} et ${minio_domain}."
}

start_stack() {
  local dir="$1"
  cd "$dir"
  log "Build & démarrage Docker Compose (prod)…"
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES pull
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES up -d --build
  ok "Stack démarrée."

  log "Attente health API (max ~3 min)…"
  local i
  for i in $(seq 1 36); do
    if curl -fsS http://127.0.0.1:8080/api/v1/health/ >/dev/null 2>&1; then
      ok "API prête : http://127.0.0.1:8080/api/v1/health/"
      return
    fi
    sleep 5
  done
  docker compose $COMPOSE_FILES logs --tail=100 backend db minio frontend || true
  die "L'API n'est pas saine après le démarrage. Corrigez les logs avant de poursuivre."
}

write_helpers() {
  local dir="$1"
  mkdir -p "$dir/scripts"

  cat > "$dir/scripts/finflow" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$dir"
if [[ -f "$dir/deploy/compose-files.sh" ]]; then
  exec docker compose \$(bash "$dir/deploy/compose-files.sh" "$dir") "\$@"
fi
exec docker compose $COMPOSE_FILES "\$@"
EOF
  chmod +x "$dir/scripts/finflow"

  if [[ -f "$dir/deploy/backup/wire-install.sh" ]]; then
    bash "$dir/deploy/backup/wire-install.sh" "$dir" \
      || die "Cron de sauvegarde non posé (/var/backups/finflow)."
  else
    die "deploy/backup/wire-install.sh manquant — sauvegarde automatique obligatoire."
  fi

  echo "$DEPLOY_MODE" > "$dir/.finflow-deploy-mode"
  chmod 644 "$dir/.finflow-deploy-mode"

  if [[ -f "$dir/deploy/ubuntu-update.sh" ]]; then
    chmod +x "$dir/deploy/ubuntu-update.sh"
    ln -sf "$dir/deploy/ubuntu-update.sh" "$dir/scripts/update.sh"
    ln -sf "$dir/deploy/ubuntu-update.sh" /usr/local/bin/finflow-update
  fi

  if [[ ! -e /usr/local/bin/finflow ]]; then
    ln -sf "$dir/scripts/finflow" /usr/local/bin/finflow
  else
    ln -sf "$dir/scripts/finflow" /usr/local/bin/finflow
  fi
  ok "Helpers : finflow, finflow-update, $dir/scripts/backup.sh"
}

post_deploy_commands() {
  local dir="$1"
  cd "$dir"
  log "Post-déploiement : migrations, rôles, bootstrap filiales…"
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py migrate --noinput
  ok "Migrations OK."

  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py sync_role_packs
  ok "Packs de rôles synchronisés."

  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py bootstrap_all_tenants
  ok "Filiales bootstrapées (circuits ML / Dation / Formalisation)."

  log "Vérification pile e-mail (cryptography, backend SMTP, worker)…"
  # shellcheck disable=SC2086
  if docker compose $COMPOSE_FILES exec -T backend \
    python manage.py shell -c "
from django.conf import settings
from cryptography.fernet import Fernet  # noqa: F401
from apps.common.secret_crypto import encrypt_str, decrypt_str
assert decrypt_str(encrypt_str('install-check')) == 'install-check'
backend = settings.EMAIL_BACKEND or ''
assert 'smtp' in backend.lower(), backend
print('OK EMAIL_BACKEND=smtp')
print('OK SMTP_SSL_VERIFY=', getattr(settings, 'SMTP_SSL_VERIFY', None))
print('OK FIELD_ENCRYPTION=', 'set' if (getattr(settings, 'FIELD_ENCRYPTION_KEY', '') or '').strip() else 'derived')
print('OK DEFAULT_FROM_EMAIL=', settings.DEFAULT_FROM_EMAIL)
"
  then
    ok "Pile crypto / settings e-mail OK."
  else
    warn "Vérification e-mail incomplète — contrôlez les logs backend."
  fi

  # shellcheck disable=SC2086
  if docker compose $COMPOSE_FILES ps --status running 2>/dev/null | grep -qE '[[:space:]]worker[[:space:]]'; then
    ok "Worker Celery actif (envoi async des alertes)."
  else
    warn "Worker Celery non détecté — les alertes e-mail async ne partiront pas."
  fi
}

print_summary() {
  local scheme="http"
  cat <<EOF

${C_OK}═══════════════════════════════════════════════════════════${C_RST}
${C_OK} FIN_FLOW — déploiement terminé${C_RST}
${C_OK}═══════════════════════════════════════════════════════════${C_RST}

  Application : ${scheme}://${APP_DOMAIN}
  API health  : ${scheme}://${APP_DOMAIN}/api/v1/health/
  MinIO       : ${scheme}://${MINIO_DOMAIN}
  Répertoire  : ${INSTALL_DIR}
  Compose     : finflow ps   |   finflow logs -f backend

  Prochaines étapes :
    1. Créer un super-utilisateur :
         cd ${INSTALL_DIR}
         finflow exec backend python manage.py createsuperuser
    2. Vérifier bootstrap (si filiales déjà créées) :
         finflow exec backend python manage.py bootstrap_all_tenants
    3. E-mail : Administration → Alertes e-mail (SMTP filiale) + bouton Test
       (repli global déjà dans .env si configuré à l'install)
    4. Sauvegardes auto : cron 02:30 → /var/backups/finflow/snapshots (hors projet).
       Épreuve : ${INSTALL_DIR}/scripts/restore.sh --target drill --snapshot <dir>
       Sinistre : … --target live --confirm=RESTORE
    5. Mises à jour ultérieures :
         sudo finflow-update
         # ou : sudo bash ${INSTALL_DIR}/deploy/ubuntu-update.sh

  Conservez précieusement le fichier ${INSTALL_DIR}/.env (secrets,
  dont FIELD_ENCRYPTION_KEY — ne pas régénérer après sauvegarde de mots de passe SMTP).
  Copiez aussi /root/.finflow-backup-pass dans un coffre sécurisé hors serveur.

EOF
}

collect_inputs() {
  echo
  echo "========== Paramètres de déploiement FIN_FLOW =========="
  echo

  if [[ -n "${FINFLOW_LOCAL_INSTALL_DIR:-}" ]]; then
    INSTALL_DIR="$FINFLOW_LOCAL_INSTALL_DIR"
    echo "Répertoire d'installation : $INSTALL_DIR"
  else
    prompt "Répertoire d'installation" "$INSTALL_DIR_DEFAULT"
    INSTALL_DIR="$REPLY"
  fi

  if [[ -n "${FINFLOW_LOCAL_SOURCE_DIR:-}" ]]; then
    REPO_URL="archive locale"
    GIT_BRANCH="sans Git"
    echo "Source du code : archive locale (sans Git)"
  else
    prompt "URL du dépôt Git" "$REPO_URL_DEFAULT"
    REPO_URL="$REPLY"
    prompt "Branche Git" "${GIT_BRANCH:-main}"
    GIT_BRANCH="$REPLY"
  fi

  prompt "Domaine applicatif (ex. finflow.exemple.tld)" ""
  APP_DOMAIN="$REPLY"
  valid_hostname "$APP_DOMAIN" || die "Nom DNS applicatif invalide."

  DEFAULT_MINIO="minio.${APP_DOMAIN}"
  if [[ "$APP_DOMAIN" == finflow.* ]]; then
    DEFAULT_MINIO="minio.${APP_DOMAIN#finflow.}"
  fi
  prompt "Domaine MinIO (ex. minio.exemple.tld)" "$DEFAULT_MINIO"
  MINIO_DOMAIN="$REPLY"
  valid_hostname "$MINIO_DOMAIN" || die "Nom DNS MinIO invalide."

  prompt "CIDR du réseau local autorisé" "$(bash "$SCRIPT_DIR/lan-firewall.sh" detect-default-cidr)"
  LAN_CIDR="$(bash "$SCRIPT_DIR/lan-firewall.sh" validate-cidr "$REPLY")" \
    || die "CIDR LAN invalide : $REPLY"

  prompt "Image MinIO accessible depuis ce serveur" "${MINIO_IMAGE:-cgr.dev/chainguard/minio:latest}"
  MINIO_IMAGE="$REPLY"
  valid_image_ref "$MINIO_IMAGE" || die "Référence d'image MinIO invalide."
  prompt "Image du client MinIO (mc) accessible depuis ce serveur" "${MINIO_CLIENT_IMAGE:-cgr.dev/chainguard/minio-client:latest}"
  MINIO_CLIENT_IMAGE="$REPLY"
  valid_image_ref "$MINIO_CLIENT_IMAGE" || die "Référence d'image minio-client invalide."

  GEN_PG="$(rand_password | tr -d '\n')"
  prompt_secret "Mot de passe PostgreSQL (lettres, chiffres, . _ - ~)" "$GEN_PG"
  POSTGRES_PASSWORD="$REPLY"
  [[ ${#POSTGRES_PASSWORD} -ge 12 ]] || die "Mot de passe PostgreSQL trop court (≥ 12)."
  [[ "$POSTGRES_PASSWORD" =~ ^[A-Za-z0-9._~-]+$ ]] || die "Mot de passe PostgreSQL : utilisez uniquement lettres, chiffres, point, tiret, underscore ou tilde (URL PostgreSQL)."

  prompt "Utilisateur MinIO (root)" "finflow_minio_admin"
  MINIO_ROOT_USER="$REPLY"
  [[ "$MINIO_ROOT_USER" =~ ^[A-Za-z0-9_-]{3,20}$ ]] || die "Utilisateur MinIO : 3 à 20 caractères alphanumériques, underscore ou tiret."
  GEN_MINIO="$(rand_password | tr -d '\n')"
  prompt_secret "Mot de passe MinIO (lettres, chiffres, . _ - ~)" "$GEN_MINIO"
  MINIO_ROOT_PASSWORD="$REPLY"
  [[ ${#MINIO_ROOT_PASSWORD} -ge 12 ]] || die "Mot de passe MinIO trop court (≥ 12)."
  [[ "$MINIO_ROOT_PASSWORD" =~ ^[A-Za-z0-9._~-]+$ ]] || die "Mot de passe MinIO : utilisez uniquement lettres, chiffres, point, tiret, underscore ou tilde."

  GEN_DJANGO="$(rand_secret)"
  prompt_secret "DJANGO_SECRET_KEY" "$GEN_DJANGO"
  DJANGO_SECRET_KEY="$REPLY"
  [[ ${#DJANGO_SECRET_KEY} -ge 40 ]] || die "DJANGO_SECRET_KEY doit contenir au moins 40 caractères."
  case "${DJANGO_SECRET_KEY,,}" in
    *change-me*|*insecure*|secret|changeme) die "DJANGO_SECRET_KEY est une valeur interdite en production." ;;
  esac

  GEN_FERNET="$(rand_fernet_key)"
  prompt_secret "FIELD_ENCRYPTION_KEY (chiffrement mots de passe SMTP filiale)" "$GEN_FERNET"
  FIELD_ENCRYPTION_KEY="$REPLY"
  validate_fernet_key "$FIELD_ENCRYPTION_KEY" || die "FIELD_ENCRYPTION_KEY doit être une clé Fernet valide (32 octets encodés en base64 URL-safe)."

  echo
  SMTP_GLOBAL_CONFIGURED=0
  if ask_yes_no "Configurer un SMTP global maintenant ? (sinon UI filiale Admin → Alertes)" "y"; then
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
    prompt "SMTP host" "smtp.gmail.com"
    EMAIL_HOST="$REPLY"
    prompt "SMTP port" "587"
    EMAIL_PORT="$REPLY"
    EMAIL_USE_TLS="True"
    EMAIL_USE_SSL="False"
    prompt "SMTP user" ""
    EMAIL_HOST_USER="$REPLY"
    prompt_secret "SMTP password / app password" ""
    EMAIL_HOST_PASSWORD="$REPLY"
    prompt "DEFAULT_FROM_EMAIL" "FIN_FLOW <noreply@${APP_DOMAIN}>"
    DEFAULT_FROM_EMAIL="$REPLY"
    [[ -n "$EMAIL_HOST" ]] || die "SMTP host obligatoire."
    [[ -n "$EMAIL_HOST_USER" ]] || die "SMTP user obligatoire."
    [[ -n "$EMAIL_HOST_PASSWORD" ]] || die "SMTP password obligatoire."
    SMTP_GLOBAL_CONFIGURED=1
  else
    # Toujours le backend SMTP en prod : sans credentials = repli UI filiale
    # (évite le backend console qui fait croire à un envoi réussi).
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST=""
    EMAIL_PORT="587"
    EMAIL_USE_TLS="True"
    EMAIL_USE_SSL="False"
    EMAIL_HOST_USER=""
    EMAIL_HOST_PASSWORD=""
    DEFAULT_FROM_EMAIL="FIN_FLOW <noreply@${APP_DOMAIN}>"
    warn "SMTP global vide — configurez chaque filiale dans Administration → Alertes e-mail."
  fi

  echo
  warn "Mode LAN uniquement : le challenge HTTP public Let's Encrypt n'est pas activé. Configurez un certificat interne si HTTPS est requis."

  EXPOSE_MINIO_PORT=0
  # Avec sous-domaine HTTPS, pas besoin d'ouvrir 9000 publiquement

  echo
  echo "---------- Récapitulatif ----------"
  echo "  Install dir : $INSTALL_DIR"
  echo "  Repo/branch : $REPO_URL @ $GIT_BRANCH"
  echo "  App domain  : $APP_DOMAIN"
  echo "  MinIO domain: $MINIO_DOMAIN"
  echo "  DB user     : finflow"
  echo "  MinIO user  : $MINIO_ROOT_USER"
  echo "  SMTP global : $([[ $SMTP_GLOBAL_CONFIGURED -eq 1 ]] && echo "oui ($EMAIL_HOST)" || echo "non — UI filiale")"
  echo "  E-mail pile : SMTP backend + SSL verify + Fernet + worker Celery"
  echo "  Réseau LAN  : $LAN_CIDR (ports 22/80/443 limités à cette plage)"
  echo "  TLS         : certificat interne à provisionner si HTTPS est requis"
  echo "----------------------------------"
  ask_yes_no "Lancer le déploiement ?" "y" || die "Annulé."
}

main() {
  need_root
  detect_ubuntu

  if [[ "${1:-}" == "--resume" ]]; then
    shift
    resume_install "${1:-$INSTALL_DIR_DEFAULT}"
    return
  fi

  echo
  echo "FIN_FLOW — installateur Ubuntu interactif"
  echo "Guide : documentation/13-guide-deploiement-ubuntu.md"
  echo

  collect_inputs
  [[ ! -e "$INSTALL_DIR/.env" ]] || die "Une installation existe déjà dans $INSTALL_DIR. Utilisez deploy/ubuntu-update.sh pour la mettre à jour."
  install_base_packages
  install_docker
  systemctl enable --now fail2ban || true

  prepare_install_dir "$INSTALL_DIR" "$REPO_URL" "$GIT_BRANCH"
  write_env_file "$INSTALL_DIR"
  printf '%s\n' "$LAN_CIDR" > "$INSTALL_DIR/.finflow-lan-cidr"
  chmod 644 "$INSTALL_DIR/.finflow-lan-cidr"
  write_install_state
  write_helpers "$INSTALL_DIR"
  configure_ufw
  write_nginx_http_only "$APP_DOMAIN" "$MINIO_DOMAIN"
  start_stack "$INSTALL_DIR"

  warn "Application disponible en HTTP sur le LAN : http://${APP_DOMAIN}. Provisionnez un certificat de l'autorité interne avant d'activer HTTPS."

  # Sync post-déploiement (migrations, rôles, circuits)
  post_deploy_commands "$INSTALL_DIR"
  rm -f "$INSTALL_DIR/.finflow-install-state"

  print_summary
}

main "$@"
