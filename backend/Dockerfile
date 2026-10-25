# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

# Dépendances système (build psycopg2, Pillow, netcat pour l'attente DB)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential libpq-dev netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Certificats CA d'entreprise (proxy à inspection TLS). Le bundle local
# (non versionné) est ajouté au magasin système ; pip et le runtime pointent
# vers ce magasin, qui contient déjà les racines publiques. Robuste que le
# bundle d'entreprise soit présent, vide ou absent.
COPY certs/ /certs/
# Hors proxy d'entreprise le dossier peut ne contenir que .gitkeep.
RUN touch /certs/ca-bundle.crt \
    && if [ -s /certs/ca-bundle.crt ]; then \
        cat /certs/ca-bundle.crt >> /etc/ssl/certs/ca-certificates.crt; \
    fi
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

COPY requirements/ requirements/
RUN pip install --upgrade pip && pip install -r requirements/prod.txt

COPY . .

# Normalise les fins de ligne (checkout Windows) puis rend exécutable
RUN sed -i 's/\r$//' docker/entrypoint.sh && chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
