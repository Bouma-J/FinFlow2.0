# Comparaison du cURL positif et correction du produit crédit CBS

Date : 21 octobre 2026, heures UTC. Dossier local AG0100057 : CR-2026-00003.

> État ultérieur : l'essai demandé avec produit crédit 6 et mécanisme 2 réussit. Voir le rapport 42 du 21/10/2026 ; les refus ci-dessous concernent les combinaisons antérieures.

## Conclusion corrigée

L'exemple positif fourni par l'utilisateur révèle une erreur dans notre correspondance : **le produit crédit CBS et l'objet de financement sont deux champs indépendants**. Le cURL utilise `idProduitCrd = "1"` et `idObjetFinancement = "30"`. Le générateur utilisait jusque-là l'objet 45 dans les deux champs.

Cette erreur est corrigée. Il était également trop général de conclure que la référence de remboursement 1 était invalide : elle est acceptée dans la combinaison de l'exemple utilisateur pour AG0100027. Les refus précédents ne décrivaient que les requêtes envoyées pour AG0100057.

Après correction du produit crédit et un essai supplémentaire avec le seul code adhérent, **le CBS refuse encore la combinaison du dossier AG0100057**. Aucun prêt local n'a été créé. Le rattachement ou l'éligibilité du compte de remboursement pour cet adhérent reste à vérifier ; sa cause exacte n'est pas démontrée.

## Comparaison des requêtes

| Champ | Exemple positif utilisateur | Notre requête avant correction | Interprétation |
| --- | --- | --- | --- |
| URL | Même serveur et même route `gateway-perfect/crd/simple` | Identiques | La destination n'explique pas la différence observée |
| `idProduitCrd` | `"1"` | `"45"` | Erreur de correspondance corrigée |
| `idObjetFinancement` | `"30"` | `"45"` | Objets différents ; ce champ reste distinct du produit crédit |
| `idProduitRemb` | `"1"` | `"1"` | Même référence, déjà transmise sous le même type JSON |
| `codeAdherent` | AG0100027 | AG0100057 | Adhérents différents |
| `numManuel` | AG0100027 | AG0100057 | Identification supplémentaire propre à chaque adhérent |
| `numPieceIdentite` | CI-AG0100027 | UAT-AG0100057 | Notre valeur est un complément KYC local fictif ; elle a été retirée du message de création lorsque le code CBS suffit |
| `montantDemande` | 100 000 | 350 000 | Conditions financières différentes |
| `nombreEcheance` | 12 | 6 | Durées différentes |
| `idPointService` | AG01 | AG01 | Identique |
| `idGestionnaire` | AG011U1 | AG011U1 | Identique |
| `idPeriodicite`, `codeDevise`, `taux` | M, FCFA, 14,0 | Identiques | Aucune différence de valeur |
| `externalId`, chemin de callback | Référence et dossier de l'exemple | UUID de notre dossier | Corrélation différente, conservée pour ne pas réutiliser un contrat existant |

**Les types JSON étaient déjà identiques** : les identifiants sont des chaînes, le montant et le taux des nombres, le nombre d'échéances un entier. Le test précédent n'avait donc pas envoyé le nombre JSON `1` à la place de la chaîne attendue `"1"`.

## Vérification de l'exemple positif dans le CBS

Avec notre connexion au même serveur, la consultation réelle de `refDemande = CR-2026-00003` pour AG0100027 renvoie :

- code métier 200 ;
- `numDemande = AG01DMD2022000U00059` ;
- `refDemande` et `numContrat = CR-2026-00003` ;
- montant 100 000, devise FCFA.

Ces références correspondent à la réponse fournie par l'utilisateur. **Aucune nouvelle création n'a été effectuée en rejouant son cURL.** Ce contrat n'a pas été importé comme s'il appartenait à notre dossier AG0100057, malgré l'égalité de leur référence métier locale.

La différence entre HTTP 200 et succès métier est bien prise en compte : l'exemple positif contient `responseCode = 200`, alors que nos refus contiennent `responseCode = 409` dans des réponses HTTP 200.

## Corrections appliquées

1. **Produit crédit indépendant.** En mode CBS réel, `idProduitCrd` provient désormais d'une référence CREDIT confirmée, associée au produit local, et jamais de l'objet de financement. La référence 1 est documentée par le cURL et sa réponse fournis, puis confirmée par l'API d'administration et associée à CONSO-STD.
2. **Objet conservé.** `idObjetFinancement` continue de provenir du choix exact du dossier. L'objet 45 de l'accord AG0100057 n'a pas été remplacé par 30 pour chercher un succès.
3. **Paramétrage visible.** Référentiels CBS propose les références « Produits crédit », avec source et confirmation. Le produit local sélectionne sa référence crédit. Le détail du dossier distingue produit crédit, référence de remboursement et objet.
4. **Identification unique en création réelle.** Si le code adhérent CBS est disponible, il est envoyé seul ; sinon le compte manuel, puis la pièce, servent d'alternatives. Les compléments KYC locaux ne sont plus ajoutés à une recherche CBS déjà identifiée par le code adhérent.
5. **Preuves renouvelées.** La revue et l'autorisation ont été renouvelées après les changements. La preuve comprend le produit documenté et la politique d'identification. Les garde-fous de filiale, connecteur, devise, activité, source et confirmation restent bloquants.

