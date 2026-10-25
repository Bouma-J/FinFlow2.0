# Centre de configuration métier — premier lot

> Mise à jour du 20 octobre 2026 : les extensions livrées sont décrites dans les documents 23 à 27. Les descriptions historiques du premier lot ci-dessous doivent être lues avec ces compléments, notamment pour les socles Groupe et le passage obligatoire des modifications de politique et de seuils par publication indépendante.

> Le deuxième lot étend ce socle avec l'éligibilité et le scoring. Voir [20 — Éligibilité et scoring configurables](20-eligibilite-et-scoring-configurables.md). Les limites décrites ci-dessous correspondent au premier lot.

## Périmètre livré

Ce lot installe le socle et un premier parcours de configuration des crédits. Il ne constitue pas l'achèvement des neuf lots du plan de développement.

L'écran **Administration → Catalogue → Centre de configuration** (`/admin/configuration`) permet de préparer, comparer, soumettre, publier, retirer et réviser des adaptations de la politique filiale.

Modules intégrés au nouveau moteur :

| Domaine | Paramètres | Consommateurs effectifs |
|---|---|---|
| Politique de crédit | Tous les réglages existants, sauf la suppression du contrôle final obligatoire | Création/modification de la demande, soumission, décisions, contrats, gouvernance et transmission CBS |
| Analyse financière | Seuils de ratios, stress, pondération des revenus, décotes | Calcul de l'analyse, restitution des métriques, couverture des garanties et contrôles de crédit |
| Exigences d'analyse | Champs et vérifications requis, tableaux détaillés, nombre minimal de mois de relevés | Formulaire d'analyse, checklist de préparation et contrôle serveur avant soumission |

Les modèles `CreditInstructionPolicy` et `AnalysisThreshold` restent les sources des valeurs de base de la filiale. Aucun seuil réglementaire nouveau n'est imposé par ce lot. Les profils d'exemple doivent être adaptés et validés par l'établissement.

## Catalogue et priorité

Les paramètres disposent d'un type, d'un libellé, de choix éventuels et de leur valeur par défaut issue du serveur. Les valeurs inconnues, nombres non finis, valeurs négatives, choix invalides et pourcentages hors limites sont refusés dans les adaptations.

Les profils sont limités à une filiale. Leur périmètre peut combiner produit, agence, type de client et profil particulier. Les références d'une autre filiale sont refusées.

Chaque profil ne définit que les valeurs à remplacer. L'ordre de composition est croissant :

1. Valeurs de la filiale.
2. Agence — poids 1.
3. Type de client — poids 2.
4. Profil salarié, indépendant ou mixte — poids 4.
5. Produit — poids 8.

Le score d'un périmètre est la somme de ses poids. Les profils de score supérieur remplacent les clés explicitement définies par les profils précédents. Ainsi, un profil produit prime sur un profil clientèle sans produit ; un profil produit + salarié est encore plus spécifique. L'aperçu présente l'ordre et l'origine de chaque valeur.

Deux séries publiées de même périmètre ne peuvent pas coexister. Un code identifie une série dont le périmètre reste stable ; un changement de périmètre nécessite un nouveau code. Les publications d'une filiale sont sérialisées sous verrou pour éviter une concurrence sur ces contrôles.

Les listes de champs et de tableaux remplacent la liste héritée lorsqu'elles sont explicitement définies. Une liste vide l'efface ; l'action « Hériter de la liste » supprime l'adaptation. Le minimum de relevés laissé vide est hérité.

Un champ numérique requis accepte zéro, qui est une valeur valide. Cette exigence ne prouve pas qu'un zéro provient d'une saisie explicite plutôt que du défaut du modèle. Une vérification booléenne requise doit être vraie. Les tableaux doivent contenir une ligne renseignée. Les exigences sont contrôlées à la soumission, pas à l'enregistrement d'une analyse en cours.

## Cycle de publication

`Brouillon → À valider → Publié → Retiré`

- Le motif est obligatoire avant soumission à validation.
- Seul un brouillon peut être modifié ; son horodatage est contrôlé pour éviter d'écraser une modification concurrente.
- Une version à valider peut être renvoyée en brouillon.
- Le publieur doit être habilité et distinct de l'auteur et du dernier rédacteur, y compris pour un superutilisateur.
- Une version publiée ne peut pas être réécrite via l'API. L'action « Créer une nouvelle version » prépare un nouveau brouillon.
- Une seule version peut être en rédaction ou en validation dans une série.
- Une publication peut être immédiate ou programmée. Les dates rétroactives sont refusées.
- Un retrait exige un motif. Retirer la version courante ne réactive pas silencieusement une version plus ancienne.
- Une version future retirée ne s'active pas ; si elle est la dernière version de la série, son retrait désactive cette série. Utiliser une nouvelle version pour rétablir explicitement un fonctionnement.
- Chaque création et transition est enregistrée dans la piste d'audit avec le contexte utilisateur.

La séparation des acteurs concerne les nouveaux profils versionnés. Les écrans historiques de politique et de seuils restent disponibles pour administrer le socle filiale selon leurs droits existants ; leur migration vers un cycle de publication identique reste un travail ultérieur.

## Conservation des règles et dossiers existants

Chaque nouvelle soumission conserve dans `configuration_snapshot` les valeurs de base et adaptations applicables, le contexte, les identifiants/versions des profils, les origines et une empreinte. La capture et le démarrage du circuit sont atomiques. Un refus de soumission ne laisse pas de capture persistée.

Les contrats, ratios et contrôles suivants utilisent ces règles conservées. Une nouvelle publication ne remplace pas automatiquement les exigences métier d'un dossier déjà soumis.

