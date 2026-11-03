#!/usr/bin/env bash
# Branche les scripts de sauvegarde sur une instance installée.
# Appelé par ubuntu-install.sh / ubuntu-install-ip.sh / ubuntu-update.sh :
#   bash deploy/backup/wire-install.sh /opt/finflow
#
# Les dumps vont dans /var/backups/finflow (hors du dépôt /opt/finflow).
set -euo pipefail

DIR="${1:-}"
[[ -n "$DIR" && -d "$DIR" ]] || {
  echo "[ERR] Usage: wire-install.sh /opt/finflow" >&2
  exit 1
}

SCRIPT_SRC="${DIR}/deploy/backup"
BACKUP_ROOT="/var/backups/finflow"
mkdir -p "${DIR}/scripts" "${BACKUP_ROOT}/snapshots" /var/log
chmod 700 "${BACKUP_ROOT}" 2>/dev/null || true

chmod +x "${SCRIPT_SRC}/backup.sh" "${SCRIPT_SRC}/restore.sh" \
  "${SCRIPT_SRC}/verify.sh" "${SCRIPT_SRC}/selftest.sh" 2>/dev/null || true

ln -sfn "${SCRIPT_SRC}/backup.sh" "${DIR}/scripts/backup.sh"
ln -sfn "${SCRIPT_SRC}/restore.sh" "${DIR}/scripts/restore.sh"
ln -sfn "${SCRIPT_SRC}/verify.sh" "${DIR}/scripts/verify.sh"

cat > "${DIR}/scripts/backup-db.sh" <<EOF
#!/usr/bin/env bash
# Compatibilité : l'ancien cron appelait backup-db.sh (dump SQL seul).
set -euo pipefail
export FINFLOW_DIR="${DIR}"
exec "${SCRIPT_SRC}/backup.sh" "\$@"
EOF
chmod +x "${DIR}/scripts/backup-db.sh"

PASS_FILE="${BACKUP_PASSPHRASE_FILE:-/root/.finflow-backup-pass}"
install -d -m 0700 "$(dirname "$PASS_FILE")"
[[ ! -L "$PASS_FILE" ]] || {
  echo "[ERR] Le fichier de phrase de passe est un lien symbolique : ${PASS_FILE}" >&2
  exit 1
}
if [[ ! -f "$PASS_FILE" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 32 > "$PASS_FILE"
  else
    head -c 32 /dev/urandom | base64 > "$PASS_FILE"
  fi
  chmod 600 "$PASS_FILE"
  echo "[OK] Phrase de chiffrement créée : ${PASS_FILE}"
  echo "[WARN] Copiez cette phrase dans un coffre sécurisé hors de ce serveur."
fi
chmod 600 "$PASS_FILE"

if [[ -d /etc/cron.d ]]; then
  cat > /etc/cron.d/finflow-backup <<EOF
# FinFlow — archive chiffrée quotidienne 02:30 (Postgres + MinIO + secrets)
# Destination : ${BACKUP_ROOT}/snapshots (hors du projet ${DIR})
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 2 * * * root FINFLOW_DIR=${DIR} BACKUP_ROOT=${BACKUP_ROOT} BACKUP_PASSPHRASE_FILE=${PASS_FILE} ${SCRIPT_SRC}/backup.sh >> /var/log/finflow-backup.log 2>&1
EOF
  chmod 644 /etc/cron.d/finflow-backup
  echo "[OK] Cron installé : /etc/cron.d/finflow-backup (02:30) → ${BACKUP_ROOT}/snapshots"
else
  echo "[WARN] /etc/cron.d absent — cron de sauvegarde non posé." >&2
fi

echo "[OK] Wrappers : ${DIR}/scripts/backup.sh restore.sh verify.sh backup-db.sh"
