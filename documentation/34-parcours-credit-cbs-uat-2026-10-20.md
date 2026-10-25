# Parcours réel d'un dossier UAT jusqu'à l'envoi au CBS

Date : 20 octobre 2026, heures UTC. Filiale : FIL01. Serveur CBS : `visiondaw.cagecfi.pro`.

## Conclusion

**Parcours local exécuté jusqu'à l'autorisation et à l'envoi réel au CBS ; mise en place non aboutie.** Le CBS refuse le produit de démonstration `CRED-CONSO` avec un code métier 409, transporté en HTTP 200 : `For input string: "CRED-CONSO" !`.

Le dossier **CR-2026-00001** reste `DISBURSEMENT_PENDING`. Le contrôle final constate **zéro prêt local**, aucune référence CBS de création et un journal `SUBMIT_CREDIT` en statut `RETRY`, avec une tentative. Aucun décaissement réussi n'est démontré.

Ce rapport complète les rapports 32 et 33. Les observations du rapport 33 sur le mode simulé et l'absence d'import décrivent sa campagne initiale : le présent parcours a ensuite importé les référentiels et activé le mode réel pour FIL01.

## Autorisation et nature des données

L'utilisateur a confirmé un bac à sable UAT, fourni l'adhérent `AG0100027`, demandé la création puis la transmission d'un dossier complet, et autorisé les compléments fictifs manquants.

- Les informations effectivement reçues du CBS sont conservées dans un instantané séparé et dans les champs de provenance CBS du client.
- L'identité complémentaire, les revenus, la visite, l'analyse et les pièces justificatives sont **synthétiques**. Ils permettent de tester le logiciel ; ils ne prouvent rien sur la situation réelle de cet adhérent.
- Les PDF et le contrat signé de simulation portent des mentions UAT et d'absence de valeur contractuelle. Aucune signature réelle n'a été obtenue.
- Les rôles existants ont été employés via les API métier et leurs contrôles. Aucun statut d'accord ou de décaissement n'a été forcé en base.
- Les API locales ont été exercées avec l'authentification de test Django des utilisateurs existants. Cela vérifie les permissions des routes, pas la connexion interactive ou le parcours visuel du navigateur.

## Dossier et scénario

| Élément | Valeur |
|---|---|
| Dossier | CR-2026-00001 |
| Identifiant | `89a7b5ae-2238-4165-839c-5eb29cc23ca2` |
| Client local UAT | `808c5804-4783-4701-b83e-fee34098d667` |
| Adhérent CBS | AG0100027 |
| Produit local | CONSO-STD |
| Montant | 200 000 XOF |
| Durée et périodicité | 3 mois, mensuelle |
| Taux annuel | 14 % |
| Amortissement | Dégressif |
| Revenus / charges du scénario | 600 000 / 200 000 XOF mensuels, dette existante déclarée nulle dans le scénario |

## Imports et paramètres utilisés

La synchronisation a été appelée par l'API administrateur standard, avant la constitution du dossier. Les réponses originales, l'état antérieur des référentiels et le bilan d'import sont sauvegardés.

| Import standard | Lignes reçues | Résultat |
|---|---:|---|
| Devises | 3 | Importées ; XOF correspond au code CBS FCFA |
| Périodicités | 6 | Importées ; MONTHLY correspond à M |
| Objets de financement | 83 | Importés ; objet 45 utilisé pour la consommation |
| Points de service | 6 | Importés ; deux agences locales rattachées ; AG01 utilisé |
| Gestionnaires | 4 | Importés ; utilisateur chargé associé à AG011U1 |
| Sources de financement | 2 | Importées |
| Motifs de décision | 2 | Importés |
| Professions | 0 | Réponse CBS `datas: null`, aucune profession réelle importée |

Soit **106 lignes** reçues dans les huit périmètres d'import standards. Les cinq types de pièces d'identité avaient aussi été consultés lors de la campagne précédente ; ils ne disposent pas d'un périmètre de synchronisation dans la version du projet examinée.

Le CBS renvoie des codes numériques d'objets qui ne permettent pas au rapprochement automatique actuel de déduire leur usage métier. L'objet 45, libellé crédit à la consommation, a donc été associé explicitement au motif CONSUMPTION dans les paramètres du connecteur.

