#!/usr/bin/env bash
# FIN_FLOW — installation ou mise à jour depuis une copie/une archive locale,
# sans git clone, git fetch ni git pull.
#
# Première installation :
#   sudo bash deploy/ubuntu-deploy-local.sh --install-ip [/opt/finflow]
#   sudo bash deploy/ubuntu-deploy-local.sh --install-domain [/opt/finflow]
#
# Mise à jour depuis un ZIP extrait :
#   sudo bash deploy/ubuntu-deploy-local.sh --update /opt/finflow
set -euo pipefail

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAGE=""
PASS_FILE="${BACKUP_PASSPHRASE_FILE:-/root/.finflow-backup-pass}"
SNAPSHOT_ARCHIVE=""

log()  { echo "[INFO] $*"; }
ok()   { echo "[OK] $*"; }
warn() { echo "[WARN] $*" >&2; }
die()  { echo "[ERR] $*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage :
  sudo bash deploy/ubuntu-deploy-local.sh --install-ip [INSTALL_DIR]
  sudo bash deploy/ubuntu-deploy-local.sh --install-domain [INSTALL_DIR]
  sudo bash deploy/ubuntu-deploy-local.sh --update INSTALL_DIR

La source doit être le dépôt local ou son ZIP déjà extrait à sa racine.
Les mises à jour créent et vérifient un snapshot chiffré avant de copier le code.
EOF
}

cleanup() {
  local rc=$?
  [[ -z "$STAGE" ]] || rm -rf -- "$STAGE"
  if [[ "$rc" -ne 0 && -n "$SNAPSHOT_ARCHIVE" ]]; then
    warn "Snapshot pré-déploiement vérifié : $SNAPSHOT_ARCHIVE"
  fi
  exit "$rc"
}
trap cleanup EXIT

need_root() {
  [[ "${EUID}" -eq 0 ]] || die "Exécutez ce script avec sudo."
}

