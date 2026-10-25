# Tarification configurable des crédits

## Périmètre

Ce quatrième incrément ajoute un barème tarifaire aux profils du **Centre de configuration** (`/admin/configuration`). Il utilise leur périmètre produit, agence, clientèle et profil particulier, leur ordre de priorité et leur publication par un autre utilisateur habilité.

Le simulateur (`/simulateur`) et les dossiers partagent le même moteur de devis. Les composants et styles existants sont conservés.

Le mode par défaut reste **LEGACY** : les frais saisis au dossier et le taux du dossier, ou du produit s'il est absent, conservent leur fonctionnement. La publication d'un profil sans tarification n'active pas de frais supplémentaires. Pour utiliser les nouvelles règles, définir explicitement un barème en mode **CONFIGURED** et sa devise.

## Paramètres du barème

| Élément | Fonctionnement |
|---|---|
| Taux annuel | Défaut, minimum, maximum, négociable ou imposé |
| Frais de dossier (%) | Défaut, minimum, maximum, négociables ou imposés |
| Épargne obligatoire par échéance (%) | Défaut, minimum, maximum, négociable ou imposée |
| Tranches | Montant et durée, avec taux de remplacement pour chaque catégorie |
| Frais complémentaires | Code, libellé, montant fixe ou pourcentage du capital |
| Plancher/plafond de frais | Montants hors taxe propres à chaque frais configuré |
| Taxes sur frais | Taux sur les frais de dossier et sur chaque frais configuré |
| Frais manuels | Autorisation ou interdiction des lignes additionnelles du dossier |
| Plafond global | Total frais et taxes sur frais, exprimé en pourcentage du capital |
| Devise | Une devise explicite ; aucune conversion automatique |

Le barème est une adaptation atomique : le profil le plus spécifique qui définit `pricing.tariff` remplace le barème hérité entier. Décocher « Définir le barème dans ce profil » rétablit l'héritage. Un barème explicite en mode LEGACY peut rétablir le fonctionnement existant dans un périmètre plus spécifique.

### Taux effectifs

Pour chaque catégorie, le moteur utilise :

1. Le taux saisi au dossier, s'il est renseigné, **y compris zéro**.
2. Sinon, le taux de la tranche applicable.
3. Sinon, le défaut du barème.
4. Sinon, le taux du produit pour l'intérêt et les frais de dossier ; zéro pour l'épargne.

Le recours aux frais de dossier du produit à l'étape 4 concerne le mode CONFIGURED. Le mode LEGACY conserve l'absence de frais de dossier lorsque le champ du dossier est vide.

En mode CONFIGURED, un taux saisi doit respecter les bornes. S'il n'est pas négociable, il doit être égal au taux attendu par la tranche, le défaut ou le produit. Un champ vide n'est pas une dispense : il hérite du taux calculé. Pour rendre une épargne ou un taux effectivement obligatoire, fixer les bornes ou désactiver son caractère négociable.

Les taux monétaires de ces champs acceptent trois décimales. Les limites techniques sont 0 à 999,999 % pour l'intérêt et 0 à 100 % pour les frais et l'épargne. **Ce sont des limites de stockage et de validation du logiciel, pas des seuils réglementaires ni une recommandation de tarification.** Les taux, plafonds et taxes applicables doivent être définis et validés par l'établissement pour son activité et son contexte.

### Tranches

Un barème accepte au maximum 50 tranches. Chaque tranche combine des bornes inclusives de montant et de durée ; une borne vide est ouverte. Les durées renseignées sont comprises entre 1 et 600 mois.

Deux tranches ne peuvent pas se chevaucher simultanément en montant **et** en durée. Deux tranches de montants identiques restent possibles si leurs durées sont disjointes. Deux tranches de durées identiques restent possibles si leurs montants sont disjoints. Une seule tranche peut donc s'appliquer ; aucune priorité cachée entre lignes n'est utilisée.

