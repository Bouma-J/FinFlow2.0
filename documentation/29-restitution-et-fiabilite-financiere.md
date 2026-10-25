# Restitution et fiabilité de l'analyse financière

## Consultation

La page de dossier conserve les composants et la charte graphique existants.
L'analyse présente une synthèse mensuelle, puis des rubriques dépliables :

- données saisies selon le profil, résultat, actif/passif, ménage et activité ;
- stabilité salariale, patrimoine, fiabilité et champs personnalisés ;
- prévisions et rapprochements, tableau et graphique flux/soldes ;
- formules, unités, seuils applicables et conformité ;
- comparaison des indicateurs courants avec les derniers indicateurs enregistrés.

Les tableaux produits, stocks, engagements, historique et prévisions sont
présentés sous forme de tableaux en lecture seule. Les zéros restent visibles.
Les commentaires d'activité, de groupement et de trésorerie sont restitués.
Les erreurs de chargement sont distinguées d'une absence d'analyse.

## Une base de calcul cohérente

`FinancialAnalysis.save` et la consultation utilisent `compute_metrics`.
L'API restitue les indicateurs courants dans `metrics`, `flags` et les anciennes
clés de synthèse (`debt_ratio`, `dscr`, `repayment_capacity`, etc.). Les résultats
persistés ne sont pas mélangés aux voyants du calcul courant.

L'API expose également :

- `recorded_indicators` : derniers indicateurs enregistrés et date de modification ;
- `calculation_context` : date du calcul, montant et nature demandé/proposé/accordé,
  conditions du prêt, taux et versions de configuration applicables ;
- `custom_field_definitions` : libellés et types des champs de l'analyse.

La lecture ne réécrit pas l'analyse. `recorded_indicators` n'est pas présenté
comme un instantané complet de décision : les anciens dossiers n'en possèdent
pas tous les éléments. Les règles conservées à la soumission continuent d'être
résolues par le centre de configuration.

## Capacité, revenu négatif et effort de trésorerie

- Le taux d'endettement n'est calculable qu'avec un revenu retenu positif.
  Un revenu nul ou négatif produit une non-conformité, jamais un ratio négatif
  favorable. La composante capacité historique vaut zéro en cas de capacité
  insuffisante ; une grille personnalisée ne renormalise pas un revenu non
  positif comme s'il s'agissait d'une information absente.
- Le bénéfice d'activité est pondéré ; une perte est retenue intégralement.
- Les voyants de capacité tiennent compte du nouveau crédit et de l'épargne
  obligatoire. Capacité avant prêt et reste après prêt sont séparés.
- Échéance institution, épargne, effort global, effort moyen sur la durée et pic
  à financer sont distincts. L'échéancier simulé est partagé avec les prévisions.
- En cas d'échéancier non calculable, les indicateurs qui en dépendent restent
  indisponibles. Les contrôles d'octroi, de droits et de mise en place CBS restent
  ceux du processus existant ; aucun fonds n'est décaissé par cette restitution.

## Compléments facultatifs

Ils sont conservés dans `analysis_details`, sans migration ni réécriture des
anciennes analyses. La validation serveur refuse les valeurs non finies,
montants négatifs non autorisés et pourcentages hors bornes. Laisser vide pour
inconnu et saisir zéro pour un montant vérifié nul.

| Groupe | Clés |
|---|---|
| Résultat | `income_tax_expense`, `provision_expense`, `provision_reversal`, `exceptional_income`, `exceptional_expense` |
| Flux avant dette | `bfr_change` (signée), `maintenance_investment` |
| Seuil de rentabilité | `fixed_operating_costs`, `variable_operating_costs` |
| Rotation et bilan | `period_purchases`, `opening_stock`, `opening_receivables`, `opening_supplier_debt`, `declared_equity` (signée) |
| Trésorerie | `opening_cash_balance` (signée) |
| Sensibilité | `purchase_stress_pct` (0–100), `receivable_delay_days` |
| Soldes historiques | `cash_detail_mode`, `fixed_assets_detail_mode` : `DETAIL`, `LEGACY` ou vide pour le comportement historique |

### Résultat, flux et DSCR

Le résultat reconstitué déduit les charges financières, amortissements, impôt
et dotations renseignés, ajoute les reprises et éléments exceptionnels.
Le cash-flow ajoute les charges non décaissées nettes au résultat.
Le flux récurrent avant service de dette réintègre les charges financières,
retire les éléments exceptionnels et déduit variation de BFR et investissements
de maintien renseignés, puis est ramené au mois. Le DSCR retient le plus prudent
de ce flux et du prévisionnel synthétique hors dette s'il est renseigné.

L'absence de compléments ne vaut pas certification de CAF ou d'états comptables
complets. La synthèse explique le pont utilisé et les limites des postes fournis.

### Seuil de rentabilité et rotations

