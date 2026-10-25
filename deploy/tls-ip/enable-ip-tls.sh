#!/usr/bin/env bash
# Active HTTPS sur une instance FinFlow installée par IP (sans nom de domaine).
#
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow --self-signed
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow --lets-encrypt
#
# Réseau interne (IP privée) : certificat auto-signé, HSTS désactivé
# (Let's Encrypt refuse les IP RFC1918 ; HSTS + auto-signé verrouille le navigateur).
# IP publique uniquement : Let's Encrypt (profil shortlived, 6 jours) + HSTS 7 j.
set -euo pipefail

if [[ -t 1 ]]; then
  C_INFO='\033[1;36m' C_OK='\033[1;32m' C_WARN='\033[1;33m' C_ERR='\033[1;31m' C_RST='\033[0m'
else
  C_INFO='' C_OK='' C_WARN='' C_ERR='' C_RST=''
fi
log()  { echo -e "${C_INFO}[INFO]${C_RST} $*"; }
ok()   { echo -e "${C_OK}[OK]${C_RST} $*"; }
warn() { echo -e "${C_WARN}[WARN]${C_RST} $*"; }
err()  { echo -e "${C_ERR}[ERR]${C_RST} $*" >&2; }
die()  { err "$*"; exit 1; }

[[ "${EUID}" -eq 0 ]] || die "Exécutez en root : sudo bash deploy/tls-ip/enable-ip-tls.sh"

DIR=""
FORCE_MODE=""
ACME_EMAIL=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --self-signed) FORCE_MODE="selfsigned"; shift ;;
    --lets-encrypt|--le) FORCE_MODE="le"; shift ;;
    --email) ACME_EMAIL="${2:-}"; shift 2 ;;
    --email=*) ACME_EMAIL="${1#*=}"; shift ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      if [[ -z "$DIR" && -d "$1" ]]; then
        DIR="$1"
        shift
      else
        die "Option inconnue : $1"
      fi
      ;;
  esac
done
DIR="${DIR:-/opt/finflow}"
[[ -f "$DIR/.env" ]] || die "Instance introuvable : $DIR/.env"

is_ipv4() { [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }
is_private_ip() {
  [[ "$1" =~ ^10\. ]] || [[ "$1" =~ ^192\.168\. ]] || [[ "$1" =~ ^127\. ]] \
    || [[ "$1" =~ ^169\.254\. ]] \
    || [[ "$1" =~ ^172\.(1[6-9]|2[0-9]|3[01])\. ]]
}

load_env() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$DIR/.env" | tail -n 1 || true)"
  line="${line#${key}=}"
  line="${line%\"}"; line="${line#\"}"
  line="${line%\'}"; line="${line#\'}"
  printf '%s' "$line"
}

APP_IP="$(load_env FINFLOW_PUBLIC_IP)"
if [[ -z "$APP_IP" ]]; then
  local_url="$(load_env FRONTEND_BASE_URL)"
  APP_IP="${local_url#http://}"
  APP_IP="${APP_IP#https://}"
  APP_IP="${APP_IP%%/*}"
  APP_IP="${APP_IP%%:*}"
fi
is_ipv4 "$APP_IP" || die "IP d'accès introuvable dans .env (FRONTEND_BASE_URL / FINFLOW_PUBLIC_IP)."

MODE="$FORCE_MODE"
if [[ -z "$MODE" ]]; then
  if is_private_ip "$APP_IP"; then
    MODE="selfsigned"
    warn "IP privée ${APP_IP} : Let's Encrypt refuse (pas d'HTTP-01 public). Certificat auto-signé."
  else
    MODE="le"
  fi
fi
if [[ "$MODE" == "le" ]] && is_private_ip "$APP_IP"; then
  die "Let's Encrypt exige une IP publique joignable sur le port 80. Utilisez --self-signed."
fi

TLS_ROOT="/etc/finflow/tls"
CURRENT="${TLS_ROOT}/current"
WEBROOT="/var/www/html"
HSTS_SECONDS=0
mkdir -p "$TLS_ROOT" "$WEBROOT"

