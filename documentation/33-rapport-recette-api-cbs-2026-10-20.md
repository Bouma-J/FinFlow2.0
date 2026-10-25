# Rapport de tests de l'API CBS et préparation UAT

Date : 20 octobre 2026, heures UTC. Filiale : FIL01. Serveur : `visiondaw.cagecfi.pro`. Le serveur a été déclaré bac à sable UAT par l'utilisateur.

## Avis de recette

**Connexion et lecture des référentiels opérationnelles ; parcours complet d'un crédit non validé pour l'UAT en l'état.**

L'authentification réelle et les neuf référentiels répondent. Une consultation d'adhérent existant fonctionne. En revanche, le portefeuille/impayés renvoie 404, l'adhérent renvoyé ne fournit pas les données nécessaires à un import complet, les correspondances locales sont incomplètes et l'application conserve son mode simulé. La création avec le seul code adhérent a effectivement été envoyée après instruction de l'utilisateur et a été refusée pour paramètres manquants.

L'application ne peut donc pas encore démontrer un parcours réel complet : client utilisable → dossier instruit → accord → crédit créé au CBS → situation et impayés → clôture. Les résultats ci-dessous ne constituent pas une recette de charge ni une validation des effets financiers dans le CBS.

## Périmètre et rythme

- **14 endpoints distincts identifiés** dans le code et les chemins du connecteur ; aucun scan de routes inconnues.
- **23 échanges HTTP**, un par un, dans trois campagnes : 22:25:07, 22:28:03 et 22:31:18 UTC.
- **3 secondes au minimum après chaque réponse avant la requête suivante** dans une campagne ; pauses plus longues entre campagnes. Aucun parallélisme réseau ni retry automatique.
- Aucun HTTP 429 observé. Cela confirme uniquement l'absence de limitation sur cet échantillon et à ce rythme.
- HTTP : 20 réponses 200, deux 404, une 500. Temps observés par appel : minimum 172 ms, médiane 203 ms, maximum 719 ms. Ces mesures ne représentent pas un engagement de performance en charge.
- TLS vérifié à chaque appel, avec les autorités de confiance du système ajoutées à celles de Requests pour cette campagne. Pas de désactivation de validation HTTPS.
- Les réponses ont été rejouées hors ligne dans l'adaptateur actuel pour vérifier leur traitement par FinFlow, sans appel supplémentaire au CBS.
- Les identifiants secrets, en-têtes d'authentification et jetons ne sont pas conservés en clair dans les preuves. Les réponses d'adhérent peuvent contenir des données personnelles et restent dans le dossier local d'artefacts exclu de Git.
- Aucun import de référentiel/client dans la base métier, aucune activation du mode réel et aucune correction de parseur n'ont été appliqués pendant cette campagne.

Le nombre de résultats `PASS` du lanceur ne constitue pas le nombre de fonctions métier validées : un test négatif passe lorsque le serveur refuse la requête. Le test exploratoire « situation avec code seul » avait une attente de succès et échoue dans la trace ; son 409 est ensuite interprété comme une exigence de contrat API, pas comme une panne du CBS.

## Résultats endpoint par endpoint

Les chemins ci-dessous sont relatifs à l'URL de base du connecteur.

