# Circuits, comités et calendriers ouvrés

## Périmètre livré

Le troisième incrément étend **Administration → Circuits d'approbation** (`/admin/circuits`). Il utilise les composants et styles existants. Les paramètres sont propres à chaque filiale.

| Domaine | Paramètres disponibles |
|---|---|
| Circuit | Mode d'exécution historique ou explicite ; calendrier ouvré associé |
| Étape | Ordre, mode séquentiel/parallèle, rôle, nature consultative/décisionnelle, montants, risque minimal, renvoi autorisé |
| Délais | Heures continues ou ouvrées ; durée ; absence d'échéance avec zéro en mode explicite |
| Comité | Activation pour un rôle personnalisé, quorum, majorité, fraction qualifiée, abstentions, saisie nominative, PV de crédit |
| Calendrier | Fuseau IANA, jours de semaine travaillés, ouverture/fermeture, dates fériées, activation |

Les paramètres du circuit restent indépendants des profils d'analyse financière du centre de configuration. Chaque exécution référence sa version de circuit et conserve une copie de son calendrier.

## Préparation et versions

1. Créer un calendrier si des délais ouvrés sont nécessaires.
2. Créer un circuit **inactif**, puis définir ses critères de sélection et son calendrier.
3. Ajouter les étapes, dont au moins une étape décisionnelle couvrant chaque montant du circuit sans condition de risque.
4. Paramétrer les comités et vérifier les rôles et membres dans l'administration des habilitations.
5. Activer le circuit préparé.

La création par API n'accepte pas de circuit immédiatement actif. La duplication crée par défaut une nouvelle version inactive et conserve l'ancienne version disponible. L'activation de la nouvelle version ne désactive pas automatiquement les autres circuits : leur sélection conserve les critères existants de spécificité puis de version. L'établissement doit organiser la désactivation des versions qu'il ne souhaite plus utiliser.

L'API interdit les changements structurels et la suppression d'un circuit déjà utilisé, y compris son mode d'exécution, son calendrier, ses critères, son code, sa version et son type de processus. Dupliquer permet de préparer une évolution. Les instances en cours continuent de référencer leur circuit initial ; désactiver celui-ci n'annule pas ces instances.

Une bascule immédiate reste disponible pour les anciens clients API via `deactivate_source=true` lors du clonage : elle exige aussi le droit de modification et contrôle la structure et la couverture décisionnelle de la copie avant validation de la transaction. L'interface utilise la préparation inactive.

## Séquences et branches parallèles

### Compatibilité historique

La migration attribue `LEGACY_ORDER` à tous les circuits existants. Leur comportement est conservé : les étapes applicables ayant le même ordre s'ouvrent ensemble, quel que soit le champ `mode` anciennement renseigné. Les clones héritent du mode de leur source.

### Modes explicites

Les nouveaux circuits utilisent par défaut `EXPLICIT_MODE` :

- des ordres différents s'exécutent successivement ;
- les étapes simultanées d'un même ordre doivent toutes porter `PARALLEL` ;
- deux étapes séquentielles de même ordre sont acceptées si leurs tranches de montant sont disjointes dans le périmètre du circuit ; les bornes sont inclusives ;
- le circuit attend le traitement de toutes les tâches ouvertes à l'ordre courant avant d'avancer ;
- un rejet clôt le circuit et classe les autres tâches en attente comme ignorées.

Une condition de risque minimal seule ne rend pas deux étapes mutuellement exclusives : les deux peuvent s'appliquer aux risques supérieurs. La validation de structure en tient compte.

Les décisions d'une même instance prennent un verrou commun avant le verrou de tâche. Cela évite que deux branches finales soient traitées simultanément sans qu'aucune n'effectue la progression. La sérialisation effective nécessite une base prenant en charge les verrous de lignes, notamment PostgreSQL ; SQLite reste la base de développement locale et n'offre pas les mêmes garanties de concurrence.

L'activation refuse les circuits vides ou sans couverture décisionnelle sur leur propre tranche de montant. Le démarrage refuse également un dossier sans étape décisionnelle applicable. Ces contrôles de démarrage ne réécrivent pas les instances historiques.

