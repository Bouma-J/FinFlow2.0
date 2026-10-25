# Isolation multi-tenant — options long terme

## Mode actuel : `shared` (défaut)

- Une base PostgreSQL, colonne `tenant_id` + `TenantManager`.
- Adapté aux pilotes et à la consolidation Groupe (requêtes `all_tenants`).
- Variable : `TENANT_ISOLATION_MODE=shared`.

## Mode cible réglementaire : `schema`

Quand une filiale / pays exige une séparation forte :

1. Introduire `django-tenants` **ou** schémas Postgres manuels (`SET search_path`).
2. Garder `TenantScopedModel` comme façade — le manager bascule selon `TENANT_ISOLATION_MODE`.
3. La consolidation Groupe passe par une base de reporting / snapshots (déjà en place) plutôt que des jointures cross-schema live.

## Checklist avant bascule schema-per-tenant

- [ ] Inventaire des accès `all_tenants` (reporting, Celery, audit)
- [ ] Stratégie de migration des données existantes
- [ ] Connexions / pooling (PgBouncer session vs transaction)
- [ ] Backups et restauration par filiale
- [ ] Tests d'isolement (fuite cross-tenant)

Le code métier ne doit **pas** hardcoder le mode ; utiliser `settings.TENANT_ISOLATION_MODE`.