| Endpoint | Méthode / cas | Réponse et données | Traitement et verdict |
|---|---|---|---|
| `gateway-perfect/authentification` | POST formulaire, trois sessions | HTTP 200, jeton obtenu à chaque fois | Authentification réelle réussie ; secrets masqués |
| `gateway-perfect/ref/devise-list` | GET authentifié | HTTP 200, code métier 200, **3** lignes | 3 lignes normalisées, identifiants/codes/libellés présents |
| `gateway-perfect/ref/gestionnaire-list` | GET authentifié | HTTP 200/200, **4** lignes | 4 lignes normalisées ; associations aux utilisateurs à vérifier |
| `gateway-perfect/ref/motif-decision-list` | GET authentifié | HTTP 200/200, **2** lignes | 2 lignes normalisées |
| `gateway-perfect/ref/object-fin-list` | GET authentifié | HTTP 200/200, **83** lignes | 83 lignes normalisées ; choix métier à associer aux objets FinFlow |
| `gateway-perfect/ref/periodicite-list` | GET authentifié | HTTP 200/200, **6** lignes | 6 lignes normalisées ; codes locaux non alignés avec les identifiants reçus |
| `gateway-perfect/ref/point-service-list` | GET authentifié | HTTP 200/200, **6** lignes | 6 lignes normalisées ; le point de l'adhérent fourni existe dans la liste |
| `gateway-perfect/ref/profession-list` | GET authentifié | HTTP 200/200, **`datas: null`** | Adaptateur : liste vide ; disponibilité HTTP confirmée, contenu métier indisponible |
| `gateway-perfect/ref/source-fin-list` | GET authentifié | HTTP 200/200, **2** lignes | 2 lignes normalisées |
| `gateway-perfect/ref/type-piece-identite-list` | GET authentifié | HTTP 200/200, **5** lignes | 5 lignes normalisées ; endpoint déclaré mais absent des scopes de synchronisation standards |
| `gateway-perfect/adh/situation` | POST adhérent existant fourni par l'utilisateur | HTTP 200/200, nom agrégé, compte, plafond, agence et indicateur de validité | Correspondance des données reçues réussie ; réponse insuffisante pour un import complet |
| `gateway-perfect/adh/situation` | POST sans paramètres puis code inexistant | HTTP 200, code métier **409** | Refus correct ; FinFlow rejette ces réponses |
| `gateway-perfect/crd/situation` | POST sans paramètres, référence inconnue, puis adhérent seul | HTTP 200, code métier **409** | Contrôles négatifs corrects. Consultation positive non validée : une `refDemande` existante reste nécessaire |
| `gateway-perfect/crd/impayes` | POST impayés uniquement puis corps vide | **HTTP 404 dans les deux cas** | Portefeuille/impayés indisponible au chemin configuré. Corps d'erreur enregistré, sans assimilation à une liste vide |
| `gateway-perfect/crd/simple` | OPTIONS, puis POST avec le seul code adhérent sur instruction de l'utilisateur | OPTIONS HTTP 200 ; POST HTTP 200, **code métier 409 : « Paramètres manquants ! »** | Route joignable et validation d'entrée observée. Aucune création confirmée et aucune référence de nouveau crédit obtenue |

Au total : **111 lignes de référentiels** reçues et conservées, sans doublon d'identifiant ni champ id/code/libellé manquant dans les listes non vides. Aucun référentiel n'a perdu de ligne entre la réponse et la normalisation.

### Cas sans authentification

Le GET sans Bearer sur `ref/devise-list` renvoie **HTTP 500**, au lieu d'un refus explicite 401 ou 403. Aucune donnée de référentiel n'a été reçue dans ce cas. Ce résultat ne démontre pas une fuite d'accès ; il révèle une mauvaise gestion d'erreur côté passerelle/CBS, susceptible d'être prise à tort pour une panne temporaire.

### Sens du HTTP 200 avec code métier 409

Plusieurs refus fonctionnels sont transportés en HTTP 200. La réponse brute à la création avec code seul est :

```json
{
  "message": "Paramètres manquants !",
  "responseCode": 409
}
```

Il s'agit d'un échec de création. FinFlow doit continuer à vérifier le code métier et ne jamais confirmer une opération sur le seul HTTP 200. L'adaptateur client/crédit vérifie bien les codes numériques >= 400 sur ces cas ; la même règle n'est pas appliquée uniformément aux référentiels.

## Qualité de la réponse de l'adhérent existant

L'API retourne 12 champs : compte, code adhérent, plafond, point de service, date d'inscription, contexte, référence externe, indicateur de validité, message, nom agrégé, identifiant du point et code métier. La normalisation restitue correctement les informations présentes. Le nom agrégé et le plafond sont disponibles ; le point de service correspond au référentiel réel ; le CBS marque l'adhérent valide.

