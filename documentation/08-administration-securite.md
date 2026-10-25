# 08 — Administration et sécurité

## 1. Modèle de sécurité

| Couche | Mécanisme |
|--------|-----------|
| Authentification | JWT access + refresh |
| Session API | Stateless ; refresh rotaté et blacklisté |
| Autorisation | Permissions Django + rôles filiale |
| Isolation données | `tenant_id` + `data_scope` + agences |
| Abus | Throttles API + login |
| Traçabilité | Audit log + journaux notif / CBS |

## 2. RBAC

1. Créer un **rôle** filiale (ex. Chargé d'affaire).
2. Lui attribuer des **permissions** (codenames Django).
3. Affecter le rôle aux **utilisateurs**.
4. Régler `data_scope` et les agences.

Les API crédit / clients appliquent réellement ces permissions
(`HasModelPermission` + packs bootstrap). Sans le droit correspondant,
l’action est refusée (403), pas seulement masquée dans l’UI.

### Packs bootstrap (création de filiale)

À chaque création de filiale, **23 rôles** sont créés avec un pack adaptable
(modifiable ensuite dans Administration → Rôles & droits) :

| Rôle | Contenu typique |
|------|-----------------|
| **Administrateur filiale** | Pack complet (tous modules métier + paramétrage) : clients, dossiers, garanties, recouvrement, admin — **uniquement** sa filiale |
| **Chargé d'affaire** | Instruction : clients, dossiers (création / édition créateur), analyses, garanties, cautions, contrats générés — pas de mise en place |
| **Chef d'agence** | Même pack instruction (validation 1er niveau via groupe circuit) |
| **Analyste crédit et risque** | Analyses / visites / documents uniquement — **pas** de création ni d’édition des champs dossier |
| **Responsable crédit et risque** | Lecture large + contributions analyse — pas d’édition dossier ni paramétrage |
| **Responsable exploitation** | Lecture transverse activité |
| **Responsable retails** | Portefeuille retail (lecture + contributions limitées) |
| **Comité de crédit** | Lecture + contributions analyses/visites en circuit — pas de création de dossier |
| **Directeur Général** | Lecture quasi complète — **pas** de mise en place ni admin technique |
| **Lecteur** | Consultation seule (clients, dossiers, garanties, contrats, circuit, recouvrement) — **aucune** écriture ni décision |
| **Responsable des opérations** | Contrats générés, main levée / dation, **validation de la mise en place**, CBS |
| **Assistant des opérations** | Contrats générés + **initiation** de la mise en place (à valider par le responsable) |
| **Responsable Juridique** / **Assistant juridique** | Lecture transverse (exploitation + recouvrement) + contentieux / intervenants ; Resp. : main levée / dation ; Assist. : contentieux sans initiation ML/dation |
| **Responsable / Assistant recouvrement** | Module recouvrement + initiation dation (+ lecture clients / dossiers / circuit) |
| **Responsable administratif et financier** | Lecture transverse + pilotage encaissements / recouvrement financier + audit |
| **Chef comptable** | Lecture prêts / clients / CBS + gestion des remboursements (y compris suppression) |
| **Comptable** | Lecture prêts / clients + saisie / modification des remboursements |
| **Responsable / Assistant contrôle interne** | Lecture large + piste d'audit |
| **Responsable / Assistant Audit** | Piste d'audit + lecture métier pour investigations |

Les anciens rôles bootstrap **Analyste crédit** et **Responsable agence** sont
retirés (supprimés à la sync s'ils n'ont plus d'utilisateur).

#### Mise en place (séparation des pouvoirs)

1. L’**Assistant des opérations** initie (`credits.initiate_disburse_creditapplication`) → statut `DISBURSEMENT_PENDING`.
2. Le **Responsable des opérations** valide (`credits.disburse_creditapplication`) → prêt + échéancier.
3. Le responsable peut aussi mettre en place directement sans étape d’initiation.

Les ViewSets métier (`TenantScopedViewSet`) appliquent `HasModelPermission` par défaut.
Exceptions : décisions workflow (`decide` / levée de réserves) = groupes de circuit ;
admin Django = `/django-admin/`.

La validation d’étape reste basée sur le **groupe du circuit**
(`ApprovalStep.required_group`), en plus des droits Django de consultation.

Resynchroniser les packs sur les filiales existantes :

```bash
docker compose exec backend python manage.py sync_role_packs
```

### Administrateur filiale (provisionné par l'admin Groupe)

L’admin Groupe sélectionne une filiale puis, dans **Administration → Utilisateurs** :
- coche **Administrateur filiale**, ou
- appelle `POST /api/v1/users/provision-filiale-admin/`.

Effets :
- rattachement à la filiale (`data_scope = TENANT`) — **aucune** donnée des autres filiales ;
- `is_staff = True` (menus Administration) ;
- rôle **Administrateur filiale** : pack métier complet (clients, crédit, GED, workflow, CBS, garanties, recouvrement, etc.) **en plus** du paramétrage.

Permissions métier notables :
- `credits.disburse_creditapplication`
- `credits.initiate_disburse_creditapplication`
- `guarantees.initiate_dationrequest`
- `guarantees.initiate_guaranteereleaserequest`

Alignement des nouvelles actions recouvrement / ML :
- Stade, prochaine action, relance → `collections.change_collectioncase`
- Restructuration / radiation → `collections.add_loanrestructure` / `add_writeoff`
- Encaissement sur dossier → `collections.add_repayment`
- Dépôt acte signé (main levée) → initiateur **ou** validateur du circuit

Superutilisateur / staff : accès admin Django (`/django-admin/`).

## 3. MFA (TOTP)

Activation (utilisateur connecté) :
1. `POST /auth/mfa/setup/` → secret + URI `otpauth://`
2. Scanner dans une app MFA
3. `POST /auth/mfa/confirm/` avec un OTP valide

Désactivation : mot de passe + OTP (`/auth/mfa/disable/`).

En cas de perte du second facteur : intervention admin (vider `mfa_secret`, `mfa_enabled=False`) sous procédure contrôlée.

## 3 bis. Mots de passe

| Événement | Comportement |
|-----------|--------------|
| Création utilisateur (Groupe ou filiale) | Mot de passe **généré** + envoyé par e-mail ; `must_change_password=True` |
| Régénération admin | `POST /users/{id}/reset-password/` → nouveau MDP temporaire + e-mail |
| Première connexion / après reset | Redirection vers `/changer-mot-de-passe` |
| Changement volontaire | Menu utilisateur → **Mon profil** → formulaire ; ou `POST /users/me/change-password/` |

L’e-mail est **obligatoire** à la création.  
Configurer l’e-mail **par filiale** : Administration → **Alertes e-mail** (SMTP + expéditeur).  
Détail : [`05-configuration.md` §6](05-configuration.md).

## 4. Quotas GED

Sur chaque filiale :
- `ged_quota_bytes` (défaut 10 Go)
- `ged_used_bytes` (maintenu à l’upload / suppression)

Un upload qui dépasserait le quota est **refusé**.  
Augmenter le quota via API tenants / admin.

## 5. Audit

- Journalisation automatique des objets `TenantScopedModel`.
- Consultation : menu **Piste d’audit** / `GET /audit-logs/`.
- Rétention : `AUDIT_RETENTION_DAYS` (purge Celery nocturne).

## 6. Secrets et accès infra

- Ne pas exposer MinIO/Postgres sans authentification forte hors réseau de confiance.
- Rotation périodique : `DJANGO_SECRET_KEY`, mots de passe DB, clés S3, SMTP.
- Limiter CORS aux origines légitimes.
- Activer HTTPS de bout en bout en production.

## 7. Admin Django

URL : `/django-admin/`  
(les routes `/admin/*` sont réservées à l’administration FIN_FLOW dans la SPA)  
Utile pour : inspection modèles, correction ponctuelle, supervision snapshots reporting, connecteurs.

Accès réservé aux comptes `is_staff` / superuser.

## 8. Délégations

Permettent de transférer temporairement les pouvoirs d’un valideur à un collègue (congés, absence).  
Configurer via API `/delegations/` ou écran admin utilisateurs selon droits.
