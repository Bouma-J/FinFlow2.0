# Audit complet du parcours de crédit et de la cohérence des données

Date : 21 octobre 2026. Heures UTC. Filiale FIL01, CBS UAT `visiondaw.cagecfi.pro`.

## 1. Conclusion

**Un nouveau dossier a parcouru le circuit métier jusqu'à une création réelle acceptée dans le CBS.** Le montage, les calculs du scénario, les pièces, les deux décisions, le contrat, la revue, l'autorisation, la transmission et la création du prêt local fonctionnent pour ce scénario.

**Je ne recommande pas de clôturer l'UAT globale en l'état.** Deux défauts de normalisation CBS sont reproduits : l'encours du détail d'un prêt additionne plusieurs crédits du client, puis cet encours est présenté comme un impayé assorti d'un retard artificiel. La suite automatisée complète n'est pas verte : **692 tests réussis et 27 échecs sur 719**.

Les données de revenus, d'identité complémentaire et les pièces sont fictives et explicitement autorisées pour cette recette. Aucune appréciation de solvabilité du client réel n'est tirée de cet exercice. Le prêt UAT précédent reste enregistré : le client possède maintenant deux prêts de recette de 350 000 FCFA, soit 700 000 FCFA d'encours brut dans la réponse CBS.

## 2. Dossier effectivement créé

| Élément | Valeur |
| --- | --- |
| Code adhérent | AG0100057 |
| Client local réutilisé | PAR-2026-00003 |
| Nouveau dossier | **CR-2026-00004** |
| UUID du dossier et identifiant externe CBS | `04d3b21d-b6ad-42de-9d6d-fa2e9e0c12c3` |
| Prêt local | `53a30b53-9e42-469b-8519-8cccde3f29d8` |
| Statut dossier / prêt | DISBURSED / ACTIVE |
| Produit CBS / mécanisme CBS / objet CBS | **6 / 2 / 45** |
| Montant / taux annuel / durée | **350 000 FCFA / 14 % / 6 mois** |
| Demande CBS | **AG01DMD2022000U00062** |
| Numéro de prêt renvoyé par la consultation CBS | **AG01PRT2022000U00040** |
| Réponse de création | HTTP 200, `responseCode: 200`, `message: "Success !"` |
| Journal de transmission | `39e4b0a6-3fbf-4af2-ae9c-9c682887ebb8`, SUCCESS, **une seule tentative** |
| Statut de confirmation CBS conservé localement | SUBMITTED |

Le succès de création et la présence du prêt dans le CBS sont vérifiés. Le mouvement de fonds et la confirmation asynchrone finale ne sont pas démontrés par ces contrôles.

## 3. Méthode et périmètre

Le parcours utilise les API métier existantes, les comptes de rôles existants et leurs contrôles de permission. Aucun statut d'approbation n'est forcé, aucun prêt n'est créé directement en base et aucune réponse positive CBS n'est simulée dans la campagne réelle.

Les appels métier sont exécutés avec `APIClient` et authentification des acteurs de test. Une lecture HTTP avec un vrai JWT sur le serveur démarré et une vérification du dossier dans le navigateur complètent cette exécution ; il ne s'agit pas d'une saisie intégrale du parcours par clics dans chaque formulaire.

La transmission réelle comporte une seule création distante. Les requêtes CBS de la campagne et du rapprochement sont espacées de trois secondes après les réponses précédentes. TLS reste vérifié et les secrets sont masqués dans les preuves. Une interruption d'authentification du premier import des devises est conservée dans son rapport d'erreur ; seule cette consultation a été reprise ensuite.

### Étapes réellement exécutées