Cela **ne constitue pas un KYC complet**. Les exigences dépendent du profil juridique sélectionné, que le nom agrégé ne suffit pas à déduire.

- Pour une personne physique, le contrôle d'import actuel signale **9 données manquantes** : nom distinct, prénoms, naissance, numéro de pièce, dates d'établissement et d'expiration de pièce, téléphone, ville, adresse.
- Pour une personne morale, le contrôle actuel signale **4 données manquantes** : IFU/identification nationale, RCCM/carte opérateur, téléphone et adresse/siège.

Le processus d'import bloquera donc normalement cet échantillon, même si `estValide` vaut vrai. Il faut obtenir un endpoint fournissant l'identité complète, enrichir la réponse côté CBS, ou définir un enrichissement contrôlé dans FinFlow avec justificatifs et revue KYC. Déduire un nom/prénom par découpage automatique ne constitue pas une correction fiable.

## Correspondances entre données réelles et référentiels locaux

Comparaison en lecture seule de la configuration actuelle de FIL01 avec les réponses reçues. Les devises se comparent au code CBS ; les autres références, à leur identifiant.

| Référentiel | Lignes CBS | Lignes locales actives | Codes locaux correspondants | Codes locaux absents de la réponse |
|---|---:|---:|---:|---:|
| Devises | 3 | 6 | 1 | 5 |
| Périodicités | 6 | 7 | 0 | 7 |
| Objets de financement | 83 | 0 | 0 | 0 |
| Sources de financement | 2 | 0 | 0 | 0 |
| Motifs de décision | 2 | 0 | 0 | 0 |
| Professions | 0 | 0 | 0 | 0 |
| Points de service | 6 | 0 | 0 | 0 |
| Gestionnaires | 4 | 0 | 0 | 0 |

Ce constat exige une synchronisation contrôlée et une vérification des associations agences/utilisateurs/produits. Les correspondances de simulation ne doivent pas être envoyées comme si elles étaient des identifiants réels. L'absence locale n'est pas une erreur de l'API : aucune synchronisation métier n'a été lancée par cet audit.

Le catalogue des types de pièces est accessible mais sa synchronisation n'est pas proposée parmi les scopes de `ref_sync.py`. Il faut clarifier son utilisation par les formulaires KYC et les codes configurables. Aucun endpoint de catalogue des produits crédit/remboursement n'est déclaré ici ; leurs identifiants restent à faire confirmer par l'équipe CBS.

## Constats pour la solidité de FinFlow

### Bloquants avant le parcours UAT complet

1. **Simulation toujours active dans le connecteur.** `get_adapter` choisit encore `SimulatedAdapter` et la mise en place reste en mode LOCAL. Les sondes ont explicitement utilisé l'adaptateur REST réel, en mémoire, pour tester le serveur. Le fonctionnement courant de l'application n'a donc pas été basculé en réel par ces tests.
2. **Confiance TLS du backend à configurer.** Requests échoue dans sa configuration habituelle, alors que la validation avec les autorités du système réussit. Il faut installer/configurer la chaîne d'autorités approuvée dans l'environnement qui exécutera Django/Celery, en maintenant la validation TLS. Le réglage utilisé par la sonde n'est pas une correction persistante de l'application.
3. **Endpoint impayés absent au chemin configuré.** Vérifier le chemin et la version réellement exposés par le fournisseur. Le corps 404 mentionne un chemin interne `.../itf/crd/impayes`, mais cela ne permet pas de deviner une route de remplacement. Ne pas transformer ce 404 en portefeuille vide ni en résultat simulé.
4. **Données d'adhérent insuffisantes pour le dossier.** Le cas valide testé ne passe pas les exigences d'import KYC. La recette positive doit commencer par un emprunteur UAT complet et des justificatifs contrôlés.
5. **Correspondances de référentiels non préparées.** Import et rapprochement requis avant toute création positive, puis validation des identifiants de produits.
6. **Création positive non démontrée.** Le CBS refuse le seul code adhérent. Montant, taux, produit, remboursement, périodicité, nombre d'échéances, objet, gestionnaire et callback doivent être définis dans un dossier UAT approuvé.

