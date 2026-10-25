# Audit des référentiels CBS et du dossier AG0100053

Date : **20 octobre 2026**, heures UTC. Filiale FIL01. CBS : `visiondaw.cagecfi.pro`, déclaré bac à sable UAT par l'utilisateur.

## Avis

**Les imports fonctionnent et conservent les données reçues. Leur utilisation dans le parcours crédit reste incomplète et parfois incohérente. Je ne validerais pas encore une UAT de mise en place CBS de bout en bout.**

Le nouveau dossier **CR-2026-00002**, lié à l'adhérent **AG0100053**, a été créé et traité jusqu'à l'autorisation locale de mise en place. Il reste **DISBURSEMENT_PENDING**, sans prêt local et sans création CBS envoyée pour ce nouveau dossier. Les deux correspondances produits restent des valeurs de démonstration ; le test s'est arrêté avant de répéter le rejet déjà observé sur le dossier précédent.

Les principaux problèmes sont : les 83 objets importés se réduisent à une seule option « Autre » dans la logique du formulaire ; les produits crédit/remboursement ne sont pas issus d'un catalogue vérifié ; certains référentiels ne sont pas consommés ; la préparation et l'envoi utilisent des règles de résolution différentes ; l'encours client REST peut encore être simulé à zéro.

## Méthode et limites

- **25 échanges réels CBS**, séquentiels : authentification, deux imports complets, types de pièces, consultations de l'adhérent et contrôles de situation/portefeuille. Pas de scan de nouvelles routes dans cette campagne.
- Au moins **3 secondes après chaque réponse** avant l'appel suivant dans chaque exécution ; aucune relance réseau automatique, aucun 429 observé. TLS vérifié.
- **24 appels locaux** d'audit des imports, **33 étapes API** du dossier, **18 lectures des référentiels** par les rôles chargé et lecteur, puis contrôles de préparation et d'état final.
- Tests métier via les API Django avec les utilisateurs existants et leurs permissions. La navigation visuelle dans le navigateur et le login interactif ne sont pas validés par cette méthode.
- Contrôles hors réseau séparés pour les erreurs de parseur, la logique de sélection des objets du formulaire et les correspondances. Une simulation utilisée comme test de défaut est explicitement identifiée comme telle.
- Les données manquantes, revenus, visite et justificatifs ont été complétés par des données **fictives UAT**, conformément à l'autorisation déjà donnée. Ils ne constituent pas une vérification économique ou KYC réelle de l'adhérent.
- Aucun correctif fonctionnel de l'application n'a été appliqué pendant cet audit. Les scripts de recette ont été rendus réutilisables par code adhérent ; le garde-fou empêchant l'envoi du payload connu comme incorrect appartient au script de recette, pas au produit FinFlow.

## 1. Ce que contient réellement l'écran Référentiels CBS

Le bouton « Mettre à jour depuis le CBS » déclenche huit imports. Le neuvième onglet, « Méthodes de remboursement », est un catalogue **manuel**, bien qu'il se trouve sur le même écran.

Tous les chemins ci-dessous sont sous `gateway-perfect/ref/`.

| Onglet | Endpoint / origine | Reçus et actifs | Correspondance utile | Verdict |
|---|---|---:|---|---|
| Périodicités | `periodicite-list` | 6 | `LoanPeriodicity.cbs_code` → `idPeriodicite` | Import et résolution mensuelle corrects |
| Devises | `devise-list` | 3 | Code ISO local → code CBS → `codeDevise` | XOF → FCFA correct ; utiliser le code CBS, pas son ID numérique |
| Objets de financement | `object-fin-list` | 83 | `FinancingObject.cbs_code` → `idObjetFinancement` | Import correct, sélection dans le formulaire défectueuse |
| Sources de financement | `source-fin-list` | 2 | Catalogue local `FinancingSource` | Données importées, aucun champ lié dans le dossier ou le payload actuel |
| Motifs de décision | `motif-decision-list` | 2 | Catalogue local `DecisionMotif` | Données importées, non reliées aux décisions du circuit ou au payload actuel |
| Professions | `profession-list` | 0 | Catalogue `CbsProfession` ; provenance client `cbs_profession_id` | HTTP 200 mais `datas: null` ; aucun choix métier réel disponible |
| Points de service | `point-service-list` | 6 | Agence locale → `cbs_point_of_service_id` → `idPointService` | AG01 du client correctement rapproché |
| Gestionnaires | `gestionnaire-list` | 4 | Utilisateur soumissionnaire → `cbs_id` → `idGestionnaire` | AG011U1 existe et est correctement envoyé |
| Méthodes de remboursement | Saisie locale, sans import | 3 | DEGRESSIVE / IN_FINE / BULLET → `cbs_code` ou surcharge produit → `idProduitRemb` | Les trois portent COMPTE-COURANT ; correspondance CBS non vérifiée |

