#!/usr/bin/env bash
# Contrôle hors production : résolution Compose + ubuntu-update --check
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0
FAIL=0

assert_eq() {
  local got="$1" want="$2" label="$3"
  if [[ "$got" == "$want" ]]; then
    echo "  OK  $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL $label"
    echo "       got : $got"
    echo "       want: $want"
    FAIL=$((FAIL + 1))
  fi
}

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

make_tree() {
  local d="$1"
  mkdir -p "$d/deploy"
  cp "$ROOT/deploy/compose-files.sh" "$d/deploy/compose-files.sh"
  : > "$d/docker-compose.yml"
  : > "$d/docker-compose.prod.yml"
  cp "$ROOT/docker-compose.ip.yml" "$d/docker-compose.ip.yml"
  cp "$ROOT/docker-compose.ip-tls.yml" "$d/docker-compose.ip-tls.yml"
}

echo "== bash -n"
for s in \
  "$ROOT/deploy/compose-files.sh" \
  "$ROOT/deploy/ubuntu-update.sh" \
  "$ROOT/deploy/ubuntu-install.sh" \
  "$ROOT/deploy/ubuntu-install-ip.sh" \
  "$ROOT/deploy/tls-ip/enable-ip-tls.sh" \
  "$ROOT/deploy/backup/lib.sh" \
  "$ROOT/deploy/backup/backup.sh" \
  "$ROOT/deploy/backup/restore.sh" \
  "$ROOT/deploy/backup/verify.sh" \
  "$ROOT/deploy/backup/wire-install.sh"
do
  bash -n "$s"
  echo "  OK  bash -n $(basename "$s")"
  PASS=$((PASS + 1))
done

echo
echo "== compose-files.sh"

d="$tmp/domain"
make_tree "$d"
echo domain > "$d/.finflow-deploy-mode"
printf 'DJANGO_SECURE_SSL_REDIRECT="True"\nFRONTEND_BASE_URL="https://finflow.example.tld"\n' > "$d/.env"
assert_eq "$(bash "$d/deploy/compose-files.sh" "$d")" \
  "-f docker-compose.yml -f docker-compose.prod.yml" \
  "mode domain"

d="$tmp/ip-http"
make_tree "$d"
echo ip > "$d/.finflow-deploy-mode"
printf 'DJANGO_SECURE_SSL_REDIRECT="False"\nFRONTEND_BASE_URL="http://192.168.10.20"\nFINFLOW_PUBLIC_IP="192.168.10.20"\n' > "$d/.env"
assert_eq "$(bash "$d/deploy/compose-files.sh" "$d")" \
  "-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml" \
  "mode IP HTTP"

d="$tmp/ip-tls"
make_tree "$d"
echo ip > "$d/.finflow-deploy-mode"
echo selfsigned > "$d/.finflow-tls-mode"
printf 'DJANGO_SECURE_SSL_REDIRECT="True"\nFRONTEND_BASE_URL="https://192.168.10.20"\nFINFLOW_PUBLIC_IP="192.168.10.20"\n' > "$d/.env"
assert_eq "$(bash "$d/deploy/compose-files.sh" "$d")" \
  "-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml -f docker-compose.ip-tls.yml" \
  "mode IP + TLS selfsigned"

d="$tmp/legacy"
make_tree "$d"
printf 'DJANGO_SECURE_SSL_REDIRECT="False"\nFRONTEND_BASE_URL="http://10.0.0.8"\n' > "$d/.env"
assert_eq "$(bash "$d/deploy/compose-files.sh" "$d")" \
  "-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml" \
  "heuristique IP HTTP sans marker"

d="$tmp/ip-https-nomarker"
make_tree "$d"
printf 'DJANGO_SECURE_SSL_REDIRECT="True"\nFRONTEND_BASE_URL="https://10.1.2.3"\nFINFLOW_PUBLIC_IP="10.1.2.3"\n' > "$d/.env"
assert_eq "$(bash "$d/deploy/compose-files.sh" "$d")" \
  "-f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml" \
  "heuristique IP HTTPS (pas encore .finflow-tls-mode)"

echo
echo "== ubuntu-update.sh --check (IP + TLS)"
bash "$ROOT/deploy/ubuntu-update.sh" --check "$tmp/ip-tls"
PASS=$((PASS + 1))

echo
echo "== ubuntu-update.sh --check (dépôt courant)"
bash "$ROOT/deploy/ubuntu-update.sh" --check "$ROOT"
PASS=$((PASS + 1))

echo
echo "== fallback 1re update (sans compose-files.sh)"
d="$tmp/first-update"
make_tree "$d"
echo ip > "$d/.finflow-deploy-mode"
rm -f "$d/deploy/compose-files.sh"
printf 'DJANGO_SECURE_SSL_REDIRECT="False"\nFRONTEND_BASE_URL="http://192.168.1.50"\n' > "$d/.env"
got="$(bash "$ROOT/deploy/ubuntu-update.sh" --check "$d" | awk -F': ' '/compose :/{print $2}')"
assert_eq "$got" \
  "docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.ip.yml" \
  "fallback IP via --check"

echo
echo "Résultat : $PASS ok, $FAIL échec(s)"
[[ "$FAIL" -eq 0 ]]
