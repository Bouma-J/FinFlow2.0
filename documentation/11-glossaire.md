# 11 — Glossaire

| Terme | Définition |
|-------|------------|
| **Filiale / Tenant** | Unité d’isolation des données dans FIN_FLOW |
| **Agence** | Structure organisationnelle rattachée à une filiale |
| **Groupe** | Niveau transverse multi-filiales (consolidation) |
| **data_scope** | Périmètre de visibilité : OWN, AGENCY, TENANT |
| **Montant demandé** | Montant sollicité par le client |
| **Montant proposé** | Montant retenu par l’analyste |
| **Montant accordé** | Montant décidé ; capital mis en place |
| **Frais** | Commission / frais dossier ; prélevés par le CBS |
| **CBS** | Core Banking System de la filiale |
| **Connecteur CBS** | Configuration d’accès (URL, protocole, auth, mapping) par filiale |
| **IntegrationLog** | Journal d’un échange FIN_FLOW ↔ CBS (idempotence, retry) |
| **SimulatedAdapter** | Adaptateur démo sans appel réseau réel |
| **GED** | Gestion électronique des documents |
| **SLA** | Délai maximum d’une étape d’approbation |
| **PAR** | Portfolio at Risk — classification des retards |
| **Dation** | Remise de biens en paiement d’une créance |
| **Main levée** | Libération d’une garantie |
| **Caution / Surety** | Tiers qui s’engage pour l’emprunteur |
| **Snapshot reporting** | Agrégat précalculé pour le dashboard |
| **JWT** | Jeton d’accès API (access + refresh) |
| **MFA / TOTP** | Authentification à deux facteurs par code temporaire |
| **Presigned URL** | URL S3 temporaire pour upload/download direct |
| **Celery Beat** | Planificateur des tâches périodiques |
| **HPA** | Horizontal Pod Autoscaler (Kubernetes) |
| **Tenant isolation shared** | Une DB, filtrage applicatif par `tenant_id` |
| **Tenant isolation schema** | Un schéma Postgres (ou DB) par filiale — cible réglementaire |

---

Fin de la documentation FIN_FLOW. Pour toute évolution majeure, mettre à jour le fichier concerné **et** le sommaire [`README.md`](README.md).
