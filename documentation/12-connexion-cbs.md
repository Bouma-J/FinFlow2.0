# 12 — Connexion au Core Banking (CBS)

Guide complet pour **configurer**, **tester** et **étendre** l’intégration FIN_FLOW ↔ Core Banking System d’une filiale.

> Chaque filiale possède son propre CBS. FIN_FLOW n’embarque pas la comptabilité : il instruit, décide, journalise, puis s’appuie sur un **connecteur paramétrable par tenant**.

---

## 1. Principes

| Règle | Détail |
|-------|--------|
| 1 connecteur actif / filiale | `resolve_active_connector(tenant_id)` prend le connecteur `is_active=True` le plus récemment mis à jour |
| Isolation | Le connecteur est `TenantScoped` : une filiale ne voit / n’utilise que le sien |
| Orchestration commune | Idempotence, journal `IntegrationLog`, retries — indépendants du protocole |
| Adaptateur | `get_adapter(connector)` choisit l’implémentation réelle ; **aujourd’hui** = `SimulatedAdapter` (démo) |
| Blocage métier | Mains levées / dations interrogent le CBS ; échec → processus **bloqué** (`CoreBankingError`) |

Code de référence :
- Modèles : `backend/apps/corebanking/models.py`
- Services : `backend/apps/corebanking/services.py`
- API : `/api/v1/cbs-connectors/`, `/api/v1/integration-logs/`
- UI : **Administration → Connecteurs CBS** (`/admin/connecteurs`)

---

## 2. Prérequis métier côté FIN_FLOW

Avant d’appeler le CBS, renseigner les **références croisées** :

| Objet | Champ | Usage |
|-------|-------|--------|
| Client | `cbs_client_id` | Matricule client CBS (dation, encours, mise en place `codeAdherent`) |
| Client | `cbs_account_number` | Compte / `numManuel` pour mise en place |
| Agence | `cbs_point_of_service_id` | `idPointService` Perfect |
| Produit | `cbs_product_code` (/ `cbs_repayment_product_code`) | `idProduitCrd` (override `idProduitRemb`) |
| Utilisateur | `cbs_id` (sinon `employee_id`) | `idGestionnaire` |
| Périodicité | `LoanPeriodicity.cbs_code` | `idPeriodicite` |
| Méthode remboursement | `RepaymentMethod.cbs_code` | `idProduitRemb` |
| Devise | `Currency.cbs_code` (= code Perfect, ex. `FCFA`) | `codeDevise` |
| Prêt / dossier | `core_banking_reference` (loan) | Réf. prêt CBS (solde, main levée) |
| Prêt | `cbs_*` (demande, contrat, statut) | Références renvoyées par `crd/simple` |
| Main levée | `cbs_loan_reference` | Réf. prêt contrôlée au CBS |
| Dation | `cbs_client_id` | Encours total client au CBS |

UI : **Administration → Référentiels CBS** (`/admin/referentiels-cbs`).

Sans matricule / référence prêt, les contrôles CBS lèvent une erreur explicite.

---

## 3. Configurer un connecteur (UI)

1. Se connecter avec un profil **admin filiale** (ou Groupe + filiale sélectionnée).
2. Menu **Administration → Connecteurs CBS**.
3. Créer un connecteur :

| Champ UI | Description |
|----------|-------------|
| Nom | Ex. `CBS Filiale Abidjan` (unique par filiale) |
| Protocole | `REST`, `SOAP`, `SFTP`, `BATCH` |
| URL de base | Endpoint racine du CBS (ou hôte SFTP) |
| Timeout (s) | Défaut `30` |
| Tentatives max | Défaut `3` (échecs → `RETRY` puis `FAILED`) |
| Auth username / password | Stockés dans `auth_config` (write-only côté API) |
| Simulation prêt soldé | Pilotage démo `mapping_rules.simulate` |
| Simulation encours client | Montant défaut pour `GET_CLIENT_OUTSTANDING` |

4. Un seul connecteur doit être **actif** pour la filiale en exploitation (désactiver les anciens).

**Seed démo** (`SEED_DEMO=1`) crée déjà `CBS Filiale 01` (REST, URL fictive).

---

## 4. Configurer via API

### 4.1 Création

