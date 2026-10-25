# Audit du parcours et des preuves d'un dossier de crédit

Date : 20 octobre 2026. Audit technique et fonctionnel du dépôt local et de ses paramètres de développement.

## Avis

Le socle métier est développé et dépasse une simple maquette : instruction, analyse financière, décisions, réserves, contrats, autorisation de mise en place et recouvrement sont présents, avec de nombreux contrôles côté serveur. Cependant, l'état observé ne justifie pas une mise en production bancaire sans corrections. Deux défauts CBS reproduits peuvent fausser les données utilisées pour des actes financiers ; les contrats et les pièces présentent aussi des faiblesses de validation, d'accès et de conservation des preuves.

Une recette encadrée sur données de démonstration est possible. Une décision d'exploitation réelle doit attendre la correction des points critiques, la stabilisation de la suite complète et une recette avec le CBS réel et les profils métier effectifs.

## Méthode et limites

- Lecture du code backend, du détail de dossier frontend, des paramètres et des tests existants.
- Exécution de toute la suite Django sur SQLite de test en mémoire : **669 réussites, 19 échecs, 1 erreur**, en 140,28 secondes. Le test en erreur de répertoire temporaire réussit après relance avec un répertoire dans le projet.
- Les 19 échecs observés sont des réponses 403 à la place des réponses attendues : configuration, héritage Groupe, rôles et paramètres de notification. Plusieurs fixtures ne disposent manifestement pas des habilitations désormais exigées. Il faut distinguer des tests obsolètes d'une régression réelle des profils ; ces résultats ne démontrent pas à eux seuls une fuite de données.
- Quatre sondes complémentaires ont été exécutées sans sauvegarder de données métier : statuts CBS, repli simulé REST, rattachement/version GED et validation générique d'un contrat signé.
- Le build TypeScript/Vite était réussi après la dernière modification du profil client. Cela ne remplace pas une recette des interactions.
- Le contrôle du navigateur reste bloqué par la politique de l'outil. Aucun parcours visuel complet n'est donc certifié ici. Les transactions concurrentes PostgreSQL, l'antivirus, les restaurations, la charge et le CBS réel n'ont pas été testés en conditions de production.
- Aucun code métier n'a été corrigé pendant cet audit. Les résultats sont un diagnostic, pas une certification de conformité juridique ou réglementaire.

Preuves d'exécution : `backend/credit-journey-audit.log`, `backend/credit-journey-audit.xml`, `backend/credit-journey-storage-check.xml`.

## Couverture du cycle de vie