| Étape | Résultat observé |
| --- | --- |
| Import des référentiels CBS disponibles | Périodicités, objets, points de service, gestionnaires, sources et motifs récupérés ; devises récupérées après reprise |
| Nouvelle consultation de l'adhérent | HTTP 200, adhérent et compte AG0100057 confirmés |
| Essai d'import standard de cette fiche incomplète | HTTP 400 attendu ; les informations KYC absentes sont signalées |
| Consultation du prêt UAT déjà existant | Réussite ; dette existante intégrée au nouveau scénario |
| Création du nouveau dossier | HTTP 201, CR-2026-00004 |
| Soumission, autorisation et mise en place tentées prématurément | Trois HTTP 400 attendus ; aucune création CBS |
| Dépôt des sept pièces, visite simulée, analyse financière | Réussite |
| Soumission valide | Réussite |
| Analyse puis décision du chef | Deux décisions APPROVED par deux acteurs distincts |
| Génération du contrat et dépôt du PDF signé fictif | Réussite |
| Vérification des sept pièces GED | Réussite |
| Revue et autorisation par l'administration crédit | Réussite |
| Transmission par les opérations | Une création réelle, acceptée par le CBS |
| Prêt local et six échéances | Créés après le retour positif |
| Répétition de l'action locale de mise en place | Même prêt renvoyé, aucun appel distant supplémentaire |
| Consultation après création | Même demande CBS retrouvée ; anomalies de restitution décrites ci-dessous |
| Interface | Nouveau dossier et codes 6 / 2 / 45 visibles ; aucune erreur de console capturée |

La phase de montage comporte 37 appels métier : 33 réponses positives et quatre refus attendus, dont l'import KYC incomplet. Le rapprochement complémentaire comporte 33 appels métier, puis une relecture ciblée du comportement de l'en-tête de filiale.

## 4. Provenance des données et correspondances

### Référentiels effectivement relus ou importés

| Référentiel | Lignes reçues | Observation |
| --- | ---: | --- |
| Devises | 3 | Premier essai interrompu à l'authentification ; reprise réussie, trois lignes inchangées |
| Périodicités | 6 | Mensuelle associée à M et 12 périodes/an |
| Objets de financement | 83 | Objet exact 45 choisi sur le dossier |
| Points de service | 6 | Association de l'agence locale à AG01 |
| Gestionnaires | 4 | Soumissionnaire associé à AG011U1 |
| Sources de financement | 2 | Référentiel disponible ; aucune source inventée dans le message de création |
| Motifs de décision | 2 | Référentiel disponible |
| Professions | 0 | HTTP 200, code métier 200, `datas: null` ; disponibilité de données métier non démontrée |

Les lignes récupérées étaient inchangées par rapport aux imports précédents. Les produits crédit et mécanismes ne proviennent pas d'un nouveau catalogue distant : les codes 6 et 2 ont été fournis par l'utilisateur puis acceptés par deux créations réelles. Les variantes de chemins de catalogues testées précédemment renvoyaient 404. Cette distinction est conservée dans la provenance.

### Message de création transmis

| Champ CBS | Valeur | Source et contrôle |
| --- | --- | --- |
| `externalId` | UUID du nouveau dossier | Identifiant distinct du dossier précédent |
| `callbackUrl` | URL locale contenant cet UUID | Construction cohérente ; accessibilité distante non validée |
| `idProduitCrd` | `"6"` | Référence confirmée dans les paramètres du produit local |
| `idProduitRemb` | `"2"` | Code CBS du mécanisme local DEGRESSIVE |
| `idObjetFinancement` | `"45"` | Objet exact sélectionné, indépendant du produit crédit |
| `idPeriodicite` | `"M"` | Import CBS, fréquence mensuelle |
| `codeDevise` | `"FCFA"` | Correspondance de XOF ; aucune conversion de montant |
| `idPointService` | `"AG01"` | Agence du créateur et référentiel des points de service |
| `idGestionnaire` | `"AG011U1"` | Gestionnaire CBS du soumissionnaire |
| `codeAdherent` | `"AG0100057"` | Nouvelle consultation CBS et fiche locale existante |
| `taux` | `14.0` | Taux effectif conservé, identique au taux de calcul |
| `nombreEcheance` | `6` | Six mois et périodicité mensuelle |
| `montantDemande` | `350000.0` | Montant approuvé égal au capital du prêt |

Les identifiants de référentiels sont transmis en chaînes, les montants et le taux en nombres JSON, le nombre d'échéances en entier. Le CBS accepte ce message. Les identifiants alternatifs de client ne sont pas envoyés lorsque `codeAdherent` est disponible ; la pièce d'identité fictive reste locale.