```http
POST /api/v1/cbs-connectors/
Authorization: Bearer <access>
X-Tenant-Id: <uuid-filiale>   # obligatoire si utilisateur Groupe
Content-Type: application/json

{
  "name": "CBS Production",
  "protocol": "REST",
  "base_url": "https://cbs.filiale.example/api/v1",
  "timeout_seconds": 30,
  "max_retries": 3,
  "is_active": true,
  "certificate_reference": "vault:cbs-fil01-mtls",
  "auth_config": {
    "username": "VOTRE_USER",
    "password": "VOTRE_PASS",
    "scope": "perfect"
  },
  "mapping_rules": {
    "endpoints": {
      "authentification": "gateway-perfect/authentification",
      "adh_situation": "gateway-perfect/adh/situation",
      "crd_simple": "gateway-perfect/crd/simple",
      "ref_devise_list": "gateway-perfect/ref/devise-list",
      "ref_object_fin_list": "gateway-perfect/ref/object-fin-list",
      "ref_source_fin_list": "gateway-perfect/ref/source-fin-list",
      "ref_motif_decision_list": "gateway-perfect/ref/motif-decision-list",
      "ref_profession_list": "gateway-perfect/ref/profession-list",
      "ref_gestionnaire_list": "gateway-perfect/ref/gestionnaire-list"
    },
    "simulate": {
      "loan_settled_default": true,
      "loan_outstanding_default": "100000",
      "loan_unsettled_refs": ["UNSOLDE-DEMO"],
      "client_outstanding_default": "1000000",
      "client_outstanding_by_id": {
        "CLI-CBS-001": "2500000"
      }
    },
    "field_map": {
      "loan_ref": "numeroPret",
      "cbs_client_id": "matriculeClient"
    }
  }
}
```

Notes :
- `auth_config` est **write-only** (jamais renvoyé en lecture API).
- Authentification Perfect : `POST {base_url}/gateway-perfect/authentification` en `application/x-www-form-urlencoded` (`username`, `password`, `scope=perfect`) → `accessToken`, puis `Authorization: Bearer …` sur les autres appels.
- Jeton statique optionnel : `auth_config.access_token` (bypass de `/authentification`).
- Référentiels Perfect (GET + Bearer) : `ref/devise-list`, `ref/periodicite-list`,
  `ref/object-fin-list`, `ref/source-fin-list`, `ref/motif-decision-list`,
  `ref/profession-list`, `ref/point-service-list`, `ref/gestionnaire-list`
  (+ `type-piece-identite-list` déclaré).
  Réponses `{ datas: [{ id, code, libelle }] }`.
  **Source unique** : pas de CRUD manuel sur devises / périodicités / objets /
  sources / motifs / professions / points de service / gestionnaires.
  Import : `POST /api/v1/cbs-connectors/{id}/sync-referentials/`
  (UI **Référentiels CBS → Mettre à jour depuis le CBS**).
  Association manuelle : agence ↔ point de service, utilisateur ↔ gestionnaire
  (listes déroulantes sur les IDs syncés).
- `mapping_rules` est libre (JSON) : simulation, mapping de champs, codes produit CBS, etc.
- `certificate_reference` : pointeur vers un certificat (coffre / volume monté), pas le certificat lui-même.

### 4.2 Liste / activation

```http
GET  /api/v1/cbs-connectors/?is_active=true
PATCH /api/v1/cbs-connectors/{id}/
{"is_active": false}
```

### 4.3 Test de connexion (PING)

```http
POST /api/v1/cbs-connectors/{id}/test_operation/
Content-Type: application/json

{
  "operation": "PING",
  "payload": {}
}
```

Réponse = objet `IntegrationLog` (`status`, `response_payload`, `external_reference`, …).

Autres opérations de test utiles :

```json
{
  "operation": "GET_LOAN_STATUS",
  "payload": { "loan_ref": "PRET-123", "currency": "XAF" }
}
```

```json
{
  "operation": "GET_CLIENT_OUTSTANDING",
  "payload": { "cbs_client_id": "CLI-CBS-001", "currency": "XAF" }
}
```

---

## 5. Catalogue des opérations normalisées

FIN_FLOW parle au CBS via un **contrat métier interne**. L’adaptateur traduit vers l’API réelle de la filiale.

| Code opération | Payload attendu | Réponse normalisée (succès) | Consommateurs |
|----------------|-----------------|-----------------------------|---------------|
| `PING` | `{}` | `{ status: "ACK", external_reference }` | Test connecteur |
| `GET_LOAN_STATUS` | `{ loan_ref, currency? }` | `{ settled, outstanding, currency, raw, external_reference }` | Main levée, contrôle solde |
| `GET_CLIENT_OUTSTANDING` | `{ cbs_client_id, currency? }` | `{ total_outstanding, currency, breakdown[], raw, … }` | Dation (preview + initiation) |
| `GET_CLIENT_SITUATION` | `{ codeAdherent? / numManuel? / numPieceIdentite? }` | `{ raw, … }` (situation adhérent Perfect) | Import client CBS |
| `SUBMIT_CREDIT` | corps Perfect `crd/simple` | `{ num_demande, ref_demande, num_contrat, limit_credit, montant, raw, … }` | Mise en place dossier |