normalize_target() {
  local target="$1"
  [[ "$target" == /* ]] || die "INSTALL_DIR doit être un chemin absolu : $target"
  target="$(readlink -m -- "$target")" || die "Impossible de résoudre INSTALL_DIR : $1"
  case "$target" in
    /|/opt|/home|/root|/var|/usr|/etc|/tmp)
      die "INSTALL_DIR pointe vers un répertoire système trop général : $target" ;;
  esac
  printf '%s' "$target"
}

check_source() {
  [[ -f "$SOURCE_ROOT/docker-compose.yml" && -f "$SOURCE_ROOT/docker-compose.prod.yml" ]] \
    || die "Racine source invalide : docker-compose.yml ou docker-compose.prod.yml absent. Exécutez le script depuis le dépôt ou le ZIP extrait."
  [[ -f "$SOURCE_ROOT/deploy/backup/backup.sh" && -f "$SOURCE_ROOT/deploy/backup/verify.sh" ]] \
    || die "Outils de sauvegarde absents de la source locale."
  [[ -f "$SOURCE_ROOT/deploy/ubuntu-update.sh" ]] \
    || die "deploy/ubuntu-update.sh absent de la source locale."
}

stage_source() {
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/finflow-local-source.XXXXXX")"
  chmod 700 "$STAGE"
  python3 - "$SOURCE_ROOT" "$STAGE" <<'PY'
import os
import shutil
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:3])
excluded_dirs = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", ".vite", "dist", "coverage", "test-results",
    "playwright-report", "media", "staticfiles", ".audit-cache", "uat-artifacts",
}

def excluded(name):
    lower = name.lower()
    return (
        name in excluded_dirs
        or (name.startswith(".env") and name != ".env.example")
        or name.startswith(".finflow-")
        or lower.endswith((".sqlite", ".sqlite3", ".db", ".log", ".pyc", ".pyo"))
        or lower.endswith((".pem", ".key", ".p12", ".pfx"))
        or lower.startswith("db.pre-") and lower.endswith((".sqlite", ".sqlite3"))
    )

def ignored_at(directory, name):
    path = Path(directory)
    if excluded(name) or (name == "scripts" and path == source):
        return True
    return path.name == "certs" and name != ".gitkeep"

for root, dirs, files in os.walk(source, topdown=True, followlinks=False):
    dirs[:] = [name for name in dirs if not ignored_at(root, name)]
    for name in dirs + files:
        path = Path(root) / name
        if path.is_symlink():
            raise SystemExit(f"Lien symbolique non pris en charge dans la source : {path}")

def ignore(directory, names):
    return [name for name in names if ignored_at(directory, name)]

shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)
PY
  [[ -f "$STAGE/docker-compose.yml" && -f "$STAGE/deploy/ubuntu-deploy-local.sh" ]] \
    || die "La copie temporaire du code local est incomplète."
}

ensure_passphrase() {
  [[ ! -L "$PASS_FILE" ]] || die "Le fichier de phrase de passe est un lien symbolique : $PASS_FILE"
  if [[ ! -s "$PASS_FILE" ]]; then
    install -d -m 0700 "$(dirname "$PASS_FILE")"
    umask 077
    openssl rand -base64 32 > "$PASS_FILE"
    chmod 600 "$PASS_FILE"
    warn "Phrase de chiffrement créée dans $PASS_FILE. Copiez-la dans un coffre sûr hors du serveur."
  fi
  chmod 600 "$PASS_FILE"
}

install_local_update_wrapper() {
  local dir="$1" quoted_dir
  mkdir -p "$dir/scripts"
  printf -v quoted_dir '%q' "$dir"
  cat > "$dir/scripts/finflow-update-local" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ \$# -ne 1 || ! -f "\$1/deploy/ubuntu-deploy-local.sh" ]]; then
  echo "Usage : sudo finflow-update <répertoire-du-ZIP-extrait>" >&2
  exit 2
fi
exec bash "\$1/deploy/ubuntu-deploy-local.sh" --update ${quoted_dir}
EOF
  chmod 0755 "$dir/scripts/finflow-update-local"
  ln -sfn "$dir/scripts/finflow-update-local" /usr/local/bin/finflow-update
  ln -sfn "$dir/scripts/finflow-update-local" "$dir/scripts/update.sh"
  ok "FinFlow est en mode sans Git. Mise à jour suivante : sudo finflow-update <répertoire-du-ZIP-extrait>."
}

install_from_local_source() {
  local mode="$1" target="$2" installer
  [[ ! -e "$target/.env" ]] || die "Un .env existe déjà dans $target. Ce mode d'installation ne remplace pas une instance existante ; utilisez --update."
  case "$mode" in
    ip) installer="$STAGE/deploy/ubuntu-install-ip.sh" ;;
    domain) installer="$STAGE/deploy/ubuntu-install.sh" ;;
    *) die "Mode d'installation inconnu : $mode" ;;
  esac
  [[ -f "$installer" ]] || die "Installateur absent : $installer"

  log "Démarrage de l'installation $mode depuis la source locale, sans Git."
  FINFLOW_LOCAL_SOURCE_DIR="$STAGE" \
  FINFLOW_LOCAL_INSTALL_DIR="$target" \
  INSTALL_DIR_DEFAULT="$target" \
    bash "$installer"

  [[ -f "$target/.env" ]] && [[ -f "$target/docker-compose.yml" ]] \
    || die "L'installateur s'est terminé sans produire une installation complète dans $target."
  install_local_update_wrapper "$target"
  ok "Installation locale terminée dans $target."
}

validate_cidr_marker() {
  local dir="$1" marker="$1/.finflow-lan-cidr" cidr
  if [[ -s "$marker" ]]; then
    cidr="$(tr -d '[:space:]' < "$marker")"
  else
    cidr="$(bash "$STAGE/deploy/lan-firewall.sh" detect-default-cidr)"
  fi
  cidr="$(bash "$STAGE/deploy/lan-firewall.sh" validate-cidr "$cidr")" \
    || die "CIDR LAN introuvable ou invalide. Vérifiez $marker avant la mise à jour."
  printf '%s\n' "$cidr" > "$marker"
  chmod 0644 "$marker"
}

update_from_local_source() {
  local dir="$1" output="" archive
  [[ -d "$dir" && -s "$dir/.env" ]] \
    || die "Instance existante introuvable ou .env absent dans $dir. Pour une première installation, utilisez --install-ip ou --install-domain."
  [[ -f "$dir/docker-compose.yml" && -f "$dir/docker-compose.prod.yml" ]] \
    || die "Le répertoire cible ne ressemble pas à une instance FinFlow : Compose production absent."
  command -v docker >/dev/null 2>&1 || die "Docker Engine est introuvable."
  command -v rsync >/dev/null 2>&1 || die "rsync est requis pour synchroniser la source sans supprimer les données locales. Installez-le avant de poursuivre."
  docker compose version --short >/dev/null 2>&1 || die "Docker Compose v2 est requis."

  ensure_passphrase
  validate_cidr_marker "$dir"

  log "Création du snapshot chiffré avant la copie des fichiers."
  if ! output="$(env -u SKIP_MINIO -u SKIP_SECRETS \
    FINFLOW_DIR="$dir" BACKUP_PASSPHRASE_FILE="$PASS_FILE" SKIP_APP_PAUSE=0 \
    bash "$STAGE/deploy/backup/backup.sh")"; then
    printf '%s\n' "$output" >&2
    die "La sauvegarde pré-déploiement a échoué ; le code cible n'a pas été modifié."
  fi
  printf '%s\n' "$output"
  archive="$(tail -n 1 <<< "$output")"
  [[ -f "$archive" ]] || die "Archive de sauvegarde introuvable : ${archive:-inconnue}."
  FINFLOW_DIR="$dir" BACKUP_PASSPHRASE_FILE="$PASS_FILE" \
    bash "$STAGE/deploy/backup/verify.sh" "$archive" \
    || die "Le snapshot n'a pas passé le contrôle d'intégrité ; le code cible n'a pas été modifié."
  SNAPSHOT_ARCHIVE="$archive"
  ok "Snapshot vérifié : $archive"

  log "Synchronisation du code local vers $dir (configuration et données conservées)."
  rsync -a --delete-delay \
    --exclude='/.env*' --exclude='**/.env*' \
    --exclude='/.git/' --exclude='**/.git/' \
    --exclude='/.finflow-*' --exclude='**/.finflow-*' \
    --exclude='/scripts/' \
    --exclude='*.sqlite' --exclude='*.sqlite3' --exclude='*.db' \
    --exclude='*.log' --exclude='*.pyc' --exclude='*.pyo' \
    --exclude='*.pem' --exclude='*.key' --exclude='*.p12' --exclude='*.pfx' \
    --exclude='node_modules/' --exclude='.venv/' --exclude='__pycache__/' \
    --exclude='certs/' \
    --exclude='.pytest_cache/' --exclude='.ruff_cache/' --exclude='.mypy_cache/' \
    --exclude='dist/' --exclude='media/' --exclude='staticfiles/' \
    --exclude='uat-artifacts/' \
    --exclude='test-results/' --exclude='playwright-report/' \
    "$STAGE/" "$dir/"

  log "Rebuild, migrations et contrôles de santé via ubuntu-update.sh."
  env SKIP_GIT=1 SKIP_BACKUP=1 BACKUP_PASSPHRASE_FILE="$PASS_FILE" \
    bash "$dir/deploy/ubuntu-update.sh" "$dir"
  install_local_update_wrapper "$dir"
  ok "Déploiement local terminé. Snapshot conservé : $archive"
}

main() {
  local action="${1:-}" target
  if [[ "$action" == "-h" || "$action" == "--help" || -z "$action" ]]; then
    usage
    [[ -n "$action" ]] && exit 0
    exit 2
  fi
  need_root
  check_source
  stage_source

  case "$action" in
    --install-ip|--install-domain)
      target="$(normalize_target "${2:-/opt/finflow}")"
      if [[ "$action" == "--install-ip" ]]; then
        install_from_local_source ip "$target"
      else
        install_from_local_source domain "$target"
      fi
      ;;
    --update)
      [[ $# -eq 2 ]] || { usage; die "--update requiert INSTALL_DIR."; }
      target="$(normalize_target "$2")"
      update_from_local_source "$target"
      ;;
    *) usage; die "Action inconnue : $action" ;;
  esac
}

main "$@"
