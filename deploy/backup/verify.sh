#!/usr/bin/env bash
# Contrôle d'intégrité d'un snapshot (checksums + TOC Postgres + secrets).
#
#   ./deploy/backup/verify.sh /var/backups/finflow/snapshots/20260907T023000Z
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"

SNAP="${1:-}"
[[ -n "$SNAP" && -d "$SNAP" ]] || die "Usage: $0 /chemin/du/snapshot"
SNAP="$(cd "$SNAP" && pwd)"
MANIFEST="${SNAP}/manifest.json"
[[ -f "$MANIFEST" ]] || die "manifest.json manquant"
[[ -f "${SNAP}/postgres.dump" ]] || die "postgres.dump manquant"

run_python - "$(host_path "$SNAP")" "$(host_path "$MANIFEST")" "$(sha256_file "${SNAP}/postgres.dump")" \
  "$(wc -c < "${SNAP}/postgres.dump" | tr -d ' ')" \
  "$(dir_bytes "${SNAP}/minio")" \
  "$(count_files "${SNAP}/minio")" <<'PY'
import json, os, sys
snap, manifest_path, pg_sha, pg_bytes, minio_bytes, minio_files = sys.argv[1:]
with open(manifest_path, encoding="utf-8") as fh:
    m = json.load(fh)
pg = m["files"]["postgres.dump"]
errors = []
if pg["sha256"] != pg_sha:
    errors.append(f"postgres.dump sha256 attendu {pg['sha256']}, obtenu {pg_sha}")
if int(pg["bytes"]) != int(pg_bytes):
    errors.append(f"postgres.dump taille attendue {pg['bytes']}, obtenue {pg_bytes}")
mini = m["files"].get("minio") or {}
if mini and int(mini.get("objects") or 0) != int(minio_files):
    errors.append(
        f"minio objets attendus {mini.get('objects')}, obtenus {minio_files}"
    )
sec = m["files"].get("secrets.env.enc")
enc = os.path.join(snap, "secrets.env.enc")
if sec:
    if not os.path.isfile(enc):
        errors.append("secrets.env.enc manquant")
    else:
        import hashlib
        h = hashlib.sha256()
        with open(enc, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        got = h.hexdigest()
        if got != sec["sha256"]:
            errors.append(f"secrets.env.enc sha256 attendu {sec['sha256']}, obtenu {got}")
if errors:
    print("VERIFY FAIL")
    for e in errors:
        print(" -", e)
    sys.exit(1)
print("checksums OK")
print("postgres.dump", pg_bytes, "octets")
print("minio", minio_files, "objets /", minio_bytes, "octets")
print("secrets_included", m.get("secrets_included"))
print("git_sha", m.get("git_sha"))
PY

if command -v docker >/dev/null 2>&1; then
  log "TOC pg_restore (liste des objets)"
  docker run --rm -v "$(host_path "$SNAP"):/snap:ro" postgres:16-alpine \
    pg_restore -l /snap/postgres.dump >/dev/null
  ok "TOC Postgres lisible"
else
  warn "docker absent : TOC Postgres non contrôlé"
fi

if [[ -f "${SNAP}/secrets.env.enc" ]]; then
  if resolve_passphrase; then
    TMP="$(mktemp_host "$SNAP")"
    decrypt_secrets_file "${SNAP}/secrets.env.enc" "$TMP"
    if grep -q '^FIELD_ENCRYPTION_KEY=' "$TMP"; then
      ok "Secrets déchiffrables (FIELD_ENCRYPTION_KEY présent)"
    else
      rm -f "$TMP"
      die "Secrets déchiffrés mais FIELD_ENCRYPTION_KEY absent"
    fi
    rm -f "$TMP"
  else
    warn "Pas de passphrase : secrets non déchiffrés (checksum déjà vérifié)"
  fi
fi

ok "Snapshot conforme : ${SNAP}"