La fiche CBS ne fournit toujours pas les noms séparés, la date de naissance, la pièce et ses dates, le téléphone, la ville et l'adresse nécessaires à l'import standard. **Neuf informations obligatoires manquent.** Le nouvel essai réutilise donc la fiche locale déjà complétée pour l'UAT, avec sa source CBS séparée. `limitCredit: null` reste une information indisponible ; ce n'est ni zéro ni un plafond illimité démontré.

## 5. Calculs et cohérence financière

### Montage et capacité

| Contrôle | Calcul indépendant | Résultat |
| --- | --- | ---: |
| Plan de financement | 450 000 - 100 000 | Crédit de 350 000 |
| Quotité financée | 350 000 / 450 000 × 100 | 77,78 % |
| Revenus mensuels fictifs | Salaire du scénario | 750 000 |
| Charges du ménage | 120 000 + 80 000 + 25 000 + 25 000 | 250 000 |
| Dette mensuelle déjà existante | Maximum de l'échéancier local du prêt UAT précédent | 60 760 |
| Capacité avant nouveau crédit | 750 000 - 250 000 - 60 760 | **439 240** |
| Maximum de la nouvelle échéance | Capital + intérêts, épargne nulle | **60 760** |
| Effort total de dette | 60 760 + 60 760 | **121 520** |
| Taux d'endettement | 121 520 / 750 000 × 100 | **16,20 %** |
| Reste à vivre après nouveau crédit | 750 000 - 250 000 - 121 520 | **378 480** |
| Endettement sous baisse de revenus de 20 % | 121 520 / 600 000 × 100 | **20,25 %** |

Les données saisies, les indicateurs persistés, le recalcul de l'analyse, la simulation par API et les six échéances du prêt concordent. Le calcul d'endettement retient l'échéance maximale, y compris le reliquat de la dernière ligne.

La dette mensuelle existante a été renseignée explicitement dans le scénario à partir du prêt local précédent. L'encours CBS seul ne fournit pas sa mensualité contractuelle : l'import automatique et exhaustif du service de dette CBS n'est pas validé.

### Échéancier local recalculé séparément

Convention courante de ce dossier : moteur LEGACY, intérêts ACT/365 avec convention de première période nominale, annuité de référence mensuelle, arrondi commercial à la dizaine de FCFA, reliquat du capital sur la dernière ligne.

| N° | Date | Capital | Intérêts | Total | Solde capital |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | 23/11/2026 | 56 580 | 4 160 | 60 740 | 293 420 |
| 2 | 23/12/2026 | 57 360 | 3 380 | 60 740 | 236 060 |
| 3 | 25/01/2027 | 57 930 | 2 810 | 60 740 | 178 130 |
| 4 | 23/02/2027 | 58 620 | 2 120 | 60 740 | 119 510 |
| 5 | 23/03/2027 | 59 460 | 1 280 | 60 740 | 60 050 |
| 6 | 23/04/2027 | 60 050 | 710 | 60 760 | 0 |
| **Total** | | **350 000** | **14 460** | **364 460** | **0** |

Chaque ligne est recalculée avec une implémentation de contrôle séparée et rapprochée de la persistance. Le total de chaque ligne est égal au capital plus les intérêts et l'épargne, ici nulle. L'empreinte de configuration est inchangée après la transmission et les consultations.

**Convention à valider métier :** l'intérêt de la première ligne porte sur 31 jours nominaux du 21 octobre au 21 novembre, même si la date de paiement est reportée au 23 novembre. Il vaut 4 160 FCFA selon ce moteur ; un calcul sur les 33 jours jusqu'au paiement donnerait environ 4 430 FCFA avec le même arrondi. Ce test confirme l'implémentation de la convention actuelle, pas son alignement sur l'échéancier contractuel CBS, qui n'est pas fourni par la réponse de situation.

### Frais et montant net

Le taux de frais et le taux d'épargne effectifs valent zéro dans le devis. Toutefois, le mode tarifaire LEGACY renvoie `fees.total: null` et `net_after_fees: null`, avec une liste de frais vide. Le total de **364 460 FCFA** ci-dessus est donc le remboursement local du capital et des intérêts ; il ne certifie pas un coût complet intégrant des prélèvements CBS, taxes ou assurances qui n'ont pas été reçus. Un montant net de déblocage et un coût global exhaustif restent à rapprocher.