| Étape | Ce qui est en place | Ce qu'il reste à consolider |
|---|---|---|
| Client, personne physique, entreprise, groupement | Identité, dirigeants, pièces, KYC, coordonnées et paramètres de formulaire | Validation KYC indépendante, changements d'identité après revue, pièces réellement vérifiées, rapprochement des doublons, preuve de contrôle des bénéficiaires et PPE |
| Création de demande | Produit, devise, objet, montant, durée, tarification, apport, activité, emploi, assurance | État explicite des données absentes, cohérence du compte bénéficiaire, de l'apport et des sources de financement, traçabilité des justificatifs |
| Analyse financière | Analyse de référence, revenus/charges, ratios, stress, qualité de l'information, éléments sectoriels et E&S | Fraîcheur imposée, source de chaque donnée clé, preuve des vérifications et cohérence avec le montant finalement accordé |
| Engagements | Situations externes justifiées, deuxième vérificateur, plafonds et groupes liés, contrôle des devises | Exhaustivité de la collecte, traitement explicite des groupes indirects et du périmètre Groupe, blocage des situations périmées selon politique |
| Garanties et cautions | Couverture distincte des garanties réelles et des cautions, formalisation, renouvellement, mainlevée, dation | Preuves de propriété et de rang, dates de valorisation, décotes, couverture d'assurance et conservation des actes ; corriger les contrôles CBS avant mainlevée/dation |
| Soumission et circuit | Verrous, KYC, analyse requise, règles de configuration figées, retour/rejet, couverture des circuits | Recette complète des délégations, absences, branches parallèles, changements de montant et demandes simultanées |
| Décision et réserves | Photographies de décision, comités/PV, justification des rejets et levée des réserves | Dossier exact ayant servi à chaque vote, accès durable aux versions des pièces, réévaluation si changement substantiel |
| Contrats | Génération, contexte conservé, modèles applicables, dépôt du scan signé | Fermer les mutations génériques, interdire la réaffectation d'un acte, contrôler sa suppression et vérifier la signature indépendamment |
| Mise en place | Contrôle final, empreintes, autorisation préalable, contrôle du retour CBS, idempotence locale | Paramètres plus stricts, absence totale de simulation en réel, rapprochement après résultats ambigus ou changement pendant l'appel CBS |
| Vie du prêt | Prêt/échéancier local, situation et impayés CBS, recouvrement, contentieux, demandes de restructuration | Corriger l'interprétation des statuts, afficher la date et la source du solde, réconcilier les échéanciers et états ; une demande de restructuration n'est pas à elle seule une modification exécutée au CBS |
| Clôture et archivage | Clôture du prêt depuis le CBS, mainlevées, suppression logique et purge GED | Clôture cohérente de toutes les entités liées, dossier d'archive complet, conservation par catégorie et suspension de purge en cas de litige |
| Exploitation | Journaux, tâches, quotas, alertes, configuration de déploiement | Supervision des tâches réellement exécutées, alertes effectivement distribuées, sauvegarde/restauration prouvée, reprise après incident |

## Constats prioritaires

### A1 — Critique : des impayés CBS sont interprétés comme payés

Source : `backend/apps/corebanking/services.py:1259`, `_is_paid_schedule_status`, puis `_normalize_credit_schedule` et `compute_cbs_overdue`.

Le code recherche des fragments comme `paye` ou `paid` dans le texte. Ils sont aussi présents dans `impaye`, `non paye`, `unpaid` ou `partiellement paye`.

**Reproduction sans écriture :** un échéancier contenant une ligne de 100 000 au statut « Impayé » est normalisé en `(True, Decimal('0'))` : soldé, encours nul. « Non payé », « unpaid » et « Partiellement payé » donnent le même résultat. « En attente » conserve correctement 100 000.

**Impact :** impayés sous-estimés, recouvrement/clôture erronés et contrôle de mainlevée susceptible de considérer un prêt soldé. L'impact opérationnel dépend des libellés réellement renvoyés par le CBS, ce qui exige aussi des jeux de réponses réels.

**À faire :** table explicite des statuts, prise en compte des montants partiels, statut inconnu bloquant ou signalé ; tests sur négations, paiement partiel, échéancier vide/malformé et impayés multiples.

### A2 — Critique : une opération REST non implémentée peut renvoyer un encours fictif

Sources : `backend/apps/corebanking/services.py:485`, `:521`, `:313`, `:1873` ; appels dans `backend/apps/guarantees/process_services.py`.

`RestAdapter.send` utilise `SimulatedAdapter` pour les opérations non branchées. `GET_CLIENT_OUTSTANDING` suit ce chemin ; son défaut simulé est 1 000 000.

**Reproduction sans réseau ni écriture :** avec un connecteur REST et `ALLOW_SIMULATED_CBS_SETUP=False`, `RestAdapter.send(GET_CLIENT_OUTSTANDING, ...)` renvoie encore `total_outstanding='1000000'` et `raw.simulated=True`.

**Impact :** un contrôle d'encours préalable à une dation peut travailler sur une donnée de démonstration, même quand la mise en place simulée est désactivée.

**À faire :** rejeter toute opération réelle non implémentée, supprimer le repli implicite, contrôler la provenance de chaque réponse consommée par un acte financier et tester tous les adaptateurs. La protection de la seule mise en place ne suffit pas.

### A3 — Élevé : le PATCH générique d'un contrat contourne la validation de son scan signé

