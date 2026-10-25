# 14 — Backlog d’étude FinFlow

Document de cadrage. **Aucune implémentation.** Perfect reste maître des encaissements : FinFlow ne devient pas un second core banking.

Chaque fiche tient en une page : problème, état actuel, utilisateurs, dépendance CBS, livrable d’étude, hors scope.

| Vague | Id | Sujet | Effort étude | CBS |
|-------|----|--------|--------------|-----|
| Complet | E01 | Hub Après-vente visible | 1 atelier | Aucune |
| Complet | E02 | SLA visibles côté métier | 1–2 ateliers | Aucune |
| Complet | E03 | Miroir encaissements CBS + fiche prêt | 2–3 ateliers | Lecture |
| Complet | E04 | Centrale des risques (BIC) | 2 ateliers | Aucune |
| Complet | E05 | Co-emprunteurs | 2–3 ateliers | À trancher |
| Complet | E06 | Conditions suspensives qui bloquent | 2 ateliers | Aucune |
| Complet | E07 | Second regard pertes / restructuration | 2 ateliers | À trancher |
| Complet | E08 | Escalade : règles vs tranches | 1 atelier | Aucune |
| Ambitieux | E09 | Scorecard administrable + STP | 3–4 ateliers | Aucune |
| Ambitieux | E10 | Notifications client + portail | 3–4 ateliers | Lecture |
| Ambitieux | E11 | Mise en place par tranches | 3 ateliers | Structurante |
| Ambitieux | E12 | Pont comptable + provisions | 4 ateliers | À trancher |

**Ordre d’ateliers recommandé :** E08 et E01 → E02, E03, E06 → E04, E07 → E05 / E11 (après point Perfect) → E09, E10 → E12.

---

## Vague 1 — Complet

Rend l’usine de crédit utilisable au quotidien, sans changer la philosophie CBS.

### E01 — Hub Après-vente visible

**Problème.** Le hub `/apres-vente` existe déjà mais n’est pas dans le menu. L’après-vente reste trois écrans séparés (formalisations, dations, mains levées).

**Aujourd’hui.** `AfterSalesHubPage`, permission `PERM_AFTER_SALES`, aucun lien de navigation.

**Utilisateurs.** Chef d’agence, recouvrement, formalisation, admin filiale.

**Dépendance CBS.** Aucune. Agrégation FinFlow uniquement.

**Livrable d’étude.** Décider l’entrée de menu (un item Après-vente vs les trois liens) et les tuiles à garder.

**Hors scope.** Nouveau métier, SMS, portail client.

**Dépendances.** Aucune.

---

### E02 — SLA visibles côté métier

**Problème.** Les SLA sont paramétrés dans les circuits mais le comité et le chef d’agence ne voient pas l’échéance.

**Aujourd’hui.** `sla_hours` sur les étapes ; `my_task_due_at` sert surtout au style « en retard », sans date affichée.

**Utilisateurs.** Comité, chef d’agence, valideurs.

**Dépendance CBS.** Aucune. Horloge interne FinFlow.

**Livrable d’étude.** Où afficher (cartes Mes validations, timeline dossier, dashboard) et qui est alerté.

**Hors scope.** Moteur SLA générique hors circuits crédit / main levée / dation / formalisation.

**Dépendances.** E01 si le hub affiche aussi les retards.

---

### E03 — Miroir encaissements CBS + fiche prêt

**Problème.** FinFlow refuse à juste titre de saisir un paiement, mais n’offre pas une lecture fiable des encaissements ni une fiche prêt complète. Les rôles Comptable ont des droits qui ne servent à rien.

**Aujourd’hui.** `POST /repayments/` refusé ; prêts en liste ; échéancier local figé à la mise en place ; impayés rafraîchis depuis le CBS.

**Utilisateurs.** Comptable, chargé d’affaires, chef d’agence, recouvrement.

**Dépendance CBS.** Lecture. Flux situation / historique Perfect, **sans jamais écrire un encaissement**.

**Livrable d’étude.** Champs Perfect à afficher, fréquence de sync, comment montrer l’écart échéancier FinFlow vs CBS.

**Hors scope.** Saisie d’encaissement, caisse, mobile money, grand livre.