## 6. Pièces, contrats, décisions et accès

- Sept nouvelles pièces fictives sont rattachées au nouveau dossier ; leurs fichiers sont lisibles, leur taille et leur SHA-256 correspondent à la GED, et leur statut est VERIFIED.
- Le PDF signé fictif est rattaché au contrat généré pour le nouveau dossier. Les huit PDF de recette ont été rendus et inspectés visuellement.
- Le DOCX généré contient CR-2026-00004, AG0100057, 350 000 XOF, six mois et le taux de 14 %, sans variable de modèle résiduelle. Son rendu visuel reste **non vérifié** : le renderer de la compétence Documents échoue parce que `LibreOffice soffice.exe` est absent. Le journal est conservé.
- Deux décisions d'approbation proviennent de deux acteurs distincts. La revue et l'autorisation sont documentées ; l'exécutant opérations est différent de l'administration crédit.
- Les API protégées du dossier et des téléchargements GED refusent les accès anonymes avec HTTP 401.
- Pour un utilisateur de filiale, un en-tête demandant une autre filiale est ignoré au profit de sa filiale propre. L'attente initiale du script d'un refus HTTP systématique était incorrecte ; la relecture confirme que seul son propre dossier est renvoyé. Il n'existe pas de seconde filiale dans cette base de recette pour un essai manuel croisé réel ; les tests automatisés utilisent des filiales isolées.
- Les fichiers locaux sont exposés sous `/media/` en mode DEBUG selon la configuration du projet. L'accès anonyme aux API GED est contrôlé ; cela ne constitue pas une certification du stockage et de la distribution des fichiers dans un déploiement de production.

## 7. Anomalies confirmées et corrections prioritaires

### P1 — Encours de plusieurs prêts présenté dans le détail d'un seul dossier

La consultation demandée pour AG01DMD2022000U00062 contient deux lignes de prêts du client. La ligne identifiée par `numeroDemande` pour le nouveau prêt porte `montantPret: 350000` et `encours: 350000`.

La normalisation retourne pourtant `outstanding: "700000.0"` tout en affichant les références du nouveau dossier. Le total portefeuille de 700 000 est correct pour les deux prêts UAT ; son attribution au seul nouveau prêt est incorrecte.

**Correction proposée :** sélectionner les lignes par les références de demande ou de prêt avant la normalisation du détail. Conserver un résultat portefeuille distinct. Si aucune correspondance unique n'est trouvée, signaler l'ambiguïté au lieu de sommer silencieusement tous les prêts. Ajouter un test à deux prêts avec références et montants différents.

Code concerné : `backend/apps/corebanking/services.py`, `_crd_situation`, `_normalize_credit_schedule`, `get_loan_status`.

### P1 — Encours transformé en impayé et retard artificiel

| Champ | Ligne brute CBS du nouveau prêt | Résultat normalisé actuel |
| --- | ---: | ---: |
| Encours | 350 000 | 700 000 |
| Impayé | **0** | **700 000** |
| Intérêts impayés / pénalités | 0 / 0 | Pas de rapprochement dédié |
| Jours de retard | **0** | **1** |

`compute_cbs_overdue` retombe sur l'encours et un jour de retard lorsqu'aucune échéance échue n'est identifiée. Une ligne de situation d'un prêt n'est pas une échéance impayée.

**Correction proposée :** reconnaître explicitement le format situation des prêts Vision ; préserver les valeurs zéro de `impaye` et `nbreJrsRetard`, distinguer dette non soldée et dette en retard, et ne pas fabriquer de retard lorsque les dates ou l'échéancier sont absents. Tester les cas encours positif sans retard, vrai impayé, crédit soldé, calendrier futur et réponse partielle. Vérifier ensuite les consommateurs de ces indicateurs avant d'utiliser cette normalisation pour un classement de risque ou du recouvrement.

### Autres points à traiter avant clôture UAT