Constantes : `OP_*` dans `services.py`.

### 5.1 Mise en place — `SUBMIT_CREDIT` (Perfect `POST …/crd/simple`)

Après validation du dossier, l’action **Mettre en place / Valider la mise en place** appelle le CBS **avant** de créer le prêt local.

| Élément | Détail |
|---------|--------|
| Endpoint | `POST {base_url}/{mapping_rules.endpoints.crd_simple}` (défaut `gateway-perfect/crd/simple`) |
| Auth | `Authorization: Bearer {accessToken}` — jeton via `POST …/authentification` (username/password/scope=perfect) ou `auth_config.access_token` |
| Orchestration | `apps.corebanking.disbursement.submit_credit_to_cbs` |
| Idempotence | `disburse:{application_id}` |
| Callback | `POST /api/v1/cbs/callbacks/crd/{application_id}/` |

**Mapping dossier → payload**

| Champ Perfect | Source FIN_FLOW |
|---------------|-----------------|
| `externalId` | `application.reference` |
| `callbackUrl` | `{PUBLIC_API_BASE_URL}/api/v1/cbs/callbacks/crd/{id}/` |
| `idPointService` | `agency.cbs_point_of_service_id` ou `mapping_rules.disbursement.defaults` |
| `codeAdherent` / `numManuel` / `numPieceIdentite` | `client.cbs_client_id` / `cbs_account_number` / `national_id` (au moins un) |
| `idPeriodicite` | `MONTHLY` → `MENSUEL`, etc. |
| `taux` | taux dossier / produit |
| `nombreEcheance` | durée × périodicité |
| `idObjetFinancement` | `purpose_type` mappé (ex. `CONSUMPTION` → `CONSOMMATION`) |
| `idGestionnaire` | `mapping_rules.disbursement.defaults.idGestionnaire` |
| `idProduitCrd` | `product.cbs_product_code` (sinon `product.code`) |
| `idProduitRemb` | `product.cbs_repayment_product_code` ou défaut connecteur |
| `montantDemande` | montant de référence (accordé) |
| `codeDevise` | devise dossier |

**Modes** (`mapping_rules.disbursement.mode`) :

- `LOCAL` — simulation (démo / UAT) via `SimulatedAdapter` ; aucun HTTP Perfect
- `CBS` — appel REST réel (`RestAdapter._crd_simple`)

Échec CBS (`responseCode` ≥ 400, ex. limite insuffisante) → la mise en place est **bloqué** (pas de prêt local).

Références CBS stockées sur `Loan` : `cbs_external_id`, `cbs_demande_number`, `cbs_demande_ref`, `cbs_contract_number`, `cbs_disbursement_status`, `core_banking_reference`.

Exemple `mapping_rules` (défauts Perfect — `perfect_defaults.py`) :

```json
{
  "provider": "perfect",
  "force_simulate": false,
  "endpoints": {
    "authentification": "gateway-perfect/authentification",
    "adh_situation": "gateway-perfect/adh/situation",
    "crd_simple": "gateway-perfect/crd/simple"
  },
  "disbursement": {
    "mode": "CBS",
    "callback_secret": "optionnel",
    "defaults": {
      "idPointService": "PS01",
      "idGestionnaire": "GEST01",
      "idProduitRemb": "COMPTE-COURANT"
    },
    "periodicity_map": {
      "BIMONTHLY": "BIMENSUEL",
      "MONTHLY": "MENSUEL"
    },
    "purpose_map": {
      "CONSUMPTION": "CONSOMMATION",
      "EQUIPMENT": "EQUIPEMENT"
    }
  }
}
```

Chaque nouvelle filiale reçoit automatiquement ce connecteur via `bootstrap_tenant` → `ensure_perfect_connector` (idempotent). Renseigner ensuite `base_url`, `auth_config.username` / `password`.

Variable d’environnement : `PUBLIC_API_BASE_URL` (URL publique de l’API pour le callback Perfect).

### Extension du catalogue (suite)

Opérations encore à brancher selon besoins filiale :
- `CREATE_CLIENT` / `UPDATE_CLIENT`
- `GET_SCHEDULE`

