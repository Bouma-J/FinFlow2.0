# 03 — Documentation fonctionnelle

## 1. Organisation

### Filiale
Entité d’isolation. Paramètres : code, pays, zone, devise, branding, quota GED, connecteur CBS, circuits, produits.

### Agence
Rattachée à une filiale. Sert de périmètre pour la création de dossiers et le `data_scope` AGENCY.

### Utilisateurs et rôles
- Un **rôle** = groupe Django lié à la filiale (`TenantRole`).
- À la création d’une filiale, **23 rôles** sont provisionnés avec des packs de droits adaptables (voir `08-administration-securite.md`), dont finance / comptabilité.
- **Périmètre de données** (`data_scope`) :
  - `OWN` — ses propres dossiers
  - `AGENCY` — agence(s) autorisée(s)
  - `TENANT` — toute la filiale
- Délégations temporaires de pouvoirs de validation possibles.

## 2. Clients

Types : **Particulier**, **Professionnel**, **Entreprise**.

Données typiques : identité / RCCM-IFU, contacts, KYC, références CBS (`cbs_client_id`, `cbs_account_number`).  
Matricule généré par filiale (ex. `PAR-2026-00001`, `ENT-2026-00001`).

## 3. Catalogue crédit

- **Catégories** de produits
- **Produits** : taux, durée, devises, typologie client, paramètres
- **Motifs de rejet**
- **Checklists** documentaires par produit

## 4. Dossier de crédit

### Montants
| Champ | Sens |
|-------|------|
| `amount_requested` | Demande client |
| `amount_proposed` | Proposition analyste |
| `amount_approved` | Décision ; **source de la mise en place** |

Les frais (% et montants) sont calculés pour affichage / contrat. À la mise en place, Fin Flow envoie le **montant accordé** ; le **CBS prélève les frais**.

### Conditions
- Taux, périodicité, durée, mécanisme (CONSTANT / DEGRESSIVE / IN_FINE / BULLET)
- Épargne obligatoire (affichée, hors ratios institution)
- Frais de dossier + frais additionnels

### Cycle de vie (statuts)

```
DRAFT → SUBMITTED → IN_APPROVAL → APPROVED → CONTRACT_GENERATED
                 ↘ RETURNED ↗              ↘ REJECTED
                 ↘ CANCELLED
                                              ↓
                                    DISBURSEMENT_PENDING (optionnel)
                                              ↓
                                          DISBURSED → CLOSED
```

Règles clés :
- Soumission : analyse financière **de référence** obligatoire ; `risk_level` dérivé.
- Modification du dossier : brouillon / retourné, **créateur seul** (Analyste / Comité enrichissent via analyses & visites).
- Analyses / visites : ajout et édition uniquement dans la fenêtre de contribution (initiateur ou tâche PENDING) ; gel ensuite.
- Garanties / cautions : rattachement possible jusqu’à l’avant-mise en place (y compris après approbation, ex. juridique).
- Mise en place : initiation (`initiate_disburse_*`) puis validation (`disburse_*`) ; conditions suspensives levées ; création prêt + échéancier.
- **Politique d'instruction** (par filiale) : couverture garanties (alerte / blocage soumission / blocage approbation), visite obligatoire, analyse défavorable, checklist produit, KYC à la création ou soumission, bornes produit à l'enregistrement ou soumission, montant approuvé (instruction ou décision), readiness UI, annulation formelle `CANCELLED`, garanties pendant le circuit — écran **Administration → Politique crédit**.

### Analyse financière
Plusieurs analyses possibles ; une seule **référence** (`is_reference`).  
Salaires : saisie unique synchronisée. Equity / endettement selon règles produit.

### Garanties & cautions
- Garanties (hypothèque, gage, financière…) avec mouvements et photos.
- Cautions (personnes physiques / morales) + engagements plafonnés.
- Processus dédiés : **main levée**, **dation en paiement** (contrôle CBS créance).

## 5. Circuit d’approbation

1. Définition de workflow (étapes ordonnées, rôle requis, SLA heures, seuils éventuels).
2. À la soumission : instance + tâches pour l’étape 1.
3. Actions : **Approuver**, **Retourner**, **Rejeter** (+ conditions).
4. Notifications e-mail : à la soumission et à chaque validation d’étape, les utilisateurs du rôle de l’étape suivante reçoivent un e-mail (référence, client, produit, montant, durée, agence, lien) ; l’initiateur du dossier est alerté en fin de circuit — **validé** (génération des contrats), **rejeté** ou **renvoyé pour correction** ; aussi SLA dépassé.

## 6. Contrats

- Modèles Word/Excel paramétrables (variables + boucles).
- Génération synchrone ou asynchrone (`?async=1`).
- Suivi statut contrat sur le dossier ; upload exemplaire signé.

## 7. GED

- Documents rattachés à une entité (client, dossier…).
- Catégories avec suivi d’expiration.
- Upload classique ou URL présignée S3.
- Quota filiale bloquant si dépassé.

## 8. Recouvrement

- Recalcul des retards sur prêts actifs (batch nocturne).
- Classification PAR (sain → PAR1 → PAR30 → PAR90 → PAR180+).
- Dossiers de recouvrement, actions, promesses, remboursements.

## 9. Reporting

- **Dashboard filiale** : crédits, portefeuille, clients, garanties, risque.
- **Consolidation Groupe** : multi-filtres (pays, zone, produit, devise…).
- **Snapshots** matérialisés (rafraîchis périodiquement) pour éviter les full-scans.

## 10. Audit

Chaque création / modification / suppression d’objet scopé est journalisée (utilisateur, IP, snapshot).  
Purge automatique selon `AUDIT_RETENTION_DAYS`.