Les huit imports totalisent **106 lignes**. Un neuvième référentiel distant, `type-piece-identite-list`, répond aussi avec **5 lignes**, mais n'est ni importé par ce bouton ni présenté dans ces onglets.

### Qualité et fidélité de l'import

Sur les 106 lignes :

- aucun ID dupliqué ; aucun `id`, `code` ou `libelle` manquant dans les listes non vides ;
- aucune différence entre source et stockage pour les codes attendus, identifiants CBS et libellés, après les transformations documentées ;
- aucune perte de ligne dans les API servant l'écran ; les 83 objets sont récupérés sur deux pages de 50 ;
- aucune troncature constatée dans cet échantillon : le plus long libellé reçu mesure 150 caractères ;
- les deux imports successifs laissent les mêmes lignes et valeurs ; le second ne crée, ne met à jour et ne désactive aucune ligne.

Les GET des neuf listes répondent 200 pour le chargé et le lecteur. Le chargé reçoit 403 s'il tente la synchronisation. Les PATCH des sept catalogues importés non vides reçoivent 405, conformément à leur lecture seule. Aucun PATCH sur une profession existante n'a pu être testé puisque le catalogue est vide.

## 2. Vérification des champs des référentiels

| Champ | Source et transformation | Avis |
|---|---|---|
| `id` exposé par l'API FinFlow | UUID de la ligne locale | À distinguer de l'identifiant du CBS |
| `code` | Code métier local, généralement dérivé du code CBS normalisé | Peut être transformé : MONTHLY et XOF ne sont pas les codes envoyés au CBS |
| `label` | `libelle` CBS | Fidèlement conservé dans cet échantillon |
| `cbs_code` | ID source pour la plupart des catalogues ; code alphabétique pour les devises | Cette exception est nécessaire pour XOF → FCFA ; une règle « toujours envoyer id » serait incorrecte |
| `is_active` | État local piloté par la présence dans la liste importée non vide | Les données inactives sont masquées dans l'écran ; prévoir une vue d'historique |
| `sort_order` | Ordre de présentation local | Ce n'est pas une donnée bancaire retournée par le CBS |
| `description` | Champ local, absent des réponses de référence | L'import ne l'enrichit pas |
| `periods_per_year` | Déduction locale selon la périodicité | Non retourné par le CBS : convention à rapprocher avec son calcul d'échéancier |
| `purpose_type` | Déduction depuis un code sémantique comme CONSO | Vide pour les 83 codes numériques reçus ; l'écran le montre sans permettre son édition |

### Périodicités disponibles

| Code local | Identifiant CBS | Libellé | Périodes/an utilisées localement |
|---|---|---|---:|
| DAILY | J | Journalière | 360 |
| WEEKLY | H | Hebdomadaire | 52 |
| MONTHLY | M | Mensuelle | 12 |
| QUARTERLY | T | Trimestrielle | 4 |
| SEMIANNUAL | S | Semestrielle | 2 |
| ANNUAL | Y | Annuelle | 1 |

BIMONTHLY reste inactif car absent de la réponse CBS. Le choix mensuel du dossier produit correctement trois échéances pour trois mois. Les conventions journalières/hebdomadaires et les arrondis de périodes ne sont pas validés par une concordance avec un échéancier CBS positif dans ce test.

### Objets de financement : perte de choix confirmée

L'import stocke par exemple l'objet **45 — CRÉDIT À LA CONSOMMATION**. Cependant :

