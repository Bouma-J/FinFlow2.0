# Déploiement Kubernetes FIN_FLOW

## Prérequis
- Cluster K8s 1.28+
- Images `finflow-backend` et `finflow-frontend` poussées dans un registry
- PostgreSQL managé (recommandé) + Redis HA + bucket S3/MinIO

## Appliquer
```bash
kubectl apply -f deploy/k8s/00-namespace-config.yaml
kubectl apply -f deploy/k8s/10-backend.yaml
kubectl apply -f deploy/k8s/20-worker-frontend.yaml
```

## Notes
- `DB_CONN_MAX_AGE=0` si PgBouncer en mode transaction devant Postgres.
- Beat : **1 seul** replica (leader election non inclus — ne pas scaler beat).
- Health : `GET /api/v1/health/` pour probes.
- Secrets : remplacer le Secret exemple par External Secrets / Vault.
- HPA backend : CPU 70 %, 2–8 pods.