---

## 6. Mode simulation (démo / UAT sans CBS réel)

Si `mapping_rules.force_simulate` est vrai, ou si l’URL est vide, `get_adapter()` renvoie `SimulatedAdapter` (**aucun appel réseau**). Le comportement se pilote via `mapping_rules.simulate` :

| Clé | Effet |
|-----|--------|
| `loan_settled_default` | `true`/`false` — solde par défaut |
| `loan_outstanding_default` | Encours si non soldé |
| `loan_unsettled_refs` | Liste de refs toujours non soldées |
| Préfixe `UNSOLDE-` / `UNSETTLED-` | Convention recette : ref prêt forcée « ouverte » |
| `client_outstanding_default` | Encours client par défaut |
| `client_outstanding_by_id` | Override par matricule |
| `credit_submit_fail` | Simule un refus de mise en place |
| `credit_fail_external_ids` | Liste d’`externalId` refusés |

Exemple recette main levée **refusée** : utiliser une référence prêt `UNSOLDE-TEST-01`.

---

## 7. Brancher un CBS réel (REST Perfect)

`get_adapter()` sélectionne déjà `RestAdapter` lorsque `protocol=REST`, `base_url` est renseignée et `force_simulate` est faux.

Opérations REST implémentées :
- `GET_CLIENT_SITUATION` → `adh/situation`
- `SUBMIT_CREDIT` → `crd/simple`
- `GET_LOAN_STATUS` → `crd/situation` (échéancier → soldé / encours pour main levée)

### 7.1 Contrat d’un adaptateur

Sous-classer `BaseAdapter` et implémenter :

```python
def send(self, operation: str, payload: dict) -> dict:
    # 1. Lire self.connector.base_url, auth_config, mapping_rules, timeout
    # 2. Traduire operation + payload → requête CBS native
    # 3. Retourner un dict NORMALISÉ (voir §5)
    # 4. En cas d'erreur transport / 5xx : lever une Exception
    #    → send_operation marque RETRY ou FAILED
```

### 7.2 Checklist REST typique

1. Authentification Perfect : `username` / `password` / `scope=perfect` →
   `POST {base_url}/gateway-perfect/authentification` (form-urlencoded) →
   `accessToken` dans `Authorization: Bearer …`.
2. mTLS si exigé (`certificate_reference` + montage secret K8s).
3. Timeouts = `connector.timeout_seconds`.
4. Renseigner codes produit / point de service / gestionnaire (UI admin + `mapping_rules`).
5. Exposer `PUBLIC_API_BASE_URL` pour les callbacks Perfect.
6. Ne jamais logger `password` / Bearer en clair.
7. Tests unitaires + `test_operation` PING / SUBMIT_CREDIT sur l’environnement de recette.

### 7.3 SOAP / SFTP / BATCH

| Protocole | Approche suggérée |
|-----------|-------------------|
| SOAP | Client zeep / suds ; WSDL dans `mapping_rules` ; opérations = méthodes |
| SFTP | Déposer / lire fichiers nominatifs ; Celery pour polling ; ACK via fichier retour |
| BATCH | Export périodique + import statuts ; réconciliation via `IntegrationLog` |

Le journal et l’idempotence restent identiques quelle que soit la transport.

---

## 8. Flux métier qui interrogent le CBS

```
┌─────────────────┐     resolve_active_connector
│ Processus métier│ ──────────────────────────► Connecteur filiale
│ (garanties…)    │                                     │
└────────┬────────┘                                     ▼
         │                                    get_adapter().send()
         │  get_loan_status /                           │
         │  get_client_outstanding                      ▼
         │                                    IntegrationLog (journal)
         ▼
   Blocage si échec / non soldé / encours insuffisant
```

| Processus | Service CBS | Règle |
|-----------|-------------|-------|
| Initiation **main levée** | `assert_loan_settled` | Prêt **doit être soldé** |
| Consultation crédits client (UI ML) | `get_loan_status` | Affiche `cbs_settled` / encours |
| Preview **dation** | `preview_dation_cbs` → `get_client_outstanding` | Affiche créance CBS |
| Initiation **dation** | `assert_client_outstanding_for_dation` | Encours **> 0** (seuil paramétrable) |
| Retry ML / dation bloquée | Actions `retry_cbs` | Relance le contrôle |
| **Mise en place** dossier | `submit_credit_to_cbs` → `SUBMIT_CREDIT` / `crd/simple` | Succès CBS requis (sauf `skip_cbs`) |

