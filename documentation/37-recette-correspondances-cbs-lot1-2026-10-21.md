# Recette du lot 1 — correspondances CBS

> Historique : ces résultats concernent la version antérieure à la précision du contrat CBS. Le rapport 38 décrit les correspondances actuelles, les 138 tests de cette version et la tentative réelle d'envoi.

Date : 21 octobre 2026. Projet local FinFlow, filiale FIL01.

## Conclusion

Le périmètre testé du lot 1 est fonctionnel après correction de deux régressions du générateur de message et d'un libellé ambigu dans le formulaire. La suite élargie termine à **140 tests réussis, 0 échec, 0 ignoré**, auxquels s'ajoutent **27 contrôles ciblés sur la base de développement avec annulation des écritures** et **7 routes HTTP locales en statut 200**.

Cette recette valide la séparation entre objet de financement, produit crédit, produit de remboursement, périodicité et amortissement, ainsi que les blocages avant transmission. Elle ne constitue pas une validation exhaustive du projet ni une certification d'acceptation d'un crédit par le CBS distant.

Le projet reste démarré : interface `http://127.0.0.1:5173/`, API `http://127.0.0.1:8000/`.

## Corrections découvertes pendant les tests

1. **Identification client en simulation** : le nouveau résolveur permettait de construire un message local sans code adhérent, compte ou numéro de pièce. Le générateur refuse désormais ce message avant toute journalisation de réussite.
2. **Champs de transmission en simulation** : un produit de remboursement vide était accepté. Les champs point de service, gestionnaire, produit crédit, produit remboursement, périodicité et devise sont maintenant exigés également dans le générateur local. Les contraintes supplémentaires du mode CBS réel restent appliquées.
3. **Libellé du mécanisme d'amortissement** : le formulaire affichait encore « Amortissement dégressif → COMPTE-COURANT ». Le suffixe historique a été supprimé pour éviter la confusion avec un produit de remboursement confirmé.

Les anciens tests qui supposaient une mise en place sans connecteur ou avec des codes libres ont été adaptés : connexion locale explicite pour les scénarios métier isolés ; références confirmées et revue/autorisation nominative pour le scénario REST. Les contrôles du code applicatif n'ont pas été contournés pour faire passer ces scénarios.

## Résultats automatisés

| Périmètre | Résultat | Preuve |
| --- | --- | --- |
| Suite élargie de 14 fichiers : catalogue, résolution, dossier, mise en place, import client, portefeuille, situation, synchronisation, TLS, gouvernance, services crédit, politique d'instruction et uploads | 140/140 | `uat-artifacts/point1-extended.xml`, `point1-extended.log` |
| Nouveaux tests persistants des garde-fous du lot 1, inclus dans les 140 | 17/17 | `backend/tests/test_cbs_mapping_safety.py` |
| Contrôles API sur FIL01, acteurs métier habituels et écritures annulées | 27/27 | `uat-artifacts/point1-checks.json` |
| API et serveur frontal après redémarrage du backend | 7/7 HTTP 200 | `uat-artifacts/point1-runtime.json` |
| Contrôle système Django | 0 erreur | `manage.py check` |
| Écart entre modèles et migrations | Aucun | `makemigrations --check --dry-run` |
| Migrations non appliquées | Aucune | `migrate --check` |
| Encodage, TypeScript et compilation Vite | Réussite | `uat-artifacts/point1-frontend-build.log` |

Les 63 tests initiaux de régression et les 17 nouveaux tests ont aussi été exécutés séparément ; ils sont déjà inclus dans les 140 et ne doivent pas être additionnés une seconde fois.

### Scénarios principaux couverts

- Égalité entre les valeurs présentées par le résolveur et le message construit pour le CBS.
- Objet exact prioritaire sur le type de besoin ; rejet d'une correspondance ancienne ambiguë.
- Objet exact obligatoire à la création d'un nouveau dossier en mode CBS réel.
- Produits crédit et remboursement distincts ; rejet d'une référence du mauvais type.
- Rejet des références inactives, non confirmées, sans auteur/date/justificatif, de mauvaise devise, d'une autre filiale ou d'un autre connecteur, et des codes de démonstration connus.
- Confirmation documentaire soumise aux permissions et à une vérification explicite du justificatif ; modification de la source annulant la confirmation.
- Anciennes valeurs libres insuffisantes pour autoriser la mise en place réelle.
- Modification du mapping invalidant l'autorisation déjà obtenue.
- Rejet d'un message altéré ou d'une clé d'idempotence différente du dossier autorisé.
- Blocage des créations depuis le diagnostic connecteur et des rejeux génériques de création de crédit.
- Parcours REST positif avec réponse HTTP simulée, traitement des références retournées et journalisation.
- Refus CBS simulé conservant le journal, le message envoyé et le nombre de tentatives.
- Contrôles de revue finale, séparation des acteurs, idempotence de la mise en place et callbacks existants.