### Import des produits : vérification demandée par l'utilisateur

Dans cette copie du projet, ni `PERFECT_ENDPOINTS`, ni les chemins persistés du connecteur FIL01, ni `SYNC_SCOPES`, ni les onglets d'import des paramètres ne déclarent un catalogue des produits crédit ou des produits de remboursement. Le formulaire produit conserve des champs de correspondance saisis manuellement.

L'utilisateur indique que l'endpoint existe côté CBS. Pour le retrouver, six variantes de chemins de consultation cohérentes avec les autres référentiels ont été vérifiées avec authentification :

- `gateway-perfect/ref/produit-crd-list`
- `gateway-perfect/ref/produit-epg-list`
- `gateway-perfect/ref/produit-remb-list`
- `gateway-perfect/ref/produit-credit-list`
- `gateway-perfect/ref/produit-epargne-list`
- `gateway-perfect/ref/produit-list`

**Toutes répondent HTTP 404.** Six emplacements habituels de documentation OpenAPI/Swagger, à la racine ou sous `gateway-perfect`, répondent également 404. Ces vérifications limitées ne démontrent pas l'absence de cet endpoint : son chemin exact reste à obtenir de la documentation ou du fournisseur CBS. Aucun identifiant de produit numérique n'a été inventé.

Les appels sont séquentiels, sans retry automatique, avec au moins trois secondes après chaque réponse avant le suivant dans chaque exécution. Aucun 429 observé sur ces recherches. Les corps de réponse sont sauvegardés dans `product-discovery/`.

### Vérification du chemin précisé ensuite par l'utilisateur

L'utilisateur a ensuite indiqué `ref/object-fin-list`. Un nouvel appel réel à `gateway-perfect/ref/object-fin-list` confirme **HTTP 200, code métier 200, 83 lignes**. L'ensemble des champs présents dans ces lignes est exactement `id`, `code`, `libelle`. L'entrée 45 est « CRÉDIT À LA CONSOMMATION » et est bien déjà importée localement.

Dans le mapping actuel, ce référentiel alimente `idObjetFinancement`, qui vaut déjà **45** dans la demande envoyée. Les deux autres champs restent distincts : `idProduitCrd=CRED-CONSO` et `idProduitRemb=COMPTE-COURANT`. La réponse ne contient ni ces champs, ni une association permettant d'établir qu'un identifiant d'objet est aussi un identifiant de produit crédit ou de remboursement.

Le fonctionnement de cet endpoint et son import sont donc confirmés. Il reste à préciser le contrat de correspondance CBS : 45 doit-il également être envoyé comme produit crédit, et quel produit de remboursement lui associer ? Aucun nouvel envoi de création n'a été effectué sur cette seule réponse. Les preuves sont dans `object-fin-verification.json` et `product-discovery/gateway-perfect_ref_object-fin-list.json`.

### Vérification supplémentaire de `ref/periodicite-list`

Sur demande de l'utilisateur, un nouvel appel réel confirme **HTTP 200, code métier 200**, avec six lignes : J (journalière), H (hebdomadaire), M (mensuelle), T (trimestrielle), S (semestrielle) et Y (annuelle). Chaque ligne contient uniquement `id`, `code`, `libelle`.

La périodicité mensuelle est déjà importée dans le catalogue local et envoyée sous `idPeriodicite=M`, avec trois échéances pour ce dossier de trois mois. Le champ `idProduitRemb` désigne séparément le produit de remboursement dans le mapping actuel ; ce n'est pas le champ de périodicité. Cette réponse ne fournit aucun identifiant de produit crédit ou remboursement et ne résout donc pas le rejet de `CRED-CONSO`.

Les réponses et le rapprochement local sont conservés dans `product-discovery/gateway-perfect_ref_periodicite-list.json` et `periodicity-verification.json`. Aucun nouvel envoi de création de crédit n'a été effectué à partir de ces codes de périodicité.

## Étapes exécutées

