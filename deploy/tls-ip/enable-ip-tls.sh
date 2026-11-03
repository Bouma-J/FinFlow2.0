#!/usr/bin/env bash
# Active HTTPS sur une instance FinFlow installée par IP (sans nom de domaine).
#
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow --self-signed
#   sudo bash deploy/tls-ip/enable-ip-tls.sh /opt/finflow
#
# Réseau interne uniquement : IP privée et certificat auto-signé, HSTS désactivé.
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
while [[ $# -gt 0 ]]; do
  case "$1" in
    --self-signed) FORCE_MODE="selfsigned"; shift ;;
    --lets-encrypt|--le|--email|--email=*) die "Le déploiement est réservé au LAN ; provisionnez un certificat d'autorité interne séparément." ;;
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

is_ipv4() {
  python3 - "$1" <<'PY' >/dev/null 2>&1
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
raise SystemExit(0 if isinstance(ip, ipaddress.IPv4Address) else 1)
PY
}
is_private_ip() {
  python3 - "$1" <<'PY' >/dev/null 2>&1
import ipaddress, sys
ip = ipaddress.ip_address(sys.argv[1])
ranges = map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
raise SystemExit(0 if any(ip in net for net in ranges) else 1)
PY
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
is_private_ip "$APP_IP" || die "HTTPS IP est limité à une adresse RFC1918 du réseau local."
[[ -z "$FORCE_MODE" || "$FORCE_MODE" == "selfsigned" ]] || die "Mode TLS non pris en charge pour une instance LAN."
MODE="selfsigned"

TLS_ROOT="/etc/finflow/tls"
CURRENT="${TLS_ROOT}/current"
HSTS_SECONDS=0
mkdir -p "$TLS_ROOT"

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

patch_env() {
  local env_file="$DIR/.env"
  python3 - "$env_file" "$APP_IP" "$HSTS_SECONDS" <<'PY'
import pathlib, re, sys
path, ip, hsts = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
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

issue_selfsigned

[[ -f "$DIR/docker-compose.ip-tls.yml" ]] \
  || die "docker-compose.ip-tls.yml manquant — git pull dans ${DIR} puis relancez."

patch_env

LAN_CIDR="$(cat "$DIR/.finflow-lan-cidr" 2>/dev/null || true)"
if [[ -z "$LAN_CIDR" ]]; then
  LAN_CIDR="$(bash "$DIR/deploy/lan-firewall.sh" detect-default-cidr)"
  LAN_CIDR="$(bash "$DIR/deploy/lan-firewall.sh" validate-cidr "$LAN_CIDR")" \
    || die "CIDR LAN introuvable ; renseignez $DIR/.finflow-lan-cidr avant d'activer TLS."
  printf '%s\n' "$LAN_CIDR" > "$DIR/.finflow-lan-cidr"
  chmod 644 "$DIR/.finflow-lan-cidr"
  warn "CIDR LAN absent sur cette ancienne installation ; CIDR détecté : $LAN_CIDR. Vérifiez-le avant de poursuivre."
fi
bash "$DIR/deploy/lan-firewall.sh" apply "$LAN_CIDR" "22 80 443 9000" \
  "$DIR/deploy/lan-firewall.sh"

# MinIO passe en 127.0.0.1:19000 avant que Nginx n'écoute :9000 en SSL.
COMPOSE_FILES="$(bash "$DIR/deploy/compose-files.sh" "$DIR")"
if [[ "$COMPOSE_FILES" != *docker-compose.ip-tls.yml* ]]; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.ip-tls.yml"
fi
# shellcheck disable=SC2086
docker compose --project-directory "$DIR" $COMPOSE_FILES up -d

write_nginx
nginx -t
systemctl reload nginx

echo "$MODE" > "$DIR/.finflow-tls-mode"
chmod 644 "$DIR/.finflow-tls-mode"
refresh_wrapper

ok "HTTPS actif : https://${APP_IP}/"
warn "HSTS désactivé : certificat auto-signé. Faites installer une CA interne sur les postes pour retirer l'avertissement du navigateur."
echo
echo "  curl -k -fsSI https://${APP_IP}/api/v1/health/"
