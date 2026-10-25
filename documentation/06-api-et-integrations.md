# 06 — API et intégrations

## 1. Bases

| Élément | Valeur |
|---------|--------|
| Préfixe REST | `/api/v1/` |
| Schéma OpenAPI | `/api/schema/` |
| Swagger UI | `/api/docs/` |
| Format | JSON (multipart pour fichiers) |
| Auth | `Authorization: Bearer <access_token>` |
| Filiale (Groupe) | `X-Tenant-Id: <uuid>` |

Pagination DRF : `count`, `next`, `previous`, `results` (page size 25, max 200).

## 2. Authentification

```http
POST /api/v1/auth/token/
{"username":"group_admin","password":"…","otp":"123456"}
```

Réponse : `{ "access", "refresh" }`.  
Si MFA actif sans OTP → `401` avec `code: mfa_required`.

| Endpoint | Description |
|----------|-------------|
| `POST /auth/token/` | Login |
| `POST /auth/token/refresh/` | Nouveau access (+ refresh rotaté) |
| `POST /auth/logout/` | Blacklist du refresh |
| `POST /auth/mfa/setup/` | Génère secret TOTP |
| `POST /auth/mfa/confirm/` | Active MFA |
| `POST /auth/mfa/disable/` | Désactive MFA |

Profil courant : `GET /users/me/`.

## 3. Ressources principales (routers)

Liste non exhaustive — le détail des champs est dans Swagger.

| Préfixe | Module |
|---------|--------|
| `/tenants/`, `/agencies/` | Organisation |
| `/users/`, `/roles/`, `/permissions/`, `/delegations/` | IAM |
| `/credit-products/`, `/product-categories/`, … | Catalogue |
| `/clients/` | Clients |
| `/credit-applications/` | Dossiers (+ actions submit, disburse, …) |
| `/financial-analyses/`, `/field-visits/`, `/loans/` | Crédit annexes |
| `/workflow-definitions/`, `/approval-tasks/`, … | Workflow |
| `/documents/`, `/document-categories/` | GED |
| `/guarantees/`, `/dation-requests/`, `/guarantee-releases/` | Sûretés |
| `/sureties/`, `/surety-engagements/` | Cautions |
| `/contract-templates/`, `/generated-contracts/` | Contrats |
| `/cbs-connectors/`, `/integration-logs/` | Core Banking |
| `/collection-cases/`, … | Recouvrement |
| `/audit-logs/` | Audit |
| `/reporting/dashboard/`, `/reporting/group-consolidation/`, `/reporting/group-breakdown/` | Reporting |
| `/notification-settings/`, `/notification-logs/` | Notifications |
| `/health/`, `/metrics/` | Exploitation |

## 4. Actions métier notables

### Dossier
- `POST /credit-applications/{id}/submit/`
- `POST /credit-applications/{id}/cancel_submission/`
- `POST /credit-applications/{id}/disburse/`

### Contrats
- `POST /generated-contracts/generate/`  
  Ajouter `?async=1` pour file Celery (`202` + `task_id`).
- `GET /generated-contracts/{id}/download/` — fichier ou URL présignée.

### GED
- `GET /documents/{id}/download/` → `{ url, … }`
- `POST /documents/upload_url/` → URL PUT S3

### CBS
- `POST /cbs-connectors/{id}/test_operation/`
- `POST /integration-logs/{id}/retry/`

## 5. Intégration Core Banking

Chaque filiale configure un **connecteur** (protocole REST/SOAP/SFTP/BATCH, URL, auth JSON, retries).

Flux :
1. Opération métier appelle `send_operation(connector, operation, payload, idempotency_key)`.
2. Journal `IntegrationLog` (PENDING → SUCCESS / RETRY / FAILED).
3. Beat rejoue périodiquement les `RETRY`.

L’adaptateur concret dépend du `protocol` ; les connecteurs « réels » institutionnels restent à brancher selon le CBS cible.

Règla mise en place Fin Flow ↔ CBS :
- Fin Flow enregistre un prêt au **montant accordé**.
- Les **frais** sont affichés dans Fin Flow mais **prélevés par le CBS**.

**Documentation complète** (paramétrage UI/API, catalogue d’opérations, mode simulation, branchement adaptateur, dépannage) :  
→ [`12-connexion-cbs.md`](12-connexion-cbs.md).

## 6. Webhooks / événements

Pas de bus externe exposé aujourd’hui. Les effets de bord passent par :
- Celery (e-mails, SLA, snapshots, PAR, retries)
- Audit log
- Journaux CBS / notifications

## 7. Erreurs

Format DRF standard (`detail`, champs de validation).  
Handler personnalisé : `apps.common.exceptions.custom_exception_handler`.

Codes utiles : `401` (auth / MFA), `403` (permission / scope), `400` (métier), `429` (throttle), `503` (health dégradé).

## 8. Tests automatisés d’API

```bash
docker compose exec -T -w /app backend \
  sh -c "PYTHONPATH=/app DJANGO_SETTINGS_MODULE=config.settings.prod \
  python scripts/test_scale_phases.py"
```