Sources : `backend/apps/contracts/serializers.py:78`, `:116`, `backend/apps/contracts/views.py:85`, `:254`.

L'action dédiée valide PDF/images, mais le serializer générique laisse `status`, `signed_file`, `signed_at`, `application` et `template` modifiables et n'applique pas la même validation de fichier.

**Reproduction sans sauvegarde :** le serializer accepte un PATCH avec `status='SIGNED'` et un fichier `audit.exe` au contenu `MZ-audit`. Les champs de rattachement au dossier et au modèle sont également modifiables.

**Impact :** faux état signé, fichier non contrôlé et possibilité structurelle de réaffecter un contrat à un dossier dont il ne reflète pas les conditions. La route générique PATCH est exposée aux utilisateurs ayant le droit de modification ; aucune exploitation sur un contrat réel n'a été effectuée.

**À faire :** transitions dédiées et atomiques, rattachements immuables, validation commune de tout fichier entrant, preuve de vérification de signature, interdiction de modification/suppression après usage selon le statut. `perform_destroy` supprime actuellement aussi les fichiers sans garde explicite sur l'état du crédit.

### A4 — Élevé : rattachement et accès aux documents moins stricts que ceux des crédits

Sources : `backend/apps/documents/serializers.py`, `backend/apps/documents/views.py:57`, `backend/apps/common/viewsets.py`.

Le serializer accepte `content_type` et `object_id` sans valider explicitement le type autorisé, l'existence de l'objet cible, sa filiale, son périmètre ou son état. Une sonde PATCH avec un UUID inexistant est acceptée. Le ViewSet GED est filtré par filiale mais n'applique pas le périmètre agence/propriétaire du dossier lié.

**Impact :** pièces orphelines ou mal rattachées ; un utilisateur habilité à la GED peut disposer d'un périmètre documentaire plus large que son périmètre crédit. Le rattachement interfiliale via API doit faire l'objet d'une reproduction isolée complémentaire avant d'en quantifier toutes les conséquences.

**À faire :** types cibles autorisés, validation d'appartenance, filtre de lecture/téléchargement sur la cible, mêmes contrôles sur les mises à jour et accès directs. Revoir aussi les périmètres des contrats, dont le ViewSet de base est également limité à la filiale.

### A5 — Élevé : la configuration locale est encore permissive

La politique par défaut résolue pour **FIL01** pendant l'audit indique : contrats de crédit signés non exigés ; demande de mise en place et double regard non exigés ; séparation avec l'autorisateur non exigée ; pièces vérifiées non exigées ; durée de validité de l'accord et âge maximal de l'analyse à zéro ; couverture des garanties en mode alerte. Les cautionnements signés sont en revanche exigés.

**Impact :** la présence d'un garde-fou dans le code ne signifie pas qu'il bloque effectivement les dossiers. Une autorisation finale existe toujours, mais les séparations complémentaires sont optionnelles.

**À faire :** publier un socle de production strict validé par les responsables métier, puis vérifier les exceptions produit/agence/profil et les versions figées sur les dossiers existants. Cette lecture du défaut courant ne permet pas d'affirmer que tous les dossiers utilisent la même politique.

### A6 — Élevé : chaîne de preuve documentaire incomplète

Sources : `backend/apps/documents/models.py:64`, `backend/apps/documents/views.py:76`, `backend/apps/documents/ged_bridge.py:19`, `backend/apps/credits/views.py:811`.

- Le champ `version` est saisissable ; aucune nouvelle révision immuable n'est créée automatiquement à chaque remplacement. Une sonde accepte `version=999`.
- Le remplacement remet bien la vérification à PENDING et recalcule l'empreinte, ce qui est utile, mais ne fournit pas une filiation des anciennes versions consultables.
- Le miroir crédit → GED est créé à l'ajout ; la mise à jour d'une pièce crédit ne resynchronise pas son miroir. Le miroir existant est ignoré par la fonction de création.
- Le quota est augmenté à la création GED, mais le remplacement ne comptabilise pas explicitement la différence de taille. Contrôle et consommation du quota sont aussi séparés.