1. Le CBS fournit des codes numériques ; le rapprochement automatique attend des codes comme CONSO ou EQUIPEMENT.
2. Les **83 lignes ont `purpose_type` vide**.
3. Le formulaire convertit chaque code inconnu en OTHER, puis déduplique par ce type générique.
4. Résultat du contrôle hors navigateur reproduisant la logique du code : **une seule option**, OTHER, libellée avec le premier objet « ACHAT D’ENCRE POUR FINALISER UNE COMANDE ».

L'utilisateur ne peut donc pas sélectionner correctement l'un des 83 objets à travers cette logique. Le dossier de test a été créé par API avec CONSUMPTION ; cela a permis de tester le workflow, mais ne valide pas la création par ce formulaire.

Le paramètre du connecteur associe déjà CONSUMPTION à 45, donc le constructeur de payload produit `idObjetFinancement=45`. Le calcul des références affichées dans le dossier ignore cette correspondance et continue à signaler l'objet comme manquant. Les deux chemins de résolution sont incohérents.

### Sources, motifs et professions

Les sources reçues sont **1 / SRC_ORD / Ressources ordinaires** et **2 / SRC_AFF / Ressources affectées**. Elles ne sont pas proposées comme référence liée du dossier actuel. Le champ libre « origine des fonds » n'est pas une association à ce catalogue.

Les motifs reçus sont **1 / CLIENT SOLVABLE** et **2 / DOSSIER INCOMPLET**. Ils ne sont pas associés aux avis et décisions du workflow, qui ont leurs propres valeurs et commentaires. Leur affichage ne démontre pas une utilisation dans le traitement d'un crédit.

Le catalogue professions est vide. Le client garde un champ profession local et un identifiant CBS de provenance, mais l'import actuel ne permet pas de vérifier une profession du nouvel adhérent contre une liste CBS disponible.

## 3. Adhérent AG0100053 : champ par champ

La consultation réelle réussit : HTTP 200 et code métier 200.

| Donnée | Réponse / constat | Utilisation et contrôle |
|---|---|---|
| Code adhérent | AG0100053 | Conservé comme `cbs_client_id`, envoyé en `codeAdherent` |
| Compte manuel | **FAD053/02** | Conservé comme `cbs_account_number`, envoyé en `numManuel` |
| Nom agrégé | Présent dans la réponse | Conservé en provenance CBS ; ce n'est pas un découpage fiable nom/prénoms |
| Nom et prénoms séparés | Absents | Deux exigences de l'import strict restent insatisfaites |
| Point de service | AG01 | Existe dans les six points importés et correspond à l'agence locale du dossier |
| Nom du point | CMT : AGENCE FOREVER | Conservé en provenance CBS |
| Date d'inscription | 2022-09-29 | Conservée et reprise comme date d'entrée en relation du scénario |
| Validité adhérent | `estValide=true` | Ne remplace pas une vérification KYC complète |
| Plafond crédit | `null` / absent | Conservé inconnu ; aucune conversion en plafond zéro ni preuve de capacité disponible |
| Date et lieu de naissance | Absents | Complément de naissance fictif pour le scénario UAT |
| Numéro, délivrance et expiration de pièce | Absents | Trois exigences de l'import strict ; compléments fictifs identifiés UAT |
| Téléphone, ville, adresse | Absents | Trois autres exigences de l'import strict ; compléments fictifs |
| Profession et ID profession | Absents | Aucun rapprochement de profession réel possible |
| Nationalité, civilité, situation matrimoniale | Absentes | Valeurs locales synthétiques pour tester la fiche |
| Produit épargne / remboursement du client | Absent | Impossible d'en déduire `idProduitRemb` |
| Encours et crédits existants | Non fournis par cette réponse | Ne pas les conclure nuls |

**Point vérifié propre à cet adhérent : le code adhérent et le compte sont différents.** Le payload distingue bien AG0100053 de FAD053/02 ; aucune substitution du compte par le code n'a été faite.

Le preview annonce **9 informations obligatoires manquantes** : nom, prénoms, naissance, numéro de pièce, délivrance, expiration, téléphone, ville et adresse. L'appel standard `cbs-import` reçoit bien **400**. C'est un contrôle utile, mais le produit manque d'un chemin explicite permettant des compléments locaux contrôlés lorsque la source est partielle.

