# Audit de la restitution de l'analyse financière — 20 octobre 2026

Les corrections consécutives à cet audit sont décrites dans
[Restitution et fiabilité financière](29-restitution-et-fiabilite-financiere.md).
Les constats ci-dessous décrivent l'état examiné avant ces corrections.

## Conclusion et périmètre

La section de consultation contient un socle utile : auteur, analyse de référence,
recommandation, ratios par type de client, stress, score détaillé, dettes, tableaux
de reconstitution, fiabilité, secteurs, E&S et pièces justificatives. Elle ne
restitue cependant pas suffisamment les données saisies pour permettre une
contre-analyse autonome. Plusieurs comportements de calcul et d'affichage doivent
être corrigés avant de présenter les indicateurs comme une synthèse fiable.

Audit du formulaire, des modèles, des calculateurs, de la sérialisation et du
composant de consultation. Aucun dossier ni calcul métier n'a été modifié. La
présente revue repose sur le code, les tests et des cas chiffrés en mémoire ;
elle ne constitue pas une recette visuelle dans un navigateur ni une validation
réglementaire de l'ensemble du produit.

Sources principales :

- `frontend/src/components/FinancialAnalysisForm.tsx` : saisie et aperçu.
- `frontend/src/pages/CreditApplicationDetailPage.tsx:710` : `AnalysisDetail`.
- `frontend/src/components/FinancialAnalysisDetails.tsx` : tableaux détaillés.
- `backend/apps/credits/models.py:1605` : agrégats et enregistrement.
- `backend/apps/credits/analytics.py:79` : indicateurs et conformité.
- `backend/apps/credits/serializers.py:138` : indicateurs courants et persistés.
- `backend/apps/credits/analysis_details.py:94` : produits, stocks, dettes et prévisions.

## 1. Fidélité à la saisie

| Profil | Déjà visible | Informations saisies mais absentes ou trop agrégées dans cette section |
|---|---|---|
| Entreprise | CA, marge brute, EBE, résultat simplifié, cash-flow, capitaux propres, BFR, DSCR, liquidité, rotation, rentabilité et croissance | CAMV, détail des charges, amortissements et charges financières ; actif/passif détaillé, caisse/banque, immobilisations, dettes par nature ; montants N-1 ; encaissements/sorties prévisionnels synthétiques et commentaire |
| Salarié | Profil, total revenus, total charges, disponible, revenu pondéré, taux d'endettement, quotité disponible, employeur | Décomposition salaire/conjoint/loyers/primes/pension, charges poste par poste, retenues, type de contrat, ancienneté, salaire vérifié/domicilié, patrimoine et coefficient de pondération appliqué |
| Indépendant ou mixte | Profil et indicateurs de ménage, nom d'activité, tableaux produits et stocks s'ils sont saisis | CA et charges de l'activité, dont achats, résultat propre à l'activité, ancienneté, jours de vente, bilan de l'activité, activité formelle et disponibilité des registres ; commentaire d'activité |
| Groupement | Membres, cotisants, cotisations, CA collectif, capacité, solidarité et taux d'effort | Épargne, mobilisation/nantissement, autres revenus, charges de fonctionnement et d'activité, ancienneté, membres en retard et taux d'impayés, registres vérifiés ; commentaire du groupement |

Les cases de vérification visite/stock/caisse et les champs personnalisés
`custom_fields` ne sont pas restitués dans `AnalysisDetail`. Les commentaires
`activity_comment`, `group_comment` et `cashflow_comment` ne le sont pas non plus.
Il ne s'agit pas d'une preuve de perte en base : l'API expose ces informations,
mais ce composant ne les affiche pas.

Le contrôle statique relève 75 des 93 champs numériques de la saisie sans
affichage individuel dans ce composant. Certains alimentent des agrégats : ce
nombre mesure l'absence de détail visible, pas l'absence de traitement.

## 2. Anomalies prioritaires reproduites

### A. Activité déficitaire et indicateurs favorables — critique

Avec recettes d'activité de 100 000, charges de 160 000, pondération par défaut
de 70 % et nouvelle mensualité de 20 000 :

