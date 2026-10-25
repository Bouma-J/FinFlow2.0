# Essai CBS : produit crédit 6, mécanisme 2

Date : 21 octobre 2026, heures UTC. Environnement CBS UAT connecté à FIL01.

## Résultat

**Succès réel de création et de relecture dans le CBS pour AG0100057.** La combinaison demandée par l'utilisateur `idProduitCrd = "6"`, `idProduitRemb = "2"` est acceptée avec l'objet de financement `"45"`, 350 000 FCFA, 6 échéances mensuelles et un taux annuel de 14 %. Cette observation valide cette combinaison pour cet essai ; elle ne démontre pas une correspondance universelle entre ces codes et tous les produits locaux.

La référence crédit 6 a été enregistrée dans les paramètres sur la base de l'instruction utilisateur pour cet essai UAT, avec cette provenance explicite. Aucun import distant de catalogue n'est revendiqué. Le produit local CONSO-STD utilise maintenant cette référence et le mécanisme local DEGRESSIVE transmet le code CBS 2 dans FIL01. Ces paramètres sont partagés par les dossiers qui les utilisent.

## Parcours exécuté

1. Absence de prêt local et de transmission précédente réussie vérifiée.
2. Paramétrage via les API administratives : produit crédit 6 et mécanisme 2.
3. Comparaison avec le dernier message : seuls `idProduitCrd` et `idProduitRemb` changent ; même identifiant externe UUID.
4. Nouvelle revue et autorisation via le rôle administration crédit.
5. Transmission via le rôle opérations : **une seule requête de création CBS**.
6. Vérification des échéances persistées, lecture du prêt local et répétition de l'action locale pour vérifier l'idempotence.
7. Consultation réelle `crd/situation` après création.

Les appels distants sont espacés d'au moins trois secondes après la réponse précédente au sein de chaque exécution. TLS reste validé ; aucun jeton n'est conservé dans les preuves.

## Requête et réponse de création

Message réellement envoyé à `/gateway-perfect/crd/simple` :

```json
{
  "externalId": "7b2e0b9e-e2e2-4ed9-93b2-cbb62a3727e6",
  "callbackUrl": "http://localhost/api/v1/cbs/callbacks/crd/7b2e0b9e-e2e2-4ed9-93b2-cbb62a3727e6/",
  "idPeriodicite": "M",
  "codeDevise": "FCFA",
  "idObjetFinancement": "45",
  "idProduitCrd": "6",
  "idProduitRemb": "2",
  "idPointService": "AG01",
  "idGestionnaire": "AG011U1",
  "codeAdherent": "AG0100057",
  "taux": 14.0,
  "nombreEcheance": 6,
  "montantDemande": 350000.0
}
```

Réponse HTTP 200 et code métier 200, à 12:34 UTC :

```json
{
  "numDemande": "AG01DMD2022000U00061",
  "limitCredit": null,
  "numContrat": "7b2e0b9e-e2e2-4ed9-93b2-cbb62a3727e6",
  "context": "CREDIT DE LA DEMANDE JUSQU'AU DEBLOQUAGE",
  "externalId": "7b2e0b9e-e2e2-4ed9-93b2-cbb62a3727e6",
  "montant": 350000.0,
  "refDemande": "7b2e0b9e-e2e2-4ed9-93b2-cbb62a3727e6",
  "dateOperation": "2022-09-29",
  "message": "Success !",
  "codeDevise": "FCFA",
  "responseCode": 200
}
```

## Vérifications après création

| Contrôle | Résultat |
| --- | --- |
| Dossier local CR-2026-00003 | DISBURSED |
| Prêt local | c9cb3fb0-3faa-412c-94a5-17a7509a2def |
| Nombre de prêts locaux pour le dossier | 1 |
| Échéances locales persistées et visibles par API | 6 |
| Somme des capitaux des échéances | 350 000 FCFA |
| Répétition de l'action locale de mise en place | Même prêt, aucun appel distant supplémentaire |
| Journal de transmission | SUCCESS, tentative cumulée 7, inchangée après répétition |
| Consultation CBS | HTTP 200 et code métier 200 |
| Numéro de prêt renvoyé par la consultation CBS | AG01PRT2022000U00039 |
| Compte de prêt CBS | 20221206AG01AG010005702 |
| Encours brut CBS | 350 000 FCFA |

Les 11 contrôles du script de vérification finale réussissent. L'assertion initiale sur `loan.installments.count()` était exécutée hors contexte de filiale : ce manager renvoie zéro par sécurité dans ce contexte. Les six échéances figuraient déjà dans la première réponse API. Une lecture explicite filtrée par filiale et prêt confirme leur présence ; ce contrôle a été corrigé dans le script, sans nouvelle création distante.

## Points restant à corriger avant un UAT complet

1. **Interprétation de la situation crédit : anomalie démontrée.** La ligne brute CBS de ce prêt contient `impaye = 0`, `impayeInteret = 0`, `penalite = 0`, `totalDU = 0`, `nbreJrsRetard = 0`. La normalisation locale expose pourtant `overdue_amount = 350000.0` et `days_overdue = 1`. Ne pas confondre encours et impayé ; corriger le parseur et couvrir ces champs par des tests dédiés. Les valeurs brutes sont conservées.
2. **Confirmation finale de déblocage :** le statut d'intégration local reste `SUBMITTED`. La création et l'existence du prêt dans le CBS sont confirmées ; le mouvement de fonds et un callback de confirmation n'ont pas été vérifiés.
3. **Callback :** l'URL localhost envoyée n'est pas joignable depuis le serveur CBS distant ; fournir une URL publique de recette.
4. **Dates CBS :** le bac à sable renvoie le 29/09/2022 alors que l'échéancier local commence en novembre 2026. Clarifier la date de travail du CBS et rapprocher les dates avant validation UAT.
5. **Échéancier :** les six échéances contrôlées sont celles calculées localement. `crd/situation` renvoie ici une ligne de situation du prêt, pas un échéancier de remboursement CBS ; leur concordance distante n'est pas démontrée.

## Preuves conservées

Répertoire : `uat-artifacts/journey-AG0100057-20261021/products-6-2-20261021T123402Z/`.

- `payload.json`, `changed-fields.json` : message envoyé et différences.
- `remote-calls.json` : authentification et réponse brute de création, secrets masqués.
- `local-steps.json`, `loan.json`, `summary.json` : parcours initial et état après acceptation ; l'assertion de contrôle initiale est conservée pour traçabilité.
- `persisted-installments.json` : contrôle corrigé des six échéances.
- `verification-local-steps.json`, `verification-remote-calls.json`, `situation.json` : idempotence, lecture locale et relecture distante.
- `verification-checks.json`, `verification-summary.json` : résultats finaux.

Ce rapport décrit l'état après le rapport 41, qui reste la trace des essais précédents refusés.
