# Fonctions métier et noms de rôles

## Périmètre

Les fonctions utilisées par les contrôles métier sont désormais des capacités explicites, portées par des permissions Django `accounts.business_*` affectées aux groupes des rôles. Le nom d'un rôle est un libellé libre : le renommer ne change plus sa fonction, et lui donner le nom d'un rôle standard ne lui accorde aucun privilège.

Les capacités complètent les permissions d'action. Par exemple, l'administration crédit requiert à la fois la fonction **Administration crédit et contrôle final** et le droit de contrôler, d'autoriser ou d'exécuter l'action correspondante. Les contrôles de filiale, de périmètre, de séparation des acteurs et de statut continuent de s'appliquer. Le contrôle final et l'autorisation de l'administrateur crédit restent obligatoires ; l'exécutant de la transmission reste configurable. Seul le retour positif du CBS permet la mise en place.

## Paramétrage

Dans **Administration → Rôles & droits**, sélectionner un rôle, modifier son nom, choisir ses **Fonctions métier** et ses permissions d'action, puis enregistrer. Les styles existants sont conservés.

Les fonctions proposées couvrent l'administration filiale, l'administration crédit, la relation clientèle, l'agence, l'analyse crédit, les comités filiale et Groupe, la décision de direction, les opérations, le contrôle permanent, l'audit, le recouvrement spécialisé ou juridique, la supervision et la consultation du recouvrement.

La fonction de consultation du recouvrement permet un périmètre filiale propre à ce module, conformément à son fonctionnement historique. Les fonctions agence et relation clientèle conservent respectivement le périmètre agence et portefeuille personnel. Une capacité seule n'accorde pas les permissions CRUD nécessaires.

L'API expose :

- `GET /roles/capabilities/` : catalogue des fonctions, réservé à la consultation des rôles ;
- `capabilities` dans les rôles : liste explicite à lire ou remplacer ;
- `capabilities` dans `/users/me/` : fonctions effectives de l'utilisateur ;
- `pack_code`, en lecture seule : identité technique du profil standard.

Les modifications des permissions d'action via `permissions` préservent les fonctions si `capabilities` est omis. Pour retirer une fonction, modifier explicitement cette liste. Les capacités reçues dans la liste brute de permissions ne remplacent pas ce champ explicite.

## Séparation des tâches et isolation

Les combinaisons suivantes sont refusées, y compris réparties entre plusieurs rôles d'un utilisateur : relation clientèle ou analyse crédit avec comité ou décision de direction ; opérations avec audit ou contrôle permanent ; recouvrement spécialisé avec audit.

Le contrôle s'applique à l'affectation de rôles, à la modification des fonctions d'un rôle déjà affecté, ainsi qu'aux formulaires de l'administration Django. Les variantes responsables et assistants des fonctions opérations, audit et contrôle partagent maintenant ces incompatibilités : une variation de libellé ne permet plus de les contourner.

Les fonctions effectives d'un utilisateur filiale proviennent seulement des groupes de sa filiale. Celles d'un utilisateur Groupe proviennent des groupes transverses, sans rattachement `TenantRole`. Un utilisateur inactif n'a aucune fonction effective. Les permissions directes utilisateur `business_*` ne confèrent pas une fonction : les fonctions s'administrent au niveau des rôles. Le superutilisateur conserve sa supervision explicite.

Le seul indicateur `is_group_level` n'accorde plus l'administration du recouvrement ; celle-ci exige un superutilisateur, un administrateur Groupe (`is_staff`) ou la fonction administration filiale. La visibilité Groupe demeure distincte des droits d'écriture.

L'audit existant des groupes, rôles, affectations et permissions conserve les acteurs, dates, identifiants et valeurs avant modification. L'identité technique du pack est également auditée. Les écritures ORM ou SQL réalisées hors des formulaires et API restent des opérations d'administration : les contrôles métier vérifient toujours les fonctions effectives à l'usage.

## Migration et profils standards

Les migrations `accounts.0010` et `0011` créent les permissions et attribuent une fois les fonctions correspondant aux profils historiques. Pour les rôles personnalisés ou déjà renommés, les permissions existantes de contrôle/autorisation/exécution crédit déterminent une fois la fonction administration crédit, et `execute_setup_operations` détermine la fonction opérations. Aucun droit d'action supplémentaire n'est ajouté par cette inférence.

La synchronisation ultérieure d'un pack utilise `pack_code`, même après renommage. Elle ne réattribue pas une capacité retirée explicitement. Un rôle personnalisé reprenant le nom d'un pack n'est jamais promu : si nécessaire, un nouveau profil standard distinct est créé. La création d'un nouvel administrateur filiale ne lui attribue pas automatiquement la fonction administration crédit.

Les noms historiques restent utilisés pour l'affichage et l'amorçage des profils, sans servir de preuve d'habilitation à l'exécution. Les rôles personnalisés existants doivent être revus par l'établissement pour confirmer leurs fonctions et les éventuels cumuls historiques incompatibles.

## Vérifications

Une recette dédiée couvre les renommages, l'absence de privilège donné par un nom, les profils standards, la préservation d'un retrait explicite, les rôles personnalisés migrés, la séparation des tâches, les formulaires Django Admin, les droits API, l'isolation entre filiales et les fonctions de notifications et de recouvrement. Ces vérifications techniques ne remplacent pas la recette bancaire de l'établissement.