## Calendriers et SLA

Le calendrier indique une plage horaire locale unique par jour travaillé. Les jours sont numérotés de `0` (lundi) à `6` (dimanche). Au moins un jour est obligatoire. La fermeture doit suivre l'ouverture dans la même journée.

Exemples de fuseaux à sélectionner selon l'établissement : `Africa/Abidjan`, `Africa/Dakar`, `Africa/Porto-Novo`. Les heures stockées dans le calendrier sont locales ; les échéances sont enregistrées comme dates et heures avec fuseau.

Les jours fériés sont des dates explicites `AAAA-MM-JJ`, sans doublons, dans une liste limitée à 2 000 dates. Ils ne sont pas importés ni déduits automatiquement d'un pays : l'établissement entretient son calendrier, y compris les jours exceptionnels.

Au démarrage, le circuit conserve dans `calendar_snapshot` l'identifiant, le code, le nom, la date de modification, le fuseau, les jours travaillés, les horaires et les dates fériées. Cette copie sert aussi pour les étapes ouvertes plus tard et pour les tâches rouvertes après renvoi à une étape antérieure. Une modification ou désactivation ultérieure du calendrier ne recalcule pas les échéances du circuit engagé.

Pour une étape en heures ouvrées, le temps hors plage, les jours non travaillés et les dates fériées ne consomment pas le délai. Le départ effectif du calcul est l'ouverture de la tâche. Une tâche rouverte reçoit une nouvelle échéance calculée à sa réouverture avec le même calendrier capturé.

Un calendrier actif de la même filiale est exigé pour démarrer un circuit avec des étapes en heures ouvrées. Sa désactivation bloque ces futurs démarrages jusqu'au choix d'un calendrier utilisable dans une nouvelle version si le circuit a déjà servi. Un calendrier référencé par un circuit ne peut pas être supprimé via l'API.

Les durées acceptées vont de 0 à 87 600 heures. En mode explicite, `0` signifie **sans échéance** (`due_at=null`). En mode historique, la signification antérieure de zéro (échéance immédiate en heures continues) reste conservée. Un calcul ouvré dépassant 100 années civiles est refusé explicitement.

Les notifications de dépassement conservent leur mécanisme existant et nécessitent les services de tâches planifiées. Elles ignorent désormais les instances terminées. Le démarrage du serveur local seul ne démarre pas Celery et son ordonnanceur.

## Règles de comité

Les rôles comité existants restent reconnus automatiquement. `committee_enabled` permet d'appliquer les mêmes contrôles à un rôle personnalisé. Décocher ce paramètre ne désactive pas la reconnaissance des anciens rôles comité.

### Quorum et majorité

- Le quorum porte sur les participants présents, habilités et sans conflit, y compris ceux qui s'abstiennent. Il est compris entre 1 et 100.
- La majorité **simple** exige strictement plus de la moitié de la base de calcul.
- La majorité **qualifiée** accepte une fraction exacte, par exemple `2/3`. Le rapport doit être supérieur à `1/2` et inférieur ou égal à `1`. La comparaison utilise des entiers, sans arrondi de pourcentage.
- L'**unanimité** exige tous les votes de la base de calcul dans le sens retenu.
- Si les abstentions sont incluses, la base est l'ensemble des présents sans conflit. Sinon, elle comprend seulement les votes pour ou contre. Une base vide ne permet aucune décision.

Une majorité favorable est exigée pour un avis favorable ; une majorité défavorable est exigée pour le rejet ou pour la transmission d'un avis défavorable à une étape consultative. Un avis défavorable ne permet toujours pas d'approuver une étape décisionnelle.

### Présences, habilitations et conflits

L'écran propose les utilisateurs actifs habilités pour la tâche, y compris les membres Groupe et les délégataires lorsque les règles existantes les autorisent. Le serveur contrôle de nouveau les habilitations et les périmètres au moment de la décision. La liste est réservée à l'acteur habilité du comité ; elle n'expose pas les adresses électroniques ni les autres données du profil.