Trois paramètres d'organisation restent courants pour les dossiers déjà soumis :

- fonction exécutant la transmission au CBS ;
- séparation entre autorisateur et exécutant ;
- séparation entre demandeur et exécutant.

Un changement de ces valeurs rend nécessaire une revue et une autorisation cohérentes avec l'organisation courante. Les droits de l'utilisateur et les preuves sont toujours contrôlés au moment de l'action.

Les dossiers déjà soumis avant ce lot, sans capture, conservent le fonctionnement historique avec la politique filiale ; les nouveaux profils ne leur sont pas appliqués rétroactivement. Le réexamen d'un accord efface la capture et impose une nouvelle soumission avec les règles courantes. L'annulation d'une soumission vers le brouillon efface également la capture. Un retour pour correction conserve les règles tant que le contexte produit/agence/clientèle ne change pas ; un changement de contexte provoque une nouvelle résolution lors de la prochaine soumission.

Les brouillons non soumis utilisent les règles actives. Le formulaire indique les profils retenus et les exigences d'analyse. Un profil particulier peut être choisi pendant la préparation de l'analyse. Une fois soumis, ce profil ne peut être changé sans retour ou réexamen.

## Aperçu avant publication

La simulation d'un profil enregistré présente :

- sa correspondance avec le produit, l'agence et la clientèle simulés ;
- les valeurs avant et après application du candidat ;
- l'origine des valeurs résultantes ;
- le nombre de dossiers modifiables de même périmètre et celui des dossiers conservant une configuration.

Il s'agit d'une comparaison de règles et d'un comptage de périmètre, pas d'une réexécution de tous les dossiers ni d'une simulation de leurs décisions. Les règles de scoring, de calcul financier et de sélection des circuits restent celles de leurs moteurs existants.

## Droits

| Permission | Usage |
|---|---|
| `configuration.view_configurationprofile` | Liste, détail et catalogue |
| `configuration.add_configurationprofile` | Nouveau profil et nouvelle version |
| `configuration.change_configurationprofile` | Rédaction, soumission et retour en brouillon |
| `configuration.publish_configurationprofile` | Publication et retrait |
| `configuration.preview_configurationprofile` | Simulation |

Les administrateurs filiale existants reçoivent ces droits lors de la migration. Les autres rôles peuvent les recevoir explicitement depuis l'administration des rôles. Les utilisateurs métier habilités à consulter un dossier voient ses règles applicables dans son propre périmètre, sans droit d'administrer les profils.

## API

- `GET/POST /api/v1/configuration-profiles/`
- `GET/PATCH /api/v1/configuration-profiles/{id}/`
- `GET /api/v1/configuration-profiles/catalogue/`
- `POST /api/v1/configuration-profiles/{id}/submit/`
- `POST /api/v1/configuration-profiles/{id}/reopen/`
- `POST /api/v1/configuration-profiles/{id}/publish/`
- `POST /api/v1/configuration-profiles/{id}/retire/`
- `POST /api/v1/configuration-profiles/{id}/revise/`
- `POST /api/v1/configuration-profiles/{id}/preview/`
- `GET /api/v1/credit-applications/{id}/configuration/`
- `GET /api/v1/credit-applications/configuration-context/`

Un PATCH nécessite `expected_updated_at`, renvoyé par la lecture précédente. Le champ `configuration_snapshot` des dossiers est en lecture seule dans l'API.

## Exemples locaux

```powershell
..\.venv\Scripts\python.exe manage.py seed_configuration_presets --tenant FIL01
```

La commande prépare deux profils **en brouillon**. Elle n'écrase aucune série existante et ne publie rien :

- Salarié : analyse datée, salaire vérifié et au moins trois mois de relevés ;
- AGR : visite terrain, analyse datée, tableaux produits, stocks, dettes et trésorerie.

Le produit reste à sélectionner si l'établissement souhaite limiter l'exemple à une offre donnée. Les exigences de stock ou de dette doivent être adaptées à la nature réelle de l'activité. Ces exemples ne sont pas des normes UMOA.

## Suite du plan de développement

| Lot | Situation après cette livraison |
|---|---|
| 0 — Inventaire | Catalogue typé des premiers domaines et documentation des consommateurs ; inventaire exhaustif des autres domaines à poursuivre |
| 1 — Socle | Profils versionnés, héritage Groupe/filiales, verrous, publication indépendante, aperçu et conservation à la soumission livrés |
| 2 — Produits et droits | Produits, éligibilité, tarification, capacités indépendantes des libellés et référentiels clients extensibles livrés ; autres référentiels métier à étendre |
| 3 — Formulaires et analyse | Exigences financières, champs additionnels typés, ordre des sections et KYC par contexte livrés ; seules les sections facultatives peuvent être masquées |
| 4 — Scoring et simulateur | Grilles, seuils, données manquantes, devis et conventions de calcul partagées livrés ; calcul réglementaire complet du coût, remises nominatives et différés capitalisés restent à définir et implémenter |
| 5 — Circuits et comités | Modes explicites, majorités, abstentions, PV et calendriers ouvrés livrés dans l'incrément 3 ; escalades, sièges, votes individuels et gouvernance de publication à poursuivre |
| 6 à 8 | Engagements documentés et plafonds livrés ; alimentation CBS consolidée dépend d'une spécification externe. Extension aux garanties, contrats, GED, recouvrement, notifications, reporting et préférences à poursuivre |

Les validations de livraison réalisées sont consignées dans le compte rendu de cette intervention. La recette métier et les tests automatisés doivent faire l'objet d'une exécution explicitement demandée ; ils ne sont pas assimilés à une compilation ou à une migration réussie.