| Étape | Utilisateur / rôle | Résultat observé |
|---|---|---|
| Import des référentiels et configuration | Administrateur FIL01 | Référentiels importés, mode CBS réel, simulation forcée désactivée |
| Lecture de l'adhérent | Chargé | Réponse CBS réelle conservée ; fiche incomplète pour l'import natif strict |
| Complément de la fiche | Chargé | Client local créé avec compléments fictifs autorisés ; provenance CBS distincte |
| Identité et KYC | Chargé puis chef | Pièce UAT jointe et KYC validé pour le scénario |
| Constitution du dossier | Chargé | Dossier créé, sept pièces attachées et répliquées en GED |
| Visite et analyse | Chargé | Visite fictive et analyse financière saisies, recommandation favorable |
| Contrôle de préparation et soumission | Chargé | API de préparation puis soumission réussies |
| Avis d'analyse | Analyste | Avis favorable enregistré |
| Décision du circuit applicable | Chef d'agence | Accord final enregistré |
| Contrat | Chargé puis juridique | Modèle UAT créé, contrat généré, PDF signé de simulation chargé |
| Vérification documentaire | Juridique | Sept pièces GED vérifiées |
| Revue de mise en place | Administration crédit | Revue effectuée après vérification des pièces |
| Autorisation nominative | Administration crédit | Autorisation enregistrée ; demande de mise en place créée automatiquement |
| Transmission réelle | Opérations | POST CBS envoyé, refus du produit reçu et propagé en HTTP 400 par l'API locale |
| Vérification finale | Opérations | Détail dossier HTTP 200, statut en attente et absence de prêt local confirmés |

Le circuit applicable à ce produit n'exigeait pas de comité. Ce scénario ne valide donc pas les circuits comité, garanties réelles, groupements, réserves, rejets ou délégations.

Deux contrôles négatifs complémentaires ont été observés : un chargé sans permission d'initier la mise en place reçoit 403 ; une demande de mise en place supplémentaire après l'autorisation automatique reçoit 400, le dossier étant déjà en attente. Le lanceur a été adapté pour reprendre l'étape existante sans recréer de dossier.

## Réponse CBS et intégrité de l'état

La requête complète contient notamment :

```json
{
  "externalId": "CR-2026-00001",
  "idPointService": "AG01",
  "idPeriodicite": "M",
  "taux": 14.0,
  "nombreEcheance": 3,
  "idObjetFinancement": "45",
  "idGestionnaire": "AG011U1",
  "idProduitCrd": "CRED-CONSO",
  "idProduitRemb": "COMPTE-COURANT",
  "montantDemande": 200000.0,
  "codeDevise": "FCFA",
  "codeAdherent": "AG0100027"
}
```

La réponse brute est :

```json
{"message":"For input string: \"CRED-CONSO\" !","responseCode":409}
```

Le message indique que la conversion du produit échoue, vraisemblablement parce qu'un identifiant numérique est attendu. Le produit de remboursement reste lui aussi un code de démonstration ; sa validité n'est pas encore évaluée par une création réussie.

FinFlow traite correctement ce code métier comme un échec malgré HTTP 200. Le journal porte l'erreur et la clé `disburse:89a7b5ae-2238-4165-839c-5eb29cc23ca2`. L'état local ne simule pas un succès. La réponse brute CBS est conservée dans les artefacts ; le champ `response_payload` du journal métier est toutefois vide pour cet échec : sa conservation dans l'application est à améliorer.

## Solidité et améliorations prioritaires pour l'UAT

### Bloquants avant validation du parcours CBS

1. **Raccorder l'import des produits réels.** Obtenir l'endpoint et son schéma, stocker les identifiants source, puis proposer les produits importés dans les paramètres de crédit et de remboursement. Vérifier l'existence et le type des identifiants avant l'autorisation.
2. **Achever une mise en place positive.** Corriger les correspondances sur le même dossier, réévaluer la validité des preuves d'autorisation, reprendre de façon idempotente, obtenir une référence CBS puis consulter sa situation. Aucune de ces étapes finales n'est encore validée.
3. **Résoudre l'endpoint portefeuille/impayés.** `crd/impayes` reste en 404 ; l'import initial déclenché par l'activation du connecteur l'a confirmé.
4. **Configurer un callback joignable par le CBS.** Le payload du test contient une URL `http://localhost/...` : elle ne peut pas désigner l'application depuis le serveur CBS distant. Définir l'URL publique UAT et vérifier le secret, les doublons et les retours asynchrones.
5. **Distinguer explicitement les fonctions simulées en mode réel.** Le calcul de l'encours client REST non implémenté peut encore tomber sur le simulateur ; une valeur simulée ne doit pas servir de preuve d'absence de dette.

