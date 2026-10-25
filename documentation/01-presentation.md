# 01 — Présentation

## 1. Qu’est-ce que FIN_FLOW ?

FIN_FLOW est une plateforme **SaaS multi-filiales** destinée aux institutions de microfinance et banques de détail. Elle couvre le **cycle de vie complet** d’un dossier de crédit :

1. Référentiel client (KYC)
2. Instruction du dossier (conditions, frais, analyse financière, garanties, cautions)
3. Circuit d’approbation paramétrable
4. Génération de contrats
5. Mise en place (capital = montant accordé ; frais prélevés côté CBS)
6. Suivi d’échéancier, recouvrement (PAR), main levée / dation
7. Reporting filiale et consolidation **Groupe**

## 2. Acteurs

| Acteur | Rôle |
|--------|------|
| **Administrateur Groupe** | Crée filiales, consolide, paramètre transverse |
| **Administrateur filiale** | Paramétrage (utilisateurs, rôles, produits, circuits, CBS) **et** opérations métier (clients, dossiers, garanties, recouvrement…), **uniquement** sur sa filiale |
| **Chargé / analyste crédit** | Clients, dossiers, analyses, soumission |
| **Responsable d’agence / comité** | Validation / rejet / renvoi selon le circuit |
| **Client emprunteur** | Hors système (données saisies par l’institution) |

## 3. Organisation multi-tenants

- Une **filiale** (`Tenant`) = unité d’isolation des données.
- Une filiale possède des **agences**, des **produits**, un **circuit** d’approbation, un **connecteur CBS**.
- Les utilisateurs **Groupe** n’ont pas de filiale attachée ; ils sélectionnent une filiale via l’UI (en-tête `X-Tenant-Id`).
- Mode d’isolation actuel : base partagée + `tenant_id` (`TENANT_ISOLATION_MODE=shared`). Voir `docs/TENANT_ISOLATION.md` pour l’option schéma.

## 4. Périmètre fonctionnel (livré)

- Clients particuliers / professionnels / entreprises
- Dossiers de crédit (montants demandé / proposé / accordé, mécanismes, frais)
- Analyses financières (référence obligatoire avant soumission)
- Garanties, cautions, dations, mains levées
- Contrats (modèles + génération)
- GED (S3/MinIO, quotas, expiration)
- Workflow multi-étapes + SLA + e-mails
- Reporting + snapshots matérialisés
- Audit, MFA TOTP, JWT blacklist

## 5. Hors périmètre actuel / feuille de route

- Signature électronique avancée
- Adaptateurs CBS métier réels (REST/SOAP/SFTP/BATCH) au-delà du cadre journalisé
- Exports Power BI / Excel avancés
- Isolation schéma-par-filiale en production

## 6. Principes métier verrouillés

- **Montant mis en place** = montant accordé (`amount_approved`) ; le CBS prélève les frais.
- **Épargne obligatoire** affichée, **exclue** des ratios institution (DSCR, score, échéance institution).
- **Mécanismes** d’échéancier : CONSTANT, DEGRESSIVE, IN_FINE, BULLET.
- Analyse financière **de référence** obligatoire avant soumission ; risque circuit dérivé de cette analyse.
