# Documentation FIN_FLOW

Plateforme SaaS multi-tenants de gestion du cycle de vie des dossiers de crédit, avec consolidation Groupe et intégration Core Banking.

## Sommaire

| Document | Contenu |
|----------|---------|
| [01 — Présentation](01-presentation.md) | Vision produit, acteurs, périmètre |
| [02 — Architecture technique](02-architecture-technique.md) | Stack, modules, flux, stockages |
| [03 — Documentation fonctionnelle](03-documentation-fonctionnelle.md) | Processus métier détaillés |
| [04 — Guide de déploiement](04-guide-deploiement.md) | Docker Compose, Kubernetes, checklist prod |
| [13 — Déploiement Ubuntu](13-guide-deploiement-ubuntu.md) | Serveur Ubuntu : outils, Docker, TLS, backups |
| [05 — Configuration](05-configuration.md) | Variables d'environnement (dont **e-mail / expéditeur**) |
| [06 — API et intégrations](06-api-et-integrations.md) | REST, JWT, CBS, OpenAPI |
| [07 — Guide utilisateur](07-guide-utilisateur.md) | Parcours opérateurs / validateurs |
| [08 — Administration et sécurité](08-administration-securite.md) | RBAC, MFA, audit, quotas |
| [09 — Montée en charge](09-montee-en-charge.md) | Court / moyen / long terme |
| [10 — Exploitation](10-exploitation-supervision.md) | Health, métriques, Celery, sauvegardes |
| [11 — Glossaire](11-glossaire.md) | Termes métier et techniques |
| [12 — Connexion au CBS](12-connexion-cbs.md) | Connecteurs, opérations, simulation, adaptateur réel |
| [14 — Backlog d’étude](14-backlog-etude.md) | 12 fiches (complet / ambitieux), hors code |
| [15 — Analyse financière UMOA](15-analyse-financiere-umoa.md) | Analyse selon le type de client et contrôles financiers |
| [16 — Gouvernance et mise en place](16-gouvernance-et-mise-en-place.md) | Accords, contrats, comités, délégations et contrôles CBS |
| [17 — Vérification des habilitations et paramètres](17-verification-habilitations-parametrage.md) | Corrections, configuration locale, comptes de recette et commandes d'audit |
| [18 — Administration crédit et autorisation CBS](18-administration-credit-autorisation-cbs.md) | Contrôle obligatoire, autorisation préalable et choix du service exécutant |
| [19 — Centre de configuration métier](19-centre-configuration-metier.md) | Profils versionnés, publication, aperçu et conservation des règles par dossier ; périmètre du premier lot |
| [20 — Éligibilité et scoring configurables](20-eligibilite-et-scoring-configurables.md) | Conditions par étape, grilles pondérées, données manquantes et simulation sur dossier |
| [21 — Circuits, comités et calendriers](21-circuits-comites-calendriers.md) | Modes d'exécution, majorités, présences, PV et conservation des calendriers ouvrés |
| [22 — Tarification configurable](22-tarification-configurable.md) | Barèmes, tranches, frais et taxes sur frais, devis, contrôles et simulation |
| [23 — Capacités métier](23-capacites-metier.md) | Fonctions indépendantes des noms de rôles, séparation des tâches et migration des habilitations |
| [24 — Gouvernance et héritage Groupe](24-gouvernance-et-heritage-groupe.md) | Socles Groupe, adaptations filiale, verrous et publication indépendante |
| [25 — Formulaires, KYC et référentiels](25-formulaires-kyc-et-referentiels.md) | Champs typés, ordre des analyses, exigences KYC et valeurs extensibles |
| [26 — Engagements et plafonds](26-engagements-consolides-et-plafonds.md) | Situations justifiées, groupes liés, limites, fraîcheur et contrôles par étape |
| [27 — Conventions de simulation](27-conventions-simulation.md) | Décompte des jours, arrondis, dates ouvrées et moteur partagé avec l'analyse |
| [28 — Audit de restitution de l'analyse financière](28-audit-restitution-analyse-financiere.md) | Fidélité à la saisie, anomalies reproduites, conventions financières et améliorations de consultation |
| [29 — Restitution et fiabilité financière](29-restitution-et-fiabilite-financiere.md) | Corrections de capacité, calcul courant cohérent, données par profil, prévisions cumulées et rapprochements |
| [30 — Jeu de démonstration financière](30-jeu-demonstration-financiere.md) | 60 dossiers VISU-, cinq profils, douze scénarios et liens directs pour apprécier les analyses |
| [31 — Consultation du dossier et administration](31-consultation-dossier-et-administration.md) | Séparation des données métier et du paramétrage, accès administrateur, engagements et cohérence de restitution |

## Documents connexes

- [Clôture et recette du lot de configuration — 20 octobre 2026](recette-configuration-2026-10-20.md)

- Cahier des charges : [`../charge.txt`](../charge.txt)
- README projet : [`../README.md`](../README.md)
- Isolation multi-tenant (détail) : [`../docs/TENANT_ISOLATION.md`](../docs/TENANT_ISOLATION.md)
- Kubernetes : [`../deploy/k8s/README.md`](../deploy/k8s/README.md)
- Lifecycle S3 : [`../deploy/s3/lifecycle.json`](../deploy/s3/lifecycle.json)

## Accès rapides (Docker Compose)

| Service | URL |
|---------|-----|
| Application | http://localhost:8080 |
| API | http://localhost:8080/api/v1/ |
| Swagger | http://localhost:8080/api/docs/ |
| Admin Django | http://localhost:8080/django-admin/ |
| MinIO console | http://localhost:9001 |

## Comptes de démonstration

| Profil | Identifiant | Mot de passe |
|--------|-------------|--------------|
| Admin Groupe | `group_admin` | `FinFlow2026!` |
| Admin Filiale (si seed) | `fil01_admin` | `FinFlow2026!` |

> Activer le seed : `SEED_DEMO=1 docker compose up -d --build`

Les profils métier séparés pour tester le circuit sont décrits dans
[la vérification des habilitations](17-verification-habilitations-parametrage.md#4-comptes-pour-la-recette-locale).

---

*Documentation générée pour FIN_FLOW — Thuin Tech. À maintenir à chaque évolution majeure.*
