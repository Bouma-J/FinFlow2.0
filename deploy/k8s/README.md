# Référence Kubernetes FIN_FLOW

Ces manifests sont des modèles à adapter au cluster. Ils ne sont pas un
installateur autonome : ils supposent un registre privé, PostgreSQL, Redis et
un stockage S3 déjà opérationnels.

## Préparer les paramètres

1. Construire puis publier `backend/` et `frontend/` dans le registre approuvé.
   Remplacer dans `10-backend.yaml`, `20-worker-frontend.yaml` et
   `30-migrate.yaml` les références `registry.example.com/...@sha256:...` par
   les digests réellement publiés. Les références par digest rendent le
   déploiement reproductible.
2. Vérifier et remplacer `10.2.203.0/24` dans l'annotation
   `whitelist-source-range` de l'Ingress par le CIDR exact des postes LAN.
   L'Ingress Controller / LoadBalancer doit lui-même être joignable uniquement
   depuis le réseau privé ; l'annotation seule ne remplace pas le pare-feu du
   cluster.
3. Configurer l'hôte `finflow.example.com` dans
   `00-namespace-config.yaml` et `20-worker-frontend.yaml`.
4. Créer hors du dépôt un fichier `finflow-k8s-secrets.env`, permissions
   `0600`, contenant les secrets et URLs runtime, notamment :

   ```env
   DJANGO_SECRET_KEY=valeur-aleatoire-longue
   FIELD_ENCRYPTION_KEY=cle-fernet-valide
   DATABASE_URL=postgres://finflow:mot-de-passe@postgres.example:5432/finflow
   CELERY_BROKER_URL=redis://redis.example:6379/0
   CELERY_RESULT_BACKEND=redis://redis.example:6379/1
   REDIS_CACHE_URL=redis://redis.example:6379/2
   AWS_ACCESS_KEY_ID=identifiant-s3
   AWS_SECRET_ACCESS_KEY=secret-s3
   AWS_S3_ENDPOINT_URL=https://s3.example
   SENTRY_DSN=
   ```

   Créer ou mettre à jour le Secret Kubernetes sans afficher ses valeurs :

   ```bash
   chmod 600 finflow-k8s-secrets.env
   kubectl create namespace finflow --dry-run=client -o yaml | kubectl apply -f -
   kubectl create secret generic finflow-secrets -n finflow \
     --from-env-file=finflow-k8s-secrets.env --dry-run=client -o yaml \
     | kubectl apply -f -
   ```

5. Créer le Secret TLS `finflow-tls` depuis le certificat de l'autorité interne
   approuvée :

   ```bash
   kubectl create secret tls finflow-tls -n finflow \
     --cert=finflow.crt --key=finflow.key
   ```

Ne committez ni le fichier de secrets ni les clés privées. Activez le chiffrement
des Secrets Kubernetes au repos et préférez External Secrets/Vault dans un
cluster partagé.

## Première installation

```bash
kubectl apply -f deploy/k8s/00-namespace-config.yaml
kubectl delete job finflow-migrate -n finflow --ignore-not-found
kubectl apply -f deploy/k8s/30-migrate.yaml
kubectl wait -n finflow --for=condition=complete job/finflow-migrate --timeout=10m
kubectl apply -f deploy/k8s/10-backend.yaml
kubectl apply -f deploy/k8s/20-worker-frontend.yaml
```

La migration est un Job unique avant le déploiement web ; les pods backend ne
lancent pas eux-mêmes les migrations en parallèle. La route `backend` est un
alias interne requis par `frontend/nginx.conf`.

## Mise à jour

Publier d'abord les nouvelles images et remplacer les digests dans les trois
manifests. Supprimer puis recréer le Job de migration avant de mettre à jour les
Deployments. Vérifier ensuite les rollouts :

```bash
kubectl delete job finflow-migrate -n finflow --ignore-not-found
kubectl apply -f deploy/k8s/30-migrate.yaml
kubectl wait -n finflow --for=condition=complete job/finflow-migrate --timeout=10m
kubectl apply -f deploy/k8s/10-backend.yaml
kubectl apply -f deploy/k8s/20-worker-frontend.yaml
kubectl rollout status -n finflow deployment/finflow-backend
kubectl rollout status -n finflow deployment/finflow-frontend
```

## Limites à traiter avant production Kubernetes

- Fournir les Services et politiques de haute disponibilité pour PostgreSQL,
  Redis et S3, ou leurs services managés.
- Configurer sauvegarde/restauration PostgreSQL et S3 hors cluster.
- Vérifier NetworkPolicy selon le CNI, les sauvegardes des Secrets, quotas,
  alertes, autoscaling et stratégie de migration/rollback.
- Le dépôt ne contient pas de pipeline CI qui construit et publie ces images.
  La procédure Ubuntu Compose reste la méthode de déploiement actuellement
  automatisée dans le projet.
