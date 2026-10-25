# 13 — Guide de déploiement Ubuntu (production)

Guide pas à pas pour déployer **FIN_FLOW** sur un serveur **Ubuntu Server 22.04 LTS** ou **24.04 LTS**, avec Docker Compose, reverse-proxy TLS et l’ensemble des outils nécessaires.

**Dépôt Git :** [https://github.com/Bouma-J/FinFlow](https://github.com/Bouma-J/FinFlow)  
**Clone :** `git clone https://github.com/Bouma-J/FinFlow.git`

Pour la vue d’ensemble multi-environnements (Compose démo, Kubernetes, bare metal), voir aussi [04 — Guide de déploiement](04-guide-deploiement.md).

### Installation assistée (recommandée)

Deux scripts interactifs au choix :

| Script | Cas d’usage | Accès |
|--------|-------------|--------|
| [`deploy/ubuntu-install.sh`](../deploy/ubuntu-install.sh) | Domaines DNS + Let’s Encrypt | `https://finflow.…` |
| [`deploy/ubuntu-install-ip.sh`](../deploy/ubuntu-install-ip.sh) | Lab / IP seule, sans DNS | `http://<IP>/` ou `https://<IP>/` |
| [`deploy/tls-ip/enable-ip-tls.sh`](../deploy/tls-ip/enable-ip-tls.sh) | HTTPS sur une install IP déjà en place | `https://<IP>/` |
| [`deploy/ubuntu-update.sh`](../deploy/ubuntu-update.sh) | **Mise à jour** d’une instance déjà en prod | — |

**Avec domaines + TLS :**

```bash
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-install.sh | bash'
# ou dépôt cloné :
sudo bash deploy/ubuntu-install.sh
```

**Par adresse IP (sans domaine — HTTP, ou HTTPS Let’s Encrypt / auto-signé) :**

```bash
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-install-ip.sh | bash'
# ou dépôt cloné :
sudo bash deploy/ubuntu-install-ip.sh
```

**Mise à jour (instance déjà déployée) :**

```bash
sudo finflow-update
# ou :
sudo bash /opt/finflow/deploy/ubuntu-update.sh
# depuis le dépôt :
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-update.sh | bash'
```

Le script d’update : backup DB → `git pull` → `docker compose up -d --build` → `migrate` → `sync_role_packs` → `bootstrap_all_tenants` (circuits ML / Dation / Formalisation). Les scripts d’install demandent IP ou domaines, mots de passe PostgreSQL/MinIO, `DJANGO_SECRET_KEY`, etc., puis déploient sous `/opt/finflow` (personnalisable). Le mode IP utilise [`docker-compose.ip.yml`](../docker-compose.ip.yml) (MinIO sur `:9000` en HTTP) et, une fois HTTPS activé, [`docker-compose.ip-tls.yml`](../docker-compose.ip-tls.yml) (MinIO en `127.0.0.1:19000`, Nginx termine le TLS sur `:443` et `:9000`). Les sections ci-dessous restent la référence manuelle pas à pas.

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
| Nginx hôte (recommandé) | TLS, domaine public | hors Compose |
| Certbot | Certificats Let’s Encrypt | hors Compose |

Flux navigateur typique :

```text
Internet → Nginx (443) → frontend:80 → API / SPA
                       ↘ MinIO:9000 (URLs présignées fichiers)
```

---

## 2. Prérequis matériel

| Ressource | Minimum | Recommandé (prod légère) |
|-----------|---------|---------------------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 8 Go | 16 Go |
| Disque | 40 Go SSD | 80 Go+ SSD |
| OS | Ubuntu 22.04 / 24.04 LTS 64-bit | idem |
| Réseau | IP publique + DNS A/AAAA | domaine dédié |

Ports à prévoir (firewall) :

| Port | Usage |
|------|--------|
| 22 | SSH |
| 80 | HTTP (redirection / ACME) |
| 443 | HTTPS (application) |
| 9000 | MinIO API (fichiers présignés) — restreindre si possible |
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
  nginx \
  certbot \
  python3-certbot-nginx
```

| Outil | Utilité |
|-------|---------|
| `git` | Récupération du code |
| `curl` / `wget` / `jq` | Tests health, scripts |
| `openssl` | Secrets, TLS |
| `ufw` | Pare-feu |
| `fail2ban` | Protection SSH |
| `nginx` + `certbot` | Reverse-proxy HTTPS |
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

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
# MinIO API (URLs présignées navigateur → serveur:9000)
sudo ufw allow 9000/tcp
# Ne pas ouvrir 9001 (console MinIO) ni 5432 / 6379
sudo ufw --force enable
sudo ufw status verbose
```

### 3.4 Fail2ban (SSH)

```bash
sudo systemctl enable --now fail2ban
sudo fail2ban-client status sshd
```

### 3.5 DNS (chez le registrar / serveur DNS — pas sur le serveur FinFlow)

Ces enregistrements se créent **sur le DNS public** de votre domaine (espace client OVH, Cloudflare, Gandi, serveur Bind/PowerDNS du prestataire, etc.).

Ils ne se mettent **pas** dans `/etc/hosts` du serveur qui héberge FIN_FLOW : ce fichier ne sert qu’à des tests locaux sur une machine de développement.

Avant le certificat TLS (Let’s Encrypt), créez :

| Type | Nom | Valeur | Où le configurer |
|------|-----|--------|------------------|
| A | `finflow.votredomaine.tld` | IP publique du serveur FinFlow | Panneau DNS du domaine |
| A | `minio.votredomaine.tld` | IP publique du serveur FinFlow | Panneau DNS du domaine (recommandé pour les fichiers) |

Vérification depuis n’importe quelle machine :

```bash
dig +short finflow.votredomaine.tld
# doit renvoyer l’IP publique du serveur
```

> **Exception lab / sans domaine :** uniquement pour un essai interne, vous pouvez ajouter une ligne dans `/etc/hosts` **sur le PC client** (celui du navigateur), pas comme solution de production :
> `IP_DU_SERVEUR  finflow.local minio.local`


---

## 4. Récupération du projet

Dépôt officiel : **https://github.com/Bouma-J/FinFlow.git**

```bash
sudo mkdir -p /opt/finflow
sudo chown "$USER":"$USER" /opt/finflow
cd /opt/finflow

git clone https://github.com/Bouma-J/FinFlow.git .
```

Mises à jour ultérieures :

```bash
cd /opt/finflow
git pull origin main
```

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
DJANGO_ALLOWED_HOSTS=finflow.votredomaine.tld,localhost,127.0.0.1,backend
DJANGO_SECURE_SSL_REDIRECT=True
DJANGO_CORS_ALLOWED_ORIGINS=https://finflow.votredomaine.tld

# --- Seed (toujours 0 en prod) ---
SEED_DEMO=0

# --- MinIO (changer les mots de passe par défaut) ---
MINIO_ROOT_USER=finflow_minio_admin
MINIO_ROOT_PASSWORD=MotDePasseMinIOTresLong!

# Domaine public MinIO vu par le navigateur (URLs présignées)
# Si vous exposez MinIO derrière minio.votredomaine.tld :
#   AWS_S3_CUSTOM_DOMAIN=minio.votredomaine.tld
#   AWS_S3_URL_PROTOCOL=https:
# Sinon (accès direct port 9000) :
#   AWS_S3_CUSTOM_DOMAIN=finflow.votredomaine.tld:9000
#   AWS_S3_URL_PROTOCOL=http:
# (préférer HTTPS + sous-domaine dédié)

# --- E-mail global (repli) ; chaque filiale peut avoir son SMTP en UI ---
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.votredomaine.tld
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=noreply@votredomaine.tld
EMAIL_HOST_PASSWORD=********
DEFAULT_FROM_EMAIL=FIN_FLOW <noreply@votredomaine.tld>
FRONTEND_BASE_URL=https://finflow.votredomaine.tld

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

> **Important :** le `docker-compose.yml` de démo fixe encore certaines variables (Postgres `finflow`/`finflow`, MinIO `localhost:9000`, etc.). Pour une prod réelle, adaptez `docker-compose.yml` (ou un `docker-compose.prod.yml`) afin de lire `DJANGO_ALLOWED_HOSTS`, `AWS_S3_CUSTOM_DOMAIN`, `FRONTEND_BASE_URL`, mots de passe DB/MinIO depuis `.env`. Voir section 10.

---

## 6. Compose production

Le dépôt fournit déjà [`docker-compose.prod.yml`](../docker-compose.prod.yml) : il surcharge les secrets, force `SEED_DEMO=0`, `SMTP_SSL_VERIFY=1`, injecte `EMAIL_*` / `FIELD_ENCRYPTION_KEY` dans **backend + worker + beat**, et expose frontend/MinIO uniquement sur `127.0.0.1` (Nginx hôte fait le TLS public).

Ajouter dans `.env` :

```env
POSTGRES_PASSWORD=MotDePassePostgresTresLong!
AWS_S3_CUSTOM_DOMAIN=minio.votredomaine.tld
AWS_S3_URL_PROTOCOL=https:
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

## 8. Nginx reverse-proxy + Let’s Encrypt

Le frontend Compose écoute sur `127.0.0.1:8080`. Nginx public termine le TLS.

### 8.1 Configuration application

`/etc/nginx/sites-available/finflow` :

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name finflow.votredomaine.tld;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name finflow.votredomaine.tld;

    # Remplacés / complétés par Certbot
    ssl_certificate     /etc/letsencrypt/live/finflow.votredomaine.tld/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/finflow.votredomaine.tld/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 100m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

### 8.2 Configuration MinIO (sous-domaine recommandé)

`/etc/nginx/sites-available/finflow-minio` :

```nginx
server {
    listen 80;
    server_name minio.votredomaine.tld;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$host$request_uri; }
}

