# Éligibilité et scoring configurables — deuxième lot

## Périmètre

Le centre de configuration dispose de deux domaines supplémentaires : les conditions d'éligibilité et les grilles de scoring. Ils suivent les mêmes périmètres, versions, dates d'application, droits et validation indépendante que les autres adaptations.

L'écran est accessible à **Administration → Catalogue → Centre de configuration**. Aucune condition ni grille personnalisée n'est activée automatiquement. Les profils d'exemple existants ne sont pas écrasés.

## Éligibilité

Une condition comporte un critère autorisé, un opérateur, une valeur attendue, un effet et un comportement si la donnée manque. Un même critère peut être utilisé plusieurs fois avec des identifiants distincts pour fixer un intervalle.

Les critères disponibles couvrent :

- âge du client à la soumission et à la dernière échéance ;
- ancienneté professionnelle, de l'activité et de la relation ;
- apport personnel rapporté au coût du projet et taux d'épargne obligatoire ;
- nombre de crédits actifs déclaré, service mensuel des engagements et retard maximal historique ;
- score financier recalculé ;
- domiciliation demandée, salaire traçable en banque, salaire vérifié et assurance ;
- consultation du bureau de crédit et incidents déclarés ;
- périodicité, mécanisme de remboursement, situation professionnelle, secteur et devise.

Les opérateurs numériques sont « au moins », « au maximum » et « égal à ». Les contrôles booléens attendent Oui ou Non. Les critères de liste permettent d'autoriser ou d'exclure des valeurs ; le formulaire fournit les choix des référentiels disponibles et permet leur sélection par libellé.

### Effets

| Effet | Soumission | Approbation finale | Contrôle avant mise en place |
|---|---|---|---|
| Alerte | Signalement | Pas de blocage propre à cette règle | Pas de blocage propre à cette règle |
| Blocage à la soumission | Bloquant | Reste bloquant si la condition cesse d'être respectée | Reste bloquant |
| Blocage à l'approbation | Signalement | Bloquant | Reste bloquant |
| Blocage avant mise en place | Signalement | Pas de blocage à ce stade | Bloquant |

Une donnée absente peut rendre la condition non satisfaite ou conduire à ignorer le contrôle avec un signalement explicite, selon le choix de l'établissement.

La liste de conditions d'un profil remplace la liste héritée si elle est définie. Une liste vide supprime les conditions héritées pour ce périmètre. Décocher la définition locale rétablit l'héritage. L'aperçu montre ces changements avant publication.

### Origine des données et conventions

- Les âges sont des années révolues. La dernière échéance enregistrée est utilisée ; en son absence, une échéance théorique est obtenue à partir de la date d'évaluation et de la durée demandée.
- Les anciennetés sont des mois révolus. Une date future n'est pas assimilée à une ancienneté valide.
- L'ancienneté d'activité renseignée dans l'analyse est utilisée pour un particulier ; celle du groupement pour un groupement ; la date de démarrage du dossier sert de repli.
- Le nombre de crédits actifs et les engagements sont des données déclarées dans l'analyse. Ce contrôle n'effectue pas une consolidation des encours du CBS ni une interrogation d'un bureau de crédit.
- Le taux d'apport est inconnu si le coût total du projet est absent ou nul.
- Le score utilisé est recalculé avec la grille applicable ; il n'est pas saisi par l'utilisateur.
- La date d'évaluation de la capture est utilisée pour conserver la cohérence des contrôles d'âge et d'ancienneté au cours du circuit.

Les critères réservés à une catégorie de clientèle nécessitent un périmètre compatible avant publication. Un produit « entreprise » pouvant également couvrir un groupement dans le fonctionnement existant, une grille exclusivement destinée aux personnes morales doit préciser ce type de clientèle dans son périmètre.

## Scoring

### Grille existante

Le calcul existant reste le défaut. Il conserve ses critères, pondérations et traitement des données manquantes. Ses quatre seuils de classement peuvent être adaptés dans une version publiée.

### Grille personnalisée

L'établissement sélectionne de 1 à 25 indicateurs dans un catalogue contrôlé. Le catalogue actuel contient notamment le DSCR global, le gearing, la liquidité, l'autonomie financière, la couverture des intérêts, la croissance du chiffre d'affaires, le taux d'effort, le taux d'effort sous stress, le reste à vivre, la couverture des garanties, la marge de sécurité, l'ancienneté et l'historique de remboursement.

Chaque critère possède :

- une pondération strictement positive ;
- une borne défavorable correspondant à la note 0 ;
- une borne favorable correspondant à la note 100 ;
- un sens favorable : croissant ou décroissant.

La note est interpolée entre les bornes et limitée à 0–100. La somme des pondérations doit être exactement égale à 100 %. Les indicateurs dupliqués et les bornes inversées sont refusés. Aucune expression Python, SQL ou formule libre n'est exécutée.

Les nombres des règles et grilles acceptent au plus huit décimales, avec des bornes finies. Cette limite évite des paramètres de précision excessive susceptibles de rendre les calculs instables.

