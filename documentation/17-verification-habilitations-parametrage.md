# Vérification des habilitations et du paramétrage métier

> État historique avant l'introduction de l'autorisation obligatoire par
> l'administration crédit. Voir [l'évolution du parcours](18-administration-credit-autorisation-cbs.md)
> pour les paramètres et les comptes supplémentaires désormais applicables.

Date : 19 octobre 2026. Périmètre : code backend et frontend, tests automatisés
en base isolée, configuration de la filiale locale FIL01 et contrôles HTTP
sur les comptes de démonstration.

## 1. Incohérences corrigées

| Point constaté | Correction |
|---|---|
| Un gestionnaire filiale pouvait soumettre une création de compte Groupe ou un changement de filiale | Validation explicite du périmètre de l'administrateur à la création et à la modification ; revalidation des agences et rôles existants lors d'un transfert |
| Le seul attribut « utilisateur Groupe » donnait accès à certaines modifications de configuration et au provisionnement d'administrateurs | Séparation entre périmètre Groupe et administration Groupe ; les droits explicites restent contrôlés pour les paramètres crédit, seuils et notifications |
| Des étapes pouvaient être rattachées à un groupe technique sans lien avec la filiale | Rôle de la filiale exigé, avec exception explicite pour le comité Groupe ; déplacement d'une étape vers un autre circuit interdit |
| Certaines décisions ne tenaient pas compte des agences accessibles au valideur | Contrôle du périmètre de données sur les dossiers rattachés à une agence, en complément du rôle de l'étape |
| Les listes génériques des tâches, instances et réserves permettaient une lecture hors périmètre crédit | Filtrage des listes et accès directs selon le périmètre du dossier associé |
| Délégation visible en file d'attente mais inutilisable ou hors plafond | Contrôle des plafonds, produit et agence dans la file « à traiter », comme lors de la décision ; délégant inactif exclu |
| Contributions au dossier non ouvertes au délégataire habilité | Même contrôle métier pour la contribution à l'étape courante et la décision |
| Les droits retournés dans le profil pouvaient rester anciens pendant le TTL du cache | Lecture du profil sans ce cache ; les révocations sont visibles à la prochaine lecture du profil et sont contrôlées par l'API |
| Les nouveaux paramètres de mise en place n'étaient pas tous exposés dans le diagnostic du dossier | Le diagnostic transmet l'intégralité des paramètres de la politique ; invalidation des diagnostics après enregistrement d'une politique |
| Le bouton de demande préalable était masqué pour un opérateur possédant également le droit d'exécution | Demande accessible avec son droit dédié ; exécution alignée sur la demande préalable et la séparation des acteurs configurées |
| La réduction ou le retrait d'une caution après accord n'entrait pas dans les preuves de décision | Engagements de caution inclus dans la photographie d'accord et dans l'empreinte du contrôle final ; retrait, remplacement et réduction détectés |
| Une pièce d'identité expirée pouvait conserver un statut KYC « validé » | Contrôle d'expiration à la mise en place lorsque la revérification KYC est activée |
| Un délai de validité d'accord ne pouvait pas être vérifié en l'absence de date de décision | Date exigée dès que ce délai est activé |
| Le PV de comité pouvait être une ligne documentaire sans fichier | Fichier et validité exigés ; vérification du PV exigée si la politique impose les pièces vérifiées |
| Le remplissage des valeurs par défaut d'un connecteur nommé pouvait cibler un autre connecteur actif | Le nom demandé est respecté |
| Le bootstrap et le jeu de démo laissaient deux connecteurs CBS actifs | Désactivation du connecteur technique de bootstrap dans la démo et diagnostic du nombre de connecteurs actifs |
| L'administrateur de démonstration cumulait analyse et comité | Neuf comptes métier distincts ; administrateur conservé pour la configuration |

Les contrôles d'accès sont appliqués côté API. Les boutons de l'interface
reflètent ces règles sans constituer à eux seuls une protection.

