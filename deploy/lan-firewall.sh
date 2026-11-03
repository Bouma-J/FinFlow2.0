#!/usr/bin/env bash
# Restrict FinFlow host ports to a private LAN and keep Docker's published
# MinIO port filtered across Docker restarts.
set -euo pipefail

die() { echo "[ERR] $*" >&2; exit 1; }

validate_cidr() {
  python3 - "$1" <<'PY'
import ipaddress, sys
try:
    net = ipaddress.ip_network(sys.argv[1], strict=False)
except ValueError as exc:
    raise SystemExit(str(exc))
if not isinstance(net, ipaddress.IPv4Network):
    raise SystemExit("seul un CIDR IPv4 est pris en charge")
private = any(net.subnet_of(ipaddress.ip_network(c)) for c in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
if not private:
    raise SystemExit("le réseau doit être une plage privée RFC1918")
print(net)
PY
}

remove_wide_ufw_rule() {
  local rule="$1" pattern="$2" attempts=0
  while LC_ALL=C ufw status 2>/dev/null | grep -Eq "$pattern"; do
    (( attempts += 1 ))
    (( attempts <= 20 )) || die "trop de règles UFW générales détectées pour ${rule}"
    LC_ALL=C ufw --force delete allow "$rule" >/dev/null \
      || die "impossible de supprimer l'ancienne règle UFW générale ${rule}"
  done
}

install_docker_filter() {
  local cidr="$1" script_path="$2" service_file=/etc/systemd/system/finflow-lan-docker-filter.service
  install -d -m 0755 /etc/finflow
  printf '%s\n' "$cidr" > /etc/finflow/lan-cidr
  chmod 0644 /etc/finflow/lan-cidr
  cat > "$service_file" <<EOF
[Unit]
Description=FinFlow LAN filter for Docker-published MinIO
After=docker.service
Requires=docker.service
PartOf=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash "$script_path" docker-filter "$cidr"

[Install]
WantedBy=multi-user.target
EOF
  chmod 0644 "$service_file"
  systemctl daemon-reload
  # Réappliquer également le CIDR si le filtre était déjà actif avant cette
  # installation ou une mise à jour de la configuration LAN.
  systemctl enable finflow-lan-docker-filter.service
  systemctl restart finflow-lan-docker-filter.service
}

docker_filter() {
  local cidr
  cidr="$(validate_cidr "$1")" || die "CIDR LAN invalide : $1"
  command -v iptables >/dev/null 2>&1 || die "iptables introuvable pour filtrer le port Docker 9000"
  iptables -nL DOCKER-USER >/dev/null 2>&1 || die "chaîne DOCKER-USER absente ; démarrez Docker avant d'appliquer ce filtre"
  iptables -N FINFLOW-LAN 2>/dev/null || true
  iptables -F FINFLOW-LAN
  iptables -A FINFLOW-LAN -p tcp -s "$cidr" -m conntrack --ctorigdstport 9000 -j RETURN
  iptables -A FINFLOW-LAN -p tcp -m conntrack --ctorigdstport 9000 -j DROP
  iptables -A FINFLOW-LAN -j RETURN
  iptables -C DOCKER-USER -j FINFLOW-LAN 2>/dev/null \
    || iptables -I DOCKER-USER 1 -j FINFLOW-LAN
}

apply_firewall() {
  local cidr ports script_path port
  cidr="$(validate_cidr "$1")" || die "CIDR LAN invalide : $1"
  ports="$2"
  script_path="$3"
  local ssh_sources=""
  if [[ -n "${SSH_CONNECTION:-}" ]]; then
    ssh_sources="${SSH_CONNECTION%% *}"
  elif [[ -n "${SSH_CLIENT:-}" ]]; then
    ssh_sources="${SSH_CLIENT%% *}"
  fi
  if [[ -z "$ssh_sources" ]] && command -v ss >/dev/null 2>&1; then
    ssh_sources="$(ss -Htn state established '( sport = :22 )' 2>/dev/null | awk '{print $5}')"
  fi
  if [[ -n "$ssh_sources" ]]; then
    python3 - "$cidr" "$ssh_sources" <<'PY' || die "une session SSH active ne vient pas du CIDR autorisé ($cidr) ; refus pour éviter de perdre l'accès"
import ipaddress, sys
net = ipaddress.ip_network(sys.argv[1])
raw = sys.argv[2].split()
sources = []
for value in raw:
    if value.startswith("[") and "]" in value:
        value = value[1:value.index("]")]
    elif value.count(":") == 1:
        value = value.rsplit(":", 1)[0]
    try:
        sources.append(ipaddress.ip_address(value))
    except ValueError:
        continue
raise SystemExit(0 if all(address in net for address in sources) else 1)
PY
  fi

  command -v ufw >/dev/null 2>&1 || die "UFW introuvable"
  ufw default deny incoming
  ufw default allow outgoing

  # Retire les anciennes ouvertures Anywhere (IPv4 et IPv6), après avoir
  # vérifié que la session SSH courante est incluse dans le nouveau CIDR.
  remove_wide_ufw_rule OpenSSH '^OpenSSH( \(v6\))?[[:space:]]+ALLOW IN[[:space:]]+Anywhere'
  for port in 22 80 443 9000; do
    remove_wide_ufw_rule "${port}/tcp" "^${port}/tcp( \(v6\))?[[:space:]]+ALLOW IN[[:space:]]+Anywhere"
  done

  for port in $ports; do
    [[ "$port" =~ ^(22|80|443|9000)$ ]] || die "port FinFlow non autorisé : $port"
    ufw allow from "$cidr" to any port "$port" proto tcp
  done
  ufw --force enable
  ufw status verbose || true
  install_docker_filter "$cidr" "$script_path"
  echo "[OK] UFW et Docker limités au réseau ${cidr}."
}

case "${1:-}" in
  detect-default-cidr)
    route="$(ip -4 route get 1.1.1.1 2>/dev/null | head -n 1)"
    iface="$(awk '{for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}' <<< "$route")"
    [[ -n "$iface" ]] || die "impossible de détecter l'interface LAN par défaut"
    ip -o -f inet addr show dev "$iface" scope global \
      | awk 'NR==1 {print $4; exit}'
    ;;
  validate-cidr)
    [[ $# -eq 2 ]] || die "Usage: $0 validate-cidr <CIDR-LAN>"
    validate_cidr "$2"
    ;;
  apply)
    [[ $# -eq 4 ]] || die "Usage: $0 apply <CIDR-LAN> '<ports>' <chemin-script>"
    apply_firewall "$2" "$3" "$4"
    ;;
  docker-filter)
    [[ $# -eq 2 ]] || die "Usage: $0 docker-filter <CIDR-LAN>"
    docker_filter "$2"
    ;;
  *) die "Usage: $0 {apply <CIDR-LAN> '<ports>' <chemin-script>|docker-filter <CIDR-LAN>}" ;;
esac
