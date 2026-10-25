#!/usr/bin/env bash
# =========================================================================
# FIN_FLOW — déploiement Ubuntu par adresse IP (sans nom de domaine)
#
# Cible principale : réseau interne (IP privée, sans DNS).
# HTTP par défaut. HTTPS optionnel :
#   • IP privée    → certificat auto-signé, HSTS désactivé (cas prévu)
#   • IP publique  → Let's Encrypt (certificat IP, ~6 jours) + HSTS 7 jours
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow --self-signed
#
# Usage :
#   curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-install-ip.sh | sudo bash
#   # ou dépôt déjà cloné :
#   sudo bash deploy/ubuntu-install-ip.sh
#
# Variante avec domaines + TLS :
#   sudo bash deploy/ubuntu-install.sh
#
# Mise à jour d'une instance déjà déployée :
#   sudo bash deploy/ubuntu-update.sh
# =========================================================================
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/Bouma-J/FinFlow.git"
INSTALL_DIR_DEFAULT="/opt/finflow"
COMPOSE_FILES="-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml"
DEPLOY_MODE="ip"
ENABLE_TLS=0
TLS_MODE=""
LETSENCRYPT_EMAIL=""

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

need_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    die "Exécutez ce script en root : sudo bash deploy/ubuntu-install-ip.sh"
  fi
}

prompt() {
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

rand_password() {
  openssl rand -base64 32 | tr -d '/+=' | head -c 28
  echo
}

escape_env() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

env_line() {
  local key="$1"
  local val="$2"
  printf '%s="%s"\n' "$key" "$(escape_env "$val")"
}

detect_default_ip() {
  local ip=""
  ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '/src/ {for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' || true)"
  if [[ -z "$ip" ]]; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  printf '%s' "${ip:-}"
}

is_ipv4() {
  [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
}

is_private_ip() {
  [[ "$1" =~ ^10\. ]] || [[ "$1" =~ ^192\.168\. ]] || [[ "$1" =~ ^127\. ]] \
    || [[ "$1" =~ ^169\.254\. ]] \
    || [[ "$1" =~ ^172\.(1[6-9]|2[0-9]|3[01])\. ]]
}

detect_ubuntu() {
  if [[ ! -f /etc/os-release ]]; then
    die "OS non détecté (/etc/os-release manquant)."
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  [[ "${ID:-}" == "ubuntu" ]] || die "Ce script cible Ubuntu (détecté: ${ID:-inconnu})."
  case "${VERSION_ID:-}" in
    22.04|24.04) ok "Ubuntu ${VERSION_ID} détecté." ;;
    *) warn "Ubuntu ${VERSION_ID:-?} — testé sur 22.04 / 24.04 LTS." ;;
  esac
}

install_base_packages() {
  log "Mise à jour APT et paquets de base…"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get upgrade -y
  apt-get install -y \
    ca-certificates curl wget gnupg lsb-release \
    apt-transport-https software-properties-common \
    git unzip jq htop net-tools openssl ufw fail2ban \
    dnsutils rsync openssh-server \
    nginx
  ok "Paquets système installés (Certbot uniquement si HTTPS Let's Encrypt)."
}

install_docker() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "Docker déjà installé : $(docker --version)"
    return
  fi
  log "Installation Docker Engine + Compose plugin…"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  # shellcheck disable=SC1091
  . /etc/os-release
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
  ok "Docker installé."
}

configure_ufw() {
  log "Configuration UFW (SSH / 80 / 9000 MinIO${ENABLE_TLS:+ / 443})…"
  ufw default deny incoming
  ufw default allow outgoing
  if ufw app list 2>/dev/null | grep -qx 'OpenSSH'; then
    ufw allow OpenSSH
  else
    warn "Profil UFW OpenSSH introuvable — ouverture du port 22/tcp."
    ufw allow 22/tcp
  fi
  ufw allow 80/tcp
  ufw allow 9000/tcp
  if [[ "${ENABLE_TLS:-0}" -eq 1 ]]; then
    ufw allow 443/tcp
  fi
  ufw --force enable
  ufw status verbose || true
  ok "Pare-feu UFW actif."
}

