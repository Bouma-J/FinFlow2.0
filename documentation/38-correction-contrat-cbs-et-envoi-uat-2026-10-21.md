# Correspondances précisées et envoi UAT au CBS

> Correction ultérieure : le cURL positif fourni par l'utilisateur démontre que produit crédit et objet de financement sont indépendants. Le rapport 41 décrit la correspondance actuelle et remplace la déduction idProduitCrd = objet exposée ici.

Date : 21 octobre 2026. Filiale FIL01, adhérent AG0100053, dossier CR-2026-00002.

## Contrat appliqué

L'utilisateur a précisé les sources attendues par le CBS :

| Champ envoyé | Source dans FinFlow | Valeur de cette tentative |
| --- | --- | --- |
| `idProduitCrd` | Objet de financement choisi, `FinancingObject.cbs_code` | `45` |
| `idProduitRemb` | Mécanisme d'amortissement choisi, `RepaymentMethod.cbs_code` | `COMPTE-COURANT` pour DEGRESSIVE |
| `idObjetFinancement` | Même objet de financement exact | `45` |
| `idPeriodicite` | Périodicité choisie | `M` |
| `codeDevise` | Devise du référentiel | `FCFA` |

Cette précision remplace l'hypothèse des rapports 36 et 37, qui imposait un catalogue de produits crédit/remboursement distinct. Ce catalogue supplémentaire n'est plus exigé pour une transmission réelle.

**Provenance à distinguer :** l'objet 45 provient bien de l'import CBS. Les trois mécanismes actuellement enregistrés ont les valeurs initiales `COMPTE-COURANT` ; aucun périmètre d'import des mécanismes n'est présent dans le synchroniseur actuel. La valeur enregistrée a été utilisée conformément à la demande de l'utilisateur, sans inventer d'identifiant numérique ni prétendre à un import supplémentaire.

## Corrections appliquées

- Le résolveur commun utilise directement l'objet et le mécanisme du dossier en mode CBS réel.
- Les deux anciennes relations de produits et leurs codes libres ne remplacent plus ces choix et ne constituent plus un préalable à l'envoi réel.
- L'objet doit rester actif, appartenir à la filiale et disposer d'un code CBS ; une sélection ancienne ambiguë est refusée.
- Le mécanisme doit être actif et posséder un code CBS ; sa modification invalide les preuves de revue et d'autorisation.
- Le mécanisme est verrouillé avec les autres correspondances pendant les opérations transactionnelles.
- Les anciennes données de produits sont conservées en lecture seule pour l'historique ; aucun effacement de données.
- L'onglet de produits supplémentaires et les sélections correspondantes du produit local ont été retirés de l'interface. Le détail du dossier affiche les deux sources effectivement utilisées.
- Le code CBS du mécanisme peut être renseigné dans Référentiels CBS → Mécanismes d'amortissement. Sa présence dans cet écran ne constitue pas à elle seule une preuve d'import distant.
- Les contrôles de permissions, revue finale, autorisation nominative, séparation des acteurs et conformité du message transmis sont conservés.

Les scénarios explicitement locaux conservent leur compatibilité historique. Aucune migration de structure n'est nécessaire.

## Tentative réelle de mise en place

La tentative passe par les API métier, avec les acteurs existants :

1. Revue finale UAT renouvelée par `fil01_admin_credit` : **HTTP 200**.
2. Autorisation renouvelée par ce même acteur habilité : **HTTP 200**.
3. Exécution par `fil01_operations`, distinct de l'autorisateur.
4. Authentification réelle du CBS : **HTTP 200**.
5. Une seule requête réelle `POST /gateway-perfect/crd/simple`, montant **200 000**, trois échéances, taux annuel **14 %**, avec les correspondances du tableau ci-dessus.

Le CBS répond **HTTP 200 avec `responseCode: 409`** :

> Une demande existe déjà avec cette référence : CR-2026-00002.

FinFlow traite correctement ce code métier comme un échec et renvoie **HTTP 400** à l'opération locale. Aucune création distante n'est confirmée par ce retour. Aucun prêt local n'est créé et le dossier reste `DISBURSEMENT_PENDING`.

La consultation réelle `POST /gateway-perfect/crd/situation`, avec `refDemande = CR-2026-00002` et `codeAdherent = AG0100053`, répond également **HTTP 200 / code métier 409** :

> Adherent - Demande ambiguë !

Ce résultat ne permet pas d'identifier la demande existante ni de confirmer son appartenance à cet adhérent. Aucune nouvelle soumission avec une autre référence n'a été effectuée pour masquer ce conflit.

Les appels de chaque séquence sont espacés d'au moins trois secondes, avec validation TLS active, jetons masqués et sans rejeu automatique de création.

## État et preuves

- Dossier : `80c0ce44-e898-48b4-8adb-e8554e5c3be1`.
- Journal de création : `a3dd78a3-3053-4c75-8ced-36079ccd37b4`.
- Journal conservé avec une tentative, message de doublon et requête envoyée. Le statut technique actuel est `RETRY` ; les tâches de rejeu générique excluent déjà `SUBMIT_CREDIT`.
- Aucun prêt local pour ce dossier.
- La revue et l'autorisation UAT sont à jour avec les correspondances corrigées.

Répertoire des preuves : `uat-artifacts/cbs-submit-AG0100053-20261021T085606Z/`.

| Fichier | Contenu |
| --- | --- |
| `mapping.json` | Sources et correspondances résolues avant envoi |
| `payload-preview.json` | Message préparé |
| `local-steps.json` | Revue, autorisation et résultat de mise en place |
| `remote-calls.json` | Requête réellement envoyée et réponse brute du CBS ; secrets masqués |
| `existing-reference-situation.json` | Consultation du conflit et réponse ambiguë |
| `summary.json` | État final et journal local |
| `dossier-mapping.png` | Vérification visuelle des valeurs 45 et COMPTE-COURANT |

## Vérification du correctif

- **138 tests automatisés réussis**, aucun échec ni test ignoré, sur 14 fichiers : `uat-artifacts/cbs-contract-extended.xml` et `.log`.
- Les tests couvrent notamment les catalogues inactifs/absents, l'isolation de filiale, la priorité de l'objet exact, l'absence de substitution par les anciens produits, l'édition de l'identifiant du mécanisme, l'invalidation d'une autorisation après changement, les messages altérés et la journalisation des refus CBS.
- Compilation frontend complète réussie : encodage, TypeScript, Vite ; avertissement de taille du bundle restant.
- Django `check` sans anomalie ; `makemigrations --check --dry-run` sans changement.
- Contrôle direct du détail dans le navigateur : les deux valeurs envoyées sont affichées et les anciennes alertes de produits à confirmer ont disparu.

## Ce que ce retour ne prouve pas

Le conflit de référence ne prouve pas que tous les autres champs, en particulier `COMPTE-COURANT`, seraient acceptés lors d'une nouvelle création. Le CBS peut arrêter ses validations au contrôle de doublon.

Pour poursuivre une recette positive, il faut rapprocher la demande existante avec sa véritable référence CBS et son adhérent. Ensuite seulement, décider d'une reprise ou d'un nouveau dossier UAT distinct. Le schéma futur d'`externalId` devrait éviter les collisions entre installations/filiales tout en restant stable pour les rejouements ; changer celui de ce dossier sans rapprochement pourrait créer un doublon.

Le callback envoyé est encore une URL locale, non joignable par le CBS distant. Son adresse publique de recette reste à configurer avant une validation des retours asynchrones. Les refus métier définitifs devraient également recevoir un statut de rapprochement explicite plutôt que le statut générique `RETRY`.
