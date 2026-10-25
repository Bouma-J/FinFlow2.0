# Consultation du dossier et administration des paramètres

## Séparation des fonctions

Le dossier restitue les conditions, les données client, les analyses et les
contrôles applicables. Il ne contient plus d'accès au paramétrage des plafonds.
La saisie d'une situation d'endettement ou d'une relation économique reste une
opération métier sur le client, soumise à ses permissions et à son périmètre.
Elle ne modifie aucune règle de crédit.

L'administration des paramètres exige la fonction explicite d'administrateur
filiale (`tenant_admin`), un administrateur Groupe (`is_group_level` et
`is_staff`) ou un superutilisateur. Les permissions d'action et les contrôles
de filiale restent nécessaires. Le nom du rôle n'intervient pas.

- Le Centre de configuration est protégé dans le menu, sa route et son API,
  y compris la consultation du catalogue administratif et les simulations.
- Les mutations des référentiels catalogue, circuits, étapes, calendriers,
  modèles de contrats, catégories GED, seuils, connecteurs, tranches et règles
  d'escalade, agences, rôles et comptes administrés exigent aussi cette fonction.
- La politique de crédit, les réglages de notification et la modification des
  paramètres de filiale disposent du même contrôle administrateur.
- Les lectures nécessaires aux formulaires opérationnels restent autorisées
  selon leurs droits. Le changement de son propre mot de passe reste possible.
- La publication des profils conserve la validation indépendante par un autre
  utilisateur habilité que l'auteur et le dernier rédacteur.

## Restitution des engagements

La section « Engagements et relations économiques » rejoint la navigation du
dossier, après l'analyse financière. Elle est repliée au chargement et respecte
les commandes de dépliage existantes.

La synthèse distingue les engagements existants justifiés, les autres demandes
en cours retenues et le montant du présent dossier ajouté comme nouvelle
demande. Un dossier déjà mis en place n'est pas ajouté de nouveau : son encours
doit être couvert par la situation documentée. Les règles de somme et les
contrôles serveur ne sont pas assouplis.

L'absence de groupe déclaré, l'absence de situation vérifiée et un groupe hors
périmètre sont distingués. Une donnée manquante n'est pas un zéro.

Les formulaires ne s'ouvrent que par une action explicite. Le motif de révocation
concerne une situation sélectionnée. La recherche de clients liés commence à
deux caractères et conserve les sélections entre recherches ; les propositions
ne sont pas présentées comme des relations déjà déclarées.

## Analyse et circuit

L'avis favorable enregistré est libellé comme tel. Si le recalcul fait apparaître
une capacité insuffisante, un revenu non positif ou un DSCR insuffisant, un
message demande de rapprocher cet avis des résultats. Aucune décision passée
ni donnée financière n'est réécrite.

Un dossier historique dépourvu d'archive de configuration est présenté comme un
recalcul indicatif. Il n'est pas présenté comme une reconstitution des conditions
de sa décision initiale. Les indicateurs anciennement enregistrés restent
consultables séparément ; aucun instantané rétroactif n'est fabriqué.

Le chargement du circuit cible le dossier et parcourt ses pages, avec maintien
du contrôle serveur de périmètre. Les états de chargement, erreur et défaut
d'habilitation sont distincts de l'absence de circuit. Un dossier déjà engagé
sans historique disponible ne reçoit plus le message « non encore soumis » :
une anomalie de traçabilité est affichée. Aucun circuit fictif n'est créé.

Les informations de transmission CBS sont regroupées dans un détail en lecture
seule, avec des libellés métier. L'autorisation finale de l'administrateur crédit,
l'exécutant configurable et le retour positif obligatoire du CBS sont conservés.

## Vérifications de livraison

Compilation TypeScript et Vite, contrôle d'encodage du frontend, vérification
Django et contrôle Ruff des erreurs Python critiques. Vérification dans le
navigateur des dossiers Fatou Diallo et de l'accès au Centre de configuration.
Ces contrôles ne remplacent pas une recette bancaire ; aucune nouvelle suite
de tests n'est ajoutée ou exécutée pour cette correction.
