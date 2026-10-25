# Analyse financière par profil client

Les conventions et la consultation ont été approfondies après audit ; voir
[Restitution et fiabilité financière](29-restitution-et-fiabilite-financiere.md),
notamment pour le flux avant service de dette, l'épargne obligatoire,
les pertes d'activité et la trésorerie cumulée.

L'analyse conserve les composants et les styles du formulaire existant. Elle
sépare le cadrage, la fiabilité des données, la reconstitution de l'activité,
le résultat, le bilan, l'historique, les dettes, la trésorerie, les sûretés,
les risques sectoriels et environnementaux, puis l'avis de l'analyste.

## Parcours

- Personne morale : produits, ventes, charges, résultat, inventaire, bilan
  détaillé, historique financier et trésorerie.
- Salarié : revenus fixes et variables, employeur, contrat, justificatifs,
  retenues, dépenses, obligations, patrimoine, endettement et reste à vivre.
- Indépendant ou mixte : revenus du ménage et bilan de l'activité distincts,
  produits, achats, stock, créances, actifs productifs et fournisseurs.
- Groupement : effectifs, cotisants, retards, ancienneté, solidarité,
  cotisations, épargne vérifiée et activité commune.

Les activités indépendantes bénéficient également des rubriques sectorielles
et E&S. Les pièces restent rattachées à chaque analyse. Le niveau déclaré,
partiellement vérifié, vérifié ou audité indique la qualité des informations.

## Conventions de calcul et de saisie

- Les revenus et charges sont saisis sur la période sélectionnée : mois,
  trimestre ou année. Les ratios de capacité convertissent ces flux au mois.
- Les stocks, créances, patrimoines, immobilisations et encours sont des soldes
  à une date. Ils ne sont jamais annualisés.
- Les mensualités existantes et les prévisions synthétiques sont mensuelles.
- L'encours financier total inclut le court et le long terme. La part long
  terme est un sous-ensemble : elle n'est pas ajoutée une seconde fois au passif.
- Les achats de l'indépendant sont inclus dans ses charges totales. Le champ
  « dont achats » fournit un détail et ne crée aucune seconde déduction.
- Les immobilisations et la trésorerie détaillées remplacent leurs anciens
  agrégats lorsque leur détail est renseigné. Les anciens agrégats restent
  disponibles dans les dossiers historiques.
- Les revenus variables et informels sont pondérés par le coefficient de
  l'analyse ou celui de l'établissement ; ce revenu pondéré alimente le taux
  d'endettement, la capacité et le stress.
- Le reste à vivre par personne utilisé pour le seuil tient compte du nouveau
  crédit. Un effectif de ménage inconnu produit un indicateur indisponible.
- La nouvelle échéance retient la plus élevée de l'échéancier simulé, puis
  un équivalent mensuel suivant la périodicité. L'échéance finale in fine est
  ainsi prise en compte. Le plan mensuel doit documenter les échéances réelles,
  notamment pour une activité saisonnière ou un remboursement unique.
- Pour la personne morale, la capacité retient le plus prudent du cash-flow
  historique mensuel et du solde prévisionnel mensuel, lorsque ce dernier est
  renseigné. Le DSCR global couvre les dettes existantes et le nouveau crédit.

Les tableaux détaillés complètent les totaux saisis sans les écraser. Le serveur
calcule les ventes reconstituées, le stock net inventorié, le service détaillé
des dettes et les mois prévisionnels déficitaires. Un écart entre le service
détaillé et le total consolidé doit être rapproché avant soumission. Les mois
déficitaires doivent être accompagnés de mesures dans les conditions proposées.
Le plan de trésorerie distingue exploitation, investissement et chaque service
de dette ; il n'ajoute pas de financement nouveau aux recettes d'exploitation.

## Paramétrage et cadre UMOA

Les seuils d'endettement, DSCR, quotité, pondération et couverture restent ceux
de l'établissement. Les valeurs par défaut de l'application ne constituent pas
une norme UMOA ni une règle nationale de saisissabilité du salaire. Les règles
applicables dépendent notamment du pays, du statut de banque ou de SFD et du
produit. La consultation BIC est tracée par date, référence et commentaire ;
ce formulaire n'effectue pas de consultation automatique du BIC.

Références de cadrage :

- [Commission bancaire de l'UMOA : risque de crédit](https://www.cb-umoa.org/fr/node/1095).
- [BCEAO : dispositif prudentiel applicable aux établissements de crédit](https://www.bceao.int/fr/reglementations/annexe-decision-ndeg013-24-06-cm-umoa-relative-au-dispositif-prudentiel-applicable).

## Mise en service

Appliquer la migration `credits.0031_deepen_financial_analysis_for_credit`
avec les migrations habituelles du projet avant de démarrer le nouveau serveur.
Elle ajoute des champs ; elle ne réécrit pas les analyses existantes. Les
indicateurs persistés sont recalculés à l'enregistrement ou au rafraîchissement
de l'analyse de référence. Les brouillons peuvent rester partiels.
