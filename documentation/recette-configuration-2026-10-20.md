# Clôture du lot de configuration — 20 octobre 2026

## Livraison intégrée

| Domaine | Résultat |
|---|---|
| Recette des quatre premiers incréments | Publications, isolation, captures, éligibilité, scoring, tarifs, calendriers et comités vérifiés ; anciennes recettes adaptées aux contrôles finaux obligatoires |
| Habilitations | Fonctions métier explicites, noms de rôles libres, profils standards identifiés par code stable, séparation des tâches et audit ; contrôle final réservé à la fonction administration crédit avec sa permission d'action |
| Gouvernance | Socle Groupe et adaptations filiale versionnés, verrous Groupe, aperçu, origines et publication indépendante ; anciennes écritures directes politique/seuils fermées dans l'API et l'administration Django |
| Formulaires et KYC | Champs additionnels typés et persistés, ordre des sections, masquage limité aux sections facultatives, exigences KYC par contexte et saisie en contexte dossier conservé |
| Référentiels clients | Civilité, situation matrimoniale, types de pièces et formes juridiques extensibles, désactivation sans effacement des anciennes valeurs, correspondances CBS explicites disponibles selon le contrat d'import existant |
| Engagements | Situations externes documentées, vérification indépendante, groupes économiques liés, plafonds, fraîcheur, absence de conversion implicite, contrôle des doubles comptes et restitution respectant le périmètre |
| Simulation | Bases de jours, arrondis et calendriers conservés ; même moteur pour simulation, analyse et prêt local ; calcul préalable avant appel CBS et restitution des conventions dans le PDF |

Les composants et styles existants sont conservés. Le fichier CSS produit garde l'empreinte `index-ClCWBHFr.css`.

## Contrôles finaux

- **664 tests réussis, aucun échec**, avec la chaîne réelle des migrations sur la base de test ; durée 380,97 secondes.
- 27 avertissements techniques signalés par la suite : dépréciations DRF/Django, bornes Decimal, pagination non ordonnée et résultats Celery en mode test. Ils ne sont pas assimilés à des échecs ni à une validation de production.
- Rapport : `backend/test-delivery-final.log` ; résultats structurés : `backend/test-delivery-final-results.xml`.
- Build frontend réussi : 2 241 modules ; avertissement de taille du bundle conservé.
- Django : aucun problème détecté ; `makemigrations --check --dry-run` : aucun changement manquant.
- Ruff : contrôles d'erreurs bloquantes et imports des modules concernés conformes. Une importation inutilisée préexistante dans l'ancienne migration crédits0017 est exclue du périmètre des migrations historiques.
- Audit en lecture seule de la base locale : `issues: []`, rapport `backend/business-configuration-audit-final.json`.
- Vérifications HTTP locales : interface 200 ; API des dossiers sans authentification 401.

Les tests couvrent notamment les permissions seules insuffisantes pour la revue crédit, les affectations hors filiale, les justificatifs réaffectés, les situations révoquées, les crédits mis en place après une situation externe, les fréquences conservées, les erreurs de calcul avant CBS et l'absence de confirmation CBS. Aucun CBS réel n'a été appelé par la recette.

## Mise à disposition locale

La base a été sauvegardée dans `backend/db.pre-delivery-20261020.sqlite3`. Les migrations comptes0010/0011, clients0012, configuration0003 et crédits0036/0037 sont appliquées. Les profils métier existants n'ont pas été publiés automatiquement.

- Interface : `http://127.0.0.1:5173`.
- API : `http://127.0.0.1:8000`.
- Serveur Django redémarré ; journaux `backend/local-configuration-delivery-django.log` et `backend/local-configuration-delivery-django-error.log`.

Le connecteur local FIL01 est en mode **LOCAL / simulation** pour la recette. En production, la simulation est désactivée par défaut : une mise en place exige le connecteur REST réel et sa réponse positive. Le paramètre `skip_cbs` est refusé, y compris pour un superutilisateur. Le contrôle final et l'autorisation de l'administrateur crédit restent obligatoires, avec exécutant configurable. Le versement effectif des fonds appartient au CBS.

## Dépendances et périmètre restant

Le lot en cours est clos. Les sujets suivants restent à développer dans les lots suivants, qui n'ont pas été déclenchés après la demande de clôture :

1. Circuits avancés : publication indépendante des définitions, priorités, suspensions et escalades, sièges et votes individuels authentifiés.
2. Garanties, contrats et GED : extension de la gouvernance de publication et des règles de valorisation, assurance, formalisation et conservation.
3. Recouvrement, notifications, reporting et préférences : extension et harmonisation des réglages existants et de leurs consommateurs.
4. Compléments spécialisés : autres référentiels métier, remises nominatives, financement des frais et différés avec capitalisation.

L'alimentation automatique d'engagements consolidés et la transmission détaillée des frais, taxes, épargne et conventions nécessitent des spécifications CBS validées. Aucun champ d'API externe n'est inventé. Le calcul d'un coût réglementaire complet nécessite également des règles et données validées ; les résultats ne sont pas présentés comme un TEG/TAEG réglementaire.

Cette recette automatisée et la compilation ne constituent pas une homologation bancaire, une recette visuelle exhaustive ou une validation de concurrence sur PostgreSQL. L'établissement doit valider ses règles internes et leur concordance avec le CBS.