server {
    listen 443 ssl http2;
    server_name minio.votredomaine.tld;

    ssl_certificate     /etc/letsencrypt/live/minio.votredomaine.tld/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/minio.votredomaine.tld/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    client_max_body_size 100m;

    # API S3 path-style : /finflow-documents/...
    ignore_invalid_headers off;
    proxy_buffering off;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300;
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
    }
}
```

Activer et obtenir les certificats :

```bash
sudo ln -sf /etc/nginx/sites-available/finflow /etc/nginx/sites-enabled/
sudo ln -sf /etc/nginx/sites-available/finflow-minio /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Première fois : commenter temporairement les blocs ssl_certificate
# puis :
sudo certbot --nginx -d finflow.votredomaine.tld -d minio.votredomaine.tld

sudo nginx -t && sudo systemctl reload nginx
sudo systemctl enable nginx
```

Renouvellement automatique (timer systemd fourni par Certbot) :

```bash
sudo certbot renew --dry-run
```

### 8.1 TLS et HSTS sans nom de domaine

Le déploiement type FinFlow est un **réseau interne (IP privée)**. Let’s Encrypt ne peut pas émettre de certificat pour une IP RFC1918 (`10/8`, `192.168/16`, `172.16–31`) : le challenge HTTP-01 doit être joignable depuis Internet.

| Situation | Certificat | HSTS | Navigateur |
|-----------|------------|------|------------|
| **IP privée / LAN (cas prévu)** | Auto-signé (`openssl`, SAN `IP:…`) ou PKI interne / mkcert. | **Désactivé.** Auto-signé + HSTS = verrouillage au prochain renouvellement. | Avertissement « certificat non fiable » à accepter une fois (ou déployer la CA interne sur les postes). |
| **IP publique** (80/443 ouverts depuis Internet) | Let’s Encrypt **certificat IP** (profil `shortlived`, ~6 jours). Certbot ≥ 5.4. | `max-age=604800` (7 jours), sans `includeSubDomains` ni preload. | Cadenas normal. |

Sur une instance interne déjà en HTTP :

```bash
sudo bash /opt/finflow/deploy/tls-ip/enable-ip-tls.sh /opt/finflow --self-signed
```

Sans `--self-signed`, le script détecte une IP privée et choisit tout seul l’auto-signé (il refuse `--lets-encrypt` sur du RFC1918).

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

1. [ ] `https://finflow.votredomaine.tld` charge la SPA  
2. [ ] `https://finflow.votredomaine.tld/api/v1/health/` → `ready: true`  
3. [ ] `https://finflow.votredomaine.tld/api/docs/` accessible (restreindre en prod si besoin)  
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
# Sans dump DB préalable
SKIP_BACKUP=1 sudo finflow-update

