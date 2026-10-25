# Gouvernance du dossier et mise en place CBS

> Le contrôle et l'autorisation préalable par l'administration crédit sont
> désormais obligatoires. Le choix du service exécutant est décrit dans
> [Administration crédit et autorisation CBS](18-administration-credit-autorisation-cbs.md).

FinFlow instruit, fait approuver et transmet le dossier au CBS. Un retour
positif confirme sa mise en place. Le versement effectif des fonds est effectué
dans le CBS. Les identifiants techniques historiques (API, permissions et statuts
comme `DISBURSED`) sont conservés pour la compatibilité ; leurs libellés métier
affichent désormais « mise en place ».

## Paramètres par filiale

L'écran Politique crédit expose les réglages suivants :

| Réglage | Effet |
| --- | --- |
| Contrats de crédit obligatoires | Contrôle les modèles actifs déclarés obligatoires et applicables au dossier |
| Signature des contrats de crédit | Si les contrats sont obligatoires, impose le fichier signé et le statut signé |
| Contrats de cautionnement obligatoires | Exige un acte par engagement de caution actif |
| Signature des cautionnements | Si les actes sont obligatoires, exige leurs fichiers signés |
| Demande préalable | Interdit l'exécution directe depuis un simple accord |
| Séparation des acteurs | Exige une demande nominative et un exécutant différent, même en cumul de rôles |
| Mode de risque | Avis, score, ou niveau le plus prudent des deux ; absence de score : repli sur l'avis |
| Validité de l'accord | Nombre de jours depuis la décision ; 0 désactive ce délai |
| Ancienneté de l'analyse | Nombre maximal de jours depuis la date d'analyse ; 0 désactive ce délai |
| Contrôle final | Exige une revue nominative des conditions, KYC, apport, assurances et sûretés |
| Actualisation KYC | Revérifie le statut KYC à la mise en place |
| Pièces vérifiées | Contrôle des documents GED réels, vérifiés et non expirés |

Les réglages de formalisation des garanties sont conservés. Le préréglage
« banque stricte » active les principaux contrôles et des délais de 90 jours,
qui sont des valeurs de configuration, sans qualification de norme réglementaire.
La migration conserve l'absence d'obligation de cautionnement des politiques
existantes où la signature était désactivée. Les obligations sont ensuite
réglables séparément dans l'écran de configuration.

## Décisions et changements

Chaque décision conserve une photographie du dossier, de l'analyse de référence,
des garanties, des pièces et des contrats consultés. L'accord final conserve
également une empreinte des conditions financières, frais et données de l'analyse.
Une modification significative empêche la mise en place. Le retrait ou la baisse
de valeur d'une garantie approuvée déclenche aussi un réexamen.

L'action « Réexaminer l'accord » exige un motif, renvoie le dossier en correction
et annule les contrats actifs pour permettre leur régénération après une nouvelle
décision. Elle conserve l'historique antérieur. Une demande de mise en place
en attente doit d'abord être annulée. Une hausse de montant après une décision
déjà prise exige également un retour avant une nouvelle instruction.

La revue finale est disponible sur la fiche du dossier aux utilisateurs habilités
à exécuter la mise en place. Elle exige des confirmations explicites et un
commentaire mentionnant les preuves. Les documents, garanties et contrats sont
empreintés : un changement ultérieur rend la revue obligatoire à nouveau quand
ce contrôle est activé. L'assurance déclarée doit être valide ; lorsque le
contrôle final est obligatoire, son numéro de police et sa fin de couverture
sont requis. Ces références peuvent être complétées lors du contrôle final.

## Documents et comités

Dans la GED, un utilisateur ayant le droit de modification peut vérifier ou
rejeter une pièce avec commentaire. Auteur et date de vérification sont conservés.
Une modification de la pièce la remet à vérifier. Un fichier absent ou expiré
ne peut être validé. Le rapprochement avec la checklist repose sur le nom de
la pièce ou le libellé/code de sa catégorie : les libellés du catalogue doivent
donc être cohérents avec ceux des pièces exigées.

Les étapes de comité ont un quorum configurable. Le panneau de décision permet
de retranscrire les présences, votes et conflits du procès-verbal déposé. Les
participants sont contrôlés, les doublons refusés, les membres en conflit exclus
du quorum et soumis à abstention ; une approbation exige une majorité favorable.
Cette saisie est une retranscription nominative du PV par l'intervenant connecté,
pas une signature électronique individuelle des votants. Le quorum historique
de 1 reste utilisable sans tableau de participants supplémentaire.

## Délégations et audit

Les nouvelles délégations créées via l'API attendent l'approbation d'un tiers
habilité, distinct du délégant et du délégataire. Elles peuvent être limitées par
montant, produit, agence et nature d'acte. Le serveur applique ces limites au
moment de décider ; une modification remet la délégation en attente d'accord.
Les délégations historiques conservent leur validité pour éviter une interruption
des circuits ; elles doivent être revues dans le cadre de l'administration des
habilitations. Les limites ne donnent aucun accès supplémentaire hors des
périmètres de données autorisés.

Les changements d'utilisateurs, rôles, permissions, affectations d'agences et
délégations sont journalisés avec l'acteur et l'adresse IP quand le contexte
de requête est disponible. Les données de comparaison excluent mots de passe
et secrets MFA. Les scripts utilisant directement `QuerySet.update()` doivent
émettre un événement explicite, car cette opération ne déclenche pas les signaux
de sauvegarde Django.

## Déploiement

Appliquer les nouvelles migrations avec la procédure habituelle du projet,
redémarrer serveur et workers, puis ajuster les politiques par filiale.
Les accords historiques n'ont pas de photographie rétroactive : ils conservent
les contrôles de validité, KYC, documents et revue finale activés dans la politique.
Un réexamen permet de les faire passer par le nouveau mécanisme de preuve.