- revenu retenu : −42 000 ;
- taux d'endettement calculé : −47,62 % ;
- `debt_ratio_ok = true` ;
- composante capacité du score historique : 100/100.

La division accepte un revenu négatif et le comparateur assimile un ratio
négatif à un faible endettement. La pondération de la perte réduit également
son ampleur. Une perte ou un revenu retenu nul doit déclencher un traitement
explicite, jamais une qualification favorable par simple comparaison du ratio.
Ce cas concerne le moteur d'indicateurs ; les contrôles de soumission peuvent
rejeter certaines analyses déficitaires, sans supprimer le défaut de restitution
ou de scoring des analyses enregistrées.

### B. Capacité positive avant le prêt et déficit après le prêt — élevée

Groupement : recettes 100 000, charges 90 000, nouvelle mensualité 30 000,
aucune dette antérieure. Le calcul produit :

- capacité avant nouveau prêt : 10 000 ;
- marge après prêt : −20 000 ;
- `capacity_ok = true`, taux d'endettement 30 % et conformité favorable avec
  les seuils par défaut.

Le voyant compare seulement la capacité avant nouveau crédit à zéro. Il faut
conserver cet agrégat, mais ajouter une conformité distincte portant sur la
couverture effective de la nouvelle échéance et le minimum de reste disponible.

Particulier : revenu 200 000, charges 150 000, dettes existantes 10 000,
nouvelle échéance 80 000. `disposable_ok = true` alors que le reste après crédit
est −40 000. Le taux d'endettement déclenche ici une autre alerte ; ce voyant ne
doit pas être interprété comme une validation de la capacité après crédit.

### C. Valeurs recalculées et valeurs persistées mélangées — élevée

Le sérialiseur recalcule `metrics`, `flags`, `new_installment` et le score.
`debt_ratio`, `dscr`, `repayment_capacity`, `dscr_stress` et
`debt_ratio_stress` restent des champs enregistrés. Le composant utilise les deux
familles pour une même analyse, parfois avec un voyant issu du calcul courant
sur un montant persisté.

Cas en mémoire simulant un changement d'échéance : taux persisté 5 %, taux
courant 50 %, échéance persistée 10 000 et échéance courante 100 000. Les deux
valeurs peuvent coexister dans le contrat de restitution. Le rafraîchissement de
l'analyse de référence lors de certaines mutations réduit ce risque, mais ne
garantit pas l'actualisation de toutes les analyses historiques affichées.

Décision de conception nécessaire : afficher les résultats conservés à la
décision, les résultats recalculés avec les conditions actuelles, ou les deux
avec date, montant de référence et version de règles. Un bloc unique ne doit
pas les mélanger.

### D. Flux mensuel présenté comme solde prévisionnel — élevée

`forecast_lowest_balance` prend le minimum des encaissements moins sorties,
investissements et services de dette de chaque ligne. Aucun solde initial ni
report de trésorerie ne participe au calcul.

Janvier : flux +500 000 ; février : flux −100 000. Le minimum annoncé est
−100 000 et un mois est compté déficitaire. Avec une ouverture à zéro et aucun
autre mouvement, les soldes cumulés seraient +500 000 puis +400 000. Le flux
mensuel négatif est une information pertinente ; il ne prouve pas une trésorerie
cumulée négative. Le contrôle de soumission exige actuellement un commentaire
sur les conditions en présence de flux mensuels déficitaires.

Afficher séparément flux mensuel, trésorerie d'ouverture, solde de clôture et
besoin de financement. Trier les mois, identifier les périodes manquantes et
rapprocher le service du nouveau crédit de l'échéancier réel.

### E. Données manquantes transformées en zéro ou en alerte — élevée

Plusieurs cartes utilisent `mNum(...) ?? 0`, notamment reste par personne,
fonds de roulement et seuil de rentabilité. Une valeur non calculable apparaît
alors comme un montant nul. Ailleurs, `debtTone` et `dscrTone` traitent `null`
comme faux, alors que `boolTone` gère déjà l'état inconnu.

Conserver trois états : zéro saisi/calculé, donnée inconnue et indicateur non
applicable. Afficher la cause et les données nécessaires lorsqu'un calcul est
indisponible. Une erreur de chargement de l'analyse ne doit pas être présentée
comme « Aucune analyse financière enregistrée ».