## Vérification directe dans le navigateur

Navigateur intégré accessible, session Admin Filiale01. Aucun enregistrement effectué depuis les formulaires inspectés.

| Écran | Constat |
| --- | --- |
| Référentiels CBS → Produits CBS | Onglet accessible, nature crédit/remboursement, connecteur, devise, source documentaire et statut à confirmer présents ; aucun produit fictif préchargé comme confirmé. |
| Produits de crédit → CONSO-STD | Deux listes distinctes de références confirmées ; les anciennes valeurs CRED-CONSO et COMPTE-COURANT sont clairement signalées comme non confirmées. |
| Nouveau dossier | 83 options CBS, 83 valeurs distinctes, champ objet exact obligatoire dans le DOM ; sélection de l'objet 45 opérationnelle ; type de besoin et amortissement conservés séparément. |
| Dossier CR-2026-00002 / AG0100053 | Page rendue, objet consommation 45 visible, produits crédit et remboursement « Correspondance à confirmer », motifs de blocage et contrôle à renouveler affichés. |
| Console du navigateur | Aucune entrée de niveau erreur capturée pendant cette navigation. |

Captures : `uat-artifacts/point1-form-browser.png` et `uat-artifacts/point1-dossier-browser.png`.

## État des données et absence de transmission distante

Les tests ne soumettent aucun nouveau crédit au CBS distant. Les échanges REST positifs/négatifs de la suite sont simulés. Les 27 contrôles locaux bloquent les méthodes HTTP CBS et annulent les écritures de leurs scénarios positifs.

Contrôle final de CR-2026-00002 :

- statut `DISBURSEMENT_PENDING` ;
- aucun prêt créé ;
- aucun journal `SUBMIT_CREDIT` pour sa clé d'idempotence ;
- aucune référence temporaire `UAT-CHECK-*` conservée ;
- aucun produit CBS documenté dans FIL01 à ce stade.

Preuve : `uat-artifacts/point1-final-state.json`.

## Limites et suite UAT

**La création distante reste à valider.** Il faut obtenir les véritables identifiants `idProduitCrd` et `idProduitRemb`, leur justificatif CBS, les enregistrer et les confirmer dans le référentiel, puis les associer au produit local. L'objet 45 et la périodicité M ne prouvent pas ces identifiants produit. Une nouvelle revue et autorisation sont nécessaires avant transmission du dossier UAT.

La confirmation actuelle est documentaire : aucun endpoint de catalogue produit crédit/remboursement n'a été établi dans ce lot. Le contrôle de format et de cohérence local ne garantit donc pas que le CBS accepte l'identifiant saisi.

Les tests de concurrence utilisent SQLite ; ils vérifient le comportement fonctionnel et l'idempotence, sans prouver le comportement des verrous sous charge PostgreSQL. Une recette de concurrence sur la base cible reste utile avant mise en production.

Améliorations secondaires observées : messages de blocage parfois répétés et préfixes techniques dans le panneau de contrôle ; bundle frontal principal d'environ 1,72 Mo avant compression ; avertissements de dépréciation Django/DRF et de type Decimal. Ils n'empêchent pas les tests de passer, mais méritent un traitement avant une recette globale.

## Reproduction de la suite élargie

Depuis `backend`, avec le Python de l'environnement `.venv` :

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_cbs_catalog_referentials.py tests/test_cbs_crd_situation.py tests/test_cbs_disbursement.py tests/test_cbs_dossier_process.py tests/test_cbs_mapping_advanced.py tests/test_cbs_mapping_safety.py tests/test_cbs_portfolio_import.py tests/test_cbs_ref_sync.py tests/test_cbs_ssl_verify.py tests/test_client_cbs_import.py tests/test_credit_governance.py tests/test_credit_services.py tests/test_instruction_policy.py tests/test_p1_uploads_disburse.py --tb=short --durations=5 --junitxml=../uat-artifacts/point1-extended.xml
```

Dernière exécution complète : **140 réussites en 90,74 secondes**. Les artefacts de recette sont locaux et ignorés par Git.
