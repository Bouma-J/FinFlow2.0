# Conventions de simulation et d'échéanciers

## Périmètre livré

Le centre de configuration propose une section **Conventions du simulateur et des échéanciers**. Elle suit les profils versionnés, leurs périmètres, leurs dates d'effet et leur validation indépendante. Les composants et styles existants sont conservés.

Le moteur est commun à la simulation, au calcul de l'échéance de référence de l'analyse financière et à la création des échéances du prêt local après confirmation du CBS. Le dossier conserve ses conventions et une copie du calendrier utilisé.

Le mode **LEGACY**, par défaut, conserve les résultats historiques : intérêts réels/365, arrondi à la dizaine, première période théorique pour le dégressif et report des seules échéances intermédiaires du week-end. Les captures anciennes restent dans ce mode ; leur empreinte n'est pas réécrite.

## Paramètres du mode configuré

| Paramètre | Choix et effet |
|---|---|
| Décompte de jours | Réels/365 fixe ; réels/360 ; 30E/360 Eurobond |
| Pas monétaire | De 0,01 à 1 000, avec deux décimales maximum |
| Arrondi | Au plus proche, moitié supérieure ; ou moitié vers le nombre pair |
| Ajustement des échéances | Aucun ; jour ouvré suivant ; suivant sauf changement de mois, puis précédent ; jour ouvré précédent |
| Dates des intérêts | Dates nominales ; ou dates après ajustement |
| Calendrier | Calendrier actif de la même filiale, obligatoire pour ajuster les dates |

Les dates fériées proviennent du calendrier renseigné et validé par l'établissement. Aucun calendrier national n'est déduit du pays et aucune date externe n'est inventée. Les heures d'ouverture ne servent pas au report d'une date d'échéance : seuls les jours de semaine travaillés et dates fériées interviennent.

Le calendrier est copié à la conservation des règles, avec son identité, son nom, ses jours ouvrés et ses jours fériés. Une modification ou désactivation ultérieure ne réécrit pas les échéances des dossiers déjà conservés. Les nouveaux dossiers ne peuvent pas utiliser un calendrier inactif ou appartenant à une autre filiale.

La fréquence du référentiel de périodicités est également copiée pour les conventions configurées. Un changement ultérieur du référentiel ne change pas le nombre d'échéances d'un dossier conservé. Une fréquence incohérente avec la convention de dates du code est refusée.

## Calcul

- **Dégressif et CONSTANT historique** : l'annuité théorique est résolue à partir des facteurs d'intérêt effectifs de toutes les périodes, puis arrondie. Chaque ligne calcule l'intérêt sur le capital restant et la fraction d'année retenue. Le capital est limité au solde restant ; la dernière échéance corrige le résidu des arrondis.
- **In fine** : intérêts périodiques et capital à la dernière échéance.
- **Bullet** : une seule ligne à la dernière date nominale du nombre de périodes prévu, puis ajustement éventuel.

En mode configuré, la première période commence à la date d'effet/simulation et se termine à la première échéance nominale ou ajustée selon le choix. Une première date éloignée produit une période irrégulière réellement calculée. Elle ne crée ni différé contractuel distinct ni capitalisation des intérêts.

Les bases réelles divisent le nombre exact de jours par 360 ou 365 fixe, y compris en année bissextile. En **30E/360 Eurobond**, chaque jour 31 est remplacé par 30, puis les années et mois sont comptés à 360 et 30 jours. La fin de février ne reçoit pas le traitement spécifique de la variante 30E/360 ISDA. Référence de définition : [documentation primaire OpenGamma Strata sur les conventions de jours](https://strata.opengamma.io/day_counts/).

Les périodicités conservent les conventions de dates définies par le modèle : pas d'un jour ou d'une semaine ; pas fixe de quinze jours pour le code `BIMONTHLY` ; puis un, trois, six ou douze mois calendaires pour les autres codes. Le nombre de lignes résulte de la durée en mois et de la fréquence annuelle du code (journalier : 360 ; hebdomadaire : 52 ; bimensuel : 24 ; mensuel : 12 ; trimestriel : 4 ; semestriel : 2 ; annuel : 1). Le code bimensuel représente donc un pas de quinze jours ; il ne définit pas deux dates fixes dans chaque mois. Une périodicité personnalisée dont le calendrier n'est pas défini est refusée par le moteur configuré.

L'épargne reste une obligation distincte du coût du crédit. Elle est arrondie au pas choisi. Les intérêts, l'annuité de référence et l'épargne utilisent ce pas ; le solde final du capital peut comporter un résidu hors de ce pas afin de préserver exactement le capital initial. Un arrondi qui empêche tout amortissement sur une période dégressive est refusé. Aucun capital négatif ni sur-remboursement du capital n'est créé.

## Mise en place et restitution

Le calcul complet des paramètres et échéances est effectué **avant l'appel CBS**. Une erreur de date, de calendrier, de fréquence ou d'arrondi empêche cet appel. Après retour positif du CBS et recontrôle de l'autorisation, le même résultat prévalidé crée les échéances locales : aucun nouveau calcul monétaire susceptible d'échouer n'est lancé après l'effet externe.

Le contrôle final et l'autorisation de l'administrateur crédit restent obligatoires. L'exécutant continue de dépendre de la politique de gestion. Le décaissement effectif des fonds se déroule dans le CBS.

Le simulateur affiche les conventions effectives, les dates nominales lorsqu'elles ont été ajustées, les frais et taxes déjà décrits, le coût hors épargne et le flux total client. Le PDF reprend les conventions et le calendrier du résultat calculé, indépendamment des modifications ultérieures du formulaire.

## Limites et dépendances externes

Le connecteur Perfect existant ne fournit pas de champ documenté pour transmettre ces conventions de jours, d'arrondi ou de calendrier. Leur concordance avec les paramètres du produit CBS doit donc être validée par l'établissement. Aucun champ CBS n'a été ajouté ou supposé.

Les frais et taxes paramétrés dans le quatrième incrément restent calculés selon leurs règles propres. Ce lot ne crée pas de remise individuelle non tracée, de financement automatique des frais ni de différé avec intérêts capitalisés. Un tel mécanisme nécessite un modèle contractuel, un circuit d'autorisation et une spécification de concordance CBS dédiés.

Le coût affiché n'est pas présenté comme un TEG ou TAEG réglementaire. Les primes d'assurance, taxes sur intérêts et coûts externes ne sont inclus que s'ils disposent de données et règles explicitement modélisées ; aucun taux réglementaire ou fiscal UMOA n'est introduit ici.

## Vérifications

La recette dédiée vérifie les trois décomptes, les quatre mécanismes, les années bissextiles et fins de mois, les taux nuls, la conservation exacte du capital, les arrondis, le refus d'un amortissement nul, les reports de jours fériés, la conservation des calendriers et fréquences, l'isolation des filiales, les valeurs inconnues et copies de calendrier falsifiées, la stabilité du moteur historique et la concordance avec la capacité de remboursement.

Des tests d'API vérifient l'application d'un profil publié. Un test de mise en place utilise un CBS simulé pour prouver qu'une date invalide n'entraîne aucun appel externe et que les échéances créées après succès correspondent exactement au calcul préalable. Les contrôles d'habilitation et d'autorisation, couverts dans la recette de gouvernance, sont isolés dans ce test spécifique. Aucun CBS réel n'est appelé par ces vérifications.