Pour poursuivre la recette autorisée, le client local a été créé avec une identité distinctement marquée TEST/UAT. Les champs CBS ont été alimentés par le mapping canonique et un acteur d'audit, avec conservation séparée de la réponse originale. Ce contournement de recette du manque de données **ne vaut pas validation du bouton d'import client standard**.

## 4. Nouveau dossier créé et validations

[Ouvrir CR-2026-00002](http://127.0.0.1:5173/dossiers/80c0ce44-e898-48b4-8adb-e8554e5c3be1)

| Élément | Valeur / résultat |
|---|---|
| Identifiant dossier | `80c0ce44-e898-48b4-8adb-e8554e5c3be1` |
| Client local | `66f1eaf1-668b-419d-802e-238fdb71dfb8` |
| Hypothèse de profil UAT | Personne physique salariée, sans affirmation sur le profil réel du titulaire CBS |
| Produit | CONSO-STD |
| Conditions | 200 000 XOF, 3 mois, 14 % annuel, mensuel, dégressif |
| Situation financière fictive | Revenus 600 000 XOF/mois, charges 200 000, apport 50 000 sur projet 250 000 |
| Pièces | 7 justificatifs joints au dossier et vérifiés en GED ; scan d'identité client ; contrat signé de simulation |
| KYC | Validé par le chef pour ce scénario fictif |
| Analyse et visite | Analyse de référence créée, recommandation favorable, visite explicitement simulée |
| Circuit | Avis analyste puis accord du chef, selon le circuit applicable |
| Contrat | Modèle UAT, génération réussie et upload du PDF signé de simulation |
| Administration crédit | Revue puis autorisation nominative réussies |
| État final | DISBURSEMENT_PENDING |
| Prêt local / référence de création CBS | Aucun / aucune |

Les PDF synthétiques ont été rendus et contrôlés visuellement. Le contrat a été généré par l'application ; sa vérification visuelle DOCX reste limitée par l'absence de LibreOffice dans cet environnement. Les fichiers sont des pièces de recette sans valeur contractuelle.

Ce circuit n'exige pas de comité ni de garantie obligatoire. Ces parcours n'ont donc pas été validés par ce scénario.

## 5. Chaque champ de la requête de mise en place préparée

Le payload ci-dessous est une **préparation enregistrée**, pas une requête de création envoyée pour AG0100053.

| Champ CBS | Valeur préparée | Provenance / correspondance | Avis |
|---|---|---|---|
| `externalId` | CR-2026-00002 | Référence du nouveau dossier | Correct, stable |
| `callbackUrl` | `http://localhost/api/v1/cbs/callbacks/crd/<uuid>/` | Configuration publique de l'application | Injoignable depuis le serveur distant ; à configurer en URL UAT publique |
| `idPointService` | AG01 | Agence locale associée au point importé et au client | Correspondance vérifiée |
| `idPeriodicite` | M | MONTHLY → catalogue CBS | Correspondance vérifiée |
| `taux` | 14.0 | Conditions approuvées / produit local | Cohérent avec le scénario ; compatibilité avec un produit CBS réel non validée |
| `nombreEcheance` | 3 | Durée et nombre de périodes/an | Correct pour ce scénario mensuel |
| `idObjetFinancement` | 45 | Correspondance CONSUMPTION du connecteur vers l'objet importé | Présent dans le CBS ; incohérence avec le contrôle d'affichage à corriger |
| `idGestionnaire` | AG011U1 | `cbs_id` du chargé soumissionnaire, entrée importée | Identifiant existant ; le référentiel reçu n'expose pas de relation explicite gestionnaire/agence |
| `idProduitCrd` | CRED-CONSO | Paramètre du produit local | **Bloquant : code de démonstration déjà rejeté par le CBS lors du dossier précédent** |
| `idProduitRemb` | COMPTE-COURANT | Surcharge produit, prioritaire sur la méthode de remboursement | **Non vérifié : aucun catalogue source ou identifiant produit réel établi** |
| `montantDemande` | 200000.0 | Montant proposé et approuvé | Conforme aux bornes du produit local ; plafond CBS du client inconnu |
| `codeDevise` | FCFA | XOF local → code de devise importé | Correspondance vérifiée |
| `codeAdherent` | AG0100053 | Consultation réelle | Correspondance vérifiée |
| `numManuel` | FAD053/02 | Consultation réelle | Correspondance vérifiée, distincte de l'adhérent |
| `numPieceIdentite` | UAT-AG0100053 | Complément fictif autorisé | Donnée UAT, pas une identité certifiée par le CBS |

`idProduitRemb` désigne ici le produit de remboursement ; `idPeriodicite` porte la fréquence. Ils ne doivent pas être confondus. L'objet de financement constitue encore un troisième champ distinct de `idProduitCrd`.

Les sources de financement, motifs de décision, frais, garanties, justificatifs, revenus et contrat ne figurent pas dans ce payload de création actuel. Leur gestion locale peut être utile à la décision, mais ne signifie pas que le CBS les reçoit. Le contrat d'interface doit préciser ce qui doit être transmis ou conservé uniquement dans FinFlow.

## 6. Contrôles négatifs et problèmes reproduits

### Contrôles qui fonctionnent

- Identifiant de point de service inconnu : **400** par l'API d'agence.
- Identifiant de gestionnaire inconnu : **400** par l'API utilisateur.
- Périodicité, mécanisme et devise inconnus : rejet par le validateur de références utilisé pour le dossier, testé hors enregistrement.
- Import client incomplet : **400**, avec liste des champs manquants.
- Écriture dans les catalogues importés non vides : **405**.
- Synchronisation par le chargé : **403**.
- Situation d'un crédit inexistant : HTTP 200 / code métier **409**, correctement rejeté par l'adaptateur.

### Problèmes reproduits

1. **Choix d'objet perdu dans le formulaire.** 83 objets → OTHER → une seule option après déduplication. Le champ d'objet doit conserver l'identifiant précis sélectionné, même si plusieurs objets relèvent du même type métier.
2. **Produit non vérifié accepté au paramétrage.** Le sérialiseur du produit accepte `UAT-NONEXISTENT-PRODUCT` lors d'une validation sans sauvegarde. Aucun rattachement à un catalogue réel n'est contrôlé.
3. **Résolution CBS divergente.** `application_cbs_refs` signale l'objet absent alors que le constructeur du payload résout bien 45 via le connecteur.
4. **État prêt ambigu.** L'API de préparation renvoie `ready=true` malgré `cbs_mapping.ok=false`, car ce contrôle est non bloquant. Elle ne signale pas la nature factice des codes produits.
5. **Erreurs de référentiel assimilées à du vide.** Hors réseau, une réponse HTTP 200 / métier 409 et une enveloppe sans `datas` sont toutes deux interprétées comme `[]`, sans exception. La vraie liste vide valide devient indiscernable de ces erreurs.
6. **Encours REST simulé.** En appelant l'opération d'encours avec le connecteur réel, le code retourne ACK, encours zéro et `raw.simulated=true`, avec **zéro appel HTTP**. C'est un défaut de preuve, pas un résultat réel pour AG0100053.
7. **Portefeuille toujours indisponible.** Le nouvel appel à `crd/impayes` répond **404** ; aucune liste d'encours/impayés du client ne peut être déduite de cet échec.

### Points supplémentaires relevés dans le code

- Les scopes d'import sont traités séparément et les erreurs remontent par périmètre : prévoir un statut global explicite de réussite partielle et conserver l'état de fraîcheur de chaque catalogue.
- Une réponse vide ne désactive pas les anciennes lignes avec la règle actuelle ; définir une politique distinguant liste réellement vide, données indisponibles et erreur technique.
- La fonction qui complète les endpoints de références peut remplacer des chemins personnalisés par les chemins par défaut. Respecter les surcharges filiale pour éviter de casser un connecteur adapté.
- Les valeurs de repli du connecteur contiennent encore PS01, GEST01 et les périodicités historiques MENSUEL, JOURNALIER, etc. Le dossier actuel utilise les vrais catalogues en priorité ; ces valeurs de secours ne sont pas validées pour le serveur connecté.
- Les validations de correspondance des agences/gestionnaires et celles des produits sont de niveaux différents ; uniformiser les contrôles de présence, activation, source et filiale.

## 7. Améliorations proposées et critères de recette

| Priorité | Modification | Résultat attendu en UAT |
|---|---|---|
| P1 | Sélectionner un objet CBS précis dans le dossier ; garder le type métier séparément | Les 83 objets restent sélectionnables ; sélectionner 45 affiche et envoie 45 |
| P1 | Importer ou configurer les produits crédit et remboursement avec une source vérifiable | Aucun code de démonstration n'est autorisé en mise en place réelle ; devise, activité et conditions du produit sont contrôlées |
| P1 | Utiliser le même résolveur pour le formulaire, le détail, la préparation et l'envoi | Le dossier affiché « prêt CBS » correspond exactement au payload autorisé |
| P1 | Rendre les contrôles CBS bloquants à l'autorisation/envoi | Impossible d'autoriser un produit non résolu ; l'erreur est visible avant les dernières validations |
| P1 | Supprimer les retours simulés implicites des opérations REST réelles | Encours inconnu ou indisponible est explicite ; jamais assimilé à zéro |
| P1 | Rétablir portefeuille/situation positive et configurer le callback public | Une création produit une référence, sa situation est consultée et les retours sont rapprochés |
| P2 | Vérifier code métier et schéma avant chaque import | Une erreur 409 ou une enveloppe invalide n'affiche pas « import vide réussi » |
| P2 | Proposer des compléments client contrôlés et une provenance par champ | Le client incomplet est traité sans falsifier la source CBS ni supprimer les contrôles KYC |
| P2 | Relier les sources et motifs lorsque le contrat CBS les requiert | Les données sélectionnées sont conservées, auditées et transmises lorsque nécessaire |
| P2 | Intégrer les types de pièces et clarifier l'onglet manuel des remboursements | Le personnel distingue imports CBS, paramètres locaux et données manquantes |
| P2 | Afficher fraîcheur, erreurs, écarts, désactivations et mappings manquants | Un import partiel ne donne pas l'impression d'une configuration complète |

L'étape suivante de recette est de renseigner des correspondances produits établies par le contrat CBS, puis reprendre **ce même dossier**, revoir la validité de son autorisation si son paramétrage change, effectuer une création idempotente et rapprocher la situation et l'échéancier retournés. Les tests de timeout après acceptation, reprise, doublon, callback, rejet, réserve, comité, garantie, multi-filiale et clôture restent nécessaires pour une UAT complète.

## 8. État du projet et preuves

Les contrôles finaux HTTP vérifient le backend sur `127.0.0.1:8000/api/v1/health/` et le frontend sur `127.0.0.1:5173/` : **200**. Ils confirment des serveurs accessibles, pas l'absence de toute erreur de rendu navigateur.

Répertoire des preuves : `uat-artifacts/journey-AG0100053-20261020/`, exclu de Git. Il contient des données client ; les jetons d'authentification sont masqués.

- `audit-summary.json`, `sync-first.json`, `sync-second.json` : résultats et idempotence des imports.
- `references-before.json`, `references-after-first.json`, `references-after-second.json` : états du catalogue.
- `reference-field-equality.json` : comparaison de chaque ligne source aux champs locaux.
- `remote-calls.json`, `responses/` : appels réels et réponses de la campagne d'import/client.
- `local-audit-calls.json`, `final-controls.json` : droits, lectures, contrôles négatifs et nouvelles lectures CBS.
- `client-preview-api.json`, `client-strict-import.json` : fiche incomplète et refus standard.
- `genuine-CBS-client.json`, `client-source-all-fields.json`, `synthetic-client-complements.json` : provenance et compléments.
- `ui-purpose-options-offline.json` : déduction des options du formulaire à partir des 83 objets réels.
- `reference-parser-negative-offline.json`, `outstanding-rest-fallback-offline.json` : défauts reproduits sans réseau.
- `application-cbs-refs.json`, `readiness-final-charge.json`, `setup-payload-preview.json` : écart entre préparation et payload.
- `execution-state.json`, `local-*.json` : les 33 étapes du nouveau dossier et ses identifiants.
- `correspondence-checks.json`, `final-state.json`, `final-dossier-api.json` : concordance des valeurs et absence de prêt créé.

**Conclusion pratique :** la synchronisation constitue une bonne base technique sur l'échantillon reçu ; la chaîne « référentiel importé → choix utilisateur → donnée du dossier → contrôle d'autorisation → champ CBS envoyé » doit encore être unifiée avant de déclarer le parcours solide.