### Défauts de traitement reproduits hors ligne

Ces essais réutilisent des réponses enregistrées ou leurs variantes synthétiques ; ils **n'ont pas été envoyés au CBS**. Ils sont consignés dans `offline-analysis.json`.

| Scénario | Résultat actuel | Comportement attendu |
|---|---|---|
| Statuts « Impayé », « Non payé », « unpaid », « Partiellement payé » | Tous reconnus comme payés | Table de statuts explicite ; ne pas ignorer une échéance partielle ou impayée |
| Référentiel HTTP 200 avec `responseCode=409` et `datas=null` | Retour d'une liste vide sans erreur | Lever une erreur métier ; garder les dernières données valides avec un état de synchronisation en échec |
| Situation crédit de forme inconnue avec une ligne non reconnue | Déduite soldée avec encours nul | Rejeter la structure inconnue ; un résultat indéterminé ne doit pas autoriser une clôture/mainlevée |
| Code métier client non numérique | `ValueError` non convertie | Erreur de protocole maîtrisée, présentée à l'opérateur sans erreur serveur brute |
| Opération d'encours client non implémentée dans RestAdapter | Repli simulé, montant zéro avec la configuration actuelle | Échec explicite « opération non disponible » en usage réel |

Les contrôles positifs de statuts « Payé » et « En attente » réussissent. Parmi les 10 vérifications hors ligne, 2 contrôles positifs passent et 8 révèlent un comportement à corriger. Ce nombre ne doit pas être confondu avec les appels HTTP réels.

### Améliorations opérationnelles

- Distinguer HTTP, code métier et qualité de la donnée dans les journaux et l'interface. Un HTTP 200/409 doit rester un échec métier, un HTTP 200/`datas:null` une réponse vide à examiner, un HTTP 404 une capacité non disponible.
- Ne pas rejouer automatiquement les erreurs déterministes de chemin, droits et validation. Respecter `Retry-After` sur 429, utiliser une temporisation croissante pour les erreurs temporaires et limiter les nouvelles authentifications.
- Mettre en cache les jetons par connecteur/filiale jusqu'à leur expiration, avec protection des secrets. La campagne réutilise un jeton par session ; le code applicatif résout autrement un jeton à chaque appel de référentiel.
- Conserver les dernières données valides lorsque la réponse est ambiguë. Le code actuel évite déjà de désactiver tout un catalogue si aucun identifiant n'a été reçu ; ce garde-fou doit être conservé.
- Valider les schémas de réponses et l'exhaustivité avant d'en tirer une conclusion financière. Ajouter dates de fraîcheur, source réelle/simulée et état de rapprochement à l'affichage du dossier.
- Prévoir une corrélation locale ↔ CBS par `externalId`, un callback réellement joignable depuis le CBS et sécurisé, puis une reprise après timeout. Une URL loopback de développement ne sera pas joignable depuis le CBS distant.
- Étendre la recette aux types de clients, devises, arrondis, dates, rejets, doublons, callbacks répétés, modifications d'autorisation, fichiers et séparation des rôles décrits dans l'audit global du parcours.

## Dossier fictif préparé

Le fichier `draft-credit-for-review.json` du premier dossier de preuves contient une proposition **non exécutable en l'état**, distincte de la requête minimale effectivement envoyée :

- emprunteur et point de service issus de la réponse CBS ;
- périodicité mensuelle et devise issues des référentiels réels ;
- proposition de montant **200 000**, taux **10 %**, **3 échéances**, reprise d'un produit local actif ; ces conditions et les codes produits ne sont pas encore validés par le CBS ;
- objet de financement, gestionnaire et URL de callback restent à choisir ; les données KYC doivent être complétées.

Aucun de ces montants/conditions n'a été transmis à `crd/simple`. Seul le corps avec `codeAdherent` a été envoyé, et refusé. Aucun nouveau prêt local n'a été créé pour contourner les informations obligatoires.