## 3. Calculs cohérents dans les conventions actuelles

- Conversion mois/trimestre/année des flux pour les ratios de capacité ; les
  soldes de bilan ne sont pas annualisés.
- Marge brute = CA − CAMV ; somme des charges d'exploitation ; reconstitution
  EBE/résultat/cash-flow conforme au modèle simplifié actuellement codé.
- Part long terme traitée comme sous-ensemble de l'encours financier, sans
  seconde addition de cette part au total des dettes.
- Somme des ventes détaillées = quantité × prix ; stock net = quantité × coût
  moins dépréciation ; agrégation des engagements détaillés.
- Rapprochement du service détaillé des dettes avec le service global déclaré,
  contrôlé avant soumission.
- Couverture des garanties réelles après décotes ; cautions traitées dans un
  pilier distinct, sans les assimiler automatiquement à de la trésorerie.
- Seuils et pondérations issus du contexte configuré du dossier.

Ces vérifications établissent des comportements ciblés, pas une certification
de tous les calculs financiers, mécanismes de remboursement ou cas réglementaires.

## 4. Conventions financières à préciser ou enrichir

| Sujet | Constat | Amélioration recommandée |
|---|---|---|
| DSCR | Numérateur = résultat simplifié + amortissements, donc après charges financières ; dénominateur = service global de dette | Définir un flux disponible avant service de dette et documenter intérêts, impôts, variation de BFR et investissements ; éviter de compter une charge d'intérêt dans le flux et dans le service sans convention explicite |
| Résultat et cash-flow | Pas de compte de résultat complet ni de pont CAF/flux d'exploitation | Afficher « reconstitution simplifiée » ; compléter selon le profil comptable avec impôt sur le résultat, provisions/reprises, éléments exceptionnels et rapprochement aux comptes |
| Fonds propres | Calculés par différence actif − dettes | Distinguer capitaux propres déclarés et fonds propres reconstitués/ajustés ; un équilibre par différence ne contrôle pas l'exhaustivité du passif |
| Point mort | Utilise la marge sur CAMV et classe les charges d'exploitation comme fixes | Séparer charges fixes/variables et utiliser la marge sur coûts variables ; sinon nommer le résultat « approximation » |
| DPO, DIO et DSO | Soldes de clôture rapportés au CAMV ou au CA annualisé, base 360 | Afficher les bases ; proposer soldes moyens, achats de la période et cohérence HT/TTC si les données sont disponibles |
| Gearing | Encours financier / capitaux propres | Expliciter les dettes retenues, les comptes courants d'associés, la dette nette et les éventuelles dettes subordonnées |
| Croissance du résultat | Division par le résultat précédent, même négatif | Traiter explicitement perte aggravée et retour au bénéfice ; ne pas présenter automatiquement un pourcentage positif comme une amélioration |
| Épargne obligatoire | Échéance calculée avec `savings_rate=0`, conformément au libellé hors épargne | Ajouter l'effort de trésorerie total, épargne et autres prélèvements récurrents compris, pour le reste à vivre et le plan de trésorerie |
| In fine / remboursement unique | Plus forte échéance convertie selon la périodicité | Distinguer pic à financer, effort régulier et besoin à maturité ; un pic contractuel ne doit pas être assimilé sans explication à une charge mensuelle récurrente |
| Stress | Décote uniforme du flux ou du revenu ; pas de recalcul détaillé des postes | Ajouter scénarios baisse CA, hausse achats, retard clients, perte d'emploi, retrait de cotisants et saisonnalité ; afficher hypothèses et impact sur le solde disponible |

Les tableaux produits/stocks ne sont pas rapprochés automatiquement des agrégats
CA/stock. Exemple reproduit : CA déclaré 1 000 000 et ventes détaillées 100 000,
stock déclaré nul et inventaire net 1 000, sans drapeau de rapprochement dédié.
Les coûts unitaires produits ne donnent pas encore de marge détaillée. Le bilan
de l'activité indépendante reste peu exploité en indicateurs propres à l'activité.

