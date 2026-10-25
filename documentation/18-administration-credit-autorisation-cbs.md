# Administration crédit et autorisation de mise en place

## Parcours

1. Le circuit de crédit rend sa décision d'approbation.
2. L'administrateur crédit contrôle le dossier approuvé : KYC, apport, sûretés,
   formalités, contrats et signatures selon la politique, assurance et réserves.
3. Il enregistre son contrôle documenté, puis clique explicitement sur
   **Autoriser la mise en place**.
4. Le dossier passe en **Transmission au CBS en attente**.
5. Le service choisi dans la configuration transmet le dossier au CBS.
6. Le retour positif confirme la mise en place. Le versement des fonds reste
   réalisé dans le CBS.

L'autorisation préalable est obligatoire. Le champ historique
`require_final_review` est conservé en lecture seule avec la valeur vraie.
Les exigences de contrats, signatures, pièces, formalisation et délais restent
paramétrables. Une autorisation ne permet pas de contourner une réserve.

## Habilitations

Le nouveau rôle métier **Administrateur crédit** est distinct de
l'Administrateur filiale et dispose de la lecture métier et des droits
documentaires nécessaires. Les permissions restent attribuables dans les rôles.

| Permission | Action |
|---|---|
| `credits.review_setup_creditapplication` | Contrôler et demander des compléments |
| `credits.authorize_setup_creditapplication` | Autoriser ou retirer l'autorisation |
| `credits.disburse_creditapplication` | Droit commun de transmission conservé pour compatibilité |
| `credits.execute_setup_creditadmin` | Transmettre au titre de l'administration crédit |
| `credits.execute_setup_operations` | Transmettre au titre des opérations |

Les opérations ne reçoivent pas les droits de contrôle ou d'autorisation dans
leur pack par défaut. L'administrateur filiale conserve son pack complet et le
superutilisateur sa supervision technique ; ils doivent également enregistrer
le contrôle et l'autorisation avant une nouvelle transmission.

## Configuration

Dans **Administration → Politique crédit → Décision et mise en place CBS** :

- **Responsable de la transmission au CBS** : Opérations (par défaut) ou
  Administrateur crédit.
- **Exécutant différent de l'auteur de l'autorisation** : en mode Administration
  crédit, son activation impose deux personnes habilitées distinctes.
- La contrainte historique d'un exécutant différent du demandeur reste
  distincte. L'autorisation crée normalement la demande nominative : pour
  autoriser et transmettre soi-même, les deux contraintes doivent être désactivées.

L'exigence historique d'une demande préalable est satisfaite par la demande
nominative créée lors de l'autorisation. Les configurations restent propres
à chaque établissement.

## Compléments et traçabilité

**Demander des compléments** conserve l'accord, inscrit le motif et invalide le
contrôle ainsi que l'autorisation. Un nouveau contrôle puis une nouvelle
autorisation sont nécessaires. **Retirer l'autorisation** conserve son motif,
son auteur et sa date. Une mise en place déjà confirmée ne peut être retirée ici.
Si les conditions approuvées doivent changer, le réexamen existant relance le
circuit ; une demande en attente doit d'abord être annulée.

L'autorisation conserve auteur, date, motif, contrôle utilisé, empreintes du
dossier et des preuves, politique et service exécutant. La transmission conserve
son exécutant et sa date. Ces événements apparaissent dans la chronologie.

Une modification du dossier, des preuves ou de la politique impose un nouveau
contrôle et une nouvelle autorisation. Le changement du service exécutant
invalide donc aussi une autorisation antérieure. Les contrôles sont rejoués
avant l'appel CBS et avant la confirmation locale. Un retour reçu pendant une
révocation reste dans le journal d'intégration et exige une régularisation.

## Déploiement et instance locale

Migrations : `credits/0034_alter_creditapplication_options_and_more.py` et
`accounts/0009_credit_setup_roles.py`. La seconde provisionne les permissions
et le rôle sur les établissements existants. Les anciens groupes habilités à
transmettre conservent cette capacité au titre des opérations.

Les dossiers déjà mis en place sont conservés. Les dossiers approuvés ou en
attente doivent recevoir le nouveau contrôle et l'autorisation : aucune
autorisation rétroactive n'est créée automatiquement.

Compte local ajouté : **`fil01_admin_credit`**, mot de passe initial
**`FinFlow2026!`**. **`fil01_operations`** transmet dans le mode par défaut.
Les mots de passe des comptes existants ne sont pas réinitialisés.

Le design et la feuille de style sont conservés. Les bilans de tests des
documents précédents décrivent l'état antérieur à cette évolution du parcours.