## Plan de recette UAT et critères d'acceptation

| Étape | Critère vérifiable | État actuel |
|---|---|---|
| Connexion réelle | Authentification et TLS vérifié avec configuration applicative normale | API OK ; confiance TLS et mode du connecteur à corriger |
| Référentiels | Catalogues reçus, contrôlés, synchronisés et correctement associés | Réponses conservées ; synchronisation/associations à effectuer |
| Emprunteur UAT | Identité, KYC, compte et point de service complets et justifiés | Données complémentaires requises |
| Instruction et décision | Analyse, garanties, réserves, signatures et séparation des rôles contrôlées | À recetter sur le dossier fictif complet |
| Création positive | Un seul crédit créé, références et conditions retournées rapprochées | Non validée ; requête minimale refusée |
| Situation positive | `refDemande` et adhérent valides, encours et échéancier cohérents | Référence de crédit nécessaire |
| Impayés | Route supportée ; résultat daté, montants/statuts correctement interprétés | Route 404 et parseurs à corriger |
| Incidents | 401/403/409/429/5xx, expiration de jeton, timeout avant/après acceptation | Quelques refus observés ; reprise et cas financiers à qualifier |
| Clôture/mainlevée | Solde confirmé sans ambiguïté, preuve conservée, contrôle indépendant | Bloquée tant que les défauts de solde ne sont pas corrigés |
| Mise en production | Suite complète expliquée/verte, PostgreSQL concurrent, fichiers, audit et restauration | Hors validation de cette campagne |

Le rapport précédent `32-audit-parcours-credit-2026-10-20.md` reste applicable : il recense aussi les faiblesses de contrats, d'accès et de versionnement documentaire, de pagination et de conservation des preuves. Le résultat précédent de la suite complète était 669 réussites, 19 échecs de droits à qualifier et une erreur temporaire ensuite résolue ; la suite n'a pas été rejouée sans modification métier pendant cette campagne.

## Preuves conservées et reproductibilité

Les artefacts sont sous `uat-artifacts/`, exclu de Git par un fichier `.gitignore` local :

- `cbs-20261020T222507Z/` : campagne initiale, neuf référentiels normalisés, essais négatifs et portefeuille ;
- `cbs-20261020T222803Z/` : adhérent existant et situation avec adhérent seul ;
- `cbs-20261020T223118Z/` : authentification et POST de création avec le seul code adhérent ;
- `results.json` dans chaque dossier : méthode, chemin, statut, code métier, temps, requête masquée et liens vers les réponses ;
- `responses/*.response.json` : réponses reçues, avec secrets masqués ;
- `responses/*.normalized.json` : résultats des parseurs actuels, lorsque la réponse est acceptée ;
- `all-http-cases.csv` et `aggregate-summary.json` dans le premier dossier : inventaire transversal des 23 échanges ;
- `offline-analysis.json` : qualité client, comparaison des catalogues et vérifications hors ligne ;
- `draft-credit-for-review.json` : préparation à examiner, pas un crédit envoyé ;
- `manifest.json` : taille et empreinte SHA-256 des fichiers conservés. Les empreintes portent sur les preuves masquées, pas sur des secrets réseau conservés.

Trois scripts locaux permettent de reproduire les contrôles : `backend/scripts/check_demo_cbs_connection.py`, `backend/scripts/audit_cbs_endpoints.py`, `backend/scripts/analyze_cbs_uat_results.py`. Le lanceur complet utilise l'API réelle pour les consultations, attend 3 secondes entre les réponses et les appels suivants, et arrête la campagne s'il reçoit un 429. Il exige une sélection explicite pour le cas minimal de création UAT.

La couverture est celle des endpoints déclarés et des cas documentés ci-dessus. Une spécification officielle CBS est nécessaire pour compléter les routes éventuellement exposées mais non déclarées, notamment les produits et l'identité détaillée. Aucune disponibilité d'un endpoint non inventorié n'est présumée.