Le taux intitulé « concentration cotisants » est en réalité la proportion des
membres qui cotisent, pas la concentration des montants sur quelques membres.
Avec zéro cotisant, le calcul renvoie actuellement `null` au lieu de 0 % ; le
voyant placé sur les cotisants contrôle le nombre total de membres. Renommer en
« taux de participation » et séparer participation, impayés et concentration.

L'ancien agrégat de caisse/banque ou d'immobilisations est repris lorsque le
détail totalise zéro. Ce repli est annoncé dans le formulaire historique, mais
un zéro explicite doit pouvoir être distingué d'un détail absent.

Le choix « analyse de référence » est proposé dans le formulaire alors que
`is_reference` est en lecture seule dans le sérialiseur : le choix transmis n'est
pas appliqué par ce chemin. La désignation automatique conserve une référence,
mais ne matérialise pas le choix exprimé par l'utilisateur.

## 5. Organisation recommandée de la consultation

Conserver les composants et la charte existants, avec une synthèse courte puis
des rubriques dépliables dans l'ordre du formulaire :

1. **Synthèse de décision** : profil, fiabilité, date d'arrêté, analyse de
   référence, montant demandé/proposé/accordé utilisé, conditions du crédit,
   effort mensuel, effort de trésorerie total, reste après crédit, conformité.
2. **Données de base par profil** : compte de résultat et bilan pour entreprise ;
   revenus/charges/stabilité/patrimoine pour salarié ; activité et ménage
   séparés pour indépendant/mixte ; cotisations/activité/épargne pour groupement.
3. **Reconstitution et rapprochements** : produits, stocks, engagements,
   déclaratif/pièces/visite/BIC, écarts chiffrés et explications de l'analyste.
4. **Ratios expliqués** : valeur, unité, formule, numérateur/dénominateur,
   seuil applicable, statut conforme/non conforme/non calculable et source.
5. **Historique et prévisions** : N/N-1 et historique détaillé, flux et trésorerie
   cumulée mensuelle, échéancier, saisonnalité et scénarios défavorables.
6. **Sûretés et conclusion** : valeur brute/retenue et décotes, cautions séparées,
   score expliqué, points forts/faibles, conditions, suivi et pièces.

Les champs personnalisés doivent apparaître avec les libellés et unités de la
configuration applicable au dossier. Masquer les rubriques non pertinentes à
un profil, sans cacher une information déjà saisie. Un graphe des flux et soldes
mensuels et une comparaison avant/après crédit seraient particulièrement utiles.

Ordre proposé : corriger les anomalies A–E, unifier la restitution et les unités,
afficher les données déjà disponibles, puis enrichir les conventions, ratios,
scénarios et comparaisons. Conserver la décision humaine et les seuils métier
paramétrables ; une formule invalide ne doit pas produire un voyant favorable.

## 6. Vérifications exécutées

Commande, depuis `backend` :

```text
..\.venv\Scripts\python.exe -m pytest tests/test_financial_analysis_detail.py tests/test_analysis_validation.py tests/test_delivery_simulation.py
```

Résultat : **59 tests réussis**, avec base de tests distincte en mémoire.

Cas complémentaires exécutés sans enregistrement en base : activité déficitaire,
reste après crédit négatif, groupement sans cotisant et capacité insuffisante,
bases du DSCR, flux mensuels non cumulés, détails non rapprochés, divergence
persisté/courant et lecture seule de la référence. Les garanties ont été
neutralisées dans ces cas isolés pour examiner les formules de capacité ; ils
ne valident donc pas une intégration CBS ou un scénario complet d'octroi.

## 7. Référence de méthode

Les principes du Comité de Bâle recommandent l'analyse de la capacité de
remboursement, des tendances financières historiques et des projections sous
plusieurs scénarios. Ils servent ici de référence de méthode, sans présumer de
leur transposition réglementaire à chaque banque ou SFD de l'UMOA :
[Principles for the management of credit risk](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/cri/10).

Les seuils internes de taux d'endettement, DSCR et quotité ne doivent pas être
présentés comme des normes universelles de l'UMOA. La reconstitution disponible
dans FIN_FLOW ne remplace pas, à elle seule, des états financiers comptables
complets lorsqu'ils sont requis pour le client concerné.
