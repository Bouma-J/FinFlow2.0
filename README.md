# FIN_FLOW

Plateforme **SaaS multi-tenants** de gestion du cycle de vie complet des dossiers de crédit, avec consolidation Groupe et intégration multi-Core Banking. Ce dépôt contient le **backend** (API REST Django) et le **frontend** (SPA React), conformes au cahier des charges `charge.txt`, ainsi qu'une **orchestration Docker** complète.

**Dépôt :** [https://github.com/Bouma-J/FinFlow](https://github.com/Bouma-J/FinFlow)

## Sommaire
- [Architecture](#architecture)
- [Choix techniques structurants](#choix-techniques-structurants)
- [Modules métier](#modules-métier)
- [Documentation complète](#documentation-complète)
- [Démarrage rapide avec Docker](#démarrage-rapide-avec-docker)
- [Déploiement Ubuntu](#déploiement-ubuntu)
- [Prérequis](#prérequis)
- [Installation locale](#installation-locale)
- [Frontend (React)](#frontend-react)
- [Données de démonstration](#données-de-démonstration)
- [Documentation de l'API](#documentation-de-lapi)
- [Tests](#tests)
- [Structure du projet](#structure-du-projet)
- [Feuille de route](#feuille-de-route)

## Documentation complète

La documentation produit (fonctionnelle, technique, déploiement, API, exploitation, montée en charge) se trouve dans le dossier **[`documentation/`](documentation/README.md)**.

## Architecture

- **Backend** : Python 3.12 / Django 5.1 / Django REST Framework
- **Frontend** : React 18 + TypeScript + Vite, TanStack Query, React Router (SPA)
- **Base de données** : PostgreSQL (production) — repli SQLite en développement
- **Authentification** : JWT (SimpleJWT) + RBAC (rôles = groupes, permissions Django) + MFA TOTP
- **Asynchrone** : Celery + Redis (notifications, connecteurs CBS, batchs)
- **Stockage documentaire (GED)** : compatible S3 (MinIO ou équivalent)
- **Documentation API** : OpenAPI 3 (drf-spectacular) + Swagger UI
- **Déploiement** : Docker Compose (PostgreSQL, Redis, MinIO, backend, worker/beat Celery, frontend Nginx)

## Choix techniques structurants

### Multi-tenants (isolation des filiales)
Approche **base de données partagée + colonne discriminante** (`tenant`) avec **filtrage automatique** :
- `TenantScopedModel` : modèle de base ; le champ `tenant` est renseigné automatiquement à la sauvegarde à partir du contexte courant.
- `apps/common/tenancy.py` : résolution du tenant courant via `ContextVar` (compatible sync/async).
- Le tenant est résolu par `TenantContextMixin` (viewsets) après l'authentification JWT, puis appliqué par le manager `objects`. Un manager d'échappement `all_tenants` est disponible pour les traitements système et la consolidation Groupe.

> Alternative « un schéma par filiale » (django-tenants) : l'abstraction `TenantScopedModel` permet de faire évoluer ce choix sans réécrire le code métier.

### Niveau Groupe et consolidation
- Les utilisateurs `is_group_level=True` accèdent à des vues **consolidées** transverses.
- La consolidation est **multi-axes avec filtres combinables** (filiale, pays, zone, produit, segment, devise, période, statut, risque…) — voir `apps/reporting/`.

### Piste d'audit
- `apps/audit/` journalise automatiquement (signaux) toute création / modification / suppression des entités métier, avec utilisateur, IP et horodatage.

## Modules métier (`backend/apps/`)

| Module | Rôle |
|--------|------|
| `common` | Socle : modèles de base, multi-tenancy, mixins, pagination, exceptions |
| `tenants` | Filiales, agences, branding (logo et couleurs) |
| `accounts` | Utilisateurs, rôles (RBAC), délégations de pouvoirs, MFA |
| `catalog` | Produits de crédit, familles, motifs de rejet, check-lists |
| `clients` | Clients particuliers / professionnels / entreprises + KYC |
| `credits` | Dossiers de crédit, analyse financière, visites, prêt et échéancier |
| `workflow` | Moteur d'approbation paramétrable (étapes, seuils, SLA, conditions suspensives) |
| `documents` | GED (catégories, versionning, intégrité, alertes d'expiration) |
| `guarantees` | Garanties et mouvements (réévaluation, mainlevée, dation, réalisation, transfert) |
| `sureties` | Cautions et engagements (plafonds) |
| `contracts` | Modèles de contrats, génération DOCX/XLSX, condition de décaissement |
| `corebanking` | Connecteurs Core Banking par filiale (idempotence, journalisation, rejeu) |
| `collections` | Recouvrement (PAR, encaissements FIFO, promesses, contentieux) |
| `notifications` | SMTP par filiale, alertes workflow / SLA |
| `audit` | Piste d'audit inaltérable |
| `reporting` | Tableaux de bord filiale + consolidation Groupe multi-axes |

## Démarrage rapide avec Docker

La méthode recommandée : tout tourne en conteneurs, aucune installation locale de Python/Node requise (seulement Docker Desktop).

```powershell
# Depuis la racine du projet — stack seule (sans comptes de démo)
docker compose up --build

# Avec le jeu de données de démonstration
$env:SEED_DEMO = "1"; docker compose up --build
```

Par défaut Compose fixe `SEED_DEMO=0` (base propre). Le seed n'est **pas** lancé au premier démarrage sauf si vous passez `SEED_DEMO=1`.

Une fois les services démarrés :

| Service | URL |
|---------|-----|
| Application (SPA) | http://localhost:8080 |
| API REST | http://localhost:8080/api/v1/ |
| Documentation Swagger | http://localhost:8080/api/docs/ |
| Back-office Django | http://localhost:8080/django-admin/ |
| Console MinIO | http://localhost:9001 (`minioadmin` / `minioadmin`) |

Le frontend Compose est publié sur le **port 8080** (le port 80 de l'hôte reste libre pour Nginx/Certbot en production Ubuntu). MinIO est lié à `127.0.0.1`.

> Pour la production, définissez au minimum `DJANGO_SECRET_KEY` et adaptez `DJANGO_ALLOWED_HOSTS`, `FRONTEND_BASE_URL` (liens e-mail), la terminaison TLS et les identifiants PostgreSQL/MinIO. Voir `docker-compose.prod.yml` et [13 — Déploiement Ubuntu](documentation/13-guide-deploiement-ubuntu.md).

### Réseau d'entreprise avec inspection TLS (proxy)

Derrière un proxy qui inspecte le trafic HTTPS (certificat racine interne), `pip` et `npm` échouent dans les conteneurs (`CERTIFICATE_VERIFY_FAILED`). Les Dockerfiles font confiance à un bundle de certificats local (non versionné) attendu dans `backend/certs/ca-bundle.crt` et `frontend/certs/ca-bundle.crt`. Générez-le depuis le magasin de certificats Windows :

```powershell
New-Item -ItemType Directory -Force -Path backend\certs, frontend\certs | Out-Null
$stores = @('Cert:\LocalMachine\Root','Cert:\CurrentUser\Root','Cert:\LocalMachine\CA','Cert:\CurrentUser\CA')
$certs = ($stores | ForEach-Object { Get-ChildItem $_ -ErrorAction SilentlyContinue }) | Sort-Object Thumbprint -Unique
$pem = ($certs | ForEach-Object { "-----BEGIN CERTIFICATE-----`n" + [Convert]::ToBase64String($_.RawData,'InsertLineBreaks') + "`n-----END CERTIFICATE-----" }) -join "`n"
Set-Content backend\certs\ca-bundle.crt "$pem`n" -Encoding ascii
Set-Content frontend\certs\ca-bundle.crt "$pem`n" -Encoding ascii
```

Hors proxy d'entreprise, cette étape est inutile : créez simplement les fichiers `certs/ca-bundle.crt` vides (ou avec les racines publiques) — les Dockerfiles restent fonctionnels.

> Note : `npm install` en local sur cette machine nécessite aussi `--use-system-ca` (Node 20+) ; définissez `NODE_OPTIONS=--use-system-ca` avant de lancer npm.

## Déploiement Ubuntu

Installation serveur (Docker, TLS, backups) :

```bash
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-install.sh | bash'
```

Mise à jour d’une instance déjà en production :

```bash
sudo finflow-update
# ou :
sudo bash -c 'curl -fsSL https://raw.githubusercontent.com/Bouma-J/FinFlow/main/deploy/ubuntu-update.sh | bash'
```

Détail : [`documentation/13-guide-deploiement-ubuntu.md`](documentation/13-guide-deploiement-ubuntu.md), scripts `deploy/ubuntu-install.sh`, `deploy/ubuntu-install-ip.sh` et `deploy/ubuntu-update.sh`.

## Prérequis
- Docker Desktop (voie recommandée), **ou**
- Python 3.12 et Node.js 20+ pour un développement local hors conteneurs.

## Installation locale

Sous Windows (PowerShell), depuis la racine du projet :

```powershell
# 1. Environnement virtuel
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements\dev.txt

# 2. Configuration
Copy-Item backend\.env.example backend\.env   # puis adapter si besoin

# 3. Migrations
.\.venv\Scripts\python.exe backend\manage.py migrate

# 4. Données de démonstration (optionnel)
.\.venv\Scripts\python.exe backend\manage.py seed_demo

# 5. Serveur de développement
.\.venv\Scripts\python.exe backend\manage.py runserver
```

L'API est disponible sur `http://127.0.0.1:8000/api/v1/`.

Variables utiles (détail : [`documentation/05-configuration.md`](documentation/05-configuration.md) et `backend/.env.example`) : `DJANGO_SECRET_KEY`, `DATABASE_URL`, `SEED_DEMO`, stockage S3/MinIO, Celery/Redis, bloc e-mail, `FRONTEND_BASE_URL` (en Docker démo : `http://localhost:8080`).

## Frontend (React)

Application monopage (SPA) en React + TypeScript (Vite) consommant l'API. En développement, un proxy redirige `/api` vers le backend Django (`http://127.0.0.1:8000`).

```powershell
cd frontend
npm install
npm run dev
```

L'interface est servie sur `http://localhost:5173`. Fonctionnalités couvertes :
- Authentification JWT (rafraîchissement automatique), MFA TOTP, changement de mot de passe forcé.
- Branding filiale (logo et couleurs) ; tableau de bord filiale / consolidé Groupe.
- Clients, dossiers de crédit (création, soumission, décaissement), analyses, file de validations.
- Catalogue produits, cautions, garanties, mains-levées, dations.
- Génération de contrats, recouvrement / contentieux, simulateur d'échéancier.
- Administration : filiales, agences, utilisateurs, rôles, circuits, connecteurs CBS, SMTP, audit.

Build de production : `npm run build` (sortie dans `frontend/dist/`, servie par Nginx dans l'image Docker).

Les écrans sont chargés à la demande par route et affichent un état de chargement pendant le téléchargement. Pour conserver un démarrage léger, ajouter les nouvelles pages à `frontend/src/App.tsx` avec un import dynamique.

Parcours frontend automatisés : `npm run test:e2e` depuis `frontend/`. Les réponses API sont simulées pour isoler l'interface des données locales et des appels CBS. Sur Windows, le test utilise Edge s'il est installé ; ailleurs, installez d'abord le navigateur Playwright avec `npx playwright install chromium`.

Smoke test isolé avec l'API réelle : `npm run test:e2e:api:isolated` depuis `frontend/`. Cette commande crée une SQLite temporaire, exécute les migrations et `seed_demo`, démarre Django et Vite sur des ports locaux libres, puis supprime la base et les artefacts même si le test échoue. Elle utilise une clé de recette temporaire, un backend e-mail mémoire et le connecteur CBS simulé. Le parcours vérifie les écrans métier et les routes de consultation, sans modifier de dossier métier ni envoyer d'opération CBS. Pour utiliser un environnement déjà démarré, `npm run test:e2e:api` accepte `FINFLOW_API_BASE_URL` et `FINFLOW_SMOKE_PASSWORD` (nom par défaut : `fil01_admin`). Le parcours des routes d'administration utilise aussi `FINFLOW_GROUP_SMOKE_USERNAME` et `FINFLOW_GROUP_SMOKE_PASSWORD` ; la commande isolée les configure sur `group_admin` et le mot de passe de démonstration.

## Données de démonstration
La commande `seed_demo` crée :
- Administrateur **Groupe** : `group_admin` / `FinFlow2026!`
- Administrateur **Filiale** : `fil01_admin` / `FinFlow2026!`
- Une filiale, deux agences, un catalogue de produits, des circuits et un connecteur local de démonstration.
- Avec le comportement par défaut, des dossiers à plusieurs statuts, des analyses, cautions, garanties, prêts, échéanciers et dossiers de recouvrement pour tester les parcours liés.

Utilisez `seed_demo --no-rich` pour un socle minimal limité aux premiers écrans. Ce mode n'ajoute volontairement pas de codes CBS de démonstration : en mode connecteur local, l'objet CBS reste facultatif ; en mode CBS réel, le référentiel exact doit être chargé avant la création d'un dossier.

Pour les listes de recette, utilisez `seed_demo --volume --count 20` (le volume est limité à 20–120 lignes par module). Cette variante ajoute aussi des documents GED et des échéanciers aux prêts générés. Le seed peut être relancé sans dupliquer les données opérationnelles.

Ces identifiants sont **uniquement destinés à la démo / UAT**, jamais à la production.

## Documentation de l'API
- Schéma OpenAPI : `http://127.0.0.1:8000/api/schema/` (Docker : `http://localhost:8080/api/schema/`)
- Swagger UI : `http://127.0.0.1:8000/api/docs/` (Docker : `http://localhost:8080/api/docs/`)
- Authentification : `POST /api/v1/auth/token/` (username / password) → jeton `access` à placer dans l'en-tête `Authorization: Bearer <token>`.
- Un utilisateur Groupe peut cibler une filiale via l'en-tête `X-Tenant-Id: <uuid>`.

Scripts de vérification manuelle (serveur démarré) :
```powershell
.\.venv\Scripts\python.exe backend\scripts\smoke_test.py   # isolation, permissions, dashboard
.\.venv\Scripts\python.exe backend\scripts\e2e_credit.py   # cycle de vie complet d'un dossier
```

## Tests
```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
```

Depuis la racine : `.\.venv\Scripts\python.exe -m pytest backend`

La CI GitHub Actions exécute les checks Django, **pytest**, le build frontend et (sur `push`) la construction des images Docker.

## Structure du projet
```
fin flow/
├── charge.txt                 # Cahier des charges
├── documentation/             # Documentation complète (voir documentation/README.md)
├── docker-compose.yml         # Orchestration démo (db, redis, minio, backend, celery, frontend)
├── docker-compose.prod.yml    # Variante production
├── docker-compose.ip.yml      # Accès par IP
├── deploy/                    # Ubuntu, Kubernetes, lifecycle S3
├── docs/                      # Notes techniques ciblées (ex. isolation tenant)
├── .github/workflows/         # CI
├── backend/
│   ├── manage.py
│   ├── pytest.ini
│   ├── Dockerfile
│   ├── .env.example
│   ├── config/                # Projet Django (settings, urls, wsgi/asgi, celery)
│   │   └── settings/          # base / dev / prod / test
│   ├── docker/                # entrypoint (migrations, collectstatic, seed)
│   ├── apps/                  # Modules métier (voir tableau ci-dessus)
│   ├── scripts/               # Scripts utilitaires (smoke test, e2e)
│   ├── tests/                 # Suite de tests pytest
│   └── requirements/          # base / dev / prod
└── frontend/
    ├── Dockerfile             # Build Vite + service Nginx
    ├── nginx.conf             # SPA + proxy /api /django-admin /static /media
    ├── package.json
    ├── vite.config.ts
    ├── public/                # Favicon / assets statiques
    └── src/
        ├── api/               # Client axios (JWT + refresh) et types
        ├── auth/              # Contexte d'authentification
        ├── components/        # Layout, UI réutilisable, route protégée
        └── pages/             # Écrans (dashboard, dossiers, clients, …)
```

## Feuille de route
- [x] Frontend React (SPA) consommant l'API.
- [x] Conteneurisation (Docker Compose).
- [x] Notifications e-mail + escalades SLA via Celery beat.
- [x] Cache Redis, pagination, S3/MinIO, throttle, MFA TOTP.
- [x] Reporting matérialisé (snapshots) + quotas GED + health/metrics.
- [x] CI/CD (GitHub Actions) + manifests Kubernetes (HPA).
- [x] Génération de contrats (DOCX/XLSX) et circuit de décaissement associé.
- [ ] Signature électronique des contrats.
- [ ] Adaptateurs Core Banking réels (REST/SOAP/SFTP/BATCH) + réconciliation.
- [ ] Exports reporting avancés (Excel/PDF/Power BI).
- [ ] Isolation schema-per-tenant (option réglementaire — voir `docs/TENANT_ISOLATION.md`).