# Branche / répertoire personnalisés
GIT_BRANCH=main INSTALL_DIR=/opt/finflow sudo -E bash /opt/finflow/deploy/ubuntu-update.sh
```

Le script détecte automatiquement le mode **domaine** ou **IP** (`.finflow-deploy-mode`, `.finflow-tls-mode`, ou heuristique `.env`) via [`deploy/compose-files.sh`](../deploy/compose-files.sh).

### 10.2 Commandes manuelles

```bash
cd /opt/finflow
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
# Mode IP : ajouter  -f docker-compose.ip.yml

# État
$COMPOSE ps
$COMPOSE logs -f --tail=200 backend worker beat

# Mise à jour release (manuel)
git pull
$COMPOSE up -d --build
$COMPOSE exec backend python manage.py migrate
$COMPOSE exec backend python manage.py sync_role_packs
$COMPOSE exec backend python manage.py bootstrap_all_tenants

# Shell Django
$COMPOSE exec backend python manage.py shell

# Redémarrage ciblé
$COMPOSE restart backend worker beat
```

Images **bakées** (pas de volume code) : tout changement Python/React exige `--build`.

---

## 11. Sauvegardes

L’install pose un cron 02:30 (`/etc/cron.d/finflow-backup`) et une phrase de
chiffrement dans `/root/.finflow-backup-pass` (mode 600). Chaque snapshot
contient Postgres (format custom), le miroir MinIO et les clés
`FIELD_ENCRYPTION_KEY` / `DJANGO_SECRET_KEY` chiffrées.

```bash
# Snapshot manuel
sudo FINFLOW_DIR=/opt/finflow /opt/finflow/scripts/backup.sh

