# 09 — Montée en charge

FIN_FLOW a été préparé en **trois phases**. Script de validation : `backend/scripts/test_scale_phases.py`.

## 1. Court terme (fondations)

| Mesure | Détail |
|--------|--------|
| Stockage objet | MinIO/S3 branché (`STORAGE_BACKEND=s3`) |
| Pagination UI | Précédent / suivant sur listes principales |
| Throttling | Classes DRF + limite login |
| Pooling DB | `CONN_MAX_AGE` (+ PgBouncer recommandé plus tard) |
| Listes API | Serializers allégés (crédits, clients, garanties, cautions) |

## 2. Moyen terme (pilote)

| Mesure | Détail |
|--------|--------|
| Cache Redis | Dashboard, `/users/me/`, catalogue produits |
| Celery | SLA, PAR, retry CBS, purge audit, GED, contrats async |
| Présign S3 | Download / upload hors Gunicorn |
| MFA TOTP | Enrôlement + gate login |
| JWT blacklist | Logout + rotation |
| Index | `(tenant, reference)` clients & dossiers |

## 3. Long terme (scale)

| Mesure | Détail |
|--------|--------|
| Snapshots reporting | Agrégats matérialisés (beat horaire) |
| Quotas GED | Par filiale |
| Lifecycle S3 | `deploy/s3/lifecycle.json` |
| Health / metrics | Probes K8s + JSON exploitation |
| CI/CD | GitHub Actions `.github/workflows/ci.yml` |
| Kubernetes | Manifests + HPA backend |
| Isolation | `TENANT_ISOLATION_MODE` ; schéma documenté, non basculé |

## 4. Capacités cibles (indicatif)

| Échelle | Aptitude |
|---------|----------|
| Démo / 1–2 filiales | Compose tel quel |
| Pilote régional | Phase 1+2 + Postgres/Redis dimensionnés |
| Multi-pays | Phase 3 + K8s, S3 managé, reporting snapshots, supervision |

## 5. Recommandations ops

1. Mettre PgBouncer devant Postgres dès que les workers API se multiplient.  
2. Monitorer files Celery et latence p95 (`load_smoke.py`, APM/Sentry).  
3. Ne jamais servir le GED depuis le disque local d’un pod multi-replica.  
4. Pour la consolidation Groupe massive, s’appuyer sur les **snapshots** (`?live=1` seulement en diagnostic).  
5. Planifier l’isolation schéma uniquement si contrainte réglementaire (voir `docs/TENANT_ISOLATION.md`).