### Fiabilité et traçabilité

- Tester et corriger le classement des échéances : la recherche par sous-chaîne peut confondre « impayé », « non payé », « unpaid » ou « partiellement payé » avec un paiement complet. Voir audit 32 pour les autres constats source.
- Valider les codes métier aussi pour les référentiels ; une erreur sous HTTP 200 ne doit pas être importée comme une liste vide.
- Conserver la réponse brute expurgée dans le journal métier des échecs. Distinguer erreur de paramétrage définitive et erreur transitoire : le rejet actuel est classé `RETRY`.
- Formaliser un import client avec aperçu, compléments locaux et provenance champ par champ lorsque le CBS fournit une identité partielle. Ici, le chemin d'import natif strict n'a pas accepté la fiche : les compléments ont été créés par API et les champs CBS reportés par le mapping canonique avec acteur d'audit.
- Compléter les imports des types de pièces et des produits ; présenter clairement les catalogues vides ou non disponibles.
- Revalider les autorisations si les pièces, conditions ou correspondances CBS changent après revue ; garantir que le dossier envoyé correspond bien à celui autorisé.
- Revoir les contrôles de remplacement/rattachement des contrats et des versions GED identifiés dans l'audit global.

### Couverture à ajouter

Une recette complète doit encore couvrir : accès interfiliales, circuits de montants élevés et comités, réserves puis levée, refus, pièces périmées, garanties requises, identité morale/groupement, indisponibilité réseau et reprise, timeout après acceptation distante, double clic, callback dupliqué ou invalide, rapprochement échéancier local/CBS, remboursement partiel, impayé, restructuration et clôture. Ce scénario positif local unique ne permet pas d'affirmer que tous ces parcours sont solides.

## Projet démarré et limites de vérification

Le backend a été redémarré pour prendre en compte le fichier de confiance TLS local. La validation HTTPS reste activée. Le contrôle HTTP final vérifie le backend sur `http://127.0.0.1:8000/api/v1/health/` et le frontend sur `http://127.0.0.1:5173/` : tous deux répondent 200. Cela ne constitue pas une vérification visuelle du navigateur, dont l'accès était bloqué dans cette session.

Le contrat a bien été généré par l'application. La vérification visuelle du DOCX via l'outil documentaire n'a pas pu aboutir, LibreOffice étant absent. Un aperçu PDF des justificatifs synthétiques a été contrôlé ; ne pas considérer tous les rendus bureautiques comme validés.

## Preuves et reprise

Répertoire : `uat-artifacts/journey-20261020T223709Z/`, exclu de Git, avec réponses contenant potentiellement des données client.

- `execution-state.json` : étapes et identifiants de reprise ; 37 actions enregistrées avant le contrôle final séparé.
- `reference-sync-api.json`, `reference-backup.json`, `responses/` : bilan, état antérieur et réponses d'import.
- `genuine-CBS-client.json`, `synthetic-client-complements.json` : séparation source CBS / compléments UAT.
- `local-*.json` : acteur, route, statut et réponse des étapes métier.
- `execution-remote-calls.json`, `journey-cbs-*.json` : appels CBS du parcours et corps expurgés.
- `product-discovery/` : recherches limitées de route produits et documentation.
- `final-state.json`, `final-dossier-api.json`, `final-disbursement-journal.json` : contrôle d'état et données réellement envoyées.
- `files/` : justificatifs et modèle synthétiques UAT.

Le script `backend/scripts/run_cbs_uat_credit.py` reprend le même dossier. **Ne pas le relancer sans nouvelle information sur les produits** : il répéterait le rejet connu. Après obtention des identifiants source, contrôler les correspondances et les validations avant de reprendre ; après une réponse ambiguë, rapprocher avec le CBS avant toute nouvelle création.