prepare_install_dir() {
  local dir="$1"
  local repo="$2"
  local branch="$3"

  mkdir -p "$dir"
  if [[ -f "$dir/docker-compose.yml" && -f "$dir/docker-compose.prod.yml" ]]; then
    log "Projet déjà présent dans $dir — git pull…"
    git -C "$dir" fetch --all --prune || true
    git -C "$dir" checkout "$branch" || true
    git -C "$dir" pull --ff-only origin "$branch" || warn "git pull échoué (déploiement local ?)."
  else
    if [[ -n "$(ls -A "$dir" 2>/dev/null || true)" ]]; then
      die "Le répertoire $dir n'est pas vide et ne contient pas FinFlow."
    fi
    log "Clone de $repo → $dir (branche $branch)…"
    git clone --branch "$branch" "$repo" "$dir"
  fi

  if [[ ! -f "$dir/docker-compose.ip.yml" ]]; then
    die "docker-compose.ip.yml manquant — tirez la dernière version du dépôt (git pull)."
  fi
  ok "Code prêt dans $dir"
}

write_env_file() {
  local dir="$1"
  local env_file="$dir/.env"
  local base_url="http://${APP_IP}"

  {
    echo "# Généré par deploy/ubuntu-install-ip.sh — $(date -Iseconds)"
    echo "# Mode IP — ne pas committer. HTTPS via deploy/tls-ip/enable-ip-tls.sh"
    echo
    env_line DJANGO_SECRET_KEY "$DJANGO_SECRET_KEY"
    echo 'DJANGO_DEBUG="False"'
    env_line DJANGO_ALLOWED_HOSTS "${APP_IP},localhost,127.0.0.1,backend"
    echo 'DJANGO_SECURE_SSL_REDIRECT="False"'
    echo 'DJANGO_SECURE_HSTS_SECONDS="0"'
    echo 'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS="False"'
    echo 'DJANGO_SECURE_HSTS_PRELOAD="False"'
    env_line DJANGO_CORS_ALLOWED_ORIGINS "$base_url"
    env_line FRONTEND_BASE_URL "$base_url"
    env_line FINFLOW_PUBLIC_IP "$APP_IP"
    echo 'SEED_DEMO="0"'
    echo 'SMTP_SSL_VERIFY="1"'
    env_line FIELD_ENCRYPTION_KEY "$FIELD_ENCRYPTION_KEY"
    echo
    env_line POSTGRES_PASSWORD "$POSTGRES_PASSWORD"
    echo
    env_line MINIO_ROOT_USER "$MINIO_ROOT_USER"
    env_line MINIO_ROOT_PASSWORD "$MINIO_ROOT_PASSWORD"
    env_line AWS_S3_CUSTOM_DOMAIN "${APP_IP}:9000"
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

write_nginx_ip() {
  local app_ip="$1"

  # Retirer les vhosts domaine/TLS éventuels d'une install précédente
  rm -f /etc/nginx/sites-enabled/finflow-minio
  rm -f /etc/nginx/sites-enabled/default

  cat > /etc/nginx/sites-available/finflow <<EOF
# FIN_FLOW — accès par IP (généré par ubuntu-install-ip.sh)
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${app_ip} _;

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

  ln -sf /etc/nginx/sites-available/finflow /etc/nginx/sites-enabled/finflow
  nginx -t
  systemctl enable nginx
  systemctl reload nginx
  ok "Nginx HTTP configuré pour http://${app_ip}/"
}

start_stack() {
  local dir="$1"
  cd "$dir"
  log "Build & démarrage Docker Compose (prod + IP)…"
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES pull || true
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
  warn "Health check encore en échec — vérifiez : docker compose $COMPOSE_FILES logs backend"
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

  ln -sf "$dir/scripts/finflow" /usr/local/bin/finflow
  ok "Helpers : finflow, finflow-update, $dir/scripts/backup.sh"
}

post_deploy_commands() {
  local dir="$1"
  cd "$dir"
  log "Post-déploiement : migrations, rôles, bootstrap filiales…"
  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py migrate --noinput \
    && ok "Migrations OK." \
    || warn "migrate à relancer."

  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py sync_role_packs \
    && ok "Packs de rôles synchronisés." \
    || warn "sync_role_packs à relancer plus tard."

  # shellcheck disable=SC2086
  docker compose $COMPOSE_FILES exec -T backend \
    python manage.py bootstrap_all_tenants \
    && ok "Filiales bootstrapées (circuits ML / Dation / Formalisation)." \
    || warn "bootstrap_all_tenants : aucune filiale encore, ou à relancer après création."

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
  local title="déploiement IP / HTTP terminé"
  local extra_tls=""
  if [[ "${ENABLE_TLS:-0}" -eq 1 ]]; then
    scheme="https"
    title="déploiement IP / HTTPS terminé"
    if [[ "${TLS_MODE}" == "le" ]]; then
      extra_tls="  TLS          : Let's Encrypt (IP, ~6 jours) · HSTS 7 jours
  Renouveler   : sudo certbot certificates
"
    else
      extra_tls="  TLS          : certificat auto-signé (avertissement navigateur) · HSTS off
"
    fi
  fi
  cat <<EOF

${C_OK}═══════════════════════════════════════════════════════════${C_RST}
${C_OK} FIN_FLOW — ${title}${C_RST}
${C_OK}═══════════════════════════════════════════════════════════${C_RST}

  Application : ${scheme}://${APP_IP}/
  API health  : ${scheme}://${APP_IP}/api/v1/health/
  MinIO API   : ${scheme}://${APP_IP}:9000/
  Répertoire  : ${INSTALL_DIR}
  Compose     : finflow ps   |   finflow logs -f backend
${extra_tls}
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

  HTTPS plus tard (instance déjà en HTTP) :
    sudo bash ${INSTALL_DIR}/deploy/tls-ip/enable-ip-tls.sh ${INSTALL_DIR}
    # IP privée : ajouter --self-signed
    # IP publique : --lets-encrypt --email vous@exemple.tld

  Passage ultérieur en domaines + TLS :
    sudo bash ${INSTALL_DIR}/deploy/ubuntu-install.sh

EOF
}

collect_inputs() {
  echo
  echo "========== Déploiement FIN_FLOW par IP =========="
  echo "  Sans domaine DNS · HTTP ou HTTPS (certificat IP / auto-signé)"
  echo

  prompt "Répertoire d'installation" "$INSTALL_DIR_DEFAULT"
  INSTALL_DIR="$REPLY"

  prompt "URL du dépôt Git" "$REPO_URL_DEFAULT"
  REPO_URL="$REPLY"

  prompt "Branche Git" "main"
  GIT_BRANCH="$REPLY"

  DEFAULT_IP="$(detect_default_ip)"
  prompt "Adresse IP d'accès (IPv4)" "${DEFAULT_IP}"
  APP_IP="$REPLY"
  is_ipv4 "$APP_IP" || die "Adresse IPv4 invalide : ${APP_IP}"

  GEN_PG="$(rand_password | tr -d '\n')"
  prompt_secret "Mot de passe PostgreSQL (utilisateur finflow)" "$GEN_PG"
  POSTGRES_PASSWORD="$REPLY"
  [[ ${#POSTGRES_PASSWORD} -ge 12 ]] || die "Mot de passe PostgreSQL trop court (≥ 12)."

  prompt "Utilisateur MinIO (root)" "finflow_minio_admin"
  MINIO_ROOT_USER="$REPLY"
  GEN_MINIO="$(rand_password | tr -d '\n')"
  prompt_secret "Mot de passe MinIO" "$GEN_MINIO"
  MINIO_ROOT_PASSWORD="$REPLY"
  [[ ${#MINIO_ROOT_PASSWORD} -ge 12 ]] || die "Mot de passe MinIO trop court (≥ 12)."

  GEN_DJANGO="$(rand_secret)"
  prompt_secret "DJANGO_SECRET_KEY" "$GEN_DJANGO"
  DJANGO_SECRET_KEY="$REPLY"

  GEN_FERNET="$(rand_fernet_key)"
  prompt_secret "FIELD_ENCRYPTION_KEY (chiffrement mots de passe SMTP filiale)" "$GEN_FERNET"
  FIELD_ENCRYPTION_KEY="$REPLY"
  [[ -n "$FIELD_ENCRYPTION_KEY" ]] || die "FIELD_ENCRYPTION_KEY obligatoire."

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
    prompt "DEFAULT_FROM_EMAIL" "FIN_FLOW <noreply@${APP_IP}>"
    DEFAULT_FROM_EMAIL="$REPLY"
    [[ -n "$EMAIL_HOST" ]] || die "SMTP host obligatoire."
    [[ -n "$EMAIL_HOST_USER" ]] || die "SMTP user obligatoire."
    [[ -n "$EMAIL_HOST_PASSWORD" ]] || die "SMTP password obligatoire."
    SMTP_GLOBAL_CONFIGURED=1
  else
    # Toujours le backend SMTP en prod : sans credentials = repli UI filiale
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST=""
    EMAIL_PORT="587"
    EMAIL_USE_TLS="True"
    EMAIL_USE_SSL="False"
    EMAIL_HOST_USER=""
    EMAIL_HOST_PASSWORD=""
    DEFAULT_FROM_EMAIL="FIN_FLOW <noreply@${APP_IP}>"
    warn "SMTP global vide — configurez chaque filiale dans Administration → Alertes e-mail."
  fi

  echo
  ENABLE_TLS=0
  TLS_MODE=""
  LETSENCRYPT_EMAIL=""
  if is_private_ip "$APP_IP"; then
    if ask_yes_no "Activer HTTPS (certificat auto-signé, avertissement navigateur, sans HSTS) ?" "y"; then
      ENABLE_TLS=1
      TLS_MODE="selfsigned"
    fi
  else
    if ask_yes_no "Activer HTTPS (Let's Encrypt sur l'IP, HSTS 7 jours) ?" "y"; then
      ENABLE_TLS=1
      TLS_MODE="le"
      prompt "E-mail Let's Encrypt (avis d'expiration)" ""
      LETSENCRYPT_EMAIL="$REPLY"
      [[ -n "$LETSENCRYPT_EMAIL" ]] || die "E-mail Let's Encrypt obligatoire."
    fi
  fi

  echo
  SETUP_UFW=0
  ask_yes_no "Configurer UFW (SSH / 80 / 9000${ENABLE_TLS:+ / 443}) ?" "y" && SETUP_UFW=1

  local url_scheme="http"
  local tls_label="HTTP (sans TLS)"
  [[ "$ENABLE_TLS" -eq 1 ]] && url_scheme="https"
  [[ "$TLS_MODE" == "le" ]] && tls_label="HTTPS Let's Encrypt + HSTS 7j"
  [[ "$TLS_MODE" == "selfsigned" ]] && tls_label="HTTPS auto-signé (HSTS off)"

  echo
  echo "---------- Récapitulatif ----------"
  echo "  Mode         : IP / ${tls_label}"
  echo "  Install dir  : $INSTALL_DIR"
  echo "  Repo/branch  : $REPO_URL @ $GIT_BRANCH"
  echo "  IP d'accès   : $APP_IP"
  echo "  URL app      : ${url_scheme}://${APP_IP}/"
  echo "  MinIO        : ${url_scheme}://${APP_IP}:9000/"
  echo "  DB user      : finflow"
  echo "  MinIO user   : $MINIO_ROOT_USER"
  echo "  SMTP global  : $([[ $SMTP_GLOBAL_CONFIGURED -eq 1 ]] && echo "oui ($EMAIL_HOST)" || echo "non — UI filiale")"
  echo "  E-mail pile  : SMTP backend + SSL verify + Fernet + worker Celery"
  echo "  UFW          : $([[ $SETUP_UFW -eq 1 ]] && echo oui || echo non)"
  echo "----------------------------------"
  ask_yes_no "Lancer le déploiement ?" "y" || die "Annulé."
}

main() {
  need_root
  detect_ubuntu

  echo
  echo "FIN_FLOW — installateur Ubuntu par IP (HTTP ou HTTPS sans domaine)"
  echo "Variante domaines + TLS : deploy/ubuntu-install.sh"
  echo "Guide : documentation/13-guide-deploiement-ubuntu.md"
  echo

  collect_inputs
  install_base_packages
  install_docker
  systemctl enable --now fail2ban || true

  [[ "$SETUP_UFW" -eq 1 ]] && configure_ufw

  prepare_install_dir "$INSTALL_DIR" "$REPO_URL" "$GIT_BRANCH"
  write_env_file "$INSTALL_DIR"
  write_helpers "$INSTALL_DIR"
  write_nginx_ip "$APP_IP"
  start_stack "$INSTALL_DIR"
  post_deploy_commands "$INSTALL_DIR"

  if [[ "${ENABLE_TLS:-0}" -eq 1 ]]; then
    local tls_args=()
    if [[ "$TLS_MODE" == "le" ]]; then
      tls_args+=(--lets-encrypt --email "$LETSENCRYPT_EMAIL")
    else
      tls_args+=(--self-signed)
    fi
    log "Activation HTTPS (${TLS_MODE})…"
    bash "$INSTALL_DIR/deploy/tls-ip/enable-ip-tls.sh" "$INSTALL_DIR" "${tls_args[@]}"
  fi

  print_summary
}

main "$@"