write_nginx() {
  local hsts_line=""
  if [[ "$HSTS_SECONDS" -gt 0 ]]; then
    hsts_line="    add_header Strict-Transport-Security \"max-age=${HSTS_SECONDS}\" always;"
  fi
  cat > /etc/nginx/sites-available/finflow <<EOF
# FIN_FLOW — HTTPS par IP (généré par deploy/tls-ip/enable-ip-tls.sh)
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${APP_IP} _;

    location /.well-known/acme-challenge/ {
        root ${WEBROOT};
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ${APP_IP} _;

    ssl_certificate     ${CURRENT}/fullchain.pem;
    ssl_certificate_key ${CURRENT}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_session_timeout 1d;
    ssl_session_cache   shared:SSL:10m;
${hsts_line}

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
        client_max_body_size 25m;
    }
}

# MinIO / GED — même certificat, pour éviter le contenu mixte
server {
    listen 9000 ssl;
    listen [::]:9000 ssl;
    server_name ${APP_IP};

    ssl_certificate     ${CURRENT}/fullchain.pem;
    ssl_certificate_key ${CURRENT}/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
${hsts_line}

    ignore_invalid_headers off;
    proxy_buffering off;
    client_max_body_size 25m;

    location / {
        proxy_pass http://127.0.0.1:19000;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 300;
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
EOF
  rm -f /etc/nginx/sites-enabled/default
  ln -sf /etc/nginx/sites-available/finflow /etc/nginx/sites-enabled/finflow
}

issue_selfsigned() {
  local dir="${TLS_ROOT}/selfsigned"
  mkdir -p "$dir"
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
    -keyout "${dir}/privkey.pem" \
    -out "${dir}/fullchain.pem" \
    -subj "/CN=${APP_IP}" \
    -addext "subjectAltName=IP:${APP_IP}"
  chmod 640 "${dir}/privkey.pem"
  ln -sfn "$dir" "$CURRENT"
  HSTS_SECONDS=0
  ok "Certificat auto-signé (SAN IP:${APP_IP}) — le navigateur affichera un avertissement."
}

ensure_certbot() {
  if ! command -v certbot >/dev/null 2>&1; then
    if command -v snap >/dev/null 2>&1; then
      snap install --classic certbot
      ln -sfn /snap/bin/certbot /usr/bin/certbot
    else
      apt-get update -y
      apt-get install -y certbot
    fi
  fi
  local ver
  ver="$(certbot --version 2>/dev/null | awk '{print $2}' || true)"
  ok "Certbot ${ver:-inconnu}"
}

issue_letsencrypt() {
  ensure_certbot
  if [[ -z "$ACME_EMAIL" ]]; then
    ACME_EMAIL="$(load_env LETSENCRYPT_EMAIL)"
  fi
  if [[ -z "$ACME_EMAIL" ]]; then
    read -r -p "E-mail Let's Encrypt (expiration / avis) : " ACME_EMAIL || true
  fi
  [[ -n "$ACME_EMAIL" ]] || die "Un e-mail est requis pour Let's Encrypt."

  # Nginx HTTP doit déjà servir le webroot ACME (write_nginx après le premier cert :
  # on pose d'abord un vhost HTTP-only challenge si 443 n'existe pas encore).
  if [[ ! -f "${CURRENT}/fullchain.pem" ]]; then
    cat > /etc/nginx/sites-available/finflow <<EOF
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name ${APP_IP} _;
    location /.well-known/acme-challenge/ { root ${WEBROOT}; }
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/finflow /etc/nginx/sites-enabled/finflow
    nginx -t && systemctl reload nginx
  fi

  local extra=()
  if certbot --help 2>/dev/null | grep -q -- '--ip-address'; then
    extra+=(--ip-address "$APP_IP" --preferred-profile shortlived)
  else
    die "Certbot trop ancien (il faut ≥ 5.4 pour --ip-address). Installez le snap : snap install --classic certbot"
  fi

  certbot certonly --webroot -w "$WEBROOT" \
    "${extra[@]}" \
    --agree-tos --non-interactive -m "$ACME_EMAIL" \
    --deploy-hook "systemctl reload nginx" \
    || die "Échec Certbot. L'IP ${APP_IP} doit être publique et le port 80 ouvert depuis Internet."

  local live="/etc/letsencrypt/live/${APP_IP}"
  [[ -f "${live}/fullchain.pem" ]] || die "Certificat introuvable dans ${live}"
  ln -sfn "$live" "$CURRENT"
  HSTS_SECONDS=604800
  # Timer systemd Certbot + cron 3×/jour (certificats IP = 6 jours).
  cat > /etc/cron.d/finflow-certbot <<'CRON'
0 */8 * * * root certbot renew --quiet --deploy-hook "nginx -t && systemctl reload nginx"
CRON
  chmod 644 /etc/cron.d/finflow-certbot
  ok "Certificat Let's Encrypt (IP, ~6 jours) — renouvellement timer Certbot + cron 3×/jour."
}

patch_env() {
  local env_file="$DIR/.env"
  python3 - "$env_file" "$APP_IP" "$HSTS_SECONDS" "${ACME_EMAIL:-}" <<'PY'
import pathlib, re, sys
path, ip, hsts = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
email = sys.argv[4] if len(sys.argv) > 4 else ""
text = path.read_text(encoding="utf-8")
updates = {
    "DJANGO_SECURE_SSL_REDIRECT": "True",
    "DJANGO_SECURE_HSTS_SECONDS": hsts,
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "False",
    "DJANGO_SECURE_HSTS_PRELOAD": "False",
    "FRONTEND_BASE_URL": f"https://{ip}",
    "DJANGO_CORS_ALLOWED_ORIGINS": f"https://{ip}",
    "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{ip}",
    "AWS_S3_URL_PROTOCOL": "https:",
    "AWS_S3_CUSTOM_DOMAIN": f"{ip}:9000",
    "FINFLOW_PUBLIC_IP": ip,
}
if email:
    updates["LETSENCRYPT_EMAIL"] = email
for key, value in updates.items():
    pattern = re.compile(rf"^{re.escape(key)}=.*$", re.M)
    line = f'{key}="{value}"'
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        text = text.rstrip() + "\n" + line + "\n"
path.write_text(text, encoding="utf-8")
print("env patched")
PY
}

refresh_wrapper() {
  mkdir -p "$DIR/scripts"
  cat > "$DIR/scripts/finflow" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$DIR"
if [[ -f "$DIR/deploy/compose-files.sh" ]]; then
  exec docker compose \$(bash "$DIR/deploy/compose-files.sh" "$DIR") "\$@"
fi
exec docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml "\$@"
EOF
  chmod +x "$DIR/scripts/finflow"
  ln -sfn "$DIR/scripts/finflow" /usr/local/bin/finflow
}

log "Instance ${DIR} · IP ${APP_IP} · mode ${MODE}"

if [[ "$MODE" == "le" ]]; then
  issue_letsencrypt
else
  issue_selfsigned
fi

echo "$MODE" > "$DIR/.finflow-tls-mode"
chmod 644 "$DIR/.finflow-tls-mode"
[[ -f "$DIR/docker-compose.ip-tls.yml" ]] \
  || die "docker-compose.ip-tls.yml manquant — git pull dans ${DIR} puis relancez."

patch_env
refresh_wrapper

if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 443/tcp || true
  ok "UFW : 443/tcp ouvert"
fi

# MinIO passe en 127.0.0.1:19000 avant que Nginx n'écoute :9000 en SSL.
COMPOSE_FILES="$(bash "$DIR/deploy/compose-files.sh" "$DIR")"
# shellcheck disable=SC2086
docker compose --project-directory "$DIR" $COMPOSE_FILES up -d

write_nginx
nginx -t
systemctl reload nginx

ok "HTTPS actif : https://${APP_IP}/"
if [[ "$HSTS_SECONDS" -gt 0 ]]; then
  ok "HSTS max-age=${HSTS_SECONDS}s (7 jours) — pas de preload, pas de includeSubDomains."
  warn "Ne passez pas à 31536000 tant que le renouvellement Certbot n'a pas tourné au moins une fois."
else
  warn "HSTS désactivé : certificat auto-signé. Un max-age long bloquerait les navigateurs au prochain renouvellement."
fi
echo
echo "  curl -k -fsSI https://${APP_IP}/api/v1/health/"
echo "  sudo certbot certificates   # si mode le"
