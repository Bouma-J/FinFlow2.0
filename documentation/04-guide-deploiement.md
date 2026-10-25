# 04 — Guide de déploiement complet

> **Dépôt Git :** [https://github.com/Bouma-J/FinFlow](https://github.com/Bouma-J/FinFlow)  
> (`git clone https://github.com/Bouma-J/FinFlow.git`)
>
> **Production sur Ubuntu Server** (outils, Docker, Nginx/TLS, sauvegardes) :  
> voir le guide dédié [13 — Déploiement Ubuntu](13-guide-deploiement-ubuntu.md)  
> et le fichier `docker-compose.prod.yml` à la racine du dépôt.

## 1. Prérequis

| Élément | Minimum |
|---------|---------|
| Docker Engine + Compose v2 | Recommandé |
| RAM hôte | ≥ 8 Go pour la stack complète |
| Disque | ≥ 20 Go (images + volumes + GED) |
| Ports libres | 8080 (SPA Docker démo), 9000, 9001 (et 5432/6379 si exposés). Port 80 en production Ubuntu derrière Nginx. |

Pour un déploiement « bare metal » hors Docker : Python 3.12, Node 20, PostgreSQL 16, Redis 7, bucket S3.

## 2. Déploiement Docker Compose (référence démo / UAT)

### 2.1 Fichiers
À la racine du dépôt :
- `docker-compose.yml`
- `backend/`, `frontend/`
- Variables optionnelles dans un `.env` racine (e-mail, secrets)

### 2.2 Premier démarrage

```bash
cd "fin flow"
docker compose up -d --build
```

Services démarrés : `db`, `redis`, `minio`, `backend`, `worker`, `beat`, `frontend`.

Au démarrage backend :
1. Attente PostgreSQL
2. Création bucket MinIO `finflow-documents`
3. `migrate` + `collectstatic`
4. `seed_demo` **uniquement si** `SEED_DEMO=1`

Par défaut Compose force `SEED_DEMO=0` (base propre). Pour peupler la démo :

```bash
SEED_DEMO=1 docker compose up -d --build backend
```

### 2.3 Vérifications

```bash
docker compose ps
curl http://localhost:8080/api/v1/health/
# → {"status":"ok","ready":true,...}
```

| URL | Attendu |
|-----|---------|
| http://localhost:8080 | SPA |
| http://localhost:8080/api/docs/ | Swagger |
| http://localhost:9001 | MinIO (`minioadmin` / `minioadmin`) |

### 2.4 Comptes après seed

- `group_admin` / `FinFlow2026!`
- `fil01_admin` / `FinFlow2026!`

Sans seed : seul le compte que vous créez (ou celui recréé manuellement) existe.

### 2.5 Rebuild après changement code

```bash
docker compose up -d --build backend frontend worker beat
```

Les images backend sont **bakées** (pas de volume code) : un rebuild est obligatoire après modification Python.

### 2.6 Logs et maintenance

```bash
docker compose logs -f backend worker beat
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py shell
```

### 2.7 Remise à zéro base (destructif)

```bash
docker compose exec backend python manage.py flush --no-input
# puis recréer group_admin (voir scripts / seed)
```

## 3. Configuration production (Compose ou VM)

Checklist minimale :

1. `DJANGO_SECRET_KEY` fort et unique  
2. `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` restreints  
3. `DJANGO_SECURE_SSL_REDIRECT=True` derrière un reverse-proxy TLS (domaine **ou** IP : voir [13 §8.1](13-guide-deploiement-ubuntu.md#81-tls-et-hsts-sans-nom-de-domaine))  
4. Postgres managé + sauvegardes ; `DB_CONN_MAX_AGE` adapté (0 avec PgBouncer transaction)  
5. Redis dédié (broker + cache DB index distincts)  
6. MinIO / S3 avec credentials non par défaut + lifecycle (`deploy/s3/lifecycle.json`)  
7. SMTP réel (désactiver le backend console)  
8. `SEED_DEMO=0`  
9. `SENTRY_DSN` renseigné  
10. Secrets hors dépôt (`.env` non versionné, Vault, etc.)

Exemple reverse-proxy : Nginx/Traefik termine TLS et route vers frontend `:80` (qui proxy déjà l’API).

## 4. Déploiement Kubernetes

Manifests : `deploy/k8s/`

```bash
kubectl apply -f deploy/k8s/00-namespace-config.yaml
kubectl apply -f deploy/k8s/10-backend.yaml
kubectl apply -f deploy/k8s/20-worker-frontend.yaml
```

Points d’attention :
- Pousser les images `finflow-backend` / `finflow-frontend` vers votre registry et adapter les noms d’image.
- Remplacer le `Secret` exemple par External Secrets / Sealed Secrets.
- **Beat : 1 seul replica** (pas de HPA beat).
- Backend : HPA CPU 70 %, 2–8 pods ; probes sur `/api/v1/health/`.
- Postgres / Redis / objet storage **externes** recommandés (pas dans les manifests de démo).
- Ingress exemple : `finflow.example.com` (adapter + TLS cert-manager).

Voir `deploy/k8s/README.md`.

## 5. Déploiement local développeur (sans Docker full stack)

```powershell
# Backend
cd backend
..\env_virtuel\Scripts\activate
copy .env.example .env
pip install -r requirements\dev.txt
python manage.py migrate
python manage.py runserver

# Frontend
cd frontend
npm install
npm run dev
```

API : http://127.0.0.1:8000 — SPA : http://localhost:5173  
Configurer CORS et `VITE_API_BASE_URL` si besoin.

## 6. Migrations et données

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_demo   # optionnel
```

Scripts utiles :
- `backend/scripts/test_scale_phases.py` — validation 3 phases scale  
- `backend/scripts/load_smoke.py` — smoke de charge  
- `backend/scripts/e2e_dossier_global.py` — parcours dossier (si présent)

## 7. Sauvegarde / restauration

Mécanisme d’instance : `deploy/backup/backup.sh` (Postgres `-Fc` + MinIO +
secrets chiffrés), `verify.sh`, `restore.sh --target drill|live`. Détail et
cron : [13 — Déploiement Ubuntu §11](13-guide-deploiement-ubuntu.md).

| Volume / composant | Action |
|--------------------|--------|
| PostgreSQL | inclus dans le snapshot (`pg_dump -Fc`) |
| MinIO/S3 | miroir du bucket + versioning recommandé |
| Redis | non sauvegardé (cache / files Celery) |
| Secrets | `secrets.env.enc` dans le snapshot (`FIELD_ENCRYPTION_KEY`) |

## 8. Mise à jour d’une release

1. Backup DB + bucket  
2. `git pull`  
3. `docker compose up -d --build`  
4. Vérifier `/api/v1/health/` et Swagger  
5. Smoke login + dashboard  

## 9. Dépannage rapide

| Symptôme | Piste |
|----------|-------|
| 502 sur /api | Backend down — `docker compose logs backend` |
| Health storage KO | MinIO / credentials S3 |
| Login MFA bloqué | `auth/mfa/disable` ou reset `mfa_secret` en admin |
| Fichiers 404 | `STORAGE_BACKEND` et `AWS_S3_CUSTOM_DOMAIN` |
| Worker silencieux | Redis, `CELERY_BROKER_URL`, logs worker |
| Seed réapparaît | `SEED_DEMO` encore à 1 |