**À faire :** source documentaire unique ou synchronisation durable, identifiant de version stable, empreinte de chaque binaire utilisé dans une décision, conservation des anciennes versions, règles de suppression cohérentes et quota transactionnel. Les clés S3 ne sont pas écrasées par défaut, mais cela ne constitue pas à lui seul un historique métier de versions.

### A7 — Élevé : la consultation peut cacher des pièces ou des analyses

Sources : `frontend/src/pages/CreditApplicationDetailPage.tsx:1745`, `:1826`, `:2049`, `:3627` ; pagination de l'API à 25 ; `backend/apps/documents/list_filters.py:72`.

Les garanties, cautions et analyses sont consommées depuis la première page `results`, sans parcours de `next`. L'analyse de référence peut donc se trouver au-delà des résultats chargés. Les documents crédit sont recherchés par libellé dans la checklist mais ne disposent pas d'une liste générale dans la section documents : une pièce complémentaire hors checklist peut rester invisible sur cet écran. Le filtre GED par client tronque aussi certaines listes de cibles à 400 objets.

**À faire :** charger toutes les pages ou proposer une vraie pagination visible, rendre toute pièce complémentaire accessible, distinguer présence/vérification/expiration, afficher les totaux et les erreurs de chargement. Un échec API ne doit jamais être présenté comme une absence de donnée.

### A8 — À renforcer : rapprochement CBS et reprise après incident

Sources : `backend/apps/credits/services.py:632` et suite ; `backend/apps/corebanking/services.py:1165` ; `backend/apps/corebanking/tasks.py:73`.

Le code verrouille le crédit, exige un retour positif et revérifie l'autorisation après l'appel. En revanche, un succès CBS suivi d'une révocation ou d'un échec local peut laisser le CBS et le dossier divergents. Le retour est journalisé, mais la tâche de retry rejoue l'intégration sans finaliser elle-même le prêt local. Le journal d'intégration conserve une transaction ouverte pendant l'appel réseau ; une création concurrente initiale peut rencontrer la contrainte d'unicité au lieu de retourner proprement le résultat existant.

**À faire :** état explicite « résultat à rapprocher », file de réconciliation, reprise idempotente de la finalisation locale, gestion du timeout ambigu, clés reconnues par le CBS, contrôles PostgreSQL concurrents et tests de crash entre chaque phase. Ce sont des scénarios à qualifier ; aucun double décaissement réel n'a été reproduit.

### A9 — À renforcer : audit, conservation, notifications

- `backend/apps/audit/signals.py:60` enregistre des états après sauvegarde ; les `QuerySet.update`/`bulk_create` ne déclenchent pas ces signaux. Des événements métier spécifiques compensent une partie de ces opérations, mais il faut une cartographie des trous restants.
- L'API audit est en lecture seule et l'admin interdit ajout/modification ; l'admin n'interdit pas explicitement la suppression. Aucun mécanisme append-only indépendant de l'application ou scellement de journal n'a été identifié dans ce périmètre.
- La purge GED dépend d'un délai global de suppression logique, 90 jours par défaut. Cela ne représente pas une politique complète d'archivage par catégorie, dossier, clôture et contentieux ; la suspension de purge doit être explicite.
- L'alerte d'expiration GED journalise un nombre (`documents/tasks.py:14`) ; elle ne distribue pas elle-même de notification métier nominative. Le canal SMS est un stub qui n'envoie pas de message (`collections/services.py:1693`).

**À faire :** journalisation des consultations/téléchargements sensibles et des mutations par lot, accès audit séparé, conservation contrôlée, preuve de restauration des fichiers avec la base, alertes affectées à un responsable et suivi de livraison.

## Données et preuves à rendre disponibles pour décider