## 2. Paramètres et application dans le processus

| Étape | Paramètres contrôlés | Application |
|---|---|---|
| Création / modification | Exigence KYC dès la création, bornes produit à l'enregistrement, correspondance client/produit, saisie du montant approuvé | Validation du dossier par le serveur |
| Analyse | Seuils d'endettement, DSCR, ratios entreprise, reste à vivre, stress, décotes, pondération des revenus informels | Calculs financiers, alertes et indicateurs de couverture |
| Soumission | KYC, produit actif, bornes, analyse de référence, recommandation, visite, checklist, pièces vérifiées, couverture bloquante | Contrôles avant ouverture du circuit |
| Orientation | Montant, produit/famille, niveau de risque et mode de détermination du risque | Sélection du circuit et des étapes applicables |
| Décision | Rôle habilité, délégation approuvée et limitée, séparation initiateur/décideur, quorum, votes, conflits, PV, couverture à l'accord | Validation de chaque décision et de l'accord final |
| Réserves | Acteur autorisé à lever et à valider une réserve | Blocage de la mise en place tant que les réserves applicables subsistent |
| Contractualisation | Contrats de crédit requis, signature requise, contrats de caution requis, signature des cautions requise | Contrôles avant demande et exécution de mise en place |
| Sûretés | Formalisation obligatoire si activée ; conservation des garanties et cautions de l'accord | Contrôles avant mise en place et détection des diminutions |
| Préparation de mise en place | Demande nominative préalable et exécutant distinct si configurés | API et disponibilité des actions dans l'interface |
| Contrôle final | Revue documentée, validité de l'accord, fraîcheur de l'analyse, KYC, assurance, pièces, empreintes des conditions et preuves | Blocage si une exigence active échoue ; nouvelle revue si les preuves changent |
| Intégration CBS | Connecteur actif et mode configuré, références CBS, réponse et journal d'intégration | FinFlow transmet le dossier ; mise à disposition des fonds dans le CBS |
| Recouvrement et processus annexes | Tranches, rôles, circuits de formalisation, mainlevée et dation, décisions de restructuration et radiation | Couverture par les tests métier et les contrôles de périmètre existants |

## 3. Configuration locale effective

- Une filiale : FIL01, en XOF.
- 24 rôles filiale et 12 circuits actifs.
- Un connecteur de démonstration actif : « CBS Filiale 01 », mode LOCAL simulé.
- Aucun écart détecté par le diagnostic des comptes, rôles, affectations,
  couverture décisionnelle, membres habilités et connecteurs actifs après correction.
- Aucune politique personnalisée n'était enregistrée lors du diagnostic :
  les valeurs par défaut du modèle s'appliquent.

Les contrôles optionnels restent configurables. L'état local est notamment :

| Paramètre | Valeur effective |
|---|---|
| Contrats de crédit requis | Oui, pour les modèles marqués obligatoires |
| Signature obligatoire des contrats de crédit | Non |
| Contrats de caution requis / signés | Oui / oui |
| Demande préalable obligatoire | Non |
| Exécutant différent du demandeur obligatoire | Non |
| Revue finale obligatoire | Non |
| Pièces vérifiées obligatoires | Non |
| Formalisation des garanties obligatoire avant mise en place | Non |
| Revérification KYC à la mise en place | Oui |
| Durée de validité d'accord / âge maximal d'analyse | 0 / 0, délais désactivés |
| Couverture des garanties | Alerte, sans blocage |
| Détermination du risque | Recommandation de l'analyste |

Les seuils financiers par défaut incluent un endettement maximal particulier
de 40 %, un DSCR minimal de 1,2 et une couverture des garanties de 100 %.
Le reste à vivre minimum par personne est à 0 : il doit être renseigné pour
faire de cette exigence un contrôle significatif dans la politique de l'établissement.
Ces valeurs sont des paramètres applicatifs ; le choix des seuils métier
doit refléter la politique de crédit de chaque institution.