La référence de remboursement 1 reste celle paramétrée dans le mécanisme, selon l'instruction utilisateur. L'exemple positif démontre une valeur fonctionnelle pour AG0100027, sans fournir à lui seul le contrat complet du catalogue de remboursement ou l'éligibilité des autres clients.

## Essais contrôlés sur AG0100057

Conditions conservées : 350 000 XOF, six mois, taux 14 %, objet 45, référence de remboursement 1, même identifiant externe UUID et même clé d'idempotence.

| Essai | Différence contrôlée | Résultat |
| --- | --- | --- |
| Produit crédit corrigé | Seul `idProduitCrd` passe de 45 à 1 dans le message | HTTP 200 / métier 409 : `Compte remboursement non valide : 1 !` |
| Identifiant principal seul | Retrait de `numManuel` et de la pièce fictive ; codeAdherent AG0100057 conservé | Premier essai interrompu à l'authentification, aucun appel de création |
| Reprise après cet échec d'authentification | Message identique à l'essai précédent | HTTP 200 / métier 409 : `Compte remboursement non valide : 1 !` |

Les changements ciblés ont été comparés automatiquement avec la requête précédente avant chaque envoi. Deux nouvelles requêtes de création ont effectivement atteint le CBS pendant cette campagne, espacées de plusieurs minutes. Les appels d'une séquence sont espacés d'au moins trois secondes et TLS reste validé.

Le journal local comporte maintenant six tentatives : cinq créations effectivement envoyées depuis le début de la recette AG0100057 et un échec avant création à l'authentification. Il reste `FAILED`. Le dossier reste `DISBURSEMENT_PENDING`, avec zéro prêt local.

## Ce qui reste à établir

- Le compte de remboursement actif et le rattachement au produit 1 pour **AG0100057**, ou une requête positive fournie pour cet adhérent.
- La compatibilité éventuelle de ce produit/compte avec l'objet 45 et les conditions 350 000 sur six mois. Le refus observé ne permet pas de distinguer ces hypothèses à lui seul.
- Le contrat ou l'endpoint CBS décrivant précisément la référence de remboursement et ses liens aux comptes adhérents.

Les lectures d'adhérent déjà conservées montrent un plafond 700 000 pour AG0100027 et une valeur `null` pour AG0100057, avec agence AG01 et `estValide = true` dans les deux cas. **Un plafond null n'est pas zéro et ne démontre pas la cause du refus.** La tentative de rafraîchissement comparatif des deux fiches a échoué à l'authentification ; ces valeurs ne sont donc pas présentées comme deux nouvelles lectures simultanées.

Les montants, la durée, l'objet et le client d'un dossier approuvé n'ont pas été changés arbitrairement. Aucune création fictive de prêt local n'a été utilisée pour masquer le refus CBS.

## Vérification et limites

- **153 tests automatisés réussis**, aucun échec ni test ignoré, sur 14 fichiers. Ils couvrent notamment le triplet indépendant 1/1/30 de l'exemple, l'interdiction de repli produit → objet, les références invalides et les alternatives d'identification.
- Compilation frontend complète réussie, avertissement de taille du bundle restant.
- Django `check` sans anomalie ; aucune nouvelle migration nécessaire.
- Backend redémarré ; contrôle navigateur du dossier montrant séparément produit crédit 1, référence de remboursement 1 et objet 45, puis de l'onglet des produits crédit documentés.

Autre limite relevée pendant la lecture du crédit positif : le champ `datas` contient 24 enregistrements de prêts/encours du client, alors que l'adaptateur les expose actuellement sous `schedule`. Ces lignes ne prouvent pas l'échéancier du seul contrat interrogé. Cette anomalie de normalisation, déjà signalée dans les audits antérieurs, doit être traitée avant de conclure à un rapprochement complet des échéances.

## Preuves

Sous `uat-artifacts/journey-AG0100057-20261021/` :

- `credit-product-fix-20261021T104911Z/user-successful-example.json` : exemple déclaré par l'utilisateur, sans secret.
- Même répertoire : `comparison.json`, `changed-fields.json`, `user-example-readback.json`, `remote-calls.json`, `payload.json`, `summary.json`.
- `primary-identifier-20261021T105307Z/` : échec d'authentification sans création.
- `primary-identifier-20261021T105601Z/` : requête réduite au code adhérent et réponse CBS conservées.
- `cbs-current-client-comparison/` : rafraîchissement comparatif interrompu à l'authentification.
- `cbs-comparison-final.png` : correspondances corrigées visibles dans le dossier.

Tests : `uat-artifacts/cbs-comparison-final-regression.xml` et `.log`. Compilation : `uat-artifacts/cbs-comparison-final-build.log`.
