# 02 — Architecture technique

## 1. Vue d’ensemble

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Navigateur │────▶│ Nginx (SPA)  │────▶│ Django API  │
│  React SPA  │     │  :80         │     │ Gunicorn    │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                    ┌──────────────┬─────────────┼─────────────┐
                    ▼              ▼             ▼             ▼
               PostgreSQL       Redis        MinIO/S3      Celery
               (données)     (cache/broker)  (GED)     worker + beat
```

## 2. Stack

| Couche | Technologie |
|--------|-------------|
| Frontend | React 18, TypeScript, Vite 6, TanStack Query, React Router 6, Axios |
| Backend | Python 3.12, Django 5.1, Django REST Framework |
| Auth | SimpleJWT (+ token blacklist), MFA TOTP (`pyotp`) |
| Async | Celery 5 + Redis |
| DB | PostgreSQL 16 (prod) ; SQLite possible en dev local |
| Fichiers | django-storages + boto3 → MinIO / S3 |
| Docs API | OpenAPI 3 (drf-spectacular) + Swagger UI |
| Conteneurs | Docker Compose ; manifests Kubernetes dans `deploy/k8s/` |

## 3. Modules backend (`backend/apps/`)

| App | Responsabilité |
|-----|----------------|
| `common` | Tenancy, pagination, cache helpers, health/metrics, middleware |
| `tenants` | Filiales, agences, branding, quotas GED |
| `accounts` | Users, rôles filiale, délégations, MFA/JWT views |
| `catalog` | Produits, catégories, motifs de rejet, checklists |
| `clients` | Référentiel client KYC |
| `credits` | Dossiers, analyses, prêts, échéanciers, frais |
| `workflow` | Circuits, tâches, SLA |
| `documents` | GED, upload présigné, quotas |
| `guarantees` | Sûretés, mouvements, dations, mains levées |
| `sureties` | Cautions et engagements |
| `contracts` | Modèles et génération (sync / async Celery) |
| `corebanking` | Connecteurs, journaux, retries |
| `collections` | Recouvrement PAR |
| `audit` | Piste d’audit + purge |
| `reporting` | Dashboards + snapshots |
| `notifications` | E-mails workflow / SLA |

## 4. Frontend (`frontend/src/`)

- `api/` — client Axios, types TypeScript
- `auth/` — contexte JWT, MFA login
- `pages/` — écrans métier et admin
- `components/` — formulaires, UI, décisions workflow
- Build prod servi par Nginx (proxy `/api`, `/django-admin`, `/static`, `/media` ; `/admin/*` = SPA)

## 5. Isolation multi-tenants

1. `TenantScopedModel` + `TenantManager` filtrent par `tenant_id`.
2. Le contexte courant est posé après authentification JWT (`TenantContextMixin` / middleware).
3. Utilisateur Groupe : `is_group_level=True` + en-tête `X-Tenant-Id`.
4. Accès transverse : manager `all_tenants` (reporting Groupe, Celery, admin).

## 6. Stockage documentaire

- `STORAGE_BACKEND=s3` en Compose → MinIO bucket `finflow-documents`.
- URLs de téléchargement / upload **présignées**.
- Hash SHA-256, versioning GED, plafond fichier (`GED_MAX_UPLOAD_SIZE_MB`).
- Quotas par filiale : `ged_quota_bytes` / `ged_used_bytes`.

## 7. Traitements asynchrones (Celery Beat)

| Tâche | Fréquence |
|-------|-----------|
| SLA dépassés | 15 min |
| Retry CBS | 10 min |
| Snapshots reporting | chaque heure (:20) |
| Retards PAR | 02:15 |
| Purge audit | 03:30 |
| Docs expirants | 07:00 |

## 8. Sécurité technique

- Throttling DRF (anon / user / burst) + throttle login
- HSTS, cookies sécurisés, SSL redirect (prod)
- MFA TOTP optionnel par utilisateur
- Blacklist des refresh tokens à la déconnexion / rotation
- Sentry optionnel (Django + Celery + Redis)

## 9. Observabilité

- `GET /api/v1/health/` — DB, cache, stockage (probes K8s)
- `GET /api/v1/metrics/` — volumes (admin / Groupe)
- En-tête `X-Response-Time-Ms` + logs des requêtes lentes
