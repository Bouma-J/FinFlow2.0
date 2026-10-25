# Engagements consolidés et plafonds

## Fonctionnement livré

Le dossier présente une carte **Engagements et relations économiques**, selon les droits de l'utilisateur. Elle permet de saisir une situation externe, choisir son justificatif GED vérifié, confirmer son exhaustivité, la faire vérifier par une autre personne, puis la révoquer avec motif si nécessaire. Une situation vérifiée est immuable ; son actualisation crée une nouvelle situation. La révocation de la dernière preuve ne réactive pas une ancienne situation.

Les montants distinguent capital restant dû tiré, engagements accordés non tirés et cautions/garanties données. Leur somme est une exposition brute interne, sans pondération réglementaire présumée. La devise, la date et la référence de source sont obligatoires. Aucun solde CBS n'est fabriqué à partir du capital initial du prêt local.

Les groupes de clients liés sont explicites, justifiés et propres à une filiale. Les membres des groupes actifs directement rattachés au client sont réunis sans doublons ; il n'existe pas de propagation transitive implicite vers d'autres groupes. Les identités hors périmètre ne sont pas restituées, et le total du groupe est masqué lorsque ses membres ne sont pas tous accessibles. Les contrôles serveur continuent à porter sur le groupe complet.

## Paramètres publiables

Dans le centre de configuration, la section `exposure.rules` permet de définir :

- activation du contrôle et devise des plafonds ;
- plafond client et plafond du groupe lié ; vide signifie aucune limite, zéro reste une limite effective ;
- inclusion des autres demandes en circuit ;
- ancienneté maximale de la situation et du plafond client CBS ; zéro désactive seulement cette limite d'ancienneté ;
- exigence d'une situation externe complète et vérifiée pour chaque client lié ;
- utilisation du plafond client CBS déjà fourni par l'intégration existante ;
- alerte seule, ou début du blocage à la soumission, à l'accord final ou à la mise en place. Après son premier déclenchement, le blocage est répété aux étapes suivantes.

Les paramètres sont hérités et conservés avec les autres règles du dossier. Le contrôle est désactivé par défaut ; aucun plafond réglementaire ou institutionnel n'est inventé.

## Rapprochement et fraîcheur

La situation externe doit couvrir les engagements existants dans tous les établissements, y compris le CBS, et exclure les nouvelles demandes FIN_FLOW encore en circuit. Les demandes en circuit sont ajoutées lorsqu'elles sont configurées ; le dossier analysé est ajouté une seule fois. Un dossier déjà mis en place, clôturé, annulé ou rejeté n'est plus ajouté comme nouvelle demande.

Le portefeuille local n'est pas ajouté une deuxième fois à la situation externe. Une mise en place locale postérieure à la date ou à la préparation de cette situation la rend incomplète : il faut actualiser la preuve externe. Ce contrôle évite que la sortie d'une demande du circuit fasse artificiellement baisser l'exposition connue.

Une situation manquante, ancienne, non exhaustive ou appuyée par un justificatif supprimé, réaffecté, non vérifié ou expiré ne permet pas de démontrer le respect d'un plafond. Les devises différentes ne sont jamais additionnées ou converties implicitement. L'évaluation entre dans les preuves du contrôle final pour les nouveaux dossiers dont ce domaine est activé.

## Droits et API

- `credits.view/add/change_creditexposureobservation` : consultation, saisie et modification des brouillons dans le périmètre client.
- `credits.verify_creditexposureobservation` : vérification indépendante et révocation motivée.
- `credits.view/add/change_borrowergroup` : administration des relations économiques, avec contrôle du périmètre de tous les membres.
- `GET /api/v1/credit-applications/{id}/exposure/` exige la consultation du dossier et des situations d'engagements.
- `/api/v1/credit-exposure-observations/`, actions `verify` et `revoke`.
- `/api/v1/borrower-groups/`, désactivation par PATCH ; pas de suppression des historiques via ces API.

Les profils standards de relation client, analyse et risque peuvent préparer les situations. L'administrateur crédit peut les vérifier ; l'auteur et le dernier rédacteur ne peuvent vérifier leur propre saisie, même avec un compte superutilisateur. Les droits supplémentaires peuvent être distribués depuis l'administration des rôles.

## Dépendance externe explicite

Le CBS existant ne fournit pas de contrat d'API documenté garantissant un encours consolidé complet par client et groupe économique. La livraison utilise donc des situations documentées et vérifiées, et le plafond client déjà exposé lorsqu'il est disponible. Une alimentation automatique de ces situations nécessite une spécification validée : périmètre des engagements, identifiants, devises, dates, composantes et règles de rapprochement. La réponse positive CBS reste obligatoire pour la mise en place réelle ; le versement des fonds appartient au CBS.

## Vérifications

Les tests `backend/tests/test_delivery_exposure.py` contrôlent la consolidation, les demandes en cours, les devises, la fraîcheur, la validité et le rattachement des pièces, la séparation des acteurs, la révocation, les plafonds, les droits et la restitution limitée au périmètre. La recette automatisée utilise une base SQLite de test et aucun CBS réel.
