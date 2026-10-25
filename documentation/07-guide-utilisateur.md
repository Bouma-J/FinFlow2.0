# 07 — Guide utilisateur

Guide orienté **opérateurs** de la SPA (http://localhost:8080 en Docker Compose démo).

## 1. Connexion

1. Ouvrir l’application.
2. Saisir identifiant / mot de passe.
3. Si MFA activé : saisir le code de l’application d’authentification (Google Authenticator, etc.).
4. Utilisateur **Groupe** : choisir une **filiale** dans la barre supérieure avant de créer des objets.

## 2. Tableau de bord

- Vue **filiale** : encours d’instruction, portefeuille, clients, garanties, risque.
- Vue **Groupe** (admin Groupe) : consolidation multi-filiales ; filtres pays / zone / produit…
- Les indicateurs peuvent provenir d’un **snapshot** précalculé (rafraîchi régulièrement).

## 3. Clients

Menu **Clients** → Nouveau / Ouvrir.

- Choisir le type (particulier, professionnel, entreprise).
- Renseigner identité ou données société, contacts, KYC.
- Joindre les pièces (CNI, RCCM…) via la GED du dossier client.

## 4. Dossier de crédit

### Création
1. **Dossiers** → Nouveau dossier.
2. Sélectionner client, produit, agence.
3. Saisir montants, taux, durée, mécanisme, frais (+ frais additionnels).
4. Compléter le diagnostic / plan de financement selon le formulaire.
5. Enregistrer (statut **Brouillon**).

### Analyse
- Depuis le dossier : créer / éditer une **analyse financière**.
- Cocher **analyse de référence** (obligatoire pour soumettre).

### Garanties & cautions
- Ajouter les sûretés et/ou cautions liées au dossier.
- Vérifier les plafonds d’engagement caution.

### Soumission
- **Soumettre** lance le circuit d’approbation.
- En cas de retour : corriger puis resoumettre.

### Décision (validateur)
Menu **Tâches** / panneau de décision sur le dossier :
- Approuver / Retourner / Rejeter
- Motif de rejet si configuré
- Lever les conditions suspensives si présentes

### Contrats & mise en place
1. Générer les contrats (modèles admin).
2. Après approbation et conditions OK : **Mettre en place**.
3. Le capital du prêt = **montant accordé** ; les frais sont gérés par le CBS.

## 5. Garanties transverses

- Liste **Garanties** : consultation / mouvements.
- **Mains levées** : processus client + contrôle solde CBS.
- **Dations** : biens en paiement d’une créance (couverture contrôlée).

## 6. Recouvrement

Menu **Recouvrement** (`/recouvrement`) :
- liste filtrable (PAR, stade, mon portefeuille, recherche) ;
- fiche dossier : situation, échéancier, encaissement (répartition FIFO sur les échéances), actions de relance, promesses ;
- changement de stade (amiable → précontentieux → contentieux / clôturé).

Les retards PAR sont recalculés automatiquement (batch nocturne). Un encaissement soldant le prêt clôture le dossier et passe le prêt en **Soldé**.

## 7. Administration filiale (droits requis)

| Écran | Usage |
|-------|--------|
| Utilisateurs | Comptes, rôles, agences, périmètre. L’**admin Groupe** peut cocher « Administrateur filiale » : accès **admin + métier** (clients, dossiers, garanties…) **uniquement** sur la filiale sélectionnée. |
| Rôles | Permissions Django par rôle |
| Produits | Catalogue crédit |
| Circuits | Étapes, SLA, rôles validateurs |
| Connecteurs CBS | URL, protocole, auth, simulation, tests — voir [12 — Connexion au CBS](12-connexion-cbs.md) |
| Contrats (modèles) | Templates Word/Excel |
| Notifications | SMTP filiale, expéditeur, alertes circuit — voir [05 §6](05-configuration.md) |
| Agences | Structure organisationnelle |

## 8. Administration Groupe

- Création / paramétrage des **filiales**.
- Consolidation reporting.
- Supervision globale (`/metrics` côté API).

## 9. Bonnes pratiques utilisateur

- Toujours sélectionner la bonne filiale (Groupe).
- Ne pas partager les comptes ; activer le MFA sur les profils sensibles.
- Vérifier le **montant accordé** avant mise en place.
- Archiver / purger les documents lourds pour respecter le **quota GED**.