Sans tranche applicable, les défauts du barème restent utilisés. Un taux laissé vide dans une tranche conserve également ce défaut. Les taux des tranches et les défauts explicitement définis sont contrôlés contre les bornes du barème lors de l'enregistrement du profil.

Si un montant proposé ou accordé change pendant le circuit, le devis utilise le nouveau montant de référence. Un changement de tranche peut rendre les taux déjà saisis non conformes : l'approbation est alors bloquée jusqu'à correction selon le processus autorisé. Le moteur ne remplace pas silencieusement les termes financiers saisis par un validateur.

### Frais et taxes

Les pourcentages utilisent le montant de référence du dossier : proposé avant accord, accordé après décision, avec les replis existants sur le montant demandé. Le calcul d'une ligne configurée suit cet ordre :

1. Montant fixe ou pourcentage du capital.
2. Arrondi au centime, moitié supérieure.
3. Application du plancher et du plafond hors taxe de la ligne.
4. Taxe sur ce montant, arrondie au centime.
5. Montant de ligne = base hors taxe + taxe.

Le total inclut les frais de dossier, les frais configurés, leurs taxes et les lignes manuelles. Les lignes manuelles n'acquièrent pas automatiquement de taxe ; utiliser un frais configuré lorsque ce calcul est nécessaire.

En mode CONFIGURED, le total est contrôlé contre le plafond global s'il est défini, et ne peut pas dépasser le capital. Le net présenté est indicatif : capital moins les frais et taxes décrits. Fin Flow ne soustrait pas ce total du principal transmis au CBS.

Le barème accepte 30 frais configurés au maximum. Les codes sont uniques et courts ; `PROCESSING` et le préfixe `MANUAL_` sont réservés. Les frais configurés sont obligatoires dans le devis de leur périmètre : ils ne peuvent pas être supprimés en retirant une ligne manuelle du dossier. Une exemption individuelle, une remise sur une ligne configurée ou une taxe d'intérêt nécessitent un développement distinct.

Les frais manuels sont limités à 100 lignes. Leur liste entière est validée avant remplacement : libellés et modes invalides, valeurs négatives ou non finies, pourcentages supérieurs à 100 et précisions incompatibles sont refusés. L'enregistrement du dossier et de ces lignes est transactionnel. Les anciennes règles qui ignoraient silencieusement certaines lignes invalides ne s'appliquent plus aux nouvelles écritures.

## Conservation et contrôles métier

Les nouvelles captures de configuration portent `schema_version=3`. Elles comprennent le barème et les conditions de base du produit résolues à la soumission. Les taux hérités sont matérialisés dans les champs du dossier avant le recalcul de l'analyse et les contrôles de soumission. Un refus annule ces écritures dans la même transaction.

L'analyse, les ratios et les aperçus de score utilisent le taux effectif. Pour les captures de version 3, la date de capture sert de date d'origine stable de l'estimation analytique, afin qu'une simple lecture le lendemain ne modifie pas les preuves par un nouveau départ implicite à la date du jour. L'échéancier définitif du CBS conserve sa propre date d'effet.

Le devis est contrôlé :

- dans la checklist de préparation ;
- avant soumission ;
- avant l'approbation finale ;
- dans les contrôles de mise en place de l'administrateur crédit.

Il est inclus dans les preuves de décision et dans les empreintes financières et documentaires des dossiers avec capture de version 3. Le choix de l'exécutant CBS et l'autorisation obligatoire de l'administrateur crédit sont conservés.

Les captures de versions 1 et 2 gardent leur empreinte et le mode tarifaire historique. Les dossiers déjà soumis sans capture ne reçoivent pas les nouveaux barèmes rétroactivement. Les captures existantes ne sont pas réécrites par ce déploiement. Les règles existantes d'annulation, de retour et de réexamen continuent de déterminer quand une nouvelle résolution est effectuée.

Le taux explicite de 0 % est désormais respecté également lors de la création locale du prêt après retour positif du CBS ; il n'est plus remplacé par le taux du produit dans cette étape.

## Simulation et contrats