Pour chaque information clé, afficher la valeur, sa source, sa date, son auteur, son vérificateur et le justificatif associé. Distinguer explicitement « zéro », « non applicable », « non renseigné », « indisponible » et « expiré ».

1. **Client et relations** : identité légale complète, dirigeants, bénéficiaires effectifs et liens économiques, KYC daté, comptes utilisés, historique de relation et de remboursement. Le booléen PPE n'est pas à lui seul une preuve de revue de conformité ; le processus et ses justificatifs doivent être définis.
2. **Demande et emploi des fonds** : montant demandé/proposé/accordé et leurs écarts, objet détaillé, plan de financement, apport justifié, devise, durée, différé éventuel, frais/taxes, assurance et charge totale supportée par le client.
3. **Capacité de remboursement** : revenus/charges et hypothèses, historique, flux bancaires, endettement externe, reste à vivre ou DSCR selon profil, scénarios de stress, explications des écarts et données non vérifiées. Recalcul sur le montant effectivement accordé.
4. **Garanties et cautions** : propriétaire, rang, opposabilité/formalisation, expertise datée, décote et valeur retenue, engagements déjà affectés, capacité de la caution, durée, assurance et conditions de réalisation/libération.
5. **Décision** : risques majeurs, arguments favorables/défavorables, règles applicables, dérogations, avis des intervenants, quorum/PV, réserves avec responsable/échéance et preuve de leur validation.
6. **Exécution et suivi** : acte signé et contrôlé, conditions préalables levées, auteur de l'autorisation et exécutant, référence CBS confirmée, échéancier et frais rapprochés, retard/encours datés, incidents, restructurations réellement exécutées et preuve de clôture.
7. **Documents** : inventaire exhaustif transversal, version utilisée pour la décision, état de vérification, péremption, document remplacé, pièces manquantes et motif d'exception. Les doublons techniques ne doivent pas devenir deux preuves contradictoires.

## Ordre de traitement recommandé

**Avant toute utilisation financière réelle** : A1 et A2 ; fermeture des contournements des contrats A3 ; contrôle du rattachement/périmètre A4 ; publication et revue du socle de production A5.

**Avant validation de recette** : versionnement et cohérence des pièces A6, consultation exhaustive A7, suite de tests entièrement expliquée et stabilisée, scénarios CBS de résultat ambigu A8. Ajouter les tests manquants révélés par les sondes, pas seulement corriger les attentes de la suite existante.

**Avant ouverture à plusieurs agences/filiales** : recette PostgreSQL avec acteurs concurrents et profils réels, volumétrie et temps d'ouverture, accès aux pièces par URL directe, sauvegarde/restauration, expiration/révocation des documents et de l'accord, journal d'audit et plan de reprise A9.

**Améliorations de confort ensuite** : synthèse de décision en tête du dossier, liste de risques et données manquantes avec lien direct vers les preuves, comparaison des versions, export d'un dossier complet à une date donnée, alertes personnalisées et intégrations de conformité à définir avec les responsables concernés.

## Critères d'acceptation pour une prochaine recette

- Aucun statut CBS ambigu ni opération non implémentée ne peut produire un solde ou un accord présenté comme réel.
- Un utilisateur ne peut ni lire, ni déplacer, ni vérifier une pièce au-delà du dossier auquel il a accès.
- Un acte signé ne change pas de dossier, de contenu ou de statut par un PATCH générique ; son historique reste consultable.
- Le dossier affiche tous ses justificatifs, même hors checklist et au-delà de 25 résultats.
- Deux validations ou exécutions concurrentes ne créent pas de doublon ; tout succès CBS retrouve un état local rapproché et traçable.
- Les contrôles configurés bloquent effectivement le manque de signatures, la péremption et les défauts de séparation prévus par la politique validée.
- La suite complète est verte avec des habilitations réalistes et ses scénarios négatifs passent aussi.
- La recette navigateur couvre création, retour, correction, décision, réserves, contrat, autorisation, exécution, incident et clôture, pour chaque profil de client et chaque rôle.
