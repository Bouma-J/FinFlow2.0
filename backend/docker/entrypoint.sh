#!/usr/bin/env bash
set -e

# Attente de la base de données (si DATABASE_URL de type postgres)
if [ -n "$POSTGRES_HOST" ]; then
  echo "En attente de PostgreSQL sur ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}…"
  until nc -z "$POSTGRES_HOST" "${POSTGRES_PORT:-5432}"; do
    sleep 1
  done
  echo "PostgreSQL est prêt."
fi

# Création du bucket MinIO/S3 si nécessaire
if [ "${STORAGE_BACKEND:-local}" = "s3" ] && [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  echo "Vérification du bucket S3 « ${AWS_STORAGE_BUCKET_NAME:-finflow-documents} »…"
  python - <<'PY'
import os
import sys
import time

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

endpoint = os.environ.get("AWS_S3_ENDPOINT_URL") or ""
bucket = os.environ.get("AWS_STORAGE_BUCKET_NAME", "finflow-documents")
key = os.environ.get("AWS_ACCESS_KEY_ID", "")
secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
region = os.environ.get("AWS_S3_REGION_NAME", "us-east-1")

if not endpoint or not key:
    print("S3 non configuré (endpoint/clé manquants) — skip bucket.")
    sys.exit(0)

client = boto3.client(
    "s3",
    endpoint_url=endpoint,
    aws_access_key_id=key,
    aws_secret_access_key=secret,
    region_name=region,
    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
)

for attempt in range(30):
    try:
        client.head_bucket(Bucket=bucket)
        print(f"Bucket « {bucket} » OK.")
        break
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket", "NotFound"):
            try:
                client.create_bucket(Bucket=bucket)
                print(f"Bucket « {bucket} » créé.")
                try:
                    # Origines CORS : liste séparée par des virgules
                    # (DJANGO_CORS_ALLOWED_ORIGINS), sinon localhost démo.
                    raw_origins = os.environ.get(
                        "DJANGO_CORS_ALLOWED_ORIGINS", ""
                    ).strip()
                    if raw_origins:
                        origins = [
                            o.strip()
                            for o in raw_origins.split(",")
                            if o.strip()
                        ]
                    else:
                        origins = [
                            "http://localhost",
                            "http://localhost:8080",
                            "http://localhost:5173",
                        ]
                    client.put_bucket_cors(
                        Bucket=bucket,
                        CORSConfiguration={
                            "CORSRules": [
                                {
                                    "AllowedOrigins": origins,
                                    "AllowedMethods": [
                                        "GET",
                                        "HEAD",
                                        "PUT",
                                        "POST",
                                    ],
                                    "AllowedHeaders": ["*"],
                                    "ExposeHeaders": ["ETag", "Location"],
                                    "MaxAgeSeconds": 3600,
                                }
                            ]
                        },
                    )
                except ClientError as cors_exc:
                    print(f"CORS bucket ignoré ({cors_exc})")
                break
            except ClientError as create_exc:
                print(f"Création bucket en attente… ({create_exc})")
        else:
            print(f"MinIO pas prêt ({exc}) — tentative {attempt + 1}/30")
        time.sleep(1)
    except Exception as exc:  # noqa: BLE001
        print(f"MinIO pas prêt ({exc}) — tentative {attempt + 1}/30")
        time.sleep(1)
else:
    print("Impossible de joindre MinIO — démarrage quand même.", file=sys.stderr)
PY
fi

# Migrations et fichiers statiques (idempotents) — uniquement côté web
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput

  # Seed des données de démonstration (désactivable via SEED_DEMO=0)
  if [ "${SEED_DEMO:-1}" = "1" ]; then
    python manage.py seed_demo || echo "seed_demo ignoré (déjà exécuté ?)"
  fi
fi

exec "$@"