Fichier métier garanties : `backend/apps/guarantees/process_services.py`.  
Mise en place : `backend/apps/corebanking/disbursement.py` + `disburse_application`.

**Mise en place** : FIN_FLOW pousse la demande Perfect, puis enregistre le prêt local au **montant accordé** ; les frais sont affichés dans FIN_FLOW mais **prélevés par le CBS**.

---

## 9. Journalisation, idempotence et rejeux

### 9.1 IntegrationLog

Chaque appel crée un log :

| Statut | Signification |
|--------|----------------|
| `PENDING` | En cours |
| `SUCCESS` | ACK reçu |
| `RETRY` | Échec, `attempts < max_retries` |
| `FAILED` | Échec définitif |

Consultation :
- API `GET /api/v1/integration-logs/?status=RETRY`
- Admin Django → Journaux d’intégration

### 9.2 Idempotence

```python
send_operation(connector, operation, payload, idempotency_key="disburse:UUID")
```

Si une clé a déjà un log `SUCCESS` pour ce connecteur → **pas de nouvel envoi** (anti doubla mise en place).

Contrainte DB : unicité `(connector, idempotency_key)` lorsque la clé est non vide.

### 9.3 Rejeu automatique

Celery Beat : toutes les **10 minutes** :

```
retry-cbs-integrations → apps.corebanking.tasks.retry_cbs_integrations
```

Rejoue les logs `RETRY` (limite configurable).

Rejeu manuel :

```http
POST /api/v1/integration-logs/{id}/retry/
```

(uniquement si statut `FAILED` ou `RETRY`).

---

## 10. Procédure de mise en service filiale

1. **Recette** : créer un connecteur, laisser `SimulatedAdapter`, valider UI mains levées / dations.
2. **CBS test** : déployer `RestCbsAdapter` (ou équivalent), pointer `base_url` vers l’environnement de test.
3. `POST …/test_operation/` avec `PING`, puis `GET_LOAN_STATUS` / `GET_CLIENT_OUTSTANDING` sur des comptes connus.
4. Renseigner `cbs_client_id` / refs prêt sur un client et un dossier pilote.
5. Parcourir main levée (prêt soldé) et dation (encours > 0) de bout en bout.
6. Vérifier les `IntegrationLog` (SUCCESS) et l’absence de secrets dans les logs applicatifs.
7. **Production** : secrets via vault / variables K8s, `is_active=true` sur le connecteur prod uniquement, monitoring des `RETRY`/`FAILED`.

---

## 11. Dépannage

| Symptôme | Cause probable | Action |
|----------|----------------|--------|
| « Aucun connecteur Core Banking actif » | Pas de connecteur ou tous inactifs | Créer / activer dans Connecteurs CBS |
| « Référence prêt CBS manquante » | `cbs_loan_reference` / `core_banking_reference` vide | Compléter la fiche prêt / formulaire ML |
| « Matricule … manquant » | `cbs_client_id` vide sur le client | Mettre à jour la fiche client |
| Main levée refusée (encours) | Prêt non soldé au CBS (ou sim `UNSOLDE-`) | Vérifier CBS / simulation |
| Dation refusée | Encours CBS ≤ 0 | Vérifier matricule / `client_outstanding_*` |
| Logs en `RETRY` | Exception adaptateur / timeout | Logs `finflow`, augmenter timeout, corriger auth |
| Double envoi évité | Idempotency key déjà SUCCESS | Comportement normal |

```bash
docker compose logs -f backend worker beat | findstr /i "Core Banking CBS"
```

---

## 12. Sécurité

- Stocker mots de passe / secrets CBS hors dépôt Git (`auth_config` en base + chiffrement disque / vault).
- Restreindre les permissions de création de connecteurs aux admins filiale.
- Réseau : autoriser uniquement les IP FIN_FLOW vers le CBS (firewall).
- Ne pas exposer `auth_config` dans les exports / Swagger responses (déjà write-only).
- Auditer les changements de connecteur via piste d’audit tenant.

---

## 13. Références croisées

- Cahier des charges §3.7 — Mise en place et intégration Core Banking : [`../charge.txt`](../charge.txt)
- API générale : [`06-api-et-integrations.md`](06-api-et-integrations.md)
- Admin / sécurité : [`08-administration-securite.md`](08-administration-securite.md)
- Exploitation (Celery retry) : [`10-exploitation-supervision.md`](10-exploitation-supervision.md)
- Glossaire : [`11-glossaire.md`](11-glossaire.md)