Les indicateurs propres à une catégorie de clientèle nécessitent un périmètre compatible. Le score de qualité de l'information reflète les niveaux et vérifications enregistrés dans l'analyse ; il ne constitue pas une certification externe des pièces.

### Données manquantes

| Choix | Calcul et conséquence |
|---|---|
| Recalculer sur les indicateurs disponibles | Les poids des indicateurs absents sont exclus du dénominateur. Si aucun indicateur n'est disponible, aucun score n'est fourni. |
| Attribuer zéro | Les poids sont conservés ; les critères absents contribuent pour zéro. |
| Exiger tous les indicateurs | Le score est non calculable tant qu'un indicateur manque. La soumission et les étapes ultérieures sont bloquées. |

Le détail comporte les valeurs utilisées, les bornes, les notes, les poids, les indicateurs manquants et le poids effectivement utilisé. La restitution API recalcule le score pour éviter d'afficher un score de brouillon devenu obsolète après publication d'une grille. Le calcul enregistré est actualisé lors de la sauvegarde de l'analyse et avant soumission.

### Classes de risque

Quatre seuils strictement décroissants dans l'intervalle 0–100 définissent les cinq classes existantes. Un score égal au seuil appartient à la classe correspondante. La classe 5 regroupe les scores inférieurs au dernier seuil.

Le mode de risque de la politique conserve son rôle : avis de l'analyste, score ou choix le plus prudent. Configurer une grille n'impose donc pas automatiquement le mode « score » pour sélectionner le circuit. La couleur de restitution du score suit les seuils applicables quand ils sont présents dans son détail.

Le repli existant vers l'avis de l'analyste est conservé lorsqu'aucun score n'est disponible. Pour exiger un score avant décision, utiliser le traitement bloquant des indicateurs manquants ou une condition d'éligibilité portant sur le score.

## Simulation sur un dossier

L'aperçu peut utiliser un dossier accessible à l'utilisateur. Cette option nécessite à la fois le droit de simulation et le droit de consultation des crédits, dans le périmètre de données de l'utilisateur et de la filiale sélectionnée.

Le dossier fournit son produit, son agence, sa clientèle et son analyse de référence. La comparaison montre :

- la configuration effectivement applicable au dossier avant simulation ;
- les règles courantes avec le profil candidat ;
- le score avant/après et la classe issue du score ;
- les conditions satisfaites, non satisfaites ou ignorées ;
- les indicateurs absents.

La simulation ne sauvegarde aucune analyse, ne change aucun statut, ne remplace aucune capture et n'envoie aucun dossier au CBS. Pour un dossier déjà soumis, la configuration candidate reste une hypothèse ; sa publication ne migre pas automatiquement ce dossier.

Les décotes de garanties du candidat sont utilisées lors du calcul de sa couverture, afin que la simulation ne réutilise pas par erreur les décotes du dossier actuel.

## Compatibilité et preuves

Les nouvelles captures portent `schema_version = 2` et incluent les conditions et la grille. Les captures du premier lot (`schema_version = 1`) restent lisibles avec une liste d'éligibilité vide et la grille existante, sans modification de leur empreinte conservée.

Les dossiers historiques déjà soumis sans capture gardent leur fonctionnement antérieur et ne reçoivent pas ces nouvelles règles rétroactivement. Un réexamen permet une nouvelle soumission avec les règles courantes.

Pour les captures de version 2, le résultat détaillé de l'évaluation est inclus dans la preuve d'approbation et dans les preuves du contrôle de mise en place. Un changement des données ayant un effet sur ces résultats rend le contrôle antérieur non actuel.

Les vérifications d'éligibilité s'ajoutent au contrôle et à l'autorisation obligatoires de l'administrateur crédit. Elles ne modifient pas le choix du service exécutant ni l'exigence de confirmation CBS.

## API

Les adaptations acceptent désormais deux rubriques supplémentaires :

```json
{
  "eligibility": {
    "rules": []
  },
  "scoring": {
    "grid": {
      "engine": "LEGACY",
      "missing_data": "RENORMALIZE",
      "criteria": [],
      "risk_cutoffs": ["80", "65", "50", "35"]
    }
  }
}
```

Ces seuils illustrent le format et reproduisent les valeurs par défaut du logiciel ; ils ne sont pas des seuils réglementaires.

Le catalogue expose les critères et indicateurs autorisés. L'API de simulation accepte le champ optionnel `application`. L'API de préparation d'un dossier inclut `rule_evaluation`.

## Travaux suivants

Ce lot couvre les conditions d'offre et les grilles financières. L'incrément suivant livre les [majorités des comités et calendriers ouvrés](21-circuits-comites-calendriers.md). Les autres domaines du plan restent à poursuivre : grilles de tarification, plafonds consolidés CBS, référentiels extensibles, habilitations indépendantes du nom des rôles, masquage des formulaires et conventions du simulateur.

La compilation et les contrôles statiques ne remplacent pas la recette métier. Aucun test automatisé n'a été ajouté ou exécuté pour cette livraison.