| Priorité | Constat | Action proposée et critère de recette |
| --- | --- | --- |
| P1 | 27 échecs sur la suite complète | Revoir les contrats de permissions et les prérequis de fixtures ; obtenir une suite complète verte sans retirer les contrôles de sécurité |
| P1 | Consolidation des engagements désactivée dans la politique conservée | Activer le contrôle retenu métier, définir les sources et plafonds, rapprocher capital restant dû et service de dette sans double comptage |
| P1 | Callback envoyé vers localhost ; statut CBS local SUBMITTED | Exposer un callback UAT joignable et authentifié ; vérifier confirmation, doublon de callback et ordre des événements ; rapprocher le mouvement effectif |
| P2 | CBS daté du 29/09/2022 contre calendrier local 2026-2027 | Aligner la date de travail de recette et définir la date d'effet de référence |
| P2 | Pas d'échéancier CBS détaillé dans `crd/situation` | Obtenir le tableau distant et comparer dates, capital, intérêts, arrondis, frais et solde final |
| P2 | Import standard impossible avec la fiche CBS incomplète | Prévoir un enrichissement local audité qui conserve la source CBS et exige les validations KYC nécessaires |
| P2 | Pas de catalogue crédit/mécanisme récupéré | Obtenir les endpoints documentés ou une source officielle de correspondances ; garder la provenance et la vérification par connecteur |
| P2 | Frais et net de déblocage absents du devis LEGACY | Définir zéro explicite contre information inconnue ; rapprocher les frais effectivement appliqués dans le CBS |
| P2 | Authentification intermittente et import partiel exposé sous HTTP 200 | Restituer clairement le bilan par référentiel et permettre la reprise ciblée des seules lectures échouées |
| P2 | `/ref/profession-list` renvoie `datas: null` | Clarifier si le catalogue est volontairement vide et ce que devient un métier requis dans le KYC |
| P2 | Contrôle visuel DOCX incomplet | Fournir le renderer LibreOffice et vérifier le contrat rendu avant validation documentaire UAT |
| P3 | Bundle interface principal de 1,72 Mo | Fractionner les pages et dépendances lourdes ; mesurer le chargement sur le poste et le réseau de recette |

### Politique actuelle : contrôles réalisés et obligations réellement imposées

Les garanties couvrent 0 % contre un seuil affiché de 100 %. Le dossier passe parce que `collateral_coverage_mode` vaut ALERT. L'analyse recommande favorablement le scénario fictif ; son score de 85/100 n'est pas une mesure validée sur le client réel.

Dans la configuration conservée, la signature du contrat de crédit, la vérification des documents, la visite, la demande préalable et certaines séparations d'acteurs ne sont pas toutes obligatoires. Ces étapes ont été réalisées dans ce test, mais leur réalisation volontaire ne prouve pas qu'un dossier incomplet serait bloqué sur chacune d'elles. Faire valider et publier une politique UAT explicite : garanties ou dérogations motivées, contrat signé, pièces vérifiées, séparation des rôles, ancienneté d'analyse et contrôle des engagements selon les exigences retenues.

## 8. Résultats automatisés et techniques

| Vérification | Résultat |
| --- | --- |
| Contrôles ciblés de la campagne | **100 réussites** : 32 avant transmission, 68 après transmission et rapprochements locaux |
| Anomalies de normalisation constatées | **Deux**, conservées séparément des contrôles positifs ; elles ne sont pas couvertes par une affirmation de réussite générale |
| Suite backend complète | **692 réussites, 27 échecs, 719 tests**, 324,85 secondes |
| Groupe d'échecs 1 | **19** refus de permissions ou différences de contrat HTTP |
| Groupe d'échecs 2 | **8** scénarios bloqués par l'absence de prérequis CBS dans leurs fixtures |
| Build frontend | Réussite ; 124 fichiers contrôlés sans anomalie UTF-8 ; avertissement de taille du bundle |
| `manage.py check` | Aucune anomalie |
| `makemigrations --check --dry-run` | Aucun changement détecté |
| Serveurs réellement interrogés | Interface 5173, health API 8000 et lecture authentifiée JWT du dossier : HTTP 200 |
| Navigateur | CR-2026-00004, 350 000 XOF, six mois, références CBS et codes 6/2 visibles ; aucune erreur de console capturée |