**Dépendances.** Connecteur REST Perfect déjà partiel.

---

### E04 — Centrale des risques (BIC)

**Problème.** La consultation bureau est une case à cocher. Pas de preuve, pas d’API, pas d’historique.

**Aujourd’hui.** `credit_bureau_checked` / `credit_bureau_date` sur l’analyse financière.

**Utilisateurs.** Chargé d’affaires, analyste, comité, audit interne.

**Dépendance CBS.** Aucune. Intégration BIC / prestataire à part.

**Livrable d’étude.** Phase 1 manuelle (pièce GED + date + avis) vs phase 2 API. Seuil de montant qui impose la consultation.

**Hors scope.** Score alternatif (telco, mobile money).

**Dépendances.** Peut devenir une condition suspensive (E06).

---

### E05 — Co-emprunteurs

**Problème.** Un dossier n’a qu’un client. Conjoint, associé ou co-titulaire n’ont pas de rôle juridique au contrat.

**Aujourd’hui.** Client unique ; conjoint dans l’analyse ; cautions = garant, pas co-débiteur.

**Utilisateurs.** Chargé d’affaires, formalisation, contentieux.

**Dépendance CBS.** À trancher. Perfect accepte-t-il plusieurs adhérents / un co-titulaire sur `crd/simple` ?

**Livrable d’étude.** Modèle `ApplicationParty` (emprunteur / co-emprunteur) et impact contrat + mise en place.

**Hors scope.** Groupement membre par membre (méthode Grameen). Les cautions existent déjà.

**Dépendances.** Contrats, payload CBS, GED KYC du second titulaire.

---

### E06 — Conditions suspensives qui bloquent

**Problème.** Le texte « conditions suspensives » n’empêche pas la mise en place. Seules les réserves du circuit sont structurées.

**Aujourd’hui.** `suspensive_conditions` texte libre ; `ApprovalCondition` ; checklist produit à l’instruction seulement.

**Utilisateurs.** Comité, formalisation, middle-office, mise en place.

**Dépendance CBS.** Aucune. Gate FinFlow avant l’appel de mise en place.

**Livrable d’étude.** Catalogue de CP par produit (assurance, inscription, nantissement) + preuve GED obligatoire.

**Hors scope.** Covenants après mise en place (suivi DSCR annuel).

**Dépendances.** E04 si la BIC est une CP.

---

### E07 — Second regard pertes / restructuration

**Problème.** Write-off et restructuration sont un clic permissionné. La mise en place, lui, a initiateur + valideur.

**Aujourd’hui.** Permissions `add_writeoff` / `add_loanrestructure` ; restructuration accrochée au dossier de recouvrement.

**Utilisateurs.** Recouvrement, direction, comptable, audit.

**Dépendance CBS.** À trancher. La décision FinFlow suffit-elle, ou le CBS doit-il recevoir l’abandon / le nouvel échéancier ?

**Livrable d’étude.** Circuit type (initiateur ≠ valideur), seuils de montant, restructuration crédit sain vs recouvrement.

**Hors scope.** IFRS 9 / moteur de provisions (E12).

**Dépendances.** E03 pour voir l’effet sur le prêt.

---

### E08 — Escalade : règles vs tranches

**Problème.** `CollectionEscalationRule` est exposée en API et seedée, mais le runtime suit les **tranches**. Configuration morte, risque de paramétrer l’écran trop tard.

**Aujourd’hui.** `apply_escalation_rules()` appelle `apply_tranche_transfer()` ; UI admin = tranches seulement.

**Utilisateurs.** Admin recouvrement, responsable recouvrement.

**Dépendance CBS.** Aucune.

**Livrable d’étude.** Décision : supprimer les règles, les brancher, ou les fusionner visuellement avec les tranches.

**Hors scope.** Nouveau moteur de stratégie / scoring de recouvrement.

**Dépendances.** Aucune. À trancher **avant** tout chantier recouvrement.

---

## Vague 2 — Ambitieux

Positionne FinFlow comme système de décision et de preuve, pas comme ledger.

### E09 — Scorecard administrable + STP

**Problème.** Le score est calculé dans le code. Les seuils d’analyse informent, ils ne décident pas (sauf couverture / KYC).