Un participant ne compte qu'une fois, même si son UUID est présenté sous différentes écritures. Les personnes en conflit, le créateur et le soumissionnaire du dossier doivent s'abstenir et sont exclus du quorum et de la majorité. Cette exclusion s'applique également aux votes retranscrits pour un administrateur.

Si la saisie nominative est obligatoire, les participants et votes doivent être renseignés même avec un quorum de 1. Sinon, le mode historique à une personne reste utilisable sans saisie : le serveur enregistre l'acteur et un vote correspondant à l'avis, sous réserve des mêmes contrôles d'habilitation et de conflit.

La tâche conserve les participants, votes, conflits, auteur de saisie, paramètres appliqués et décomptes ayant permis la décision. Il s'agit d'une **retranscription des travaux du comité**, pas d'un vote numérique signé individuellement par chaque membre.

### Procès-verbal

`committee_pv_required` impose, par défaut, un document `PV_COMITE` valide avant la validation d'une tâche comité de crédit (`decision=APPROVED`), y compris la transmission d'un avis consultatif défavorable. Les règles existantes de vérification documentaire s'appliquent à ce PV. Décocher cette exigence lève ce contrôle propre à l'étape ; cela ne supprime pas une éventuelle exigence documentaire définie ailleurs dans le dossier.

Ce paramètre ne rend pas le PV obligatoire lors d'un rejet ou d'un renvoi. Il concerne le dossier de crédit ; les autres processus de garantie n'acquièrent pas automatiquement une gestion de PV liée à leur propre objet.

## Droits, isolation et audit

Le CRUD des calendriers utilise les permissions `workflow.view/add/change/delete_businesscalendar`. La migration les attribue aux rôles **Administrateur filiale** déjà présents. La création future de ces rôles inclut les permissions du module workflow par le mécanisme existant. Les autres rôles doivent recevoir explicitement les droits souhaités.

Les API de calendriers et de circuits restent isolées par filiale, exigent une filiale sélectionnée pour les utilisateurs Groupe et journalisent les écritures dans la piste d'audit existante. Les références vers calendrier, produit, famille et circuit sont contrôlées contre cette filiale. Les opérations de configuration ne transmettent rien au CBS.

Le contrôle obligatoire de l'administrateur crédit, son autorisation de mise en place, le choix du service exécutant et l'attente d'une réponse positive du CBS restent en vigueur.

## API ajoutée ou enrichie

- `/business-calendars/` : liste, création et CRUD par identifiant ;
- `/workflow-definitions/` : `execution_mode`, `business_calendar`, création inactive ;
- `/workflow-steps/` : `sla_mode`, `committee_enabled`, `committee_majority`, `committee_majority_numerator`, `committee_majority_denominator`, `committee_abstentions`, `committee_record_required`, `committee_pv_required` ;
- `/workflow-instances/` : `calendar_snapshot` en lecture seule ;
- `/approval-tasks/{id}/committee_participants/` : liste des participants habilités ;
- tâches : exposition en lecture des paramètres de comité et du mode de délai.

Toutes ces routes sont sous le préfixe d'API existant `/api/v1/`.

## Limites et suite

Restent notamment à traiter : horaires multiples ou différents selon le jour, import et récurrence des jours fériés, suspension/reprise des délais, escalade configurable, nombre et nature des sièges de comité, représentation d'un membre par délégation, voix prépondérante du président, votes individuels signés, critères supplémentaires et priorité explicite de sélection des circuits, publication indépendante des circuits et héritage Groupe.

Le reste du plan comprend aussi la tarification, les plafonds CBS consolidés, les référentiels extensibles, les capacités métier indépendantes du nom des rôles et la personnalisation des formulaires.

Les migrations locales, la compilation TypeScript/Vite, le contrôle système Django et les contrôles statiques Python ont été exécutés. Aucun test automatisé ni scénario métier dans le navigateur n'a été ajouté ou exécuté pour cet incrément ; une recette métier reste nécessaire.