## 4. Comptes pour la recette locale

Mot de passe initial des nouveaux comptes : `FinFlow2026!`.
Les mots de passe des comptes déjà présents ne sont pas réinitialisés.

| Compte | Profil | Périmètre |
|---|---|---|
| fil01_charge | Chargé d'affaire | Propres dossiers |
| fil01_analyste | Analyste crédit et risque | Filiale |
| fil01_chef | Chef d'agence | Agence |
| fil01_comite | Comité de crédit filiale | Filiale |
| fil01_comite_groupe | Rôle de comité Groupe rattaché à FIL01 pour la démo | Filiale |
| fil01_operations | Responsable des opérations | Filiale |
| fil01_assistant_ops | Assistant des opérations | Filiale |
| fil01_juridique | Responsable Juridique | Filiale |
| fil01_lecteur | Lecteur | Filiale |

`fil01_admin` conserve le rôle Administrateur filiale. Les décisions de recette
peuvent être exercées avec les acteurs métier ci-dessus. Le superutilisateur
Groupe conserve ses capacités de supervision.

Les neuf connexions ont été vérifiées par HTTP à travers le proxy du frontend :
lecture de politique autorisée, modification de politique refusée, rôle unique
sur chaque compte. L'accès à l'exécution de mise en place est autorisé au seul
responsable des opérations parmi ces comptes ; le contrôle a été fait avec un
identifiant de dossier inexistant pour éviter toute exécution métier.

## 5. Rejouer les vérifications

Résultats obtenus :

- Suite backend complète : **459 tests réussis**.
- Après le dernier renforcement des lectures de circuits : **64 tests ciblés
  réussis**, comprenant trois nouvelles vérifications d'isolation des listes
  et des accès directs aux instances, tâches et réserves. Cette seconde passe
  recouvre en partie la première ; les deux nombres ne s'additionnent pas.
- Build TypeScript et Vite : réussi, feuille de style existante conservée.
- Vérifications statiques ciblées : réussies.
- `manage.py check` : aucun problème signalé.
- `makemigrations --check --dry-run` : aucun changement manquant après
  génération et application de la migration de recouvrement.

Depuis la racine du projet :

```powershell
.\.venv\Scripts\python.exe backend\manage.py audit_business_configuration
.\.venv\Scripts\python.exe backend\manage.py check
.\.venv\Scripts\python.exe backend\manage.py makemigrations --check --dry-run
```

La commande d'audit lit les données sans changer les règles. Une différence
avec un pack de permissions par défaut doit être examinée : elle peut être
une personnalisation volontaire. Le diagnostic relève également les étapes
sans membres suffisants et le nombre de connecteurs actifs.

Tests :

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest
cd ..\frontend
npm.cmd run build
```

La suite vérifie notamment les accès refusés, l'isolation des filiales,
les agences, les rôles, les délégations, les paramètres actifs et inactifs,
les circuits, les réserves, la contractualisation et l'intégration CBS simulée.
Les tests ajoutés sont dans `backend/tests/test_configuration_consistency.py`.

Les anciens tests CBS ont été alignés sur le contrat actuel : URL passée
par argument nommé, gestionnaire issu du référentiel CBS et absence de
substitution par le matricule RH. Les fixtures des administrateurs et
des étapes utilisent désormais les profils et rôles réellement requis.

## 6. Portée des résultats

Les contrôles HTTP ont porté sur l'instance locale. Les scénarios métier
automatisés utilisent une base séparée ; le CBS réel n'a pas été sollicité.
La photographie d'accord est produite lors des nouvelles décisions ; un dossier
historique dépourvu de photographie doit être réexaminé pour disposer de cette
preuve complète. L'audit de configuration ne constitue pas une revue manuelle
du contenu de chaque dossier de crédit historique.

La migration `collections/0013_alter_collectionaction_action_type_and_more.py`
harmonise des métadonnées de recouvrement détectées lors du contrôle global
des migrations. Elle a été appliquée à la base locale.