Le simulateur peut sélectionner un produit, une agence, un type de clientèle et un profil particulier. Un taux laissé vide avec un produit sélectionné utilise le barème ou le produit. La simulation libre sans produit conserve un taux explicitement renseigné. Le moteur contrôle les références de la filiale, le périmètre d'agence, la clientèle du produit et ses bornes de montant et durée lorsqu'un produit est choisi.

Les résultats exposent :

- les taux réellement utilisés et la tranche retenue ;
- chaque frais, sa base, sa taxe et son total ;
- les intérêts et l'épargne séparément ;
- `total_cost_excluding_savings` = intérêts + frais décrits, taxes sur ces frais comprises ;
- `total_client_outflow` = flux de l'échéancier, épargne comprise, + ces frais.

Le second total est une somme des flux prévisionnels, sans actualisation et sans modélisation du remboursement ultérieur de l'épargne. Ces résultats ne constituent pas un calcul de TEG, de TAEG, de taux d'usure ou de fiscalité complète. La prime d'assurance saisie dans le dossier, les taxes sur les intérêts, les frais externes et les charges non décrites ne sont pas ajoutés automatiquement à ces totaux.

Le PDF reprend les paramètres renvoyés avec le résultat, sa devise et le détail des frais. Modifier le formulaire après une simulation ne modifie pas les paramètres de son export. La convention d'amortissement existante ACT/365, l'arrondi de l'échéancier et ses règles calendaires sont conservés ; ils ne deviennent pas paramétrables dans cet incrément.

Le contexte des nouveaux contrats expose `tarification`, `frais_detail`, `frais_total` et `taxes_frais_total`. Les modèles documentaires existants ne sont pas réécrits automatiquement : l'établissement peut ajouter ces balises et listes à ses modèles.

## Frontière avec le CBS

Le connecteur Perfect `crd/simple` actuel transmet notamment le **taux d'intérêt** et le **montant accordé**. Son payload existant ne prévoit pas la transmission des nouvelles lignes détaillées de frais, de leurs taxes ni du taux d'épargne. Cet incrément n'ajoute pas de champs non documentés à cet appel.

Les prélèvements effectifs restent dans le CBS et doivent être rapprochés de ses conditions lors du contrôle de mise en place. Le détail dans Fin Flow sert à l'instruction, au devis, aux contrats et à la traçabilité ; il ne garantit pas à lui seul que les frais sont configurés à l'identique dans le CBS. Une transmission détaillée nécessite l'interface et les mappings correspondants du CBS.

## API

- `pricing.tariff` est accepté dans `ConfigurationProfile.overrides`.
- Le catalogue expose `default_tariff` et le module `pricing`.
- La résolution expose `pricing.tariff` et `pricing.product_defaults`.
- Le détail d'un dossier expose `pricing_quote` et un `fees_breakdown` enrichi.
- L'aperçu de profil sur un dossier expose `pricing_evaluation.before/after` sans écriture.
- `POST /api/v1/credit-applications/simulate/` accepte en plus `product`, `agency`, `client_type`, `individual_profile`, `currency`, `fees_rate` et `extra_fees`. `annual_rate` et `savings_rate` peuvent être absents ou nuls selon le contexte décrit ci-dessus.
- La simulation exige le droit `credits.view_creditapplication`. Les droits de création, modification et publication des profils restent ceux du centre de configuration.

Le barème étant conservé dans les champs JSON existants, aucune migration de schéma n'est nécessaire pour ce lot.

## Travaux suivants et vérifications

Restent notamment à poursuivre : conventions du simulateur, calcul réglementaire complet du coût, remises et dérogations individualisées, fiscalité des intérêts, rapprochement et transmission détaillée des conditions au CBS, plafonds consolidés, référentiels extensibles et capacités métier des rôles.

Les contrôles système Django, l'absence de migration manquante, la compilation TypeScript/Vite et les contrôles statiques Python ont été exécutés. Aucun test automatisé ni scénario métier dans le navigateur n'a été ajouté ou exécuté pour cet incrément. La recette bancaire et les essais du connecteur doivent être demandés et réalisés séparément.
