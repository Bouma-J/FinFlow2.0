# 13 — Guide de déploiement Ubuntu (production)

Guide pas à pas pour déployer **FIN_FLOW** sur **Ubuntu Server 22.04, 24.04 ou 26.04 LTS**, avec Docker Compose, reverse-proxy TLS et l’ensemble des outils nécessaires.

**Dépôt Git :** [https://github.com/Bouma-J/FinFlow2.0](https://github.com/Bouma-J/FinFlow2.0)<br>
**Clone (dépôt privé) :** `git clone git@github.com:Bouma-J/FinFlow2.0.git`

Pour la vue d’ensemble multi-environnements (Compose démo, Kubernetes, bare metal), voir aussi [04 — Guide de déploiement](04-guide-deploiement.md).

### Installation assistée (recommandée)

Deux scripts interactifs au choix :

| Script | Cas d’usage | Accès |
|--------|-------------|--------|
| [`deploy/ubuntu-install.sh`](../deploy/ubuntu-install.sh) | Domaines internes, filtrage LAN | `http://finflow.…` |
| [`deploy/ubuntu-install-ip.sh`](../deploy/ubuntu-install-ip.sh) | Réseau local / IP privée seule | `http://<IP>/` ou HTTPS auto-signé |
| [`deploy/ubuntu-deploy-local.sh`](../deploy/ubuntu-deploy-local.sh) | Installation ou mise à jour depuis un ZIP extrait, sans Git | LAN |
| [`deploy/tls-ip/enable-ip-tls.sh`](../deploy/tls-ip/enable-ip-tls.sh) | HTTPS sur une install IP déjà en place | `https://<IP>/` |
| [`deploy/ubuntu-update.sh`](../deploy/ubuntu-update.sh) | **Mise à jour** d’une instance déjà en prod | — |

#### Déploiement depuis un ZIP local (sans Git)

Le ZIP source ne contient ni `.git`, ni secrets, ni base de données. Après l'avoir
transféré et extrait sur le serveur, lancez le script depuis le répertoire
`FinFlow2.0` extrait :

```bash
unzip FinFlow2.0-<commit>.zip -d /tmp/finflow-release
cd /tmp/finflow-release/FinFlow2.0

# Première installation — adresse IP privée
sudo bash deploy/ubuntu-deploy-local.sh --install-ip /opt/finflow

# Ou première installation — noms DNS internes
sudo bash deploy/ubuntu-deploy-local.sh --install-domain /opt/finflow

# Mise à jour d'une instance existante
sudo bash deploy/ubuntu-deploy-local.sh --update /opt/finflow
```

Le mode `--update` crée et vérifie d’abord un snapshot chiffré complet, synchronise
le code en préservant `.env`, les données, les volumes et les marqueurs LAN/TLS,
puis reconstruit les images, applique les migrations et vérifie la santé. Sur une
installation créée sans Git, `sudo finflow-update /tmp/finflow-release/FinFlow2.0`
utilise le nouveau ZIP extrait pour les mises à jour suivantes. Conservez la
phrase de chiffrement des sauvegardes hors du serveur. Le script local n'envoie
pas les fichiers `.env`, bases SQLite, certificats locaux, dépendances Node ou
journaux présents dans le dossier source.

**Avec des noms DNS internes (les ports restent limités au LAN) :**

```bash
# depuis le dépôt cloné avec un accès GitHub autorisé :
sudo bash deploy/ubuntu-install.sh
```

**Par adresse IP privée (sans domaine — HTTP, ou HTTPS auto-signé) :**

```bash
# depuis le dépôt cloné avec un accès GitHub autorisé :
sudo bash deploy/ubuntu-install-ip.sh
```

**Mise à jour (instance déjà déployée) :**

```bash
sudo finflow-update
# ou depuis le dépôt cloné :
sudo bash /opt/finflow/deploy/ubuntu-update.sh
```

L’update vérifie un snapshot chiffré complet avant de modifier le code ; si sa création ou sa vérification échoue, l’application n’est pas mise à jour. Il contrôle ensuite l’API, le frontend, PostgreSQL, Redis et les services Celery. Un échec interrompt l’opération et affiche la révision précédente ainsi que le snapshot à restaurer si le schéma a changé. Il n’y a pas de retour arrière automatique des migrations. Les deux installateurs limitent les ports d’entrée au CIDR LAN saisi. Le mode IP lie aussi MinIO à l’adresse IP privée de FinFlow ; le filtre Docker `DOCKER-USER` protège ce port, car les ports publiés par Docker ne sont pas filtrés de façon fiable par UFW seul. Le profil IP+TLS place MinIO derrière Nginx sur `127.0.0.1:19000`.

#### Reprise d’une installation interrompue

Après un échec de l’installateur IP, reprenez à partir du `.env` conservé :

```bash
sudo bash /opt/finflow/deploy/ubuntu-install-ip.sh --resume /opt/finflow
```

Pour une ancienne instance dont la sauvegarde installée est trop ancienne, lancez l’updater depuis une copie récente du dépôt. Il actualise uniquement les outils de sauvegarde, crée et vérifie le snapshot, puis reprend le déploiement :

```bash
sudo bash ~/FinFlow2.0/deploy/ubuntu-update.sh /opt/finflow
```

---

## 1. Architecture déployée

| Composant | Rôle | Conteneur / service |
|-----------|------|---------------------|
| Frontend (Nginx) | SPA React + proxy `/api` | `frontend` |
| Backend (Gunicorn) | API Django / DRF | `backend` |
| Celery worker | Tâches async (e-mails, contrats, CBS…) | `worker` |
| Celery beat | Planification périodique | `beat` |
| PostgreSQL 16 | Base de données | `db` |
| Redis 7 | Broker Celery + cache | `redis` |
| MinIO | Stockage GED / contrats (S3) | `minio` |
| Nginx hôte | Reverse-proxy LAN, TLS interne optionnel | hors Compose |

Flux navigateur typique sur le réseau local :

```text
LAN autorisé → Nginx (80/443) → frontend:80 → API / SPA
                       ↘ MinIO:9000 (URLs présignées fichiers)
```

---

## 2. Prérequis matériel

| Ressource | Minimum | Recommandé (prod légère) |
|-----------|---------|---------------------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 8 Go | 16 Go |
| Disque | 40 Go SSD | 80 Go+ SSD |
| OS | Ubuntu 22.04 / 24.04 / 26.04 LTS 64-bit | idem |
| Docker Compose | 2.24.4 minimum (`!override` requis par les fichiers Compose) | version stable fournie par le dépôt Docker |
| Réseau | IP privée et CIDR LAN connus | segmentation réseau dédiée |

Ports à prévoir (firewall) :

| Port | Usage |
|------|--------|
| 22 | SSH |
| 80 | HTTP (application) — CIDR LAN uniquement |
| 443 | HTTPS (application) — CIDR LAN uniquement |
| 9000 | MinIO API (fichiers présignés) — CIDR LAN uniquement |
| 9001 | Console MinIO — **ne pas exposer** en prod (SSH tunnel uniquement) |

---

## 3. Outils système à installer

Connectez-vous en SSH (utilisateur avec `sudo`).

### 3.1 Mise à jour et paquets de base

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
  ca-certificates \
  curl \
  wget \
  gnupg \
  lsb-release \
  apt-transport-https \
  software-properties-common \
  git \
  unzip \
  jq \
  htop \
  net-tools \
  openssl \
  ufw \
  fail2ban \
  nginx
```

| Outil | Utilité |
|-------|---------|
| `git` | Récupération du code |
| `curl` / `wget` / `jq` | Tests health, scripts |
| `openssl` | Secrets, TLS |
| `ufw` | Pare-feu |
| `fail2ban` | Protection SSH |
| `nginx` | Reverse-proxy LAN ; TLS interne si certificat disponible |
| `htop` | Supervision rapide |

### 3.2 Docker Engine + Compose v2 (plugin officiel)

```bash
# Dépôt Docker officiel
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

# Démarrage auto
sudo systemctl enable --now docker

# (Optionnel) lancer Docker sans sudo
sudo usermod -aG docker "$USER"
# Puis se déconnecter / reconnecter
```

Vérification :

```bash
docker --version
docker compose version
docker run --rm hello-world
```

### 3.3 Pare-feu UFW

Les installateurs configurent UFW à partir du CIDR LAN saisi et installent un filtre `DOCKER-USER` persistant pour le port MinIO. Ne remplacez pas ces règles par `ufw allow 22/tcp`, `ufw allow 80/tcp` ou des règles équivalentes sans source : elles ouvriraient ces ports à toutes les adresses. Le port `9001` (console MinIO), PostgreSQL `5432` et Redis `6379` ne sont jamais ouverts au réseau.

### 3.4 Fail2ban (SSH)

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

### 3.5 Noms DNS internes (facultatif)

Pour l'accès LAN, utilisez le DNS interne de l'organisation ou un nom local résolu par les postes clients. Aucun enregistrement DNS public ni challenge Let’s Encrypt n'est requis.

Les noms doivent pointer vers l'adresse privée du serveur. Si vous utilisez le fichier `/etc/hosts`, ajoutez les entrées sur chaque poste client, pas seulement sur le serveur :

| Type | Nom | Valeur | Où le configurer |
|------|-----|--------|------------------|
| A | `finflow.intra` | IP privée du serveur FinFlow | DNS interne |
| A | `minio.finflow.intra` | IP privée du serveur FinFlow | DNS interne |

Vérification depuis n’importe quelle machine :

```bash
dig +short finflow.intra
# doit renvoyer l’adresse privée du serveur
```

> **Exception lab / sans DNS :** vous pouvez ajouter une ligne dans `/etc/hosts` **sur chaque PC client** (celui du navigateur) :
> `IP_DU_SERVEUR  finflow.local minio.local`

> **Déploiement LAN pris en charge :** pour créer une instance, utilisez l’un
> des deux installateurs en haut de ce guide. Les exemples manuels des sections
> 4 à 9 expliquent les paramètres Compose, mais ne remplacent pas l’installateur
> et peuvent contourner la restriction LAN ou les contrôles de sauvegarde.


---

## 4. Récupération du projet

Dépôt officiel : **https://github.com/Bouma-J/FinFlow2.0.git**

```bash
sudo mkdir -p /opt/finflow
sudo chown "$USER":"$USER" /opt/finflow
cd /opt/finflow

git clone git@github.com:Bouma-J/FinFlow2.0.git .
```

Après l’installation, mettez le projet à jour uniquement avec `sudo finflow-update` afin de conserver le snapshot pré-update, la détection IP/TLS et les contrôles de santé.

Structure attendue à la racine : `docker-compose.yml`, `backend/`, `frontend/`, `documentation/`.

---

## 5. Fichier `.env` de production

Créer `/opt/finflow/.env` (ne jamais le committer) :

```bash
cd /opt/finflow
cp .env.example .env
chmod 600 .env
nano .env
```

Exemple minimal production :

```env
# --- Django ---
DJANGO_SECRET_KEY=REMPLACER_PAR_UNE_CLE_LONGUE_ALEATOIRE
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=finflow.intra,localhost,127.0.0.1,backend
DJANGO_SECURE_SSL_REDIRECT=False
DJANGO_CORS_ALLOWED_ORIGINS=http://finflow.intra

# --- Seed (toujours 0 en prod) ---
SEED_DEMO=0

# --- MinIO (changer les mots de passe par défaut) ---
MINIO_ROOT_USER=finflow_minio_admin
MINIO_ROOT_PASSWORD=MotDePasseMinIOTresLong!

AWS_S3_CUSTOM_DOMAIN=minio.finflow.intra
AWS_S3_URL_PROTOCOL=http:

# --- E-mail global (repli) ; chaque filiale peut avoir son SMTP en UI ---
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.intra
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=noreply@finflow.intra
EMAIL_HOST_PASSWORD=********
DEFAULT_FROM_EMAIL=FIN_FLOW <noreply@finflow.intra>
FRONTEND_BASE_URL=http://finflow.intra

# Images sélectionnées à l'installation ; utiliser des versions ou digests approuvés.
# Les images MinIO et minio-client doivent être joignables depuis le serveur.
POSTGRES_IMAGE=postgres:16-alpine
REDIS_IMAGE=redis:7-alpine
MINIO_IMAGE=cgr.dev/chainguard/minio:latest
MINIO_CLIENT_IMAGE=cgr.dev/chainguard/minio-client:latest
PYTHON_BASE_IMAGE=python:3.12-slim
NODE_BUILD_IMAGE=node:24-alpine
NGINX_RUNTIME_IMAGE=nginx:1.30-alpine

# En production Ubuntu : vérifier les certificats SMTP
SMTP_SSL_VERIFY=1

# Chiffrement au repos (mots de passe SMTP filiale) — généré par ubuntu-install.sh
# Ne pas régénérer après avoir enregistré des SMTP en UI.
# FIELD_ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
FIELD_ENCRYPTION_KEY=
```

Générer une clé secrète :

```bash
openssl rand -base64 48
```

Clé Fernet (chiffrement SMTP) :

```bash
openssl rand -base64 32 | tr '+/' '-_'
```

Les installateurs génèrent le `.env` et sélectionnent les surcharges Compose. Pour un déploiement existant, ne remplacez pas manuellement ses mots de passe ou URL : utilisez `finflow-update` après avoir vérifié les paramètres d'images.

---

## 6. Compose production

Le dépôt fournit déjà [`docker-compose.prod.yml`](../docker-compose.prod.yml) : il surcharge les secrets, force `SEED_DEMO=0`, `SMTP_SSL_VERIFY=1`, injecte `EMAIL_*` / `FIELD_ENCRYPTION_KEY` dans **backend + worker + beat**, et expose le frontend ainsi que MinIO localement. Le mode IP remplace la publication MinIO en HTTP par l'adresse LAN du serveur ; le profil IP+TLS le remet sur `127.0.0.1` derrière Nginx.

Ajouter dans `.env` :

```env
POSTGRES_PASSWORD=MotDePassePostgresTresLong!
AWS_S3_CUSTOM_DOMAIN=minio.finflow.intra
AWS_S3_URL_PROTOCOL=http:
```

Alias pratique :

```bash
echo "alias finflow='docker compose -f docker-compose.yml -f docker-compose.prod.yml'" >> ~/.bashrc
source ~/.bashrc
```

---

## 7. Premier démarrage de la stack

```bash
cd /opt/finflow

# Avec le fichier prod (sinon : docker compose up -d --build)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# Suivre le boot
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

Au démarrage du `backend` :

1. Attente PostgreSQL
2. Création du bucket MinIO `finflow-documents`
3. Migrations Django + `collectstatic`
4. Seed **désactivé** (`SEED_DEMO=0`)

Vérifications locales :

```bash
curl -sS http://127.0.0.1:8080/api/v1/health/
# → {"status":"ok","ready":true,...}
```

Créer le premier administrateur Groupe (`createsuperuser` positionne `is_group_level=True`) :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python manage.py createsuperuser
```

Si un superuser existant apparaît comme filiale, corriger :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python manage.py shell -c "from django.contrib.auth import get_user_model; u=get_user_model().objects.get(username='Admin'); u.is_group_level=True; u.tenant=None; u.agency=None; u.save(); print(u.username, u.is_group_level)"
```

Ou peupler une démo **uniquement en UAT** :

```bash
SEED_DEMO=1 docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend python manage.py seed_demo
```

Synchroniser les packs de rôles filiale :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec backend \
  python manage.py sync_role_packs
```

---

## 8. HTTPS interne

L'installation assistée configure HTTP et limite les ports au CIDR LAN. Le
mode IP peut activer un certificat auto-signé. Pour des noms DNS internes,
faites émettre les certificats par l'autorité interne de l'organisation et
configurez Nginx pour ces noms ; cette étape n'est pas automatisée par le
dépôt. Ne réouvrez pas les ports à toutes les adresses lors du provisionnement
TLS.

### 8.1 TLS sur IP et HSTS

Le déploiement type FinFlow est un **réseau interne (IP privée)**. L'installation automatique n'ouvre aucun port à Internet et n'utilise pas Let's Encrypt. HTTPS sur IP utilise un certificat auto-signé ou la PKI interne.

| Situation | Certificat | HSTS | Navigateur |
|-----------|------------|------|------------|
| **IP privée / LAN** | Auto-signé avec SAN `IP` ou PKI interne. | Désactivé avec le certificat auto-signé. | Avertissement navigateur ou confiance installée via la CA interne. |

Sur une instance interne déjà en HTTP :

```bash
sudo bash /opt/finflow/deploy/tls-ip/enable-ip-tls.sh /opt/finflow --self-signed
```

Le script refuse une IP publique et n'accepte que le mode auto-signé ; pour une confiance transparente, utilisez un certificat signé par la PKI interne.

Le script :

1. émet le certificat auto-signé sous `/etc/finflow/tls/current` ;
2. redirige HTTP:80 → HTTPS ;
3. termine le TLS aussi sur `:9000` (GED / URLs présignées) pour éviter le contenu mixte ;
4. pose `.finflow-tls-mode=selfsigned` et bascule Compose vers `docker-compose.ip-tls.yml` ;
5. aligne `.env` : `FRONTEND_BASE_URL=https://<IP>`, `DJANGO_SECURE_SSL_REDIRECT=True`, **HSTS à 0**.

Ne **pas** activer les valeurs Django du mode domaine (`SECURE_HSTS_SECONDS=31536000`, `INCLUDE_SUBDOMAINS`, `PRELOAD`) sur une IP interne.

Contrôle :

```bash
curl -k -fsSI https://<IP>/api/v1/health/
# Aucun en-tête Strict-Transport-Security (HSTS off)
```

---

## 9. Checklist post-installation

1. [ ] `http://finflow.intra` (ou l'URL LAN configurée) charge la SPA
2. [ ] `/api/v1/health/` depuis le LAN renvoie `ready: true`
3. [ ] Les routes API attendues sont accessibles depuis le LAN
4. [ ] Connexion admin + création d’une filiale
5. [ ] **Administration → Alertes e-mail** : SMTP filiale + test d’envoi
6. [ ] Génération d’un contrat / upload document → téléchargement OK (MinIO présigné)
7. [ ] `SMTP_SSL_VERIFY=1`
8. [ ] `FIELD_ENCRYPTION_KEY` présent dans `.env` (installateur ou ajout manuel)
9. [ ] `SEED_DEMO=0`
10. [ ] Mots de passe DB / MinIO / Django distincts et forts
11. [ ] Console MinIO `:9001` non exposée
12. [ ] Worker Celery up (`finflow ps`)
13. [ ] Sauvegardes planifiées (section 11)

---

## 10. Commandes d’exploitation courantes

### 10.1 Mise à jour assistée (recommandée)

```bash
sudo finflow-update
# équivalent :
sudo bash /opt/finflow/deploy/ubuntu-update.sh

# Contrôle sans toucher à la stack (Compose IP / TLS)
sudo bash /opt/finflow/deploy/ubuntu-update.sh --check /opt/finflow
```

Options utiles :

```bash
# Branche / répertoire personnalisés
GIT_BRANCH=main INSTALL_DIR=/opt/finflow sudo -E bash /opt/finflow/deploy/ubuntu-update.sh
```

Le script détecte automatiquement le mode **domaine** ou **IP** (`.finflow-deploy-mode`, `.finflow-tls-mode`, ou heuristique `.env`) via [`deploy/compose-files.sh`](../deploy/compose-files.sh). Il contrôle Docker Compose 2.24.4 ou supérieur et conserve le dépôt Git `origin` configuré par défaut.

### 10.2 Exploitation courante

```bash
cd /opt/finflow
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
# Mode IP : ajouter  -f docker-compose.ip.yml

# État
$COMPOSE ps
$COMPOSE logs -f --tail=200 backend worker beat

# Shell Django
$COMPOSE exec backend python manage.py shell

# Redémarrage ciblé
$COMPOSE restart backend worker beat
```

Images **bakées** (pas de volume code) : tout changement Python/React exige `--build`.
Pour déployer un nouveau commit, utilisez exclusivement `sudo finflow-update` :
un `git pull` suivi d'un `up` manuel contourne le snapshot chiffré, les
migrations contrôlées et les contrôles de santé.

---

## 11. Sauvegardes

L’install pose un cron 02:30 (`/etc/cron.d/finflow-backup`) et une phrase de
chiffrement dans `/root/.finflow-backup-pass` (mode 600). Chaque sauvegarde est
une archive GPG AES-256 (`.tar.gz.gpg`) contenant PostgreSQL, le miroir exact
du bucket MinIO, le manifest et le `.env` complet chiffré. Pendant la capture,
Nginx, le frontend, le backend, worker et beat sont mis en pause ; en mode IP
HTTP, le port MinIO est temporairement filtré. La fenêtre de maintenance dure
le temps du dump PostgreSQL, du miroir MinIO et de la copie du `.env`, puis les
services redémarrent avant le chiffrement et la rétention.

**Copiez la phrase de passe dans un coffre sécurisé indépendant du serveur.**
La phrase stockée uniquement dans `/root` ne survivrait pas à la perte du
serveur ; sans elle, les archives chiffrées sont irrécupérables. Testez
régulièrement une restauration `drill` sur une machine séparée.

```bash
# Snapshot manuel
sudo FINFLOW_DIR=/opt/finflow /opt/finflow/scripts/backup.sh

# Contrôle d'intégrité
sudo /opt/finflow/scripts/verify.sh /var/backups/finflow/snapshots/<stamp>.tar.gz.gpg

# Épreuve (stack jetable — ne touche pas la prod)
sudo /opt/finflow/scripts/restore.sh --target drill \
  --snapshot /var/backups/finflow/snapshots/<stamp>.tar.gz.gpg

# Sinistre (recrée la base, réécrit le bucket)
sudo /opt/finflow/scripts/restore.sh --target live \
  --snapshot /var/backups/finflow/snapshots/<stamp>.tar.gz.gpg \
  --confirm=RESTORE
# Ajouter --restore-secrets si la configuration complète du snapshot doit être restaurée.
```

Rétention : 14 jours (quotidien), 8 semaines (copie du dimanche), 12 mois
(copie du 1er). Copie hors site : `BACKUP_OFFSITE_DIR=/mnt/backup-nas`. La
phrase de passe doit rester stockée séparément du répertoire de sauvegarde.

Ne jamais réinjecter un dump avec `psql` dans la base en service : le script
`restore.sh --target live` arrête l’application, recrée une base vide, puis
`pg_restore`.

Redis n’est pas dans le snapshot (files Celery / cache). Le versioning du
bucket MinIO reste recommandé en complément (`deploy/s3/lifecycle.json`).

Épreuve isolée (sans instance FinFlow) :

```bash
sudo bash /opt/finflow/deploy/backup/selftest.sh
```

---

## 12. Supervision minimale

| Contrôle | Commande / URL |
|----------|----------------|
| Santé API | `curl -fsS http://finflow.intra/api/v1/health/` |
| Conteneurs | `docker compose … ps` |
| Logs | `docker compose … logs -f backend worker` |
| Disque | `df -h` |
| Mémoire | `free -h` / `htop` |
| Certificat interne | vérifier le certificat déployé dans Nginx / PKI de l'organisation |

En prod avancée : brancher Prometheus / Grafana / Sentry (`SENTRY_DSN`) — voir [10 — Exploitation](10-exploitation-supervision.md).

---

## 13. Dépannage Ubuntu

| Symptôme | Piste |
|----------|--------|
| 502 Bad Gateway | Frontend/backend down ; `docker compose ps` + logs |
| Health `storage` KO | MinIO, credentials, `AWS_S3_*` |
| Fichiers AccessDenied | `AWS_S3_CUSTOM_DOMAIN` / protocole HTTPS / CORS bucket |
| E-mails en échec | SMTP filiale (UI), `SMTP_SSL_VERIFY=1`, logs worker |
| Alertes workflow absentes | Worker Celery up ; prefs « Alertes e-mail » |
| Accès LAN refusé | Vérifier le CIDR enregistré dans `/opt/finflow/.finflow-lan-cidr` et les règles UFW |
| Disque plein | Volumes Docker `docker system df` ; purger anciennes images |

```bash
docker system df
docker image prune -f
journalctl -u nginx -u docker -n 100 --no-pager
```

---

## 14. Récapitulatif des outils

| Catégorie | Outils |
|-----------|--------|
| OS | Ubuntu 22.04 / 24.04 / 26.04 LTS |
| Conteneurs | Docker Engine, Compose plugin, Buildx |
| Proxy / TLS | Nginx, OpenSSL, PKI interne éventuelle |
| Sécurité | UFW, Fail2ban |
| Stack applicative | PostgreSQL 16, Redis 7, MinIO, Gunicorn, Celery |
| Exploitation | git, curl, jq, htop, mc (MinIO client), cron |
| Documentation | `documentation/04-…`, `05-configuration.md`, ce guide |

---

## 15. Références

- **Dépôt GitHub :** [https://github.com/Bouma-J/FinFlow2.0](https://github.com/Bouma-J/FinFlow2.0)
- **Script d’install Ubuntu (noms DNS internes, filtrage LAN) :** [`../deploy/ubuntu-install.sh`](../deploy/ubuntu-install.sh)
- **Script d’install Ubuntu (IP, HTTP ou HTTPS) :** [`../deploy/ubuntu-install-ip.sh`](../deploy/ubuntu-install-ip.sh)
- **HTTPS sans domaine :** [`../deploy/tls-ip/enable-ip-tls.sh`](../deploy/tls-ip/enable-ip-tls.sh)
- **Script de mise à jour production :** [`../deploy/ubuntu-update.sh`](../deploy/ubuntu-update.sh)
- **Compose surcharge IP :** [`../docker-compose.ip.yml`](../docker-compose.ip.yml), [`../docker-compose.ip-tls.yml`](../docker-compose.ip-tls.yml)
- Configuration détaillée : [05 — Configuration](05-configuration.md)
- Architecture : [02 — Architecture technique](02-architecture-technique.md)
- Exploitation : [10 — Exploitation](10-exploitation-supervision.md)
- Kubernetes (alternative) : [`../deploy/k8s/README.md`](../deploy/k8s/README.md)
- Variables d’exemple : [`.env.example`](../.env.example), [`backend/.env.example`](../backend/.env.example)

---

*FIN_FLOW — Thuin Tech — Déploiement Ubuntu.*