**Aujourd’hui.** `compute_score()` ; `AnalysisThreshold` ; `risk_level` pour le circuit.

**Utilisateurs.** Direction des risques, comité, admin politique crédit.

**Dépendance CBS.** Aucune. Décision FinFlow avant mise en place.

**Livrable d’étude.** Grille éditable (poids, cut-off) ; quels tickets en auto-accord / auto-refus / comité.

**Hors scope.** Machine learning, données telco, pricing risque automatique.

**Dépendances.** Politique crédit existante ; E06 pour les CP restantes.

---

### E10 — Notifications client + portail

**Problème.** L’emprunteur est hors système. Statut, pièces et rendez-vous de signature passent par l’agence.

**Aujourd’hui.** E-mails internes workflow ; SMS recouvrement stub ; pas de route portail.

**Utilisateurs.** Client, chargé d’affaires, formalisation.

**Dépendance CBS.** Lecture possible d’un solde. Jamais d’encaissement depuis le portail.

**Livrable d’étude.** Phase SMS / e-mail d’instruction d’abord, portail ensuite. Consentement et canaux (SMS / WhatsApp).

**Hors scope.** Origination 100 % self-service, chatbot, paiement en ligne.

**Dépendances.** Provider SMS réel (aujourd’hui stub). E03 pour afficher un solde.

---

### E11 — Mise en place par tranches

**Problème.** Un dossier = un mise en place = un prêt. Inutilisable pour un investissement par jalons (BTP, équipement).

**Aujourd’hui.** `disburse_application()` unique ; champs coût projet / quota sans modèle de tranche.

**Utilisateurs.** Chargé d’affaires, comité, middle-office, équipe CBS.

**Dépendance CBS.** Structurante. Perfect accepte-t-il plusieurs mises en place sur le même dossier / plusieurs contrats ?

**Livrable d’étude.** Modèle `DisbursementTranche` + CP par tranche. Le revolving (ligne / tirages) est une **étape 2**, pas cette fiche.

**Hors scope.** Ligne revolving, découvert, multi-prêteurs. Échéancier négocié (45 jours, 2 échéances libres) : reporté.

**Dépendances.** E06 (CP par tranche), E03 (plusieurs prêts liés).

---

### E12 — Pont comptable + provisions

**Problème.** Les rôles Comptable existent, sans journal, sans export GL, sans provision sur encours.

**Aujourd’hui.** Pas de module comptable ; le type « provision » contentieux = honoraire ; la doc pose le ledger hors scope.

**Utilisateurs.** Comptable, chef comptable, direction, audit externe.

**Dépendance CBS.** À trancher. Soit export des événements FinFlow vers Sage / SAP, soit lecture des écritures CBS. **Pas un second grand livre.**

**Livrable d’étude.** Catalogue d’événements à exporter (mise en place, perte, dation) ; matrice PAR → provision **indicative**.

**Hors scope.** Grand livre quotidien, ALM, liquidité institutionnelle, clôture de période, états BCEAO complets (chantier superviseur à part).

**Dépendances.** E03, E07. Cadre à poser avec la direction financière.

---

## Hors backlog (volontairement)

| Sujet | Pourquoi ce n’est pas ici |
|-------|---------------------------|
| Échéancier négocié (45 j, 2 échéances irrégulières) | Reporté par décision produit. |
| Encaissement saisi dans FinFlow | Contredit le contrat CBS. |
| App native / offline | Après E10 et les visites unifiées. |
| AML / SSO / MFA obligatoire | Chantier sécurité / conformité à ouvrir avec la DSI, pas dans ces 12 fiches. |
| API partenaires / Power BI | Roadmap déjà citée dans le README ; pas bloquant pour l’étude métier. |

---

## Comment tenir un atelier

1. Relire la fiche (10 min).
2. Trancher **hors scope** en premier pour éviter le glissement.
3. Si CBS = « à trancher » ou « structurante » : une question écrite à l’équipe Perfect avant tout design d’écran.
4. Sortie attendue : une demi-page de décision (on fait / on reporte / on abandonne) + 3 critères d’acceptation. Pas de ticket de dev tant que cette page n’existe pas.
