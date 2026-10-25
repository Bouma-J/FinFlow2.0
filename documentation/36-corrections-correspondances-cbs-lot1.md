# Corrections des correspondances CBS

> Historique : l'hypothèse de catalogue produit distinct de ce document a été remplacée le 21 octobre 2026 par la correspondance précisée par l'utilisateur. Voir le rapport 38 pour le comportement actuel et l'envoi réel au CBS.

Livraison du lot 1, le 20 octobre 2026. Ce document complète l'audit 35.

## Changements livrés

### Objet de financement exact

Le dossier possède maintenant une relation `financing_object` vers l'objet CBS importé. Le formulaire présente tous les objets, toutes pages comprises, sans regroupement en « Autre ». Le type de besoin métier reste un champ distinct.

La création d'un nouveau dossier en mode CBS réel exige cet objet exact. Une sélection inactive ou hors filiale est refusée. Pour les anciens dossiers, une correspondance explicite existante du connecteur ou une correspondance métier unique reste résolue ; aucune première ligne arbitraire n'est choisie en cas d'ambiguïté. Le dossier CR-2026-00002 conserve ainsi l'objet 45 via sa correspondance existante, sans réécriture de sa décision.

### Produits crédit et remboursement

Un catalogue `CbsProductReference` distingue CREDIT et REPAYMENT. Chaque référence appartient à une filiale et à un connecteur, avec identifiant CBS, libellé, devise compatible facultative et justificatif documentaire.

La référence est d'abord « À confirmer ». Un administrateur habilité doit confirmer avoir vérifié son justificatif ; la date et l'auteur sont enregistrés. La modification de l'identifiant, du connecteur, de la nature, de la devise, de l'activation ou du justificatif remet la référence en attente de confirmation. Les valeurs de démonstration connues ne peuvent pas être confirmées.

**Cette confirmation est documentaire. Elle ne prétend pas consulter un catalogue distant ni prouver que le CBS acceptera l'identifiant.** Aucun endpoint d'import de produits n'a été inventé ; aucun produit réel n'a été renseigné automatiquement.

Le produit de crédit local sélectionne deux références confirmées séparées : `cbs_credit_product` et `cbs_repayment_product`. Les références doivent être actives, appartenir au connecteur actif de la même filiale, avoir la bonne nature et être compatibles avec la devise. Les anciens champs de codes restent consultables pour l'historique ; leur saisie directe ne configure plus un envoi réel.

Les mécanismes DEGRESSIVE, IN_FINE et BULLET restent des paramètres d'amortissement. Leur ancien champ CBS et le défaut `idProduitRemb` du connecteur ne servent plus de correspondance produit en mode réel. Les règles de compatibilité pour une simulation explicitement locale restent séparées.

### Résolveur commun et blocages

Le détail du dossier, le diagnostic de préparation et la construction du payload utilisent `resolve_application_cbs`. La résolution contrôle les objets, produits, devises, périodicités, points de service, gestionnaires et appartenances à la filiale. Une ancienne correspondance CONSUMPTION → 45 valide est maintenant comprise par le détail et par l'envoi.

Les références obligatoires non résolues bloquent la revue finale, l'autorisation et la transmission réelle. Les erreurs identifient les champs à compléter.

La préparation à la **soumission au circuit** reste distincte de la préparation des **correspondances CBS** : l'API expose `cbs_mapping_ready` et le détail indique que ces points bloquent la mise en place. Une décision métier ne constitue pas une autorisation d'envoyer un mapping incomplet.

Les valeurs résolues, le connecteur et les preuves de confirmation sont conservés dans la revue et dans l'autorisation. Une modification oblige à refaire la revue et l'autorisation. Les lignes de paramétrage concernées sont verrouillées dans les transactions d'autorisation et de transmission lorsque la base le supporte. Les correspondances sont relues immédiatement avant l'envoi ; un refus CBS conserve son journal d'échec.

Les créations de crédit sont interdites depuis le diagnostic générique du connecteur et les rejouements génériques. Le service d'envoi exige le dossier autorisé et un payload conforme à celui-ci. La tâche automatique de rejeu exclut SUBMIT_CREDIT : la reprise doit passer par le dossier et ses contrôles.

## Utilisation dans les paramètres

1. Ouvrir **Référentiels CBS → Produits CBS**.
2. Enregistrer l'identifiant réel du produit crédit pour le connecteur concerné, avec son libellé, sa devise éventuelle et la référence du justificatif CBS.
3. Vérifier le justificatif puis confirmer la référence.
4. Faire de même pour le produit de remboursement, avec la nature correspondante.
5. Ouvrir **Produits de crédit**, modifier CONSO-STD et sélectionner les deux références confirmées dans « Mapping CBS ».
6. Dans un nouveau dossier, choisir séparément le type de besoin et l'objet de financement CBS exact.
7. Pour un dossier déjà approuvé, refaire le contrôle final et l'autorisation avec les nouvelles correspondances avant toute transmission.

Les identifiants réels de produits restent à obtenir : les endpoints `object-fin-list` et `periodicite-list` consultés ne fournissent pas ces associations. Les dossiers UAT existants restent en attente et ne sont pas mis en place par cette livraison.

## Migrations et exploitation

Migrations appliquées dans la base locale :

- `catalog.0009_cbsproductreference_creditproduct_cbs_credit_product_and_more`
- `credits.0038_creditapplication_financing_object`

Les nouveaux champs de relation sont facultatifs en base pour préserver les anciens dossiers. Les contrôles métier exigent les références requises avant une mise en place réelle. Les autorisations anciennes qui ne couvrent pas ces nouvelles preuves doivent être renouvelées.

API locale ajoutée : `/api/v1/cbs-product-references/`, avec l'action documentaire `/<id>/confirm/`. Ce chemin appartient à FinFlow, pas à l'API CBS distante.

## Vérification

- Contrôle Django sans anomalie.
- Aucune migration manquante détectée.
- Compilation TypeScript sans erreur.
- Build Vite réussi ; avertissement de taille de bundle à traiter séparément.
- **27 contrôles ciblés réussis**, incluant la sélection exacte persistée, les types de produits, les références non confirmées, les droits, l'égalité des valeurs du détail et du payload, la remise en attente après modification de source et l'interdiction des voies d'envoi génériques.
- Les écritures des contrôles positifs ont été annulées par transaction. Aucun produit fictif de vérification n'est conservé dans le catalogue et aucun appel CBS n'a été autorisé pendant ces contrôles.
- Les résultats sont enregistrés dans `uat-artifacts/point1-checks.json`.

Ces contrôles ne remplacent pas une recette visuelle dans le navigateur, une recette de concurrence sur la base de production ou une création positive avec des produits CBS réels. Les problèmes d'encours simulé, d'import client incomplet, de portefeuille et de callback de l'audit 35 appartiennent aux lots suivants.