# Contrôle d'intégrité
sudo /opt/finflow/scripts/verify.sh /var/backups/finflow/snapshots/<stamp>

# Épreuve (stack jetable — ne touche pas la prod)
sudo /opt/finflow/scripts/restore.sh --target drill \
  --snapshot /var/backups/finflow/snapshots/<stamp>

# Sinistre (recrée la base, réécrit le bucket)
sudo /opt/finflow/scripts/restore.sh --target live \
  --snapshot /var/backups/finflow/snapshots/<stamp> \
  --confirm=RESTORE
# Ajouter --restore-secrets si le .env actuel n'a plus les clés du dump.
```

Rétention : 14 jours (quotidien), 8 semaines (copie du dimanche), 12 mois
(copie du 1er). Copie hors site : `BACKUP_OFFSITE_DIR=/mnt/backup-nas`.

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
| Santé API | `curl -fsS https://finflow…/api/v1/health/` |
| Conteneurs | `docker compose … ps` |
| Logs | `docker compose … logs -f backend worker` |
| Disque | `df -h` |
| Mémoire | `free -h` / `htop` |
| Certificats | `sudo certbot certificates` |

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
| Certbot échoue | DNS, ports 80/443 ouverts, `server_name` correct |
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
| OS | Ubuntu 22.04 / 24.04 LTS |
| Conteneurs | Docker Engine, Compose plugin, Buildx |
| Proxy / TLS | Nginx, Certbot, OpenSSL |
| Sécurité | UFW, Fail2ban |
| Stack applicative | PostgreSQL 16, Redis 7, MinIO, Gunicorn, Celery |
| Exploitation | git, curl, jq, htop, mc (MinIO client), cron |
| Documentation | `documentation/04-…`, `05-configuration.md`, ce guide |

---

## 15. Références

- **Dépôt GitHub :** [https://github.com/Bouma-J/FinFlow](https://github.com/Bouma-J/FinFlow)  
- **Script d’install Ubuntu (domaines + TLS) :** [`../deploy/ubuntu-install.sh`](../deploy/ubuntu-install.sh)  
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