Les 19 échecs de permissions doivent être arbitrés : plusieurs tests donnent les permissions de modèles de configuration sans la capacité d'administrateur exigée par le code actuel. Les huit autres scénarios n'atteignent pas la garde métier qu'ils veulent contrôler, car ils sont bloqués plus tôt par les correspondances CBS manquantes. Ces observations expliquent les échecs ; elles ne les annulent pas et ne prouvent pas à elles seules que tous relèvent uniquement des tests. Les scénarios doivent être remis en conformité avec le contrat métier décidé, puis réexécutés.

Les 100 contrôles ciblés ne remplacent ni les 719 tests ni les corrections des deux anomalies confirmées. L'assertion initiale incorrecte du script sur le choix de filiale est conservée dans les preuves, avec sa relecture et sa correction sémantique. Aucun contrôle métier du produit n'a été assoupli pour obtenir ce résultat.

## 9. Avis UAT et prochaines étapes

**Le parcours positif de création est démontré pour ce scénario et cette combinaison de paramètres. La cohérence de l'analyse et de l'échéancier local est démontrée. La restitution du risque CBS ne l'est pas.**

Ordre recommandé :

1. Corriger la sélection du prêt et la normalisation encours/impayés ; figer les deux réponses brutes comme cas de test.
2. Corriger ou réconcilier les 27 tests, puis relancer la suite complète.
3. Valider la politique UAT et activer les obligations de preuves et d'engagements attendues.
4. Terminer la confirmation CBS, le callback, les dates de travail et le rapprochement d'échéancier et de frais.
5. Étendre la matrice UAT aux scénarios de rejet, dépassement de plafond, autre agence, autre filiale, autre produit, crédit irrégulier, garanties et cautions, signature manquante, réponse CBS ambiguë, panne après acceptation distante, concurrence et retour asynchrone reçu plusieurs fois. Une partie est couverte par les tests isolés ; tous ne sont pas validés en conditions CBS réelles par ce parcours positif.

Cette campagne ajoute un dossier et ses pièces de recette. Les corrections proposées ci-dessus ne sont pas appliquées au code de production dans ce lot d'audit. Les serveurs restent démarrés.

## 10. Preuves conservées

Répertoire de campagne : `uat-artifacts/pipeline-complet-20261021T133600Z/`.

| Fichiers | Contenu |
| --- | --- |
| `campaign-final.json` | Bilan final, 100 contrôles, limites et anomalies |
| `scenario.json`, `existing-obligations.json` | Données fictives et dette déjà existante |
| `referentials-import.json`, `referentials-retry.json`, `fresh-client-preview.json` | Imports, reprise et informations manquantes côté CBS |
| `execution-state.json`, `local-*.json`, `journey-cbs-*.json` | Circuit complet et réponses brutes de la première phase |
| `field-lineage.json`, `mapping.json`, `setup-payload-preview.json` | Provenance champ par champ et correspondances |
| `prepared-schedule.json`, `independent-schedule.json`, `simulation-api.json`, `metrics.json`, `pricing.json`, `calculation-summary.json` | Calculs, arrondis et rapprochements |
| `workflow-decisions.json`, `contract-verification.json`, `ged-verification.json`, `dossier-files.json` | Acteurs, contrat, fichiers et empreintes |
| `final-transmission-log.json`, `post-remote-calls.json`, `new-loan-situation.json`, `cbs-reconciliation.json`, `findings.json` | Création acceptée et deux défauts reproduits |
| `post-local-steps.json`, `tenant-header-recheck.json`, `running-servers.json` | Idempotence, droits et contrôle du serveur |
| `files/preview/`, `docx-render.log`, `dossier-final.png`, `browser-final.txt` | Rendus PDF, limite DOCX et preuve de l'interface |
| `regression-summary.json` | Noms et motifs des 27 échecs |

Fichiers de la suite complète : `uat-artifacts/pipeline-complete-regression-20261021.xml`, `.log` et `pipeline-complete-regression-failures.json`. Build : `uat-artifacts/pipeline-complete-frontend-build-20261021.log`. Les fichiers de recette contiennent des données de client et restent dans les preuves locales.