Le seuil exige une ventilation fixes/variables dont le total correspond aux
charges d'exploitation (tolérance 0,01). Il utilise la marge sur coûts variables
et demeure indisponible si cette marge n'est pas positive. L'ancienne estimation
sur marge brute reste disponible séparément dans l'API sous `break_even_estimate`.

Les soldes moyens sont utilisés lorsque les soldes d'ouverture sont renseignés,
sinon les soldes de clôture. Le DPO utilise les achats lorsqu'ils sont renseignés,
sinon le CAMV. La convention de rotation est explicitement une base annuelle
360 jours, distincte des conventions de dates du crédit. Les postes comparés
doivent être sur des bases HT/TTC cohérentes. Le ROE n'est pas présenté comme
interprétable lorsque les fonds propres sont non positifs.

La croissance du résultat utilise la valeur absolue du résultat précédent :
une perte qui s'aggrave donne une évolution négative, un redressement positive.
Les résultats N et N-1 restent consultables pour interpréter ce pourcentage.

### Scénario défavorable

Le pourcentage de baisse vient du seuil configuré du dossier. Les charges
d'exploitation restent présentes. Pour une entreprise, la baisse porte sur
le CA et les encaissements prévisionnels, avec éventuelle hausse des achats et
besoin prudent additionnel lié au retard clients. Pour une activité individuelle,
la baisse porte sur les ventes et les coûts restent présents, avec hausse des
achats si renseignée. Les pertes sous stress ne sont pas minorées par la
pondération des revenus. Le scénario de groupement réduit ses recettes et
maintient ses charges. Il s'agit de scénarios déterministes expliqués, pas d'une
prévision probabiliste ni d'une règle réglementaire uniforme.

## Trésorerie et rapprochements

Les mois sont triés. Les soldes cumulés nécessitent un solde d'ouverture
explicite et des mois consécutifs ; sinon ils restent inconnus. Le tableau
distingue ouverture, flux net, clôture et écart avec l'échéancier simulé.
Le graphique ne trace pas de courbe de solde lorsque ces soldes sont inconnus.
Le rapprochement d'échéancier concerne uniquement les mois saisis, pas une
affirmation de couverture sur toute la durée du prêt.

Les flux nets déduisent exploitation, investissements, dettes existantes et
nouveau service, épargne incluse si elle est saisie dans ce service. Les postes
non renseignés d'une ligne de prévision sont traités comme zéro ; vérifier leur
exhaustivité avant décision. Le contrôle existant sur mois déficitaires utilise
les soldes cumulés connus, sinon conserve l'alerte sur flux négatifs.

Les écarts ventes/CA, inventaire/stock, encours détaillé/global et fonds propres
déclarés/reconstitués sont visibles. Les tableaux complètent les totaux, sans les
écraser. Les agrégats produits, stock et engagements incomplets restent inconnus.
Le rapprochement du service des dettes conserve son contrôle avant soumission.

Le taux de cotisants est une participation, et non une concentration des montants.
Zéro cotisant donne 0 %, distinct d'un effectif inconnu. Les comptes courants
d'associés sont explicitement séparés de l'encours financier du gearing.

## Référence et droits

Le choix de l'analyse de référence est pris en compte par l'API, avec les droits
existants de contribution et de modification de l'auteur. La modification reste
interdite après verrouillage du dossier. La première analyse devient référence
automatiquement ; une nouvelle référence remplace la précédente. L'enregistrement
verrouille le dossier parent dans une transaction pour sérialiser ce choix.

## Vérifications

Les tests de régression sont dans `backend/tests/test_financial_readout.py`.
Ils couvrent les pertes, les charges après prêt, l'épargne, les ratios inconnus,
les compléments, le DSCR, le seuil de rentabilité, les prévisions cumulées,
la cohérence API sans mutation à la lecture et la référence unique.
Le test historique sur flux négatif a été précisé : sans ouverture connue,
le flux est calculable, mais le solde cumulé ne l'est pas.

Recette du 20 octobre 2026 : **689 tests backend réussis**, dont 25 cas de
régression dans le nouveau fichier, avec migrations et base de tests distincte.
Le journal est `backend/test-financial-readout-final.log` et le rapport JUnit
`backend/test-financial-readout-final.xml`. Le répertoire temporaire du test de
stockage a été placé dans le projet pour contourner une restriction Windows.
Les 27 avertissements de la suite concernent notamment les dépréciations,
la configuration de tests et les paginations existantes.

Le rendu React a également été contrôlé sur les trois types de client, avec
soldes connus/inconnus et zéros explicites. Une vérification dans le navigateur
local a couvert des dossiers de démonstration entreprise, salarié et groupement,
sans modification des dossiers. La compilation TypeScript/Vite et le contrôle
d'encodage font partie de la vérification de livraison.
